// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// RC-01 (UX-05/UX-07, 4ª fatia) — o diálogo "Importar tema ES-DE" do SHELL.
//
// Quarta frente de RC-01. O contrato medido aqui é o MESMO das duas fatias de
// painel (RetroFE, ES-DE), e é ele que torna as três provas comparáveis:
//   I.   nenhum controle de texto sai da moldura sem um mecanismo de rolagem que
//        leve até ele (o que sai sem rolagem é corte, não layout);
//   II.  as ações (Cancelar / Importar) estão na banda visível sem que o teste
//        mexa em `contentY`; quando o conteúdo passa da banda, chegar até elas é
//        feito com TECLA REAL de D-pad, e cada destino focado precisa estar
//        inteiro na banda — é isso que torna a rolagem load-bearing;
//   III. nenhum controle é espremido abaixo da própria altura implícita;
//   IV.  nada produz overflow horizontal;
//   V.   cenários produzidos pela ROTA REAL: conteúdo que cabe, listagem extensa
//        (24 esquemas), rótulo que não cabe no controle (72 caracteres), recusa
//        com aviso, rede caída e esquema nenhum. Viewports 949x593 e 1280x800.
//
// Por que este diálogo e não outro: `Main.qml`, `esdeImportDialog` é o segundo
// exemplar do importador ES-DE no produto (o primeiro, corrigido na 3ª fatia,
// vive em `ThemeEditorPanel.qml`, `esdeImportDialog`). Aqui o corpo é um
// `ColumnLayout` com
// `anchors.fill: parent` dentro de um `Dialog` sem `height` declarado, as ações
// ficam no FIM desse fluxo e não há rodapé nem corpo rolável — com 24 esquemas de
// 48 px o "Importar" cai ~1 000 px abaixo do pé da moldura e nenhuma tecla o
// alcança. Nada exercitava este caminho: os `objectName` `theme-import-esde-*`
// não aparecem em teste algum antes desta fatia.
//
// Diferença de bancada em relação às fatias de painel, e ela é o ponto:
// `ThemeEditorPanel` recebe `requestAction` injetado, então aqueles harnesses
// puderam stubear a ponte. `Main.qml` não — o `request()` fala por
// `XMLHttpRequest` com `shell.apiUrl`. Aqui a ponte é um servidor HTTP real em
// loopback, iniciado pelo teste Python, e os contratos que `requestAction`
// resolve são os que a ponte publica a partir de
// `desktop_contracts.handheld_ui_contracts()`. Stub de contrato provaria o stub.
//
// Fatos medidos no Qt 6.11.2 do projeto, reutilizados das fatias anteriores (os
// probes não vivem no checkout) — são o motivo da forma do código:
//   • `qmltestrunner` hospeda a raiz em QQuickView, que REJEITA raiz Window
//     ("QQuickView: invalid root object"); daí `Item { Main {} }`, como em
//     `check_credential_journey_e2e.qml:14`;
//   • neste runtime `Item.childItems` é `undefined` e `children` funciona — a
//     varredura abaixo une as duas listas em vez de escolher uma;
//   • um Popup não é Item: não expõe `children`, `childItems` nem `window`; a
//     varredura parte de `dialog.contentItem` e do `dialog.footer`, quando
//     houver. `dialog.background` É um Item que cobre a moldura inteira — medido —
//     e serve de oráculo do quadro sem afirmar nada sobre Popup ser Item;
//   • o oráculo de foco é `shell.activeFocusItem`, não `item.activeFocus`;
//   • o `TestCase` deste runtime NÃO expõe `keyClicks`, e `keyPress` de letra
//     chega sem `text` (medido na fatia RetroFE): as teclas reais exercitam
//     navegação, ativação e edição (Down/Up/Tab/Backtab/Space/Escape/Backspace),
//     e o conteúdo entra pela propriedade do próprio campo — que é exatamente o
//     que a digitação produziria;
//   • o botão que abre este diálogo vive dentro do `ScrollView` da seção
//     Sistema (o botão "Importar tema ES-DE"), muitas vezes abaixo da dobra.
//     Revelar por
//     `forceActiveFocus()` é o mecanismo do produto (`restoreDialogFocus()` liga
//     `onActiveFocusItemChanged` a `ensureFocusedItemVisible`), e é por isso que
//     o passo abaixo espera o botão ficar na banda em vez de escrever `contentY`.

