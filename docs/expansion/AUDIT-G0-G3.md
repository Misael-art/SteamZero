# Auditoria do track Gaming tools G0–G3

Data: 2026-07-24. Linha auditada: `codex/expansao-master-steamzero`, de
`ae00e1f` a `8cf64fa`.

## Rastreabilidade

| WI | Commit | Requisito | Contrato | Teste/evidência | Estado |
|---|---|---|---|---|---|
| G0 | `ae00e1f` | HUD legível em 1280×800 | `gtool-hud-v1` | domínio HUD + QML offscreen | `verified-offscreen` |
| G1 | `d892b46` | MangoHud por jogo, diff e rollback | `gtool-hud-v1` | plan/apply/undo + launcher | `verified-dev` |
| G2 | `7c10d05` | ambiente puro sem shell/colisão | `gtool-launch-environment-v1` | compositor + integração launcher | `verified-dev` |
| G3 | `8cf64fa` | vkBasalt por jogo, custo e off | `gtool-vkbasalt-v1` + ambiente | config transacional + QML + launcher | `verified-dev` |

Cada WI possui commit, relatório, contrato registrado e teste correspondente.
O launcher consome somente presets fechados: G1 produz a camada MangoHud, G3
produz a camada vkBasalt e G2 recusa colisões ou chaves não gerenciadas antes de
criar o processo.

## Gates do track

- 1.456 testes aprovados na suíte integral;
- cobertura total 85,34%, acima do piso de 85%;
- domínio vkBasalt e compositor de ambiente com 100% de cobertura;
- Ruff, mypy em 153 módulos, independência e fronteiras aprovados;
- oito harnesses QML offscreen aprovados;
- configs ativas, `off`, rollback, ferramentas ausentes, adulteração, colisão e
  ausência de shell possuem prova automatizada;
- nenhuma evidência offscreen foi promovida a `verified-hw`.

## Dependências e destinos

- G0–G3 concluem HUD, MangoHud, composição de ambiente e vkBasalt;
- LSFG já possui base fechada no launcher, mas fallback/OptiScaler e
  compatibilidade completa continuam em G4;
- captura, galeria e orçamento de performance continuam em G5;
- benchmark reproduzível e custo medido continuam em G6;
- resultado visual e custo físico por jogo/driver/GPU permanecem
  `PENDING-HUMAN` até a matriz de hardware;
- o diagnóstico D4 continua aberto porque depende ainda de G4, G6 e R0–R2.

Resultado: track coerente com o ledger, sem requisito promovido acima da
evidência disponível e sem variável de ambiente arbitrária ou shell.
