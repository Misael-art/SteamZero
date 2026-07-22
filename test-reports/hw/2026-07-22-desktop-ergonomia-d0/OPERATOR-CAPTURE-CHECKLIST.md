# D0-A — bloqueio técnico de controle gráfico e checklist do operador

## Bloqueio reproduzível

O agente está na sessão física ativa (`Wayland`, `WAYLAND_DISPLAY=wayland-0`,
`DISPLAY=:0`, barramento de sessão disponível). Spectacle captura o painel físico em
1280×800. O `kdotool` consegue listar/ativar uma superfície, mas não controla a
geometria da superfície efetivamente composta: após `windowactivate` e
`windowstate --add MAXIMIZED`, Dolphin continuou registrado como 948×553 lógicos e
a captura mostrou Ashyterm por trás/por cima. Assim não é possível garantir a
preparação sanitizada exigida sem uma interação física do operador.

Não foram alterados escala, perfil, regras KDE, host nem produto.

## Aplicativos e tentativas

| Casos | Aplicativo/utilitário detectado | Versão | Mecanismo tentado | Comportamento / consequência |
|---|---|---|---|---|
| 02 | Dolphin | 26.04.3 | `dolphin <diretório-temporário>` + `kdotool windowactivate/windowstate` | Diretório neutro abriu, mas a composição ainda expôs Ashyterm; a maximização não foi aplicada à superfície visível. Captura recusada. |
| 01 | Chromium/Chrome já aberto | versão não consultada | `chromium --incognito --new-window about:blank` planejado | Não executar: o bloqueio de isolamento já impede aceitar uma nova janela, e a janela existente contém estado pessoal. |
| 03 | Ashyterm já aberto | versão não consultada | nova sessão planejada | Não executar: a superfície atual contém contexto de trabalho e não pode ser manipulada/limpa pelo agente. |
| 05, 09, 10 | LibreOffice Writer | 26.2.4 | `libreoffice --writer` foi solicitado read-only | Não produziu uma janela controlável/capturável pelo agente. |
| 06 | Okular | 26.04.3 | janela existente detectada | Contém documento pessoal; não pode ser reutilizada. |
| 07, 08 | Zenity | 4.2.2 | diálogo GTK planejado | Não executar: não há garantia de foco/modalidade isolada enquanto o compositor não obedece ao controle de janela. |
| 07, 08 | YAD | 15.0 | alternativa GTK detectada | Mesmo bloqueio de foco/modalidade. |
| 09, 10 | Kate | 26.04.3 | diálogo Qt planejado via interação física | Kate é a única evidência aceita; abrir/salvar não foi acionado sem foco seguro. |

## Capturas que o operador deve produzir

Antes de cada captura: feche/minimize outras janelas visíveis, desative notificações,
use uma janela maximizada ou diálogo modal e confirme que a imagem está em 1280×800.
Use um diretório temporário neutro (por exemplo `/tmp/steamzero-d0-capture`) com
`sample-alpha.txt`, `sample-beta.txt` e `sample-gamma.txt`; apague-o após as capturas.
Salve cada PNG em `test-reports/hw/2026-07-22-desktop-ergonomia-d0/`.

1. `01-browser.png`: abra uma janela privada do Chromium, vá para `about:blank`, sem
   conta, favoritos, histórico ou autocomplete.
2. `02-file-manager.png`: abra Dolphin no diretório temporário, maximize e deixe apenas
   os três arquivos neutros visíveis.
3. `03-terminal.png`: abra uma sessão nova de Ashyterm, execute `clear`, entre no
   diretório temporário e mostre somente texto sintético curto.
4. `05-office.png`: abra LibreOffice Writer com documento novo vazio, sem tela de recentes.
5. `06-pdf.png`: abra no Okular somente um PDF sintético/público, com conteúdo neutro.
6. `07-gtk-open.png`: em Zenity ou YAD, abra o diálogo GTK de abrir no diretório neutro.
7. `08-gtk-save.png`: no mesmo toolkit, abra o diálogo GTK de salvar no diretório neutro;
   cancele-o sem salvar.
8. `09-qt-open.png`: em Kate, use Arquivo → Abrir no diretório neutro; capture e cancele.
9. `10-qt-save.png`: em Kate, use Arquivo → Salvar como no diretório neutro; capture e
   cancele sem criar arquivo.

Critério de aceitação visual em todos os casos: sem nomes reais, conteúdo pessoal,
histórico, contas, notificações, tokens, e-mails, caminhos pessoais ou outra janela;
fonte/controles/densidade e qualquer overflow devem estar visíveis para inspeção.
