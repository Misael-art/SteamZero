# Launcher: foco de teclado inicial — 2026-09-04

Host Valve Jupiter (`misael-jupiter`), KDE/Wayland. Release ativa durante toda a
medição: **2.0.0rc1-a44f52964b3e**.

## O que estava quebrado

O AURA Launcher abria **surdo ao teclado**. Nenhuma seta, Tab, Return ou Space
produzia efeito. Um clique de mouse destravava, e a partir dali a navegação por
teclado funcionava normalmente.

O anel de foco ciano era desenhado desde a abertura, então a tela *parecia*
focada sem estar — foi isso que fez a auditoria anterior classificar o defeito
como falha de ativação do cartão.

Causa: `Loader` não repassa foco ao item que carrega a menos que o próprio
`Loader` tenha `focus: true`. Em `LauncherMain.qml` o shell nasce dentro de um
`Loader` que não declarava foco. A cadeia abaixo dele estava íntegra
(`LauncherShell` e `LauncherHome` já tinham `focus: true`).

**No Game Mode do Deck não existe mouse.** Sem o clique que destrava, o Launcher
nascia inoperável por teclado e por controle.

## Por que passou por todos os gates

Os harnesses do Launcher instanciam `LauncherHome`/`LauncherShell` diretamente e
chamam `forceActiveFocus()` antes de pressionar. Eles provam que a tecla ativa o
cartão **focado** — mas entregam o foco de mão beijada, que é exatamente o que a
produção nunca faz. Nenhum deles instancia `LauncherMain`, onde mora o `Loader`.

É a mesma classe de ponto cego corrigida em 2026-09-02 (`o harness prova a
função, não o caminho`), um nível acima.

## Metodologia — controle positivo obrigatório

A medição anterior concluiu "as teclas não ativam" a partir de capturas
idênticas. Duas condições que a invalidam foram encontradas e eliminadas aqui:

1. **`ydotoold` não estava em execução** e não havia socket. Nenhuma tecla
   sintética chegava a lugar nenhum. Antes de qualquer medição foi estabelecido
   um controle positivo: uma janela QML mínima que conta teclas recebidas
   (`recebidas: 34`).
2. **A janela sob teste não tinha foco.** `kdotool getactivewindow` mostrava
   Claude Desktop. O foco de janela passou a ser conferido por PID **antes e
   depois** de cada injeção.

Um terceiro confundidor apareceu no caminho: `steamzero-launcher` não derruba o
`qml6` filho ao terminar, então uma janela órfã de uma instância anterior
recebeu injeções por engano. Janelas passaram a ser resolvidas por PID.

> Regra que fica: nenhuma afirmação sobre input físico vale sem, na mesma
> evidência, prova de que o canal estava vivo e de que a janela certa tinha foco.

## A/B no compositor real

Duas instâncias simultâneas contra **a mesma ponte**, mesmos 1.119 jogos, mesmo
compositor. Só o QML difere. Nenhum clique de mouse em nenhuma das duas.

| Instância | Anel antes | Anel depois | Moveu |
|---|---|---|---|
| Release `a44f52964b3e` (sem correção) | `48,258 → 606,520` | `48,258 → 606,520` | **não** |
| Árvore corrigida | `49,259 → 606,521` | `633,259 → 1191,521` | **sim** |

Diferença de 25.242 pixels na instância corrigida, exatamente um cartão à
direita. Zero na instalada.

## Teclas físicas do Deck

Verificado por capacidade evdev, sem depender de alguém apertar botão:

| Nó | Handler | Códigos de navegação |
|---|---|---|
| `event5` | `kbd` | `KEY_UP` `KEY_DOWN` `KEY_LEFT` `KEY_RIGHT` `KEY_ENTER` `KEY_SPACE` `KEY_TAB` `KEY_ESC` `KEY_F` |
| `event6` | `mouse0` | — (trackpad como mouse) |
| `event7` | `js0` | somente `BTN_*` de gamepad |

O `hid_steam` expõe o D-pad como teclado real, inclusive o `F` que o Launcher
usa para busca. O hardware está correto e `doctor` (`deck.input.keys: pass`)
está correto. A diferença que o operador observou — controle físico movendo em
algumas janelas e não em outras — é o bootstrap de foco: a central desktop o faz
explicitamente (`Main.qml:1881` e `forceActiveFocus` nos menus); o Launcher não
fazia.

## Capturas

| Arquivo | Conteúdo |
|---|---|
| `01-release-a44f5296-abertura.png` | release instalada, home carregada, anel no cartão 1 |
| `02-release-a44f5296-apos-seta-anel-parado.png` | após seta direita com foco conferido: anel parado |
| `03-corrigido-abertura.png` | árvore corrigida, mesma ponte, anel no cartão 1 |
| `04-corrigido-apos-seta-anel-moveu.png` | após a mesma seta: anel no cartão 2 |

## Fronteira do que está provado

- **Provado:** a primeira tecla depois de abrir navega, sem mouse, no compositor
  real, com a correção; e não navega sem ela.
- **Não provado:** ciclo completo `selecionar → jogar → sair → voltar ao mesmo
  cartão`. Continua pendente.
- **Não provado na release:** a correção foi medida na árvore, contra a ponte da
  release instalada. Confirmá-la na release exige mais um ciclo de publicação e
  instalação autorizadas.
