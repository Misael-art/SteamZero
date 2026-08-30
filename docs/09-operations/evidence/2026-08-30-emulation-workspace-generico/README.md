# Roteamento por plataforma do workspace — prova física 2026-08-30

Item: `SZ-LIBRARY-CANONICAL`. Release ativa: `2.0.0rc1-af49819e1326`
(sourceCommit `af49819e1326`, wheel SHA-256
`58afe75a69403437eed90aee2d1ffc73847fd801525a2612482baf30149a4bd0`).
Comando observado no host instalado: `steamzero emulation workspace --json`.

Branch da frente: `codex/library-auxiliary-content` → mergeado em `main`
(`af49819`), construído a partir de um run CI verde
(`33314115183`, commit `af49819`) e ativado pelo fluxo governado
(`release_host.py install`, rollback `2.0.0rc1-a897f8ffcfed`).

## O que foi provado no host, na release instalada

A migração `build_switch_workspace` → `build_emulation_workspace` (commit
`77e7f7f`) roteia cada jogo pela plataforma que a fonte canônica declarou, em
vez de despejar a lista inteira na superfície do Switch.

| Métrica | antes (`a897f8ffcfed`) | depois (`af49819e1326`) |
|---|---|---|
| `truthState` | unverified | **ready** |
| jogos totais no workspace | (36 plataformas zeradas) | **231** |
| `playstation` | 0 | **49** |
| `switch` | (lista inteira despejada) | **15** (todos `platform=switch`) |
| jogos sem campo `platform` | — | **0** |

## Evidências

- `02-entrega-funcional.txt` — resumo por plataforma, gerado do `workspace.json`
  da release instalada: `master-system` 51, `playstation` 49, `nes-famicom` 33,
  `nintendo-handheld` 30, `nintendo-3ds` 19, `sega-saturn` 18, `switch` 15,
  `playstation-2` 6, `dreamcast` 5, `wii-u` 2, `nintendo-console` 1,
  `playstation-3` 1, `neo-geo-cd` 1 — 231 no total, 0 sem plataforma.
- `02-entrega-funcional.png` — render visual do resumo acima (produzido do texto
  via PIL; conteúdo idêntico ao `.txt`).
- `02-entrega-funcional.json` — saída bruta e sanitizada de
  `steamzero emulation workspace --json` sem credenciais/paths privados.

## Escopo desta prova

Só a **projeção do workspace** (roteamento por plataforma) foi provada no host.
Não fazem parte desta evidência: lote 2 de manifestos, enxugar o read model,
consumidores restantes (busca, launcher, scraping) contra a fonte única, e
`updateCount`/`dlcCount` não-Switch em release instalada — permanecem como
próxima ação do item.
