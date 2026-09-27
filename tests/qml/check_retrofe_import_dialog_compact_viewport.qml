// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// UX-07 + UX-05 — o diálogo "Importar cena RetroFE" sob viewport compacto.
//
// O contrato medido aqui é conteúdo e ações alcançáveis, com foco visível e sem
// corte — não é uma opinião sobre widget:
//   I.   nenhum controle sai da moldura do diálogo (o que sai, é cortado);
//   II.  as ações (Cancelar / Publicar cena) estão na banda visível sem que o
//        teste mexa em `contentY`; quando o conteúdo passa da banda, chegar até
//        elas é feito com TECLA REAL de D-pad, e cada destino focado precisa
//        estar inteiro na banda (é isso que torna a rolagem load-bearing);
//   III. nenhum controle é espremido abaixo da própria altura implícita — texto
//        cortado é o mesmo defeito de alcance, só que silencioso;
//   IV.  nada produz overflow horizontal;
//   V.   os cenários são os dois: conteúdo que CABE (aí não se exige ScrollView
//        nem overflow — cobrar rolagem onde não há seria opinião) e conteúdo
//        EXTENSO, produzido pelo caminho real de erro do `Publicar cena`, para
//        exercitar rolagem de verdade. Os dois viewports 949×593 e 1280×800.
//
// Fatos medidos no Qt 6.11.2 instalado antes deste arquivo (probes fora do
// checkout, em /tmp/probe_band_rc01.qml, /tmp/probe_rc01b.qml,
// /tmp/probe_ids2.qml, /tmp/probe_keys.qml) — são o motivo da forma do código:
//   • `qmltestrunner` hospeda a raiz em QQuickView, que REJEITA raiz Window
//     ("QQuickView: invalid root object"); daí `Item { ApplicationWindow {} }`,
//     como em check_dialog_keys.qml;
//   • no binding QML deste runtime `Item.childItems` é `undefined` e `children`
//     funciona — o dual-check de check_dialog_keys.qml existe por isso, e aqui a
//     varredura une as duas listas em vez de escolher uma;
//   • um Popup não é Item: não expõe `children`, `childItems` nem `window`; a
//     varredura parte de `dialog.contentItem`. Mas `dialog.background` É um Item
//     que cobre a moldura inteira — medido (0,0)-(700,569) — então "dentro do
//     diálogo" é medido por `mapToItem` no background, sem afirmar nada sobre
//     Popup ser Item;
//   • `shell.activeFocusItem` funciona para itens dentro do Popup (medido: logo
//     após abrir, é `themeImportRetrofeSource`), então o foco é oráculo da
//     janela, não `item.activeFocus`;
//   • o `TestCase` deste runtime NÃO expõe `keyClicks` (injeção de texto);
//     `keyPress(Qt.Key_R)` chega sem `text` e não escreve no campo. Então as
//     teclas reais exercitam navegação e edição (Tab/Shift+Tab/Up/Down/Left/
//     Backspace/Escape) e o conteúdo entra pelas propriedades do painel — que é
//     exatamente o que a digitação produziria via `onTextChanged`.
//
// Chamar `moveFocus()` diretamente seria teste complementar, não prova de
// input: por isso nenhuma asserção abaixo depende de chamada de volta.

