# WI-G0 — Evidência automatizada HUD em 1280×800

## Entrega

- `gtool-hud-v1` publica viewport alvo, estado local do MangoHud, presets
  compacto/detalhado, métricas, configuração e orçamento geométrico;
- o catálogo HUD é a fonte única das strings `MANGOHUD_CONFIG` consumidas pelo
  launcher Steam, evitando divergência entre preview e execução;
- o snapshot Steam Gameplay, bridge GET `/hud/presets`, CLI `hud presets`,
  JSON-RPC e QML expõem a mesma evidência;
- a tela mostra explicitamente que o encaixe é automatizado e que a revisão
  visual permanece pendente.

## Limite da evidência

- o método `deterministic-layout-budget` prova apenas que largura, altura e
  margem declaradas cabem em 1280×800 e que o payload é schema-valid;
- disponibilidade do executável é observada separadamente e não prova que o
  overlay foi renderizado durante um jogo;
- legibilidade, obstrução de conteúdo, conforto e preferência visual permanecem
  `PENDING-HUMAN`;
- nenhum processo de jogo, rede, conteúdo pessoal ou mutação do host é usado
  para produzir a evidência.

## Evidência

- suíte integral: 1.437 testes aprovados;
- cobertura total: 85,30%; domínio HUD: 100%;
- Ruff, mypy em 151 módulos, independência e fronteiras: aprovados;
- golden do schema, três estados de runtime e consistência
  catálogo→launcher aprovados;
- bridge, CLI/JSON-RPC e catálogo de contratos Desktop aprovados;
- oito harnesses QML offscreen passaram, incluindo Steam Gameplay em 1280×800.

Estado final: `verified-offscreen`. Nenhuma observação subjetiva foi promovida a
`verified-hw`.
