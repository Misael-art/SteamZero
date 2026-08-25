# Componente: planejamento metadata-only

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base exata: `99fba64e7b39ee943eb00885fbe07920dff4e9e6`

## Baseline do host

- release ativa antes da mudança: `0.1.0a46-a02dae5f60ac`;
- `steamzero-core.service` e socket ativos;
- schema do banco: 20, íntegro;
- jobs estagnados: 0;
- operações não terminais: 0;
- backup órfão: 1, preservado para investigação;
- componentes declarados: 33;
- Citron, Eden e Ryubing instalados; RetroArch degradado.

Comando read-only: `.venv/bin/python tools/release_host.py --json inspect`.
Nenhuma mutação de host foi executada durante o diagnóstico e os gates locais.

## Reprodução vermelha

Comando:

```text
.venv/bin/python tools/run_tests_isolated.py \
  tests/integration/test_component_lifecycle.py::TestMetadataOnlyPlanning -q
```

Resultado antes da correção: `4 failed`.

- AppImage e native chamavam `ArtifactPort.fetch()` em `plan`;
- Libretro chamava `ArtifactPort.fetch()` e extraía o archive em `plan`;
- Flatpak chamava `remote-info` por `resolve()` em `plan`.

## Causa raiz

O schema v2 exigia que o envelope já contivesse o id de um plano delegado.
Para obter esse id, `ComponentLifecycle.plan()` precisava materializar o plano
do executor. Nos executores portáteis e Libretro, materializar incluía download,
checksum, cache e extração; no Flatpak, incluía resolução remota do commit.

## Correção

O envelope v3 contém somente intenção, executor, fingerprint da fonte, TTL,
token, preview e garantia de rollback. `delegated` precisa estar vazio. A
aquisição e a criação do plano delegado ocorrem somente em `apply`, depois da
confirmação. Planos Flatpak v1 e envelopes v2 continuam legíveis e aplicáveis.

Uma segunda instalação é marcada `noop` por estado persistido + versão alvo +
hash do manifesto, sem sondagem remota. O `apply` revalida o deployment real
antes de aceitar esse `noop`, impedindo sucesso falso por metadado obsoleto.

## Evidência automatizada verde

- matriz metadata-only: `5 passed`, cobrindo AppImage, native, Flatpak,
  Libretro e os 33 manifests abaixo de 2 segundos sem I/O remoto;
- lifecycle + conformance + Libretro: `254 passed, 10 skipped`;
- regressão de bridge/contratos/controlador: `216 passed`;
- suíte isolada completa: `4698 passed, 10 skipped in 968.27s`;
- `ruff check src tools tests`: aprovado;
- `ruff format --check src tools tests`: 473 arquivos formatados;
- `mypy src`: aprovado em 222 arquivos;
- `make independence boundaries`: aprovado, 0 violações;
- `make status-check`: aprovado;
- `git diff --check`: aprovado;
- QML alterado: nenhum; `qmllint` não se aplica a este incremento.

Os 10 skips são do contrato existente: Flatpak fixa commit e a prova de
checksum pertence ao executor portátil.

## Limite desta evidência

Este incremento fecha somente o planejamento metadata-only. O endpoint de
aplicação ainda é síncrono; job assíncrono, progresso, cancelamento, retry,
retomada, telemetria e terminalização de falha permanecem abertos no mesmo item.
A validação da release instalada será acrescentada depois do commit limpo e do
fluxo governado de `tools/release_host.py`, pois o instalador recusa artefato
construído de árvore não commitada.