import QtQuick
import QtQuick.Controls
import QtQuick.Window
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 1280
    height: 800

    // Alavanca determinística do cenário extenso: o erro do apply real vai
    // inteira para `retrofeImportNotice`, que é um Label com WordWrap sem limite
    // de linhas. Nada aqui infla geometria por fora do produto.
    property bool applyFailsWithLongReport: false
    property var publishedPayload: null
    property int publishedCalls: 0
    property int inspectCalls: 0
    readonly property string longReport:
        "Falha ao compilar a cena RetroFE: assets ausentes (background.png, "
        + "logo.png, font.ttf), esquemas com elementos degradados, caminho fora "
        + "da raiz permitida e arquivo recusado por extensão. "
    readonly property var fixtures: {
        "layouts": [
            {
                "id": "main",
                "name": "Main",
                "report": {"elements": 8, "degraded": 1},
                "assets": {"available": ["assets/logo.png"], "missing": [],
                           "refused": [], "ready": true}
            }
        ]
    }

    function request(method, path, _payload, callback, _errorCallback) {
        if (method === "GET" && path === "/theme/list")
            callback({"themes": []})
    }

    function requestAction(actionId, payload, callback, errorCallback) {
        if (actionId === "theme.import.retrofe.inspect") {
            inspectCalls += 1
            callback({"layouts": fixtures.layouts})
            return
        }
        if (actionId === "theme.import.retrofe.apply") {
            if (applyFailsWithLongReport) {
                errorCallback(longReport.repeat(24), {})
                return
            }
            publishedCalls += 1
            publishedPayload = payload
            callback({"sceneId": payload.sceneId, "activated": false})
        }
    }

    ApplicationWindow {
        id: shell
        visible: true
        width: harness.width
        height: harness.height

        ThemeEditorPanel {
            id: panel
            anchors.fill: parent
            request: harness.request
            requestAction: harness.requestAction
            activeThemeId: "org.steamzero.default"
        }
    }

    TestCase {
        id: suite
        name: "RetrofeImportDialogViewport"
        when: windowShown

        property var dialog: null
        property int lastPresses: 0
        property int publishesAtStart: 0

        /// Cada cenário precisa começar e terminar com o modal fechado e o
        /// importador limpo. Sem isto uma reprovação deixa o diálogo aberto, e as
        /// falhas seguintes viram cascata em vez de defeito — foi exatamente o que
        /// a primeira execução deste arquivo mediu (3 reprovações em cascata).
        function resetSurface() {
            harness.applyFailsWithLongReport = false
            harness.publishedPayload = null
            dialog = panel.retrofeImportDialogControl
            if (dialog && dialog.visible) {
                dialog.close()
                waitFor(function() { return dialog.visible === false }, 3000,
                        "limpeza: o diálogo não fechou")
            }
            waitFor(function() { return panel.retrofeImportLayouts.length === 0
                                            && panel.retrofeImportNotice === "" }, 3000,
                    "limpeza: o estado do importador não voltou ao neutro")
        }

        function init() {
            resetSurface()
        }

        function cleanup() {
            resetSurface()
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

        /// Teto de profundidade: sem ele a varredura já pendurou este harness sem
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

        /// Área útil de um controle: o viewport rolável mais próximo, se houver;
        /// senão a moldura do diálogo. `background` é Item e cobre o quadro
        /// inteiro — medido — então serve de oráculo sem afirmar que Popup é Item.
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

        /// Assinatura de geometria do estado atual. Retorna "" enquanto o layout
        /// ainda não materializou os controles — assim a espera abaixo é por
        /// observable, não por intervalo fixo.
        function signature() {
            if (!dialog || !dialog.visible || !dialog.background)
                return ""
            const apply = panel.retrofeImportApplyControl
            if (!apply || apply.width <= 0 || apply.height <= 0)
                return ""
            const notice = byObjectName("themeImportRetrofeNotice")
            const frame = dialog.background
            return Math.round(frame.width) + "x" + Math.round(frame.height)
                    + "|apply=" + describeRect(rectIn(apply, frame))
                    + "|notice=" + (notice ? Math.round(notice.implicitHeight) + "/"
                                                  + Math.round(notice.height) : "sem")
                    + "|body=" + (dialog.contentItem
                                  ? Math.round(dialog.contentItem.height) + "/"
                                    + Math.round(dialog.contentItem.implicitHeight) : "sem")
        }

        /// Espera por observable com orçamento e falha explícita. Medido neste
        /// runtime: `TestCase.tryVerify` com closure avaliada por `QJSValue` não
        /// repete a amostragem de estado (a versão anterior deste arquivo reprovou
        /// 11 cenários em 174 ms, ou seja, sem nunca esperar). `waitFor` é o mesmo
        /// contrato, implementado sobre `wait(step)` com limite e tempo medido.
        function waitFor(body, timeout, tag) {
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

        /// Estabilização observável, não intervalo fixo: aceita apenas duas
        /// amostras de geometria consecutivas e iguais, com os controles já
        /// materializados, e declara o tempo que levou. O layout deste diálogo
        /// depende de Repeater, de visibilidade condicional e do aviso que cresce
        /// — amostrar uma vez seria ler um estado transitório.
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

        function useViewport(width, height) {
            shell.requestActivate()
            waitFor(function() { return shell.active === true }, 3000,
                      "a janela do teste não ficou ativa (tecla real não tem destino)")
            shell.width = width
            shell.height = height
            waitFor(function() { return panel.width === width && panel.height === height },
                      3000, "o painel não acompanhou o viewport " + width + "x" + height)
        }

        // --------------------------------------------------------- jornada de UI

        function buttonNamed(name) {
            var found = null
            waitFor(function() {
                found = byObjectName(name)
                return found !== null
            }, 3000, "o controle '" + name + "' não apareceu na árvore do diálogo")
            return found
        }

        function triggerButton() {
            var found = null
            waitFor(function() {
                found = null
                const nodes = descendants(panel, [], 0)
                for (let index = 0; index < nodes.length; index++)
                    if (nodes[index].objectName === "themeImportRetrofeButton")
                        found = nodes[index]
                return found !== null
            }, 3000, "a área de importação não expôs o botão real da cena RetroFE")
            return found
        }

        function openThroughTheRealButton() {
            dialog = panel.retrofeImportDialogControl
            verify(dialog !== undefined && dialog !== null,
                   "o painel precisa expor o diálogo como superfície de teste, como "
                   + "Main/Emulation já expõem seus controles")
            const trigger = triggerButton()
            mouseClick(trigger, trigger.width / 2, trigger.height / 2, Qt.LeftButton)
            waitFor(function() { return dialog.visible === true }, 3000,
                      "o clique real no botão da área não abriu o diálogo")
            settleLayout("aberto")
            verify(dialog.modal === true,
                   "o diálogo precisa continuar modal — fechar modal por conveniência "
                   + "de teste mudaria o comportamento")
        }

        /// "Examinar" pelo clique real, com a origem escrita no próprio campo.
        function inspectThroughTheRealButton() {
            const source = buttonNamed("themeImportRetrofeSource")
            panel.retrofeImportSource = "/fixture/retrofe/cena"
            const inspect = buttonNamed("themeImportRetrofeInspect")
            const before = harness.inspectCalls
            mouseClick(inspect, inspect.width / 2, inspect.height / 2, Qt.LeftButton)
            waitFor(function() { return harness.inspectCalls === before + 1 }, 3000,
                      "o clique real em Examinar não disparou a ação publicada")
            waitFor(function() { return panel.retrofeImportLayouts.length === 1 }, 3000,
                      "o examine não publicou o layout no diálogo")
            settleLayout("examinado")
        }

        function fillCredits() {
            panel.retrofeImportSceneId = "org.exemplo.retrofe"
            panel.retrofeImportName = "Cena RetroFE de teste"
            panel.retrofeImportAuthor = "Autor de teste"
            panel.retrofeImportLicense = "CC0-1.0"
        }

        function closeIfOpen() {
            resetSurface()
        }

        /// Os controles que carregam texto: é onde o corte aparece como texto
        /// espremido, e onde a largura estoura.
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
            verify(nodes.length >= 6,
                   "a medição de '" + tag + "' precisa achar os controles de texto do "
                   + "diálogo (achou " + nodes.length + ")")
            let unreachable = 0
            let squeezed = 0
            let overflowX = 0
            for (let index = 0; index < nodes.length; index++) {
                const node = nodes[index]
                // Fora da banda só é aceito onde existe mecanismo de rolagem que
                // leve até o item; sem rolagem, o que passa da banda é corte.
                if (!inBand(node) && scrollOf(node) === null)
                    unreachable += 1
                if (!notSqueezed(node))
                    squeezed += 1
                if (!widthFits(node))
                    overflowX += 1
            }
            console.log("MEDIDA " + tag
                        + " moldura=" + Math.round(dialog.background.width) + "x"
                        + Math.round(dialog.background.height)
                        + " nodes=" + nodes.length
                        + " foraDaBandaSemRolagem=" + unreachable
                        + " espremidos=" + squeezed
                        + " overflowHorizontal=" + overflowX)
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

        /// Navegação com tecla REAL até o alvo, com limite e falha explícita.
        /// Cada passo tem de estar inteiro na banda visível: é isso que prova que
        /// a rolagem acompanha o foco, e não que o teste mexeu em contentY.
        function navigateWithRealKeys(target, forward, maxPresses, tag) {
            let presses = 0
            while (shell.activeFocusItem !== target && presses < maxPresses) {
                presses += 1
                if (forward)
                    keyClick(Qt.Key_Down)
                else
                    keyClick(Qt.Key_Up)
                const focused = shell.activeFocusItem
                verify(focused !== null,
                       "perder o foco no passo " + presses + " de '" + tag + "' mata a "
                       + "navegação por D-pad")
                if (!focused)
                    return presses
                const nodes = bodyNodes()
                verify(nodes.indexOf(focused) >= 0,
                       "o passo " + presses + " de '" + tag + "' levou o foco para fora "
                       + "do diálogo (" + focused.objectName + ")")
                console.log("PASSO " + presses + " tag=" + tag + " foco="                            + (focused.objectName || focused.toString())                            + " em " + describeRect(rectIn(focused, bandOf(focused)))                            + " banda=" + Math.round(bandOf(focused).height))
                waitFor(function() { return inBand(focused) }, 1200,
                          "no passo " + presses + " de '" + tag + "' o controle focado "
                          + "(+" + focused.objectName + ") não está inteiro na banda "
                          + "visível: " + describeRect(rectIn(focused, bandOf(focused)))
                          + " da banda " + Math.round(bandOf(focused).height) + " px")
            }
            verify(shell.activeFocusItem === target,
                   "teclas reais de " + (forward ? "descida" : "subida") + " não chegaram "
                   + "ao alvo em '" + tag + "' depois de " + presses + " pressões")
            return presses
        }

        // ------------------------------------------------------------- cenários

        function test_01_o_botao_real_abre_o_modal_e_o_foco_entra_no_corpo() {
            useViewport(949, 593)
            openThroughTheRealButton()
            const source = buttonNamed("themeImportRetrofeSource")
            verify(source !== null, "o campo de origem precisa existir no diálogo")
            waitFor(function() {
                return shell.activeFocusItem !== null
                        && shell.activeFocusItem.objectName === "themeImportRetrofeSource"
            }, 3000, "abrir o modal sem levar o foco deixa quem navega por teclado ou "
                     + "controle do lado de fora")
            console.log("MEDIDA aberto viewport=949x593 banda="
                        + Math.round(bandOf(source).height) + " apply="
                        + describeRect(rectIn(panel.retrofeImportApplyControl,
                                               dialog.background)))
            closeIfOpen()
        }

        function test_02_conteudo_que_cabe_nao_exige_rolagem_e_mantem_acoes_alcancaveis() {
            useViewport(949, 593)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillCredits()
            settleLayout("compacto normal")

            const cancel = buttonNamed("themeImportRetrofeCancel")
            const apply = panel.retrofeImportApplyControl
            verify(apply !== undefined && apply !== null,
                   "o primary precisa de alias de teste, como os controles de Main.qml")
            waitFor(function() { return apply.enabled === true }, 3000,
                      "com layout selecionado e ID, nome, autor e licença preenchidos, "
                      + "'Publicar cena' tem de estar habilitado")
            verify(inFrame(cancel) && inFrame(apply),
                   "as ações precisam estar dentro da moldura do diálogo: cancel="
                   + describeRect(rectIn(cancel, dialog.background)) + " apply="
                   + describeRect(rectIn(apply, dialog.background)))
            // Conteúdo que cabe: a banda é a moldura e as ações têm de estar nela
            // SEM que o teste role nada. Cobrar ScrollView aqui seria opinião sobre
            // widget, não contrato de alcance.
            verify(inBand(cancel), "Cancelar fora da banda visível com conteúdo que cabe")
            verify(inBand(apply),
                   "Publicar cena fora da banda visível com conteúdo que cabe (viewport "
                   + "compacto): " + describeRect(rectIn(apply, bandOf(apply)))
                   + " da banda " + Math.round(bandOf(apply).height)
                   + " px — com conteúdo que não cabe a alternativa válida é corpo "
                   + "rolável, não deixar a ação cortada")
            assertNoCut("compacto normal")
            console.log("MEDIDA compacto normal rolagem="
                        + (scrollOf(apply) ? "sim" : "não") + " apply="
                        + describeRect(rectIn(apply, bandOf(apply))))
            closeIfOpen()
        }

        function test_03_teclas_reais_de_dp_pad_percorrem_o_dialogo_com_foco_visivel() {
            useViewport(949, 593)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillCredits()
            settleLayout("compacto navegação")

            const source = buttonNamed("themeImportRetrofeSource")
            const apply = panel.retrofeImportApplyControl
            source.forceActiveFocus(Qt.TabFocusReason)
            waitFor(function() { return shell.activeFocusItem === source }, 3000,
                      "o campo de origem não aceitou o foco para iniciar a navegação")
            const down = navigateWithRealKeys(apply, true, 24, "compacto descida")
            const up = navigateWithRealKeys(source, false, 24, "compacto subida")
            console.log("MEDIDA navegação compacto pressõesDescida=" + down
                        + " pressõesSubida=" + up)
            closeIfOpen()
        }

        function test_04_tab_e_shift_tab_reais_avancam_retrocedem_e_mantem_foco_a_vista() {
            useViewport(949, 593)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            settleLayout("compacto tabulação")

            const focusables = []
            const nodes = bodyNodes()
            for (let index = 0; index < nodes.length; index++) {
                const node = nodes[index]
                if (node.activeFocusOnTab === true && node.enabled === true
                        && node.visible === true && focusables.indexOf(node) < 0)
                    focusables.push(node)
            }
            verify(focusables.length >= 6,
                   "o diálogo tem de expor ao menos seis controles navegáveis por Tab "
                   + "(achou " + focusables.length + ")")

            const steps = focusables.length + 1
            for (let index = 0; index < steps; index++) {
                keyClick(Qt.Key_Tab)
                const focused = shell.activeFocusItem
                verify(focused !== null, "Tab real sem foco ativo no passo " + index)
                verify(bodyNodes().indexOf(focused) >= 0,
                       "Tab real saiu do modal no passo " + index + " ("
                       + focused.objectName + ")")
                waitFor(function() { return inBand(focused) }, 1200,
                          "Tab real levou o foco para fora da banda visível no passo "
                          + index + " (" + focused.objectName + ")")
            }
            for (let index = 0; index < steps; index++) {
                keyClick(Qt.Key_Backtab)
                const focused = shell.activeFocusItem
                verify(focused !== null, "Shift+Tab real sem foco ativo no passo " + index)
                verify(bodyNodes().indexOf(focused) >= 0,
                       "Shift+Tab real saiu do modal no passo " + index + " ("
                       + focused.objectName + ")")
                waitFor(function() { return inBand(focused) }, 1200,
                          "Shift+Tab real levou o foco para fora da banda visível no passo "
                          + index + " (" + focused.objectName + ")")
            }
            // A tecla com modificador é o que um teclado físico envia; Backtab é o
            // equivalente X11 já coberto acima. Medido, não assumido.
            keyClick(Qt.Key_Tab, Qt.ShiftModifier)
            const afterShift = shell.activeFocusItem
            verify(afterShift !== null && bodyNodes().indexOf(afterShift) >= 0,
                   "Tab+Shift real precisa manter o foco dentro do modal")
            waitFor(function() { return inBand(afterShift) }, 1200,
                      "Tab+Shift real deixou o foco fora da banda visível")
            closeIfOpen()
        }

        function test_05_setas_nao_roubam_a_navegacao_de_dentro_do_campo() {
            useViewport(949, 593)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillCredits()
            settleLayout("compacto edição")

            const license = buttonNamed("themeImportRetrofeLicense")
            license.forceActiveFocus(Qt.TabFocusReason)
            waitFor(function() { return shell.activeFocusItem === license }, 3000,
                      "o campo de licença não recebeu foco")
            license.cursorPosition = license.text.length
            const caretBefore = license.cursorPosition
            const textBefore = license.text
            keyClick(Qt.Key_Left)
            waitFor(function() { return license.cursorPosition === caretBefore - 1 }, 2000,
                      "Left real não moveu o cursor dentro do campo — a seta não chegou "
                      + "ao texto")
            verify(shell.activeFocusItem === license,
                   "Left real tirou o foco do campo: seta lateral não pode roubar a "
                   + "edição de texto")
            const caretAfterLeft = license.cursorPosition
            keyClick(Qt.Key_Backspace)
            waitFor(function() { return license.text.length === textBefore.length - 1 },
                      2000, "Backspace real não apagou dentro do campo")
            verify(license.text === textBefore.slice(0, caretAfterLeft - 1)
                            + textBefore.slice(caretAfterLeft),
                   "o apagamento não aconteceu na posição do cursor que Left real marcou")
            console.log("MEDIDA edição caret=" + caretBefore + "->" + license.cursorPosition
                        + " texto=" + textBefore.length + "->" + license.text.length)
            // E o D-pad continua navegando a partir do campo.
            const focusedBefore = shell.activeFocusItem
            keyClick(Qt.Key_Down)
            waitFor(function() { return shell.activeFocusItem !== focusedBefore }, 2000,
                      "Down real não navegou a partir de um campo focado")
            fillCredits()
            closeIfOpen()
        }

        function test_06_relatorio_extenso_deixa_acoes_alcancaveis_e_texto_integro() {
            useViewport(949, 593)
            harness.applyFailsWithLongReport = true
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillCredits()
            settleLayout("compacto extenso antes do erro")

            const apply = panel.retrofeImportApplyControl
            mouseClick(apply, apply.width / 2, apply.height / 2, Qt.LeftButton)
            waitFor(function() { return panel.retrofeImportNotice.length > 900 }, 4000,
                      "o relatório longo do caminho real de erro não chegou ao aviso")
            settleLayout("compacto extenso")

            const notice = buttonNamed("themeImportRetrofeNotice")
            const band = bandOf(apply)
            // V: o cenário tem de ser extenso de verdade, senão a prova de
            // rolagem fica vacua — e honestidade exige dizer qual banda medimos.
            verify(notice.implicitHeight > 200,
                   "o aviso precisa crescer para o cenário ser determinístico de "
                   + "conteúdo extenso (implicitHeight=" + Math.round(notice.implicitHeight)
                   + ")")
            const contentPastTheBand = !inBand(notice) || band.height < notice.height + 200
            verify(contentPastTheBand,
                   "com o relatório longo o conteúdo tem de passar da banda visível; "
                   + "se couber, este cenário não exercita rolagem e precisa ser "
                   + "reformulado (banda=" + Math.round(band.height) + " px)")
            verify(inBand(apply) || scrollOf(apply) !== null,
                   "com conteúdo extenso 'Publicar cena' ou fica na banda visível (ação "
                   + "fixa) ou está dentro de corpo rolável (ação alcançável); ficou em "
                   + describeRect(rectIn(apply, bandOf(apply))) + " sem rolagem")
            assertNoCut("compacto extenso")
            // Alcance por input real: descer com o D-pad até o primary.
            const source = buttonNamed("themeImportRetrofeSource")
            source.forceActiveFocus(Qt.TabFocusReason)
            waitFor(function() { return shell.activeFocusItem === source }, 3000,
                      "o campo de origem não recebeu foco")
            const presses = navigateWithRealKeys(apply, true, 24, "compacto extenso")
            console.log("MEDIDA extenso compacto banda=" + Math.round(band.height)
                        + " avisoImplicito=" + Math.round(notice.implicitHeight)
                        + " pressõesAtéPrimary=" + presses
                        + " applyBanda=" + describeRect(rectIn(apply, bandOf(apply))))
            harness.applyFailsWithLongReport = false
            closeIfOpen()
        }

        function test_07_no_viewport_largo_acoes_continuam_alcancaveis_sem_corte() {
            useViewport(1280, 800)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillCredits()
            settleLayout("largo normal")

            const apply = panel.retrofeImportApplyControl
            const cancel = buttonNamed("themeImportRetrofeCancel")
            verify(inBand(cancel) && inBand(apply),
                   "no viewport largo as ações têm de estar na banda visível sem o teste "
                   + "rolar nada (apply=" + describeRect(rectIn(apply, bandOf(apply)))
                   + " da banda " + Math.round(bandOf(apply).height) + " px)")
            assertNoCut("largo normal")

            harness.applyFailsWithLongReport = true
            mouseClick(apply, apply.width / 2, apply.height / 2, Qt.LeftButton)
            waitFor(function() { return panel.retrofeImportNotice.length > 900 }, 4000,
                      "o relatório longo não chegou ao aviso no viewport largo")
            settleLayout("largo extenso")
            const band = bandOf(apply)
            verify(inBand(apply) || scrollOf(apply) !== null,
                   "no viewport largo com conteúdo extenso o primary tem de estar fixo "
                   + "na banda ou dentro de corpo rolável")
            assertNoCut("largo extenso")
            const source = buttonNamed("themeImportRetrofeSource")
            source.forceActiveFocus(Qt.TabFocusReason)
            const presses = navigateWithRealKeys(apply, true, 24, "largo extenso")
            console.log("MEDIDA extenso largo banda=" + Math.round(band.height)
                        + " pressõesAtéPrimary=" + presses)
            harness.applyFailsWithLongReport = false
            closeIfOpen()
        }

        function test_08_primary_permanece_bloqueado_sem_conteudo_e_escape_fecha() {
            useViewport(949, 593)
            openThroughTheRealButton()
            const apply = panel.retrofeImportApplyControl
            verify(apply.enabled === false,
                   "sem layout examinado e sem créditos o primary tem de continuar "
                   + "bloqueado — a correção não pode trocar alcance por publicar às cegas")
            mouseClick(apply, apply.width / 2, apply.height / 2, Qt.LeftButton)
            verify(harness.publishedCalls === 0,
                   "um clique no primary bloqueado não pode publicar nada")
            keyClick(Qt.Key_Escape)
            waitFor(function() { return dialog.visible === false }, 3000,
                      "Escape real não fechou o diálogo, que continua com closePolicy "
                      + "permissiva")
            waitFor(function() { return panel.retrofeImportNotice === ""
                                            && panel.retrofeImportLayouts.length === 0 },
                      3000, "fechar o diálogo não resetou o estado")
        }

        function test_09_cancelar_pelo_clique_real_fecha_e_nao_publica() {
            useViewport(949, 593)
            const before = harness.publishedCalls
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillCredits()
            settleLayout("cancelar")
            const cancel = buttonNamed("themeImportRetrofeCancel")
            mouseClick(cancel, cancel.width / 2, cancel.height / 2, Qt.LeftButton)
            waitFor(function() { return dialog.visible === false }, 3000,
                      "Cancelar real não fechou o diálogo")
            verify(harness.publishedCalls === before,
                   "Cancelar não pode publicar a cena")
        }

        function test_10_publicar_pelo_clique_real_envia_payload_e_nao_ativa() {
            useViewport(949, 593)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillCredits()
            settleLayout("publicar")
            const apply = panel.retrofeImportApplyControl
            const before = harness.publishedCalls
            mouseClick(apply, apply.width / 2, apply.height / 2, Qt.LeftButton)
            waitFor(function() { return harness.publishedCalls === before + 1 }, 4000,
                      "o clique real no primary não disparou a ação de publicar")
            const payload = harness.publishedPayload
            verify(payload !== null && payload.sceneId === "org.exemplo.retrofe"
                    && payload.license === "CC0-1.0" && payload.source === "/fixture/retrofe/cena",
                   "o payload publicado não reflete o que foi examinado e preenchido: "
                   + JSON.stringify(payload))
            verify(payload.overwrite === false,
                   "substituir uma cena existente tem de continuar explícito")
            waitFor(function() { return panel.retrofeImportNotice.indexOf("não foi ativada") >= 0 },
                      4000, "a confirmação precisa dizer que a cena não foi ativada")
            console.log("MEDIDA publicar viewport=949x593 sceneId=" + payload.sceneId)
            closeIfOpen()
        }

        function test_11_estado_de_teste_nao_vaza_para_o_proximo_cenario() {
            useViewport(1280, 800)
            dialog = panel.retrofeImportDialogControl
            verify(dialog.visible === false,
                   "nenhum teste pode deixar o modal aberto para o próximo")
            verify(panel.retrofeImportNotice === "" && panel.retrofeImportLayoutIndex === -1,
                   "o estado do importador precisa estar limpo antes do próximo cenário")
        }
    }
}
