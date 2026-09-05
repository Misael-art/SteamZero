# Auditoria consultiva UX — 2026-09-05

Auditoria somente observacional contra a release ativa `2.0.0rc1-085169f47186`,
commit `085169f471866fbb61530c777d368729002b6868`. Não houve instalação,
rollback, escrita no host, reinício ou encerramento da sessão KDE. O launcher
existente foi mantido no PID `507008`; a central foi aberta uma vez no PID
`957891`/QML `957928` somente para a captura `05-central-current.png` e então
encerrada.

## Reprodução e evidência

| Arquivo | Origem | SHA-256 |
|---|---|---|
| `01-launcher-home.png` | captura canônica da release `085169f4`, PID `507008` | `8650e80be3f097a89260461335a38ad7b2a4391843c06203e8cb62844769386c` |
| `02-launcher-search.png` | teclado `F`, busca Steam, PID `507008` | `ebdc9187517f81c28e842c15cc0ca0bb6c596659865661084646fbe2fc689911` |
| `03-steam-game.png` | jogo Steam real aberto, PID `507008` | `5674414d742390a062a2279798a1b6db0c129ff8014c3616ebe662ac5feb2a52` |
| `04-launcher-return.png` | retorno após fechar o jogo, PID `507008` | `84761a955022db9afa9c9ebcc252c5ac58388b7d28bfcd1b2d0d95e0c2e871a6` |
| `05-central-current.png` | central real atual, release `085169f4`, PID `957891` | `dbb3e37292028733c841a8fc70d9bf8f80d2f4ab47d61c958cb927795f6f9353` |
| `06-themes-current-bridge.png` | bridge-live, commit `bf23fd7d`; não carimbar como release atual | `9b0de699cc3b859464e136eec5dba74ee2b9b050ae00c8a9805e5aa1c7aa5d36` |
| `07-system-current-bridge.png` | bridge-live, commit `bf23fd7d`; não carimbar como release atual | `2091dbe129064f4195af7995294310771550fa70709c2537e167e3d2130a5101` |
| `08-library-handheld.png` | bridge-live, commit `bf23fd7d`; não carimbar como release atual | `f4d2bee588c6f740b1c72cad49c55919bd9b81a47901c1ed16bfdc3f7a04de69` |

Comandos read-only principais: `steamzero doctor`, `steamzero service status`,
`steamzero session environment`, `steamzero desktop status`, `steamzero state
audit`, `steamzero jobs list`, `steamzero operations list`, `steamzero theme
list/status`, `steamzero frontends status`, `steamzero emulation workspace`,
`steamzero component list`, `steamzero health status` e `steamzero playtime
list`. A captura visual foi feita com `spectacle --background
--activewindow --nonotify --output ...`.

O inventário atual contém **44 itens não agregados** em `docs/status/items/`,
embora o pedido mencione 43. Todos os 44 estão na tabela do relatório.
