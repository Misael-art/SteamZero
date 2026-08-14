# TRANSACTION-MODEL — modelo transacional

Generaliza o pipeline provado do PhaseZero (`linux/emulation/library/`: scan→plan com `confirmToken`→apply→verify→rollback) para **toda** mutação da plataforma.

## Pipeline canônico

```
scan      leitura do estado real (nunca escreve fora do state)
plan      diff estado→alvo; lista exata de ações; requisitos (espaço c/ margem,
          rede, privilégio); riscos; emite planId + confirmToken + hash das
          precondições (arquivos-alvo com fingerprint)
preview   render humano/JSON do plano (a UI mostra; o CLI imprime)
backup    cópia/snapshot do que será tocado → backups/<operationId>/
stage     todo material novo é preparado em staging/<operationId>/ no MESMO
          filesystem do destino (garante rename atômico)
apply     execução das ações do plano, na ordem, com journaling WAL:
          cada ação grava intent→done no journal ANTES/DEPOIS de executar
verify    pós-condições: hashes, versões, executabilidade, schema de config
activate  troca atômica (rename/symlink flip); até aqui o estado antigo era o ativo
test      smoke test declarado (ex.: emulador --version, parse da config)
commit    journal selado; staging limpo; backup retido por política de GC
```

## Regras

1. **confirmToken** (herdado de `apply.py:76`): apply sem token do plano correspondente = `E-TX-CONFIRM-REQUIRED`. Token expira e é single-use.
2. **Precondições congeladas:** apply revalida os fingerprints do plan; divergência = `E-TX-STALE-PLAN`, sem mutação (AC-TX-01).
3. **Journal write-ahead:** cada ação tem `intent` gravado antes de executar. Crash em qualquer ponto ⇒ recovery determinístico: ações `intent` sem `done` são desfeitas (undo registrado por ação) ou completadas se idempotentes e pós-`activate`.
4. **Staging no filesystem de destino:** corrige a classe de bug do download `.temp` do EmuDeck (mesmo dir, ok) aplicada inconsistentemente a configs (rsync direto).
5. **Backup verificado:** backup tem manifesto próprio com hashes; rollback compara pós-restauração (supera o `pz_rollback` atual, que restaura com `cp` sem verificar e apaga o manifesto inteiro mesmo com falha parcial — common.sh:532-556).
6. **Rollback aprovado** apenas quando (§13.6): estado restaurado (hash), dados do usuário preservados, zero temporários órfãos, journal consistente, erro compreensível.
7. **Quarentena:** conteúdo suspeito/deslocado nunca é deletado — vai para `quarantine/<operationId>/` com manifesto e ação de restauração.
8. **Dry-run universal:** toda operação aceita dry-run que percorre scan→plan→preview sem tocar backup/stage/apply (AC-TX-03).
9. **Idempotência:** plan sobre estado já-alvo produz plano vazio (`no-op`); apply de plano vazio é sucesso imediato.
10. **Custódia durável (G45, FI-06):** antes de destruir/substituir qualquer entrada, o núcleo a TIRA do lugar com rename atômico sem substituição (`RENAME_NOREPLACE`) para `quarantine/<operationId>/custody.<custodyId>` e registra no journal, NESTA ordem, com fsync após cada registro:

    - `custody.intent(actionId, custodyId, target, custody, purpose, expected)` — caminho exato da custódia, destino, finalidade (publish/remove/restore) e identidade esperada (sha256 para regular; `symlink:<readlink>` para link) — gravado ANTES do primeiro rename;
    - `custody.taken(actionId, custodyId, target, custody)` — a entrada está fora do lugar;
    - `custody.released(actionId, custodyId, custody, returned, reason)` — a entrada foi devolvida (`returned=true`), liberada (`returned=false, reason="done"`), nunca existiu (`reason="absent"`) ou a ação falhou com conservação (`reason` nomeia o motivo).

    **`custodyId` identifica uma TENTATIVA, não apenas uma ação:** cada ciclo (apply e rollback da MESMA ação, e cada re-tentativa) deriva um id novo (`custody.<actionId>.<seq>`), de modo que os registros do journal e o caminho físico da custódia são correlacionados por `custodyId`/caminho — nunca somente por `actionId`, que se repete em ciclos distintos e colidiria no mesmo caminho determinístico.

    **Recovery parte de intents NÃO finalizados:** `_reconcile_custody` considera todo `custody.intent` sem `custody.released` correspondente — inclusive intent SEM `custody.taken`. A existência física da entrada em `quarantine/<operationId>/custody.<custodyId>` prova que o rename aconteceu mesmo sem o registro da tomada (crash entre os dois); a entrada pendente é devolvida, liberada (identidade aceita pelo undo) ou preservada com falha fechada.

    Nenhuma janela de conferência: a identidade é conferida DEPOIS do rename, sobre a própria entrada em custódia. Identidade divergente ⇒ devolução sem substituição (`E-TX-STALE-PLAN` em apply, `E-TX-ROLLBACK-FAILED` em rollback) e a operação termina com as duas entradas preservadas. Ponto de crash em `postlink`/`release` deixa a custódia registrada e recuperável.
11. **Recovery prioriza rollback (G45, FI-06):** `recover_operation` só declara `kept` quando não há evidência de rollback interrompido; custódia pendente (intent sem released, mesmo sem taken), custódia não devolvida ou intenção remove/restore ⇒ o recovery executa `_do_rollback` antes de decidir, e jamais publica pendências cegamente. Estado terminal da operação: zero custódias órfãs (`_reconcile_custody`, idempotente e não destrutivo).
12. **Publicação exclusiva:** todo alvo vago é publicado por hard link exclusivo (`publish_link`) no MESMO filesystem, e a custódia devolvida por rename sem substituição; `EXDEV` (custódia/alvo em filesystems diferentes) é fechado com `E-TX-CUSTODY-CROSS-FS` — nunca fallback com janela residual.

## Layout em disco

```
$XDG_STATE_HOME/steamzero/
  state.db            (SQLite WAL)
  journal/<opId>.jsonl
  staging/<opId>/     (mesmo FS do destino quando possível; senão sub-staging por volume)
  backups/<opId>/     (+ manifest.json com hashes)
  quarantine/<opId>/
  logs/core.jsonl     (rotacionado)
```

Permissões: diretório 0700, arquivos 0600 (herda `umask 077` do PhaseZero common.sh:4).

## Operações compostas

Operação com sub-operações (ex.: "instalar plataforma GameCube" = emulador + BIOS-check + frontends) forma uma **saga**: sub-transações com compensação; falha no meio compensa as anteriores na ordem reversa; o plano composto mostra tudo antecipadamente.
