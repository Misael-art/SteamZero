# Componente: terminalização de planos

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `d2553b1`

## Hipótese a reproduzir

O job termina como `rolled-back` ou `cancelled`, mas o plano de componente e os
planos delegados permanecem `pending`. Isso permite que histórico terminal
aponte para autorização ainda reutilizável e faz o retry repetir o mesmo plano,
em vez de criar uma tentativa nova e auditável.

A correção deve terminalizar sucesso, falha, cancelamento, expiração e recovery;
um retry deve criar outro `planId`, manter a correlação com a tentativa anterior
e nunca recolocar um plano terminal em `pending`.

## Reprodução vermelha

A primeira execução focada produziu `10 failed, 107 passed`. Permaneceram
`pending`:

- o plano transacional após smoke falho e rollback bem-sucedido;
- o plano Flatpak após falha, cancelamento e recovery pós-crash;
- o envelope externo após falha de reparo e expiração;
- o envelope de job cancelado ou recuperado.

Além disso, a projeção do job não expunha `planId` e retry copiava os mesmos
parâmetros, reutilizando a autorização anterior.

## Causa raiz

Cada camada encerrava somente seu próprio artefato: transaction encerrava a
operação, Flatpak encerrava seu operation file e JobManager encerrava o job.
Nenhuma delas fechava o plano. O envelope v3 também descartava o vínculo com o
plano delegado criado depois da confirmação, impossibilitando correlacionar um
crash com recovery.

## Correção

- transaction e Flatpak marcam `aborted` após toda tentativa confirmada que
  termina em falha/cancelamento; token errado não consome o plano;
- expiração fecha a autorização sem iniciar efeito;
- o envelope v3 continua vazio durante plan, mas persiste um único vínculo
  delegado somente depois da confirmação;
- recovery dirigido pelo vínculo preserva commit durável como `applied` e
  reverte/aborta tudo antes do commit;
- o apply do envelope é serializado por `planId`, impedindo aplicação dupla;
- recovery de job fecha envelope órfão e retry cria novo plano/job com
  `retryOfPlanId` e `retryOfJobId`;
- o safepoint pós-commit foi removido: cancelamento tardio não pode mentir que
  um efeito já commitado foi cancelado;
- reaplicar diretamente um plano transacional interrompido é recusado até
  recovery, sem consumir a evidência ainda pendente;
- recovery reconcilia o job owner pelo estado durável do plano: inclusive um
  job em `cancelling` vira `completed` quando o commit já ocorreu;
- no intervalo Flatpak entre operação `committed` e plano `applied`, recovery
  preserva o deployment e faz roll-forward dos planos interno e externo.

Durante a implementação, a suíte focada detectou que o schema v3 ainda proibia
o vínculo pós-confirmação. O schema agora aceita zero ou uma referência tipada;
`validate_apply` continua exigindo envelope vazio antes da primeira execução e
recusa vínculo adulterado ou executor incompatível.

## Evidência automatizada final

Comando focado:

```text
.venv/bin/python tools/run_tests_isolated.py \
  tests/integration/test_transaction.py \
  tests/integration/test_flatpak_executor.py \
  tests/integration/test_component_lifecycle.py \
  tests/integration/test_jobs.py \
  tests/unit/test_component_jobs.py -q
```

Resultado: `144 passed in 4.51s`. O snapshot do state home real foi idêntico
antes e depois (`11916` arquivos, `1942` diretórios, `1097422908` bytes e mesmo
`max_mtime_ns`).

A suíte isolada completa, já sobre a correção final e as visões regeneradas,
terminou com `4725 passed, 10 skipped in 1112.71s`. O snapshot do state home
real permaneceu exatamente idêntico (`11916` arquivos, `1942` diretórios,
`1097422908` bytes e mesmo `max_mtime_ns`). O runner emitiu uma linha
informativa de IPC do desktop após o progresso, mas o processo terminou com
exit code zero e o relatório pytest integral permaneceu verde.

Gates sobre a mesma árvore:

- Ruff: verde;
- `ruff format --check`: `475 files already formatted`;
- mypy: `223 source files`, sem issues;
- independência de runtime: `OK`;
- fronteiras: `0` violações;
- status-check e `git diff --check`: verdes.

## Validação no host físico

Host: `misael-jupiter`  
Kernel: `6.18.42-1-MANJARO`

A sonda carregou o catálogo real empacotado e o código da branch pelo
`PYTHONPATH`, com State Store, journal, planos e payload sob uma raiz XDG
temporária. Nenhum download, comando Flatpak, instalação ou alteração da release
ativa ocorreu.

Resultados estruturados:

```json
{
  "catalogAdapter": "azahar",
  "crashRecovery": {
    "outcomes": ["rolled-back"],
    "planStatus": "aborted",
    "reapplyCode": "E-TX-STALE-PLAN",
    "targetAbsent": true
  },
  "failure": {
    "code": "E-TX-VERIFY-FAILED",
    "planStatus": "aborted",
    "rollbackTargetAbsent": true
  },
  "jobRecovery": {
    "durableCommitResolvedState": "completed",
    "initialState": "cancelling"
  },
  "releaseMutation": false,
  "stale": {
    "code": "E-TX-STALE-PLAN",
    "planStatus": "aborted"
  }
}
```

Isso prova no host real que uma confirmação stale é consumida como `aborted`,
uma falha depois da publicação faz rollback e aborta o plano, e um crash não
capturável preserva `pending` somente até o recovery. Antes dele, reaplicar é
recusado sem consumir a evidência; depois dele, operação/plano terminam em
`rolled-back`/`aborted`. Também prova que um cancelamento cruzando commit
durável é reconciliado como `completed`. A raiz temporária foi removida ao
final.

## Limites desta evidência

Este incremento encerra a semântica comum de terminalização e retry. Ele não
substitui a matriz física individual das 33 entradas nem os ciclos reais de
instalação por família; esses permanecem como a próxima frente do item.
