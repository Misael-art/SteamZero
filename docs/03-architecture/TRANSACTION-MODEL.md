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
