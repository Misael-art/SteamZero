# Evidência de isolamento do estado de testes — GAP-G26

**Data:** 2026-07-30

**Branch:** `codex/fix-test-state-isolation-g26`

**Base:** `6e253f0386a4a6816f00fc48bedaecd8a20fffff`

**Escopo:** isolamento da suíte. Nenhum cleanup, recovery de jobs ou alteração
do host faz parte deste PR.

## Causa raiz comprovada

O núcleo resolve journal, planos, backups e staging pelos homes XDG do processo.
O repositório não tinha `tests/conftest.py`; Makefile, AGENTS e os dois jobs de
CI chamavam `pytest` diretamente. Quando um teste fornecia apenas `tmp_path`
para o payload, as transações continuavam usando o XDG herdado e podiam escrever
no state real.

Uma segunda falha apareceu ao executar a suíte realmente isolada:
`test_doctor.py` escrevia `XDG_STATE_HOME` diretamente em `os.environ` e
contaminava testes posteriores. Além disso, a fixture HTTP de credenciais
consultava o Flatpak real. Com um XDG vazio, `flatpak list --user` excedeu os
três segundos do contrato HTTP. O stack foi observado em
`FlatpakCLI.status → EmulationController._adapter_installed`; a fixture agora
injeta uma porta Flatpak read-only em memória.

Essas correções pertencem a GAP-G26 porque removem dependências implícitas do
estado e das ferramentas do host nos testes. Elas não mudam o lifecycle do
produto e não antecipam GAP-G27.

## Implementação

- `tools/run_tests_isolated.py`:
  - fotografa o state home original antes de importar pytest;
  - cria homes temporários para `STATE`, `DATA`, `CONFIG`, `CACHE` e `RUNTIME`;
  - abre pytest em novo processo;
  - compara nomes, tipos, bytes, `mtime_ns`, `ctime_ns` e links depois;
  - retorna erro 86 se qualquer entrada original mudar.
- `tests/conftest.py`:
  - oferece isolamento de sessão quando pytest é chamado diretamente;
  - restaura os cinco homes antes/depois de cada teste, inclusive quando um caso
    altera `os.environ` sem `monkeypatch`.
- Makefile, CI e AGENTS usam o runner canônico.
- Testes de `media.reconcile`, `switch-library.rename` e
  `media.prune-orphan-cache` verificam que plano, journal e backup ficam dentro
  da raiz isolada.
- Testes do runner provam detecção de create/change/remove e preservação do exit
  code do pytest quando o state original não muda.

## Evidência before/after

Execução integral:

```text
real-state before: exists=True files=11738 directories=1900
bytes=1054738261 max_mtime_ns=1785406004470651608

3260 passed in 405.86s

real-state after:  exists=True files=11738 directories=1900
bytes=1054738261 max_mtime_ns=1785406004470651608
```

O manifesto de metadados também ficou idêntico; portanto, não houve criação,
remoção ou alteração silenciosa escondida pelos valores agregados.

Teste direto da defesa autouse, com todas as variáveis XDG removidas antes de
abrir pytest:

```text
1 passed
```

Testes direcionados de isolamento, mídia, rename e prune:

```text
55 passed
```

O primeiro `make check` encontrou uma falha intermitente já existente em
`test_pause_resume_with_pipeline`: a leitura imediatamente posterior ao pause
observou `paused=False`. O arquivo isolado passou em seguida (`46 passed`) e a
repetição integral de `make cov` passou com os 3.260 testes e o state real
idêntico. Nenhum código do cast engine foi alterado neste PR; a ocorrência não
foi escondida nem atribuída ao isolamento XDG sem evidência.

## Reavaliação de GAP-G23

GAP-G23 permanece fechado. A suíte integral agora percorreu o round-trip do
daemon em um ambiente integralmente isolado sem reincidência. Isso fortalece a
separação já registrada:

- G23: perda de `state`/`detail` e colapso de erro de leitura, corrigidos;
- G26: isolamento global de XDG e dependências implícitas do host, tratado
  neste PR.

Não foi encontrada evidência para reabrir ou reatribuir G23.

## Limites e preservação

- O acervo preexistente de aproximadamente 1,1 GB não foi removido nem
  modificado.
- O runner detecta mutações ocorridas durante o gate; não atribui autoria se um
  processo externo alterar o mesmo state simultaneamente. Nesse caso, o gate
  reprova de forma conservadora.
- Cleanup, jobs stale, doctor/state audit e quarentena pertencem a GAP-G25.
- GAP-G26 só deve ser marcado como fechado depois da revisão, do CI remoto e do
  merge deste PR.
