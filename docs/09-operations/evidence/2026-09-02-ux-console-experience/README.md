# Onda 1 — ativação P0 do AURA Launcher

Data: 2026-09-02  
Branch: `codex/ux-console-experience-p0-2026-09-02`  
Commit funcional: `3d8f9bb`  
Release ativa observada no baseline: `2.0.0rc1-145cf9d44738`

## Baseline reproduzido

Na release ativa, `Return`, clique e as teclas de navegação não ativavam o
cartão real `1969 (Homebrew) (SMS)`. As capturas antes/depois do audit rerun
tinham o SHA-256 `1308cd106ad6a6a7e9dfb935a8245415285a26e6888ac705698d5c103c87d4c7`;
nenhum emulador nascia e não havia página de jogo.

## Correção e prova automatizada

- `LauncherHome.qml` agora publica `gameActivated`, `actionActivated` e
  `feedbackRequested`.
- Cartões têm foco, `Accessible.name/role/description`, estado pressed,
  `TapHandler` e uma rota comum para Return/Enter/Space.
- `LauncherShell.qml` conecta a ativação a `openGame` e mantém o contexto de
  retorno; `LauncherMain.qml` resolve a página pelo catálogo carregado.
- A home vazia tem ação focável de retry; a página de jogo também aceita toque
  e teclado nas ações.

Comandos focados:

```text
tests/integration/test_qml_handheld_offscreen.py -k launcher_activation
1 passed

tests/integration/test_qml_handheld_offscreen.py -k 'launcher/'
6 passed

tests/integration/test_launcher_app.py tests/unit/test_launcher_navigation.py \
tests/unit/test_launcher_session.py tests/unit/test_launcher_catalog.py -q
47 passed
```

Os 45 harnesses QML da suíte visual também passaram. A suíte integral do
repositório foi iniciada, mas o runner ficou preso em cenários
`ui_control_probe.qml` após cerca de 18 minutos/29%; foi encerrado com SIGTERM
somente no próprio processo de teste. Não houve processo residual de QML,
Launcher ou emulador.

## Limite de validação

**Não validado fisicamente na release instalada.** Nenhuma instalação,
publicação, lançamento de emulador ou mutação de host foi executada. A captura
PNG da entrega física (`02-entrega-funcional.png`) e a prova de controle → jogo
→ retorno só podem ser registradas depois de autorização do operador para o
fluxo governado de release e interação física no host.