import QtQuick
import QtQuick.Controls
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 949
    height: 593

    /// Configuração efêmera escrita pelo teste em `build/`: endereço e token da
    /// ponte, viewport, escala publicada no `/status` e as alavancas do cenário.
    /// Nenhum nome de cenário vive aqui — o harness lê alavancas declarativas,
    /// para que a mesma suíte mede os seis cenários sem ramificação.
    property var cfg: ({})
    property var dialog: null

    Main {
        id: shell
        visible: true
        x: 0
        y: 0
        width: harness.width
        height: harness.height
    }

    TestCase {
        id: suite
        name: "ShellEsdeImportJourney"
        when: windowShown

        readonly property string sourcePath: "/fixture/esde/tema-completo"
        readonly property string themeName: "Tema ES-DE do shell"

        function config() {
            const request = new XMLHttpRequest()
            request.open("GET", Qt.resolvedUrl("../../build/ui-shell-esde-import-dialog.json"), false)
            request.send()
            verify(request.status === 0 || request.status === 200,
                   "a configuração efêmera da bridge não foi lida")
            return JSON.parse(request.responseText)
        }

        // ---------------------------------------------------------------- árvores

        /// Une `children` e `childItems`: medido que `childItems` é undefined
        /// neste runtime, e o precedente do repositório testa os dois.
        function kidsOf(item) {
            const out = []
            if (!item)
                return out
            const lists = [item.children, item.childItems]
            for (let index = 0; index < lists.length; index++) {
                const list = lists[index]
                if (!list)
                    continue
                for (let slot = 0; slot < list.length; slot++)
                    if (out.indexOf(list[slot]) < 0)
                        out.push(list[slot])
            }
            return out
        }

        /// Teto de profundidade: sem ele a varredura já pendurou o harness sem
        /// imprimir nada. Falha precisa aparecer, não silenciar.
        function descendants(root, out, depth) {
            if (!root || depth > 40)
                return out
            const kids = kidsOf(root)
            for (let index = 0; index < kids.length; index++) {
                out.push(kids[index])
                descendants(kids[index], out, depth + 1)
            }
            return out
        }

        function bodyNodes() {
            const out = []
            if (!dialog || !dialog.contentItem)
                return out
            descendants(dialog.contentItem, out, 0)
            if (dialog.footer)
                descendants(dialog.footer, out, 0)
            return out
        }

        function byObjectName(name) {
            const nodes = bodyNodes()
            for (let index = 0; index < nodes.length; index++)
                if (nodes[index].objectName === name)
                    return nodes[index]
            return null
        }

        /// Varre a árvore de Itens a partir de `raiz`. Chamar com `shell` não
        /// funciona: `Main` é uma `ApplicationWindow`, e Window não expõe
        /// `children`/`childItems` — medido, a varredura a partir de `shell` devolve
        /// 1 nó. O topo real da árvore é `shell.contentItem` (2 796 nós, o botão do
        /// importador ES-DE incluído).
        function findInShell(raiz, test) {
            const nodes = descendants(raiz, [], 0)
            return findAmong(nodes, test)
        }

        /// Varre uma lista já coletada. Passar a lista para `findInShell` silenciosa:
        /// `Array` não tem `children`/`childItems`, a varredura devolvia vazia e o
        /// controle procurado virava `null` mesmo estando na tela.
        function findAmong(nodes, test) {
            for (let index = 0; index < nodes.length; index++)
                if (test(nodes[index]))
                    return nodes[index]
            return null
        }

        function effectivelyVisible(item) {
            let current = item
            while (current) {
                if (current.visible === false)
                    return false
                current = current.parent
            }
            return true
        }

        // ---------------------------------------------------------- geometria/medida

        function rectIn(item, ancestor) {
            if (!item || !ancestor)
                return null
            const topLeft = item.mapToItem(ancestor, 0, 0)
            const bottomRight = item.mapToItem(ancestor, item.width, item.height)
            return {"left": topLeft.x, "top": topLeft.y,
                    "right": bottomRight.x, "bottom": bottomRight.y}
        }

        function describeRect(rect) {
            if (!rect)
                return "sem-rect"
            return "(" + Math.round(rect.left) + "," + Math.round(rect.top)
                    + ")-(" + Math.round(rect.right) + "," + Math.round(rect.bottom) + ")"
        }

        /// Área útil: o viewport rolável mais próximo, senão a moldura do diálogo.
        function bandOf(item) {
            let current = item ? item.parent : null
            let steps = 0
            while (current && steps < 40) {
                if (current.contentY !== undefined && current.contentHeight !== undefined
                        && current.height !== undefined && current.height > 0)
                    return current
                if (dialog && current === dialog.background)
                    return current
                current = current.parent
                steps += 1
            }
            return dialog ? dialog.background : null
        }

        function scrollOf(item) {
            let current = item ? item.parent : null
            let steps = 0
            while (current && steps < 40) {
                if (current.contentY !== undefined && current.contentHeight !== undefined)
                    return current
                current = current.parent
                steps += 1
            }
            return null
        }

        function inBand(item) {
            const band = bandOf(item)
            const rect = rectIn(item, band)
            if (!rect || !band)
                return false
            return rect.top >= -1 && rect.bottom <= band.height + 1
        }

        function inFrame(item) {
            const rect = rectIn(item, dialog.background)
            if (!rect)
                return false
            return rect.top >= -1 && rect.bottom <= dialog.background.height + 1
                && rect.left >= -1 && rect.right <= dialog.background.width + 1
        }

        function widthFits(item) {
            const band = bandOf(item)
            const rect = rectIn(item, band)
            if (!rect || !band)
                return false
            return rect.left >= -1 && rect.right <= band.width + 1
        }

        function notSqueezed(item) {
            if (item.implicitHeight === undefined || item.height === undefined)
                return true
            if (item.implicitHeight <= 0)
                return true
            return item.height >= item.implicitHeight - 1
        }

        /// Região do rodapé: o `footer` declarado, ou — na forma antiga, sem
        /// rodapé — a linha de ações onde vive o botão Importar. Medir a MESMA
        /// região nas duas árvores é o que faz o vermelho dizer "as ações estão a
        /// y=1548 numa moldura de 560 px" em vez de "campo ausente".
        function footerRegion() {
            if (!dialog)
                return null
            if (dialog.footer)
                return dialog.footer
            const apply = byObjectName("theme-import-esde-apply")
            return apply ? apply.parent : null
        }

        /// Corpo rolável (ou o contentItem nu, na forma antiga): a altura desta
        /// região é o que a escala de texto do host precisa mover.
        function bodyRegion() {
            if (!dialog || !dialog.contentItem)
                return null
            return dialog.contentItem.contentItem
                ? dialog.contentItem.contentItem : dialog.contentItem
        }

        function rectInWindow(item) {
            if (!item)
                return "ausente"
            const topLeft = item.mapToItem(shell.contentItem, 0, 0)
            const bottomRight = item.mapToItem(shell.contentItem, item.width, item.height)
            return Math.round(topLeft.x) + "," + Math.round(topLeft.y) + ","
                + Math.round(bottomRight.x - topLeft.x) + ","
                + Math.round(bottomRight.y - topLeft.y)
        }

        /// Geografia declarada pela cena, na moldura da janela. Sem esta linha o
        /// gate de capturas não teria como saber onde achar tinta — nem o de
        /// 48 px como saber o que mediu.
        function printGeometry(cena) {
            const apply = byObjectName("theme-import-esde-apply")
            const intro = findInShell(bodyRegion(), function(node) {
                return node.text !== undefined
                    && String(node.text).indexOf("Examine") === 0
                    && node.width > 0
            })
            const corpo = bodyRegion()
            // A altura visível do corpo é travada pelo teto do diálogo; o que a
            // escala do host move é o extento rolável, e é ele que se declara aqui.
            const conteudo = corpo && corpo.contentHeight !== undefined
                ? Math.round(corpo.contentHeight) : "ausente"
            console.log("GEOMETRIA|" + cena
                        + "|janela=" + Math.round(shell.width) + "x" + Math.round(shell.height)
                        + "|moldura=" + rectInWindow(dialog ? dialog.background : null)
                        + "|corpo=" + rectInWindow(corpo)
                        + "|conteudo=" + conteudo
                        + "|rodape=" + rectInWindow(footerRegion())
                        + "|acao=" + rectInWindow(apply)
                        + "|rotulo=" + (intro ? Math.round(intro.height) : "ausente")
                        + "|esquemas=" + shell.esdeImportSchemes.length
                        + "|escala=" + shell.visualScale)
        }

        // ------------------------------------------------------------------ espera

        /// Assinatura de geometria do estado atual; "" enquanto o layout não
        /// materializou os controles, para a espera ser por observable.
        function signature() {
            if (!dialog || !dialog.visible || !dialog.background)
                return ""
            const apply = byObjectName("theme-import-esde-apply")
            if (!apply || apply.width <= 0 || apply.height <= 0)
                return ""
            const corpo = bodyRegion()
            const footer = footerRegion()
            return Math.round(dialog.background.width) + "x"
                    + Math.round(dialog.background.height)
                    + "|apply=" + describeRect(rectIn(apply, dialog.background))
                    + "|corpo=" + (corpo ? Math.round(corpo.height) + "/"
                                             + Math.round(corpo.implicitHeight) : "sem")
                    + "|rodape=" + (footer ? describeRect(rectIn(footer, dialog.background))
                                           : "sem")
        }

        /// Espera por observable com limite e falha explícita (medido: `tryVerify`
        /// com closure não repete a amostragem neste runtime).
        function until(body, timeout, tag) {
            const step = 20
            let elapsed = 0
            var satisfied = body() === true
            while (!satisfied && elapsed < timeout) {
                wait(step)
                elapsed += step
                satisfied = body() === true
            }
            verify(satisfied, tag + " (expirou o limite de " + timeout
                            + " ms após " + elapsed + " ms)")
            return satisfied
        }

        /// Estabilização observável, não intervalo fixo: duas amostras iguais.
        function settleLayout(tag) {
            const step = 20
            const budget = 3000
            let elapsed = 0
            var previous = ""
            var stable = false
            while (elapsed < budget) {
                const current = signature()
                if (current !== "" && current === previous) {
                    stable = true
                    break
                }
                previous = current
                wait(step)
                elapsed += step
            }
            verify(stable, "o layout do diálogo não estabilizou observavelmente em "
                            + budget + " ms ('" + tag + "'); última assinatura: "
                            + (previous === "" ? "controles ainda ausentes" : previous))
            console.log("ESTABILIZOU '" + tag + "' em " + elapsed + " ms :: " + previous)
        }

        // ------------------------------------------------------------- superfície

        function expectedEsquemas() {
            return Number(harness.cfg.esquemas)
        }

        function activateWindowAndSize() {
            shell.requestActivate()
            until(function() { return shell.active === true }, 4000,
                  "a janela do teste não ficou ativa (tecla real não tem destino)")
            const partes = String(harness.cfg.viewport).split("x")
            harness.width = Number(partes[0])
            harness.height = Number(partes[1])
            shell.width = harness.width
            shell.height = harness.height
            until(function() {
                return Math.round(shell.width) === harness.width
                    && Math.round(shell.height) === harness.height
            }, 4000, "o shell não acompanhou o viewport " + harness.cfg.viewport)
        }

        /// Cada cenário começa e termina com o modal fechado e o importador limpo.
        /// Sem isto uma reprovação deixa o diálogo aberto e as falhas seguintes
        /// viram cascata — foi o que a primeira execução do harness RetroFE mediu.
        function resetSurface() {
            dialog = shell.esdeImportDialogControl
            // Quiescer ANTES de fechar: `onClosed` limpa o estado, e uma resposta
            // que chega depois dessa limpeza repõe esquemas e aviso — a cena
            // seguinte nasceria suja por culpa da ordem do teste, não do produto.
            until(function() { return shell.esdeImportBusy === false }, 3000,
                  "limpeza: a requisição do importador não terminou antes de fechar")
            if (dialog && dialog.visible) {
                dialog.close()
                until(function() { return dialog.visible === false }, 3000,
                      "limpeza: o diálogo não fechou")
            }
            until(function() {
                return shell.esdeImportBusy === false
                    && shell.esdeImportSchemes.length === 0 && shell.esdeImportNotice === ""
            }, 3000, "limpeza: o estado do importador não voltou ao neutro (voo="
                       + shell.esdeImportBusy + ", esquemas="
                       + shell.esdeImportSchemes.length + ", aviso='"
                       + shell.esdeImportNotice + "')")
        }

        function bootstrap() {
            harness.cfg = config()
            activateWindowAndSize()
            shell.apiUrl = harness.cfg.apiUrl
            shell.apiToken = harness.cfg.apiToken
            shell.refreshStatus("")
            until(function() {
                return shell.uiContracts !== undefined
                    && shell.uiContracts.byId !== undefined
                    && shell.uiContracts.byId["theme.import.esde.inspect"] !== undefined
                    && shell.uiContracts.byId["theme.import.esde.apply"] !== undefined
            }, 5000, "a ponte real não publicou os contratos do importador ES-DE")
            until(function() {
                return Math.round(shell.visualScale * 100)
                    === Math.round(Number(harness.cfg.escala) * 100)
            }, 3000, "a escala publicada no /status não chegou ao shell (visualScale="
                       + shell.visualScale + ", esperado " + harness.cfg.escala + ")")
            resetSurface()
        }

        function init() {
            bootstrap()
        }

        function cleanup() {
            resetSurface()
        }

        // ------------------------------------------------------- abrir pela rota real

        function triggerButton() {
            var found = null
            until(function() {
                found = findInShell(shell.contentItem, function(node) {
                    return node instanceof Button
                        && String(node.text) === "Importar tema ES-DE"
                        && node.width > 0 && node.height > 0
                        && effectivelyVisible(node)
                })
                return found !== null
            }, 5000, "o botão real do importador ES-DE não apareceu na seção Sistema")
            return found
        }

        /// Revelar pelo FOCO é o mecanismo do produto: `restoreDialogFocus()` liga
        /// `onActiveFocusItemChanged` a `ensureFocusedItemVisible`, que rola o
        /// ancestral até o item focado. O teste só espera o resultado — escrever
        /// `contentY` aqui seria rolagem manual.
        ///
        /// A banda é o `Flickable` que clipa, não o `ScrollView` que o embrulha.
        /// Medido: na janela do Deck com `bottomPadding` de 60 px as duas alturas
        /// diferem exatamente por esse padding (491 x 431), e o `ScrollView` não
        /// expõe `contentY` — quem rola é o de dentro. Comparar com a moldura
        /// externa dava um oráculo 60 px mais tolerante do que a tela: a reprovação
        /// integral dizia "4 px fora" de um alvo que estava 64 px abaixo do pé da
        /// área recortada. O quadro certo é o que clipa.
        function revealTrigger(trigger) {
            trigger.forceActiveFocus(Qt.TabFocusReason)
            until(function() { return shell.activeFocusItem === trigger }, 3000,
                  "o botão de abertura não aceitou o foco")
            visibleTrigger(trigger, "foco")
        }

        /// Espera observável, com o mesmo oráculo apertado, para usar antes e depois
        /// de uma mudança de geometria: o controle focado inteiro na banda que clipa.
        function visibleTrigger(trigger, tag) {
            const rolagem = bandOf(trigger)
            verify(rolagem !== null,
                   "o botão de abertura precisa estar dentro de uma superfície rolável; "
                   + "sem ela não há o que revelar")
            revealSnapshot(tag + "|antes", trigger)
            until(function() {
                const rect = rectIn(trigger, rolagem)
                return rect !== null && rect.top >= -1
                    && rect.bottom <= rolagem.height + 1
            }, 4000, "o foco não revelou o botão dentro da banda que clipa (" + tag + "): "
                       + describeRect(rectIn(trigger, rolagem)) + " na banda de "
                       + Math.round(rolagem.height) + " px")
            revealSnapshot(tag, trigger)
        }

        /// Diagnóstico da revelação, impresso no sucesso e na falha. Existe porque
        /// o mesmo asserter passou verde isolado e vermelho na suíte integral: sem
        /// estas grandezas não há como distinguir "a banda encolheu" de "o scroll
        /// não alcançava o alvo".
        ///
        /// Duas superfícies diferentes, e a diferença é o ponto medido: o
        /// `ScrollView` exposto como `systemScrollControl` tem `contentY`
        /// `undefined` (impresso como NaN por uma versão anterior desta sonda),
        /// porque quem rola é o `Flickable` interno — `bandOf()` é que o encontra,
        /// percorrendo os ancestrais exatamente como `ensureFocusedItemVisible`
        /// percorre. O padding vive no `ScrollView`; a altura útil e o `contentY`
        /// real vivem no `Flickable`. Medir o quadro errado é o que produzia
        /// "NaN" no log.
        function revealSnapshot(tag, trigger) {
            const banda = shell.systemScrollControl
            const rolagem = bandOf(trigger)
            const padTopo = banda.topPadding === undefined ? 0 : banda.topPadding
            const padBaixo = banda.bottomPadding === undefined ? 0 : banda.bottomPadding
            const naRolagem = rectIn(trigger, rolagem)
            const emConteudo = rolagem
                ? trigger.mapToItem(rolagem.contentItem, 0, 0) : null
            const limite = rolagem
                ? Math.max(0, rolagem.contentHeight - rolagem.height) : -1
            const visiveis = []
            let cursor = trigger
            let passos = 0
            while (cursor && passos < 40) {
                visiveis.push((cursor.clip === true ? "clip" : "-")
                              + ":" + (cursor.objectName !== undefined
                                       && cursor.objectName !== "" ? cursor.objectName
                                                                   : cursor.width + "x" + cursor.height))
                if (cursor === banda)
                    break
                cursor = cursor.parent
                passos += 1
            }
            console.log("REVELA"
                        + "|" + tag
                        + "|banda=" + Math.round(banda.height)
                        + "|bandaExpoeContentY=" + (typeof banda.contentY)
                        + "|rolagemAltura=" + (rolagem ? Math.round(rolagem.height) : "sem")
                        + "|contentHeight=" + (rolagem ? Math.round(rolagem.contentHeight) : "sem")
                        + "|contentY=" + (rolagem ? Math.round(rolagem.contentY) : "sem")
                        + "|originY=" + (rolagem ? Math.round(rolagem.originY) : "sem")
                        + "|topPadding=" + Math.round(padTopo)
                        + "|bottomPadding=" + Math.round(padBaixo)
                        + "|limiteDoProduto=" + Math.round(limite)
                        + "|alvoTop=" + describeRect(rectIn(trigger, banda))
                        + "|alvoNaRolagem=" + describeRect(naRolagem)
                        + "|alvoEmConteudo=" + (emConteudo ? Math.round(emConteudo.y) : "sem")
                        + "|alturaAlvo=" + (trigger ? Math.round(trigger.height) : "sem")
                        + "|cadeia=" + visiveis.join(">")
                        + "|compact=" + shell.compactLayout
                        + "|inset=" + shell.bottomSafeInset
                        + "|escala=" + shell.visualScale
                        + "|janela=" + Math.round(shell.width) + "x" + Math.round(shell.height))
        }

        function openThroughTheRealButton() {
            shell.sectionIndex = shell.sectionIndexOf("system")
            until(function() {
                return shell.responsiveContent.currentIndex === shell.sectionIndex
            }, 4000, "a seção Sistema não ficou ativa")
            dialog = shell.esdeImportDialogControl
            verify(dialog !== undefined && dialog !== null,
                   "o shell precisa expor o diálogo como superfície de teste, como já "
                   + "expõe os outros modais de Main.qml")
            const trigger = triggerButton()
            revealTrigger(trigger)
            mouseClick(trigger, trigger.width / 2, trigger.height / 2, Qt.LeftButton)
            until(function() { return dialog.visible === true }, 3000,
                  "o clique real no botão não abriu o diálogo")
            settleLayout("aberto")
            verify(dialog.modal === true,
                   "o diálogo precisa continuar modal — fechar modal por conveniência "
                   + "de teste mudaria o comportamento")
        }

        /// Abertura por TECLA REAL: o mesmo botão, ativado por Espaço. Cobrir as
        /// duas rotas importa — foi clicando que o shell escondeu este defeito.
        function openThroughTheRealKey() {
            shell.sectionIndex = shell.sectionIndexOf("system")
            until(function() {
                return shell.responsiveContent.currentIndex === shell.sectionIndex
            }, 4000, "a seção Sistema não ficou ativa")
            dialog = shell.esdeImportDialogControl
            const trigger = triggerButton()
            revealTrigger(trigger)
            keyPress(Qt.Key_Space)
            keyRelease(Qt.Key_Space)
            until(function() { return dialog.visible === true }, 3000,
                  "Espaço real no botão focado não abriu o diálogo")
            settleLayout("aberto por tecla")
        }

        /// "Examinar" pelo clique real, com a origem escrita no próprio campo.
        function inspectThroughTheRealButton() {
            const source = fieldNamed("theme-import-esde-source")
            source.text = sourcePath
            const inspect = buttonNamed("theme-import-esde-inspect")
            until(function() { return inspect.enabled === true }, 3000,
                  "Examinar não habilitou com o caminho informado")
            mouseClick(inspect, inspect.width / 2, inspect.height / 2, Qt.LeftButton)
            /// A resposta se espera pelo que ela PUBLICA, não pela contagem pedida.
            /// Com `esperado === 0` a condição `schemes.length === 0` já é vera antes
            /// de qualquer resposta: a espera era vazia, e a asserção seguinte lia o
            /// estado pré-resposta. Medido sob carga (16 processos em 8 núcleos), era
            /// exatamente aí que o cenário `sem-esquema` reprova e arrastava o resto
            /// da suíte. O que prova a chegada é o aviso que o produto escreve quando
            /// não há esquema nenhum (o aviso `theme-import-esde-notice`) ou a
            /// lista, com a requisição fora de voo.
            until(function() {
                return shell.esdeImportBusy === false
                    && (shell.esdeImportSchemes.length > 0 || shell.esdeImportNotice !== "")
            }, 8000, "a rota real não publicou resposta no diálogo (esquemas="
                       + shell.esdeImportSchemes.length + ", aviso='"
                       + shell.esdeImportNotice + "')")
            const esperado = expectedEsquemas()
            until(function() { return shell.esdeImportSchemes.length === esperado }, 5000,
                  "a rota real não publicou os " + esperado
                  + " esquemas no diálogo (obtidos: " + shell.esdeImportSchemes.length + ")")
            settleLayout("examinado")
        }

        function fieldNamed(name) {
            var found = null
            until(function() {
                found = byObjectName(name)
                return found !== null
            }, 4000, "o controle '" + name + "' não apareceu na árvore do diálogo")
            return found
        }

        function buttonNamed(name) {
            return fieldNamed(name)
        }

        function chooseFirstScheme() {
            if (shell.esdeImportSchemes.length === 0)
                return
            const radios = []
            const nodes = bodyNodes()
            for (let index = 0; index < nodes.length; index++) {
                const node = nodes[index]
                if (node.checkable === true && effectivelyVisible(node))
                    radios.push(node)
            }
            verify(radios.length === shell.esdeImportSchemes.length,
                   "cada esquema publicado precisa aparecer como opção selecionável no "
                   + "diálogo (opções=" + radios.length + ", esquemas="
                   + shell.esdeImportSchemes.length + ")")
            until(function() {
                return shell.esdeImportSchemeIndex === 0 || radios.length === 0
            }, 3000, "o examine não pré-selecionou o primeiro esquema")
        }

        function fillName() {
            if (shell.esdeImportSchemes.length === 0)
                return
            const field = fieldNamed("theme-import-esde-name")
            field.text = themeName
        }

        /// Estado carregado: examine + esquema escolhido + nome preenchido. É o
        /// estado em que o shell corta as ações.
        function loadTheJourney() {
            openThroughTheRealKey()
            inspectThroughTheRealButton()
            chooseFirstScheme()
            fillName()
            settleLayout("carregado")
        }

        function applyButton() {
            const apply = byObjectName("theme-import-esde-apply")
            verify(apply !== undefined && apply !== null,
                   "o botão de publicar precisa de objectName estável: sem ele a rota "
                   + "real não é alcançável pelo teste")
            return apply
        }

        // ------------------------------------------------------------ navegação real

        /// Navegação com tecla REAL até o alvo, com limite e falha explícita.
        function navigateWithRealKeys(target, forward, maxPresses, tag) {
            let presses = 0
            while (shell.activeFocusItem !== target && presses < maxPresses) {
                presses += 1
                if (forward) {
                    keyPress(Qt.Key_Down)
                    keyRelease(Qt.Key_Down)
                } else {
                    keyPress(Qt.Key_Up)
                    keyRelease(Qt.Key_Up)
                }
                const focused = shell.activeFocusItem
                verify(focused !== null,
                       "perder o foco no passo " + presses + " de '" + tag + "' mata a "
                       + "navegação por D-pad")
                if (!focused)
                    return presses
                verify(bodyNodes().indexOf(focused) >= 0,
                       "o passo " + presses + " de '" + tag + "' levou o foco para fora "
                       + "do diálogo (" + (focused.objectName || focused.toString()) + ")")
                console.log("PASSO " + presses + " tag=" + tag
                            + " foco=" + (focused.objectName || focused.toString())
                            + " em " + describeRect(rectIn(focused, bandOf(focused)))
                            + " banda=" + Math.round(bandOf(focused).height))
                until(function() { return inBand(focused) }, 1200,
                      "no passo " + presses + " de '" + tag + "' o controle focado ("
                      + (focused.objectName || "") + ") não está inteiro na banda "
                      + "visível: " + describeRect(rectIn(focused, bandOf(focused)))
                      + " da banda " + Math.round(bandOf(focused).height) + " px")
            }
            verify(shell.activeFocusItem === target,
                   "teclas reais de " + (forward ? "descida" : "subida") + " não chegaram "
                   + "ao alvo em '" + tag + "' depois de " + presses + " pressões")
            return presses
        }

        // ------------------------------------------------------------------ medição

        function textNodes() {
            const out = []
            const nodes = bodyNodes()
            for (let index = 0; index < nodes.length; index++) {
                const node = nodes[index]
                if (node.text === undefined || node.text === "" || !effectivelyVisible(node))
                    continue
                if (node.width <= 0 || node.height <= 0)
                    continue
                out.push(node)
            }
            return out
        }

        function assertNoCut(tag) {
            const nodes = textNodes()
            verify(nodes.length >= 5,
                   "a medição de '" + tag + "' precisa achar os controles de texto do "
                   + "diálogo (achou " + nodes.length + ")")
            let unreachable = 0
            let squeezed = 0
            let overflowX = 0
            for (let index = 0; index < nodes.length; index++) {
                const node = nodes[index]
                if (!inBand(node) && scrollOf(node) === null)
                    unreachable += 1
                if (!notSqueezed(node))
                    squeezed += 1
                if (!widthFits(node))
                    overflowX += 1
            }
            const banda = bandOf(applyButton())
            console.log("MEDIDA " + tag
                        + " moldura=" + Math.round(dialog.background.width) + "x"
                        + Math.round(dialog.background.height)
                        + " nodes=" + nodes.length
                        + " banda=" + Math.round(banda ? banda.height : -1)
                        + " foraDaBandaSemRolagem=" + unreachable
                        + " espremidos=" + squeezed
                        + " overflowHorizontal=" + overflowX
                        + " acao=" + describeRect(rectIn(applyButton(), dialog.background)))
            verify(unreachable === 0,
                   "todo controle de texto precisa estar na banda visível ou dentro de "
                   + "área rolável em '" + tag + "': " + unreachable
                   + " ficaram fora sem como alcançar")
            verify(squeezed === 0,
                   "nenhum controle pode ser espremido abaixo da altura implícita em '"
                   + tag + "': " + squeezed + " ficaram cortados no próprio texto")
            verify(overflowX === 0,
                   "sem overflow horizontal em '" + tag + "': " + overflowX
                   + " controles passaram da largura útil")
        }

        function desfecho(fechar, aviso) {
            console.log("DESBFECHO fechar=" + (fechar ? 1 : 0))
            console.log("DESBFECHO aviso=" + (aviso ? 1 : 0))
        }

        // ---------------------------------------------------------------- cenários

        function test_01_o_botao_real_abre_o_modal_e_o_foco_entra_no_corpo() {
            openThroughTheRealButton()
            const source = fieldNamed("theme-import-esde-source")
            verify(source !== null, "o campo de origem precisa existir no diálogo")
            until(function() {
                const ativo = shell.activeFocusItem
                return ativo !== null && bodyNodes().indexOf(ativo) >= 0
            }, 3000, "abrir o modal sem levar o foco para dentro do corpo deixa quem "
                     + "navega por teclado ou pelo controle do lado de fora")
            console.log("FOCO ABERTO "
                        + (shell.activeFocusItem.objectName || shell.activeFocusItem.toString()))
            verify(inFrame(source), "o campo de origem não pode sair da moldura ao abrir: "
                   + describeRect(rectIn(source, dialog.background)))
            desfecho(false, false)
        }

        function test_02_examinar_pela_rota_real_publica_os_esquemas() {
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            const esperado = expectedEsquemas()
            verify(shell.esdeImportSchemes.length === esperado,
                   "a ponte real publicou " + shell.esdeImportSchemes.length
                   + " esquemas, esperado " + esperado)
            const notice = findInShell(bodyRegion(), function(node) {
                return node.text !== undefined && String(node.text).length > 0
                    && effectivelyVisible(node)
                    && String(shell.esdeImportNotice).indexOf(String(node.text)) === 0
            })
            if (esperado === 0) {
                verify(shell.esdeImportNotice.length > 0,
                       "sem esquema publicado o diálogo precisa dizer isso no corpo")
                verify(notice !== null,
                       "o aviso de 'nenhum esquema' precisa aparecer no corpo do diálogo")
                const apply = applyButton()
                verify(apply.enabled === false,
                       "sem esquema selecionado, 'Importar' não pode estar habilitado")
            } else {
                const radios = []
                const nodes = bodyNodes()
                for (let index = 0; index < nodes.length; index++)
                    if (nodes[index].checkable === true && effectivelyVisible(nodes[index]))
                        radios.push(nodes[index])
                verify(radios.length === esperado,
                       "cada um dos " + esperado + " esquemas publicados precisa aparecer "
                       + "como opção selecionável (apareceram " + radios.length + ")")
            }
            printGeometry("aberto")
        }

        function test_03_teclas_reais_de_d_pad_percorrem_o_dialogo_com_foco_visivel() {
            if (expectedEsquemas() === 0) {
                console.log("PULADO test_03: sem esquema publicado não há jornada "
                            + "completa para percorrer; o cenário é o de estado vazio")
                return
            }
            loadTheJourney()
            const source = fieldNamed("theme-import-esde-source")
            const apply = applyButton()
            until(function() { return apply.enabled === true }, 3000,
                  "com esquema escolhido e nome informado, 'Importar' tem de estar "
                  + "habilitado")
            source.forceActiveFocus(Qt.TabFocusReason)
            until(function() { return shell.activeFocusItem === source }, 3000,
                  "o campo de origem não aceitou o foco para iniciar a navegação")
            const down = navigateWithRealKeys(apply, true, 40, "descida")
            const up = navigateWithRealKeys(source, false, 40, "subida")
            console.log("MEDIDA navegacao pressoesDescida=" + down + " pressoesSubida=" + up)
        }

        function test_04_tab_e_shift_tab_reais_nao_saem_do_modal() {
            if (expectedEsquemas() === 0) {
                console.log("PULADO test_04: o estado vazio tem três controles e a "
                            + "tabulação é coberta no cenário carregado")
                return
            }
            loadTheJourney()
            const focusables = []
            const nodes = bodyNodes()
            for (let index = 0; index < nodes.length; index++) {
                const node = nodes[index]
                if (node.activeFocusOnTab === true && node.enabled === true
                        && node.visible === true && focusables.indexOf(node) < 0)
                    focusables.push(node)
            }
            verify(focusables.length >= 5,
                   "o diálogo tem de expor ao menos cinco controles navegáveis por Tab "
                   + "(achou " + focusables.length + ")")
            const steps = focusables.length + 1
            for (let index = 0; index < steps; index++) {
                keyPress(Qt.Key_Tab)
                keyRelease(Qt.Key_Tab)
                const focused = shell.activeFocusItem
                verify(focused !== null, "Tab real sem foco ativo no passo " + index)
                verify(bodyNodes().indexOf(focused) >= 0,
                       "Tab real saiu do modal no passo " + index + " ("
                       + (focused.objectName || "") + ")")
                until(function() { return inBand(focused) }, 1200,
                      "Tab real levou o foco para fora da banda visível no passo "
                      + index + " (" + (focused.objectName || "") + ")")
            }
            for (let index = 0; index < steps; index++) {
                keyPress(Qt.Key_Backtab, Qt.ShiftModifier)
                keyRelease(Qt.Key_Backtab, Qt.ShiftModifier)
                const focused = shell.activeFocusItem
                verify(focused !== null, "Shift+Tab real sem foco ativo no passo " + index)
                verify(bodyNodes().indexOf(focused) >= 0,
                       "Shift+Tab real saiu do modal no passo " + index + " ("
                       + (focused.objectName || "") + ")")
                until(function() { return inBand(focused) }, 1200,
                      "Shift+Tab real levou o foco para fora da banda visível no passo "
                      + index + " (" + (focused.objectName || "") + ")")
            }
        }

        function test_05_as_setas_e_backspace_editam_sem_roubar_a_navegacao() {
            if (expectedEsquemas() === 0) {
                console.log("PULADO test_05: o campo de nome só existe com esquema "
                            + "publicado; o estado vazio não tem edição para medir")
                return
            }
            loadTheJourney()
            const name = fieldNamed("theme-import-esde-name")
            name.forceActiveFocus(Qt.OtherFocusReason)
            until(function() { return shell.activeFocusItem === name }, 3000,
                  "o campo de nome não tomou o foco para a edição")
            const antes = name.text.length
            keyPress(Qt.Key_Left)
            keyRelease(Qt.Key_Left)
            keyPress(Qt.Key_Backspace)
            keyRelease(Qt.Key_Backspace)
            const depois = name.text.length
            console.log("MEDIDA edicao dentro do campo antes=" + antes + " depois=" + depois)
            verify(depois > 0 && depois === antes - 1,
                   "Backspace real tem de editar o campo (apagar um caractere), não "
                   + "atravessar o diálogo: " + antes + " -> " + depois)
            const focoAntes = shell.activeFocusItem
            keyPress(Qt.Key_Down)
            keyRelease(Qt.Key_Down)
            verify(shell.activeFocusItem !== focoAntes,
                   "Down real precisa tirar o foco do campo e navegar o diálogo, não "
                   + "ser engolido pela edição")
        }

        function test_06_publicar_pela_tecla_real_exerce_a_rota_e_recupera() {
            if (expectedEsquemas() === 0) {
                // Estado vazio: não há o que publicar, e a prova é que nada vazou.
                openThroughTheRealButton()
                inspectThroughTheRealButton()
                const apply = applyButton()
                apply.forceActiveFocus(Qt.TabFocusReason)
                keyPress(Qt.Key_Space)
                keyRelease(Qt.Key_Space)
                verify(shell.esdeImportNotice.length > 0,
                       "o estado vazio precisa de aviso visível no corpo")
                verify(dialog.visible === true,
                       "com 'Importar' desabilitado nenhum fechamento pode acontecer")
                desfecho(false, true)
                printGeometry("vazio")
                return
            }
            loadTheJourney()
            const apply = applyButton()
            until(function() { return apply.enabled === true }, 3000,
                  "'Importar' não habilitou com esquema e nome reais")
            apply.forceActiveFocus(Qt.TabFocusReason)
            until(function() { return shell.activeFocusItem === apply }, 3000,
                  "o botão de publicar não aceitou o foco para a tecla real")
            keyPress(Qt.Key_Space)
            keyRelease(Qt.Key_Space)

            const desfechoEsperado = harness.cfg.espera
            const fechar = desfechoEsperado.fechar === true
            const aviso = desfechoEsperado.aviso === true
            if (fechar) {
                until(function() { return dialog.visible === false }, 5000,
                      "a rota real respondeu 200 e o diálogo deveria fechar")
                until(function() {
                    return shell.esdeImportSchemes.length === 0
                }, 3000, "fechar depois de publicar deixou estado para trás")
            } else {
                until(function() {
                    return String(shell.esdeImportNotice).length > 0
                }, 5000, "a ponte recusou (ou caiu) e nada apareceu no corpo do diálogo")
                verify(dialog.visible === true,
                       "recusa e falha de rede não podem fechar o diálogo com a edição "
                       + "em curso")
                const source = fieldNamed("theme-import-esde-source")
                verify(source.text.length > 0,
                       "a origem informada precisa sobreviver ao erro; o usuário corrige, "
                       + "não recomeça")
                // Recuperação: depois do aviso as ações continuam alcançáveis por
                // tecla real, com cada destino inteiro na banda.
                settleLayout("depois do erro")
                assertNoCorteAposErro()
            }
            desfecho(fechar, aviso)
            printGeometry("depois")
        }

        function assertNoCorteAposErro() {
            const apply = applyButton()
            const banda = bandOf(apply)
            const frame = dialog.background
            console.log("MEDIDA recuperacao notice=" + shell.esdeImportNotice.length
                        + " acao=" + describeRect(rectIn(apply, frame)) + " moldura="
                        + Math.round(frame.width) + "x" + Math.round(frame.height)
                        + " banda=" + (banda ? Math.round(banda.height) : -1))
            verify(inFrame(apply),
                   "depois do erro o botão de publicar não pode sair da moldura: "
                   + describeRect(rectIn(apply, frame)))
            verify(inBand(apply),
                   "depois do erro o botão de publicar precisa estar na banda visível "
                   + "ou ser revelado por rolagem: "
                   + describeRect(rectIn(apply, banda)) + " da banda "
                   + (banda ? Math.round(banda.height) : -1) + " px")
        }

        function test_07_escape_e_cancelar_fecham_sem_gravar_nada() {
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            chooseFirstScheme()
            fillName()
            settleLayout("fechamento")
            keyPress(Qt.Key_Escape)
            keyRelease(Qt.Key_Escape)
            until(function() { return dialog.visible === false }, 3000,
                  "Escape real não fechou o diálogo")
            until(function() {
                return shell.esdeImportSchemes.length === 0 && shell.esdeImportNotice === ""
            }, 3000, "fechar por Escape deixou estado do importador para trás")

            openThroughTheRealButton()
            inspectThroughTheRealButton()
            chooseFirstScheme()
            fillName()
            settleLayout("cancelar")
            const cancel = findAmong(bodyNodes(), function(node) {
                return node instanceof Button && String(node.text).indexOf("Cancelar") === 0
            })
            verify(cancel !== null,
                   "o diálogo precisa de um Cancelar real dentro do corpo medido "
                   + "(nós varridos: " + bodyNodes().length + ")")
            verify(cancel.height >= 48 && cancel.width >= 48,
                   "UX-05: Cancelar precisa de alvo de 48 px (medido "
                   + Math.round(cancel.width) + "x" + Math.round(cancel.height) + ")")
            mouseClick(cancel, cancel.width / 2, cancel.height / 2, Qt.LeftButton)
            until(function() { return dialog.visible === false }, 3000,
                  "o clique real em Cancelar não fechou o diálogo")
            until(function() { return shell.esdeImportSchemes.length === 0 }, 3000,
                  "Cancelar deixou esquemas escolhidos no estado do shell")
        }

        function test_08_o_rodape_fica_na_banda_com_conteudo_que_excede() {
            if (expectedEsquemas() === 0) {
                console.log("PULADO test_08: sem conteúdo excedente a banda não é "
                            + "colocada à prova; o cenário é o de estado vazio")
                return
            }
            loadTheJourney()
            const apply = applyButton()
            const frame = dialog.background
            /// Não-vacuidade medida no CONTEÚDO, não no contêiner. Na forma antiga
            /// o corpo é um `ColumnLayout { anchors.fill: parent }`: o Item que o
            /// hospeda devolve `implicitHeight` 0 enquanto os filhos fluem até
            /// y=1 674 — medir o contêiner diria "cabe" exatamente onde não cabe.
            /// O que excede a banda são os controles, medidos na própria banda.
            function fundoMaisProfundo(banda) {
                const nodes = textNodes()
                let max = 0
                for (let index = 0; index < nodes.length; index++) {
                    const rect = rectIn(nodes[index], banda)
                    if (rect)
                        max = Math.max(max, rect.bottom)
                }
                return max
            }

            const banda = bandOf(apply)
            const excede = banda !== null
                && fundoMaisProfundo(banda) > banda.height + 1
            verify(excede || Number(harness.cfg.esquemas) <= 2,
                   "com " + harness.cfg.esquemas + " esquemas o conteúdo precisa exceder "
                   + "a banda visível; se couber, este cenário não exercita rolagem e "
                   + "tem de ser reformulado (banda="
                   + (banda ? Math.round(banda.height) : -1) + " px, conteúdo até "
                   + Math.round(banda ? fundoMaisProfundo(banda) : -1) + " px)")
            verify(inFrame(apply),
                   "as ações não podem sair da moldura do diálogo: apply="
                   + describeRect(rectIn(apply, frame)) + " moldura="
                   + Math.round(frame.width) + "x" + Math.round(frame.height))
            const rodape = footerRegion()
            verify(rodape !== null && inFrame(rodape),
                   "a linha de ações precisa estar inteira dentro da moldura: "
                   + describeRect(rectIn(rodape, frame)))
            assertNoCut("carregado")
            printGeometry("dialogo")
        }

        function test_09_escala_de_texto_nao_corta_a_moldura() {
            if (expectedEsquemas() === 0) {
                console.log("PULADO test_09: a escala é medida no diálogo carregado, "
                            + "onde o texto existe")
                return
            }
            loadTheJourney()
            verify(Math.round(shell.visualScale * 100)
                       === Math.round(Number(harness.cfg.escala) * 100),
                   "a escala publicada pelo /status precisa chegar ao shell antes da "
                   + "medição (visualScale=" + shell.visualScale + ")")
            const apply = applyButton()
            verify(inFrame(apply),
                   "com escala " + harness.cfg.escala + " as ações não podem sair da "
                   + "moldura: " + describeRect(rectIn(apply, dialog.background)))
            assertNoCut("escala " + harness.cfg.escala)
            printGeometry("dialogo")
        }

        /// O teorema que a suíte integral cobrou: revelar pelo foco é um
        /// *instantâneo*. `onActiveFocusItemChanged` só dispara quando o foco
        /// MUDA; `ensureFocusedItemVisible` rola uma vez e nunca mais. Medido na
        /// banda que clipa, o `ScrollView` da seção Sistema encolhe 94 px quando a
        /// faixa de atenção aparece (`Main.qml:341`, guiada pelo `/status`) e a
        /// coluna cresce quando os cartões de diagnóstico chegam — nos dois casos
        /// o controle que já tinha o foco sai da área recortada e nenhum sinal o
        /// traz de volta. É o que fazia o gate reprovar sob carga: sem carga o
        /// `/status` chega antes do foco; com carga chega depois.
        ///
        /// O cenário é a MESMA mudança de geometria, produzida sem depender de
        /// sorte: a janela encolhe com o foco já instalado na banda. Reduzir a
        /// janela é caminho real do shell (o Modo Desktop é janela, e a dobra de
        /// layout do Deck se decide por altura), e o efeito no scroll é o do
        /// instante medido: a banda muda debaixo de um foco que não mudou.
        function test_10_a_banda_que_muda_mantem_o_foco_revelado() {
            shell.sectionIndex = shell.sectionIndexOf("system")
            until(function() {
                return shell.responsiveContent.currentIndex === shell.sectionIndex
            }, 4000, "a seção Sistema não ficou ativa")
            const trigger = triggerButton()
            revealTrigger(trigger)

            const novaAltura = Math.max(420, harness.height - 120)
            const bandaAntes = bandOf(trigger).height
            // `activateWindowAndSize()` atribui `shell.height` de forma imperativa,
            // e um atributo desses substitui o vínculo: encolher só o `harness` não
            // moveria nada. A janela é o que o produto mede, então é ela que muda.
            harness.height = novaAltura
            shell.height = novaAltura
            until(function() {
                return Math.round(shell.height) === novaAltura
            }, 4000, "a janela não acompanhou a mudança de altura")
            until(function() {
                return bandOf(trigger).height < bandaAntes - 40
            }, 4000, "a banda que clipa não encolheu com a janela (antes "
                       + Math.round(bandaAntes) + " px, agora "
                       + Math.round(bandOf(trigger).height)
                       + " px): sem mudança de geometria o cenário não exercita nada")
            visibleTrigger(trigger, "depois da banda mudar")
        }
    }
}
