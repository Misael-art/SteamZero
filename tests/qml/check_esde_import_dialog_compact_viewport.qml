// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// UX-07 + UX-05 — o diálogo "Importar tema ES-DE" sob viewport compacto.
//
// Terceira fatia de RC-01. O contrato medido aqui é o MESMO da fatia RetroFE, e é
// ele que torna a prova comparável — conteúdo e ações alcançáveis, com foco visível
// e sem corte, medidos com teclado real:
//   I.   nenhum controle de texto sai da moldura do diálogo sem um mecanismo de
//        rolagem que leve até ele (o que sai sem rolagem é corte, não layout);
//   II.  as ações (Cancelar / Importar como editável) estão na banda visível sem
//        que o teste mexa em `contentY`; quando o conteúdo passa da banda, chegar
//        até elas é feito com TECLA REAL de D-pad, e cada destino focado precisa
//        estar inteiro na banda — é isso que torna a rolagem load-bearing;
//   III. nenhum controle é espremido abaixo da própria altura implícita;
//   IV.  nada produz overflow horizontal;
//   V.   os dois cenários: conteúdo que CABE (aí não se cobra ScrollView — cobrar
//        rolagem onde não há conteúdo excedente seria opinião sobre widget) e
//        conteúdo EXTENSO produzido pelo caminho real de erro do `Importar` (o
//        relatório vai inteiro para `esdeImportNotice`, um Label com WordWrap sem
//        limite de linhas). Viewports 949×593 e 1280×800.
//
// Por que este diálogo e não outro: `git show 7fe9e8b2` mostra que a correção da
// fatia anterior alcança só o modal RetroFE. O ES-DE do ThemeEditorPanel continua
// com `contentItem: ColumnLayout` sem corpo rolável, com as ações dentro do corpo e
// com um `ScrollView` ANINHADO para a lista de esquemas — exatamente a forma que
// produziu o vermelho medido na fatia anterior (24 pressões de Down sem sair do
// primeiro RadioButton). A classe de defeito é a mesma; o que muda é o conteúdo.
//
// Fatos medidos no Qt 6.11.2 do projeto ANTES deste arquivo (ver os logs 09 e 10 da
// pasta de evidência da fatia anterior; os probes não vivem no checkout) — são o
// motivo da forma do código:
//   • `qmltestrunner` hospeda a raiz em QQuickView, que REJEITA raiz Window
//     ("QQuickView: invalid root object"); daí `Item { ApplicationWindow {} }`;
//   • neste runtime `Item.childItems` é `undefined` e `children` funciona — a
//     varredura abaixo une as duas listas em vez de escolher uma;
//   • um Popup não é Item: não expõe `children`, `childItems` nem `window`; a
//     varredura parte de `dialog.contentItem` (e do `dialog.footer`, quando houver).
//     `dialog.background` É um Item que cobre a moldura inteira — medido — e serve
//     de oráculo do quadro sem afirmar nada sobre Popup ser Item;
//   • o oráculo de foco é `shell.activeFocusItem`, não `item.activeFocus`;
//   • o `TestCase` deste runtime NÃO expõe `keyClicks`: as teclas reais exercitam
//     navegação e edição (Tab/Shift+Tab/Up/Down/Left/Backspace/Escape) e o conteúdo
//     entra pelas propriedades do painel — que é exatamente o que a digitação
//     produziria via `onTextChanged`;
//   • `Dialog.footer` não é descendente do corpo rolável, e um `ScrollView` aninhado
//     prende as setas no seu primeiro foco: por isso a descida esperada aqui é a
//     travessia dos ESQUEMAS (que têm de continuar navegáveis) e não um número fixo.
//
// Chamar `moveFocus()` diretamente seria teste complementar, não prova de input:
// nenhuma asserção abaixo depende de chamada de volta.

import QtQuick
import QtQuick.Controls
import QtQuick.Window
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 1280
    height: 800

    // Alavanca determinística do cenário extenso: o erro do apply real vai inteira
    // para `esdeImportNotice`. Nada aqui infla geometria por fora do produto.
    property bool applyFailsWithLongReport: false
    property var importedPayload: null
    property int importedCalls: 0
    property int inspectCalls: 0
    readonly property string longReport:
        "Falha ao converter o tema ES-DE: esquemas com paleta fora do espaço de cor, "
        + "arquivos de referência ausentes, tema-monocromático sem derivação possível "
        + "e um caminho recusado por estar fora da raiz permitida. "
    /// 24 esquemas é o que um tema ES-DE grande publica de fato (arquivos `*.xml`
    /// de esquema por resolução/variantes). É o conteúdo que faz a lista estourar.
    readonly property var manySchemes: {
        const out = []
        for (let index = 0; index < 24; index++)
            out.push({"scheme": "esquema-" + index,
                      "isMonochrome": index % 3 === 0})
        return out
    }

    function request(method, path, _payload, callback, _errorCallback) {
        if (method === "GET" && path === "/theme/list")
            callback({"themes": []})
    }

    function requestAction(actionId, payload, callback, errorCallback) {
        if (actionId === "theme.import.esde.inspect") {
            inspectCalls += 1
            callback({"schemes": harness.extensiveContent ? manySchemes
                                                         : [{"scheme": "principal",
                                                             "isMonochrome": false}]})
            return
        }
        if (actionId === "theme.import.esde.apply") {
            if (applyFailsWithLongReport) {
                errorCallback(longReport.repeat(24), {})
                return
            }
            importedCalls += 1
            importedPayload = payload
            callback({"themeId": payload.name})
        }
    }

    // O cenário extenso é escolhido antes de abrir o diálogo, porque é o que o
    // botão "Examinar" devolve — não um estado injetado depois do layout.
    property bool extensiveContent: false

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
        name: "EsdeImportDialogViewport"
        when: windowShown

        property var dialog: null

        /// Cada cenário começa e termina com o modal fechado e o importador limpo.
        /// Sem isto uma reprovação deixa o diálogo aberto e as falhas seguintes
        /// viram cascata — foi o que a primeira execução do harness RetroFE mediu.
        function resetSurface() {
            harness.applyFailsWithLongReport = false
            harness.importedPayload = null
            harness.extensiveContent = false
            dialog = panel.esdeImportDialogControl
            if (dialog && dialog.visible) {
                dialog.close()
                waitFor(function() { return dialog.visible === false }, 3000,
                        "limpeza: o diálogo não fechou")
            }
            waitFor(function() { return panel.esdeImportSchemes.length === 0
                                            && panel.esdeImportNotice === "" }, 3000,
                    "limpeza: o estado do importador não voltou ao neutro")
        }

        function init() {
            resetSurface()
        }

        function cleanup() {
            resetSurface()
        }

        // ---------------------------------------------------------------- árvores

        /// Une `children` e `childItems`: medido que `childItems` é undefined neste
        /// runtime, e o precedente do repositório (check_dialog_keys.qml) testa os
        /// dois.
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

        /// Assinatura de geometria do estado atual; "" enquanto o layout não
        /// materializou os controles, para a espera ser por observable.
        function signature() {
            if (!dialog || !dialog.visible || !dialog.background)
                return ""
            const apply = panel.esdeImportApplyControl
            if (!apply || apply.width <= 0 || apply.height <= 0)
                return ""
            const notice = byObjectName("themeImportEsdeNotice")
            const frame = dialog.background
            return Math.round(frame.width) + "x" + Math.round(frame.height)
                    + "|apply=" + describeRect(rectIn(apply, frame))
                    + "|notice=" + (notice ? Math.round(notice.implicitHeight) + "/"
                                                  + Math.round(notice.height) : "sem")
                    + "|body=" + (dialog.contentItem
                                  ? Math.round(dialog.contentItem.height) + "/"
                                    + Math.round(dialog.contentItem.implicitHeight) : "sem")
        }

        /// Espera por observable com orçamento e falha explícita (medido:
        /// `tryVerify` com closure não repete a amostragem neste runtime).
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
                    if (nodes[index].objectName === "themeImportEsdeButton")
                        found = nodes[index]
                return found !== null
            }, 3000, "a área de importação não expôs o botão real do ES-DE")
            return found
        }

        function openThroughTheRealButton() {
            dialog = panel.esdeImportDialogControl
            verify(dialog !== undefined && dialog !== null,
                   "o painel precisa expor o diálogo como superfície de teste, como já "
                   + "expõe o modal RetroFE e os modais de Main.qml")
            const trigger = triggerButton()
            mouseClick(trigger, trigger.width / 2, trigger.height / 2, Qt.LeftButton)
            waitFor(function() { return dialog.visible === true }, 3000,
                      "o clique real no botão da área não abriu o diálogo")
            settleLayout("aberto")
            verify(dialog.modal === true,
                   "o diálogo precisa continuar modal — fechar modal por conveniência de "
                   + "teste mudaria o comportamento")
        }

        /// "Examinar" pelo clique real, com a origem escrita no próprio campo.
        function inspectThroughTheRealButton() {
            panel.esdeImportSource = "/fixture/esde/tema"
            const inspect = buttonNamed("themeImportEsdeInspect")
            const before = harness.inspectCalls
            mouseClick(inspect, inspect.width / 2, inspect.height / 2, Qt.LeftButton)
            waitFor(function() { return harness.inspectCalls === before + 1 }, 3000,
                      "o clique real em Examinar não disparou a ação publicada")
            const esperado = harness.extensiveContent ? 24 : 1
            waitFor(function() { return panel.esdeImportSchemes.length === esperado }, 3000,
                      "o examine não publicou os " + esperado + " esquemas no diálogo")
            settleLayout("examinado")
        }

        function fillName() {
            panel.esdeImportName = "Tema ES-DE de teste"
        }

        function closeIfOpen() {
            resetSurface()
        }

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
                console.log("PASSO " + presses + " tag=" + tag
                            + " foco=" + (focused.objectName || focused.toString())
                            + " em " + describeRect(rectIn(focused, bandOf(focused)))
                            + " banda=" + Math.round(bandOf(focused).height))
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
            const source = buttonNamed("themeImportEsdeSource")
            verify(source !== null, "o campo de origem precisa existir no diálogo")
            waitFor(function() {
                return shell.activeFocusItem !== null
                        && shell.activeFocusItem.objectName === "themeImportEsdeSource"
            }, 3000, "abrir o modal sem levar o foco deixa quem navega por teclado ou "
                     + "controle do lado de fora")
            console.log("MEDIDA aberto viewport=949x593 banda="
                        + Math.round(bandOf(source).height) + " apply="
                        + describeRect(rectIn(panel.esdeImportApplyControl,
                                               dialog.background)))
            closeIfOpen()
        }

        function test_02_conteudo_que_cabe_mantem_acoes_na_moldura_e_na_banda() {
            useViewport(949, 593)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillName()
            settleLayout("compacto normal")

            const cancel = buttonNamed("themeImportEsdeCancel")
            const apply = panel.esdeImportApplyControl
            verify(apply !== undefined && apply !== null,
                   "o primary precisa de alias de teste, como o do modal RetroFE")
            waitFor(function() { return apply.enabled === true }, 3000,
                      "com esquema escolhido e nome informado, 'Importar como editável' "
                      + "tem de estar habilitado")
            verify(inFrame(cancel) && inFrame(apply),
                   "as ações precisam estar dentro da moldura do diálogo: cancel="
                   + describeRect(rectIn(cancel, dialog.background)) + " apply="
                   + describeRect(rectIn(apply, dialog.background)))
            verify(inBand(cancel), "Cancelar fora da banda visível com conteúdo que cabe")
            verify(inBand(apply),
                   "Importar fora da banda visível com conteúdo que cabe (viewport "
                   + "compacto): " + describeRect(rectIn(apply, bandOf(apply)))
                   + " da banda " + Math.round(bandOf(apply).height) + " px")
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
            fillName()
            settleLayout("compacto navegação")

            const source = buttonNamed("themeImportEsdeSource")
            const apply = panel.esdeImportApplyControl
            source.forceActiveFocus(Qt.TabFocusReason)
            waitFor(function() { return shell.activeFocusItem === source }, 3000,
                      "o campo de origem não aceitou o foco para iniciar a navegação")
            const down = navigateWithRealKeys(apply, true, 24, "compacto descida")
            const up = navigateWithRealKeys(source, false, 24, "compacto subida")
            console.log("MEDIDA navegação compacto pressõesDescida=" + down
                        + " pressõesSubida=" + up)
            closeIfOpen()
        }

        function test_04_tab_e_shift_tab_reais_avancam_e_retrocedem_sem_sair_do_modal() {
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
            verify(focusables.length >= 5,
                   "o diálogo tem de expor ao menos cinco controles navegáveis por Tab "
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
            // O campo de nome só aparece com esquema publicado; o cenário aqui é o de
            // digitação, então o esquema entra pelo caminho real do Examinar.
            inspectThroughTheRealButton()
            settleLayout("edição no campo")

            const source = buttonNamed("themeImportEsdeSource")
            source.forceActiveFocus(Qt.OtherFocusReason)
            waitFor(function() { return shell.activeFocusItem === source }, 3000,
                      "o campo de origem não tomou o foco")
            // O conteúdo entra pela propriedade do painel (o runtime não expõe
            // keyClicks) e é exatamente o que a digitação produziria via
            // onTextChanged; depois as teclas reais editam esse texto.
            panel.esdeImportSource = "/fixture/esde/tema"
            waitFor(function() { return source.text === "/fixture/esde/tema" }, 3000,
                      "o texto não chegou ao campo de origem")
            const antes = source.text.length
            keyClick(Qt.Key_Right)
            keyClick(Qt.Key_Left)
            keyClick(Qt.Key_Backspace)
            const depois = source.text.length
            console.log("MEDIDA edicao dentro do campo antes=" + antes + " depois=" + depois)
            verify(depois > 0 && depois === antes - 1,
                   "Backspace real tem de editar o campo (apagar um caractere), não "
                   + "atravessar o diálogo: " + antes + " -> " + depois)
            verify(panel.esdeImportSource === source.text,
                   "a edição real tem de voltar ao estado do painel pelo mesmo canal da "
                   + "digitação: painel='" + panel.esdeImportSource + "' campo='"
                   + source.text + "'")
            const focoAntes = shell.activeFocusItem
            keyClick(Qt.Key_Down)
            verify(shell.activeFocusItem !== focoAntes,
                   "Down real precisa tirar o foco do campo e navegar o diálogo, não "
                   + "ser engolido pela edição")
            closeIfOpen()
        }

        function test_06_relatorio_extenso_deixa_importar_alcancavel_por_tecla_real() {
            useViewport(949, 593)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillName()
            settleLayout("antes do erro")

            const apply = panel.esdeImportApplyControl
            const source = buttonNamed("themeImportEsdeSource")
            harness.applyFailsWithLongReport = true
            mouseClick(apply, apply.width / 2, apply.height / 2, Qt.LeftButton)
            waitFor(function() { return panel.esdeImportNotice.length > 200 }, 3000,
                      "o clique real em Importar com apply em falha não publicou o "
                      + "relatório extenso no diálogo")
            settleLayout("relatorio extenso")

            const notice = buttonNamed("themeImportEsdeNotice")
            const band = bandOf(apply)
            verify(notice !== null && notice.implicitHeight > dialog.background.height / 2,
                   "o cenário extenso precisa produzir conteúdo que passa da banda — "
                   + "sem isso o teste abaixo seria vazio (notice="
                   + (notice ? Math.round(notice.implicitHeight) : "ausente")
                   + " de uma moldura de "
                   + Math.round(dialog.background.height) + " px)")
            verify(!inBand(notice) || band.height < notice.height + 200,
                   "com o relatório longo o corpo tem de passar da banda visível; se "
                   + "couber, este cenário não exercita rolagem e precisa ser "
                   + "reformulado (banda=" + Math.round(band.height) + " px, aviso="
                   + Math.round(notice.height) + " px)")
            assertNoCut("relatorio extenso")

            // Alcance por input real: o clique acima deixou o foco NO primary, então
            // descrever 0 pressões não provaria nada. O ponto de partida é o campo
            // de origem, de novo, e a descida é toda por tecla real.
            source.forceActiveFocus(Qt.TabFocusReason)
            waitFor(function() { return shell.activeFocusItem === source }, 3000,
                      "o campo de origem não recebeu o foco para a descida")
            const presses = navigateWithRealKeys(apply, true, 40, "extenso descida")
            verify(presses >= 1,
                   "chegar ao primary partindo do campo de origem exige ao menos uma "
                   + "tecla real; 0 pressões significa que o clique anterior deixou o "
                   + "foco no alvo e a prova seria vacua")
            // ... e voltar ao campo de origem, também com tecla real.
            navigateWithRealKeys(source, false, 40, "extenso subida")
            console.log("MEDIDA extenso banda=" + Math.round(band.height)
                        + " avisoImplicito=" + Math.round(notice.implicitHeight)
                        + " pressoesAtePrimary=" + presses
                        + " applyBanda=" + describeRect(rectIn(apply, bandOf(apply))))
            closeIfOpen()
        }

        function test_07_o_listagem_extensa_de_esquemas_continua_navegavel() {
            useViewport(949, 593)
            harness.extensiveContent = true
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillName()
            settleLayout("24 esquemas")

            const radios = []
            const nodes = bodyNodes()
            for (let index = 0; index < nodes.length; index++) {
                const node = nodes[index]
                // O RadioButton e o Text interno do seu contentItem carregam o mesmo
                // `text`: sem distinguir o controle, a varredura conta 48 para 24
                // esquemas (medido). `checkable` só existe no controle.
                if (node.checkable === true && node.text !== undefined
                        && String(node.text).startsWith("esquema-")
                        && effectivelyVisible(node))
                    radios.push(node)
            }
            verify(radios.length === 24,
                   "os 24 esquemas publicados pelo examine têm de estar na árvore do "
                   + "diálogo (achou " + radios.length + ")")
            assertNoCut("24 esquemas")

            // O D-pad tem de atravessar os esquemas: na forma antiga, um ScrollView
            // aninhado prendia o foco no primeiro RadioButton (medido: 24 pressões
            // sem progresso no modal RetroFE).
            const source = buttonNamed("themeImportEsdeSource")
            source.forceActiveFocus(Qt.TabFocusReason)
            waitFor(function() { return shell.activeFocusItem === source }, 3000,
                      "o foco não voltou ao campo de origem")
            let passos = 0
            let visitados = 0
            const vistos = []
            while (passos < 40 && visitados < 6) {
                passos += 1
                keyClick(Qt.Key_Down)
                const focused = shell.activeFocusItem
                verify(focused !== null && bodyNodes().indexOf(focused) >= 0,
                       "o passo " + passos + " saiu do diálogo ("
                       + (focused ? focused.objectName : "sem foco") + ")")
                if (vistos.indexOf(focused) < 0)
                    vistos.push(focused)
                visitados = vistos.length
                waitFor(function() { return inBand(focused) }, 1200,
                          "no passo " + passos + " o esquema focado ("
                          + focused.text + ") não está inteiro na banda visível: "
                          + describeRect(rectIn(focused, bandOf(focused)))
                          + " da banda " + Math.round(bandOf(focused).height) + " px")
            }
            verify(visitados >= 6,
                   "a descida por D-pad real tem de percorrer os esquemas, não empacar "
                   + "no primeiro (visitas distintas: " + visitados + " em " + passos
                   + " pressões)")
            console.log("MEDIDA esquemas pressoes=" + passos + " visitasDistintas=" + visitados)
            closeIfOpen()
        }

        function test_08_escape_e_cancelar_fecham_e_o_payload_nao_ativa_nada() {
            useViewport(949, 593)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillName()
            settleLayout("fechamento")

            keyClick(Qt.Key_Escape)
            waitFor(function() { return dialog.visible === false }, 3000,
                      "Escape real não fechou o diálogo")
            waitFor(function() { return panel.esdeImportSchemes.length === 0
                                            && panel.esdeImportNotice === "" }, 3000,
                      "fechar por Escape deixou estado do importador para trás")

            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillName()
            settleLayout("cancelar")
            const cancel = buttonNamed("themeImportEsdeCancel")
            mouseClick(cancel, cancel.width / 2, cancel.height / 2, Qt.LeftButton)
            waitFor(function() { return dialog.visible === false }, 3000,
                      "o clique real em Cancelar não fechou o diálogo")
            verify(harness.importedCalls === 0,
                   "Cancelar não pode importar nada (chamadas: " + harness.importedCalls + ")")

            // E o apply real publica payload sem ativar o tema.
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillName()
            settleLayout("apply")
            const apply = panel.esdeImportApplyControl
            mouseClick(apply, apply.width / 2, apply.height / 2, Qt.LeftButton)
            waitFor(function() { return harness.importedCalls === 1 }, 3000,
                      "o clique real em Importar não publicou a ação")
            const payload = harness.importedPayload
            verify(payload && payload.name === "Tema ES-DE de teste"
                        && payload.scheme === "principal"
                        && payload.source === "/fixture/esde/tema",
                   "o payload publicado tem de trazer o esquema e o nome escolhidos: "
                   + JSON.stringify(payload))
            closeIfOpen()
        }

        function test_09_viewport_largo_mostra_o_relatorio_inteiro() {
            useViewport(1280, 800)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillName()
            const apply = panel.esdeImportApplyControl
            const source = buttonNamed("themeImportEsdeSource")
            harness.applyFailsWithLongReport = true
            source.forceActiveFocus(Qt.TabFocusReason)
            mouseClick(apply, apply.width / 2, apply.height / 2, Qt.LeftButton)
            waitFor(function() { return panel.esdeImportNotice.length > 200 }, 3000,
                      "sem o relatório extenso o cenário largo não mede nada")
            settleLayout("largo relatorio extenso")
            assertNoCut("largo relatorio extenso")
            verify(inFrame(apply),
                   "no viewport largo as ações não podem sair da moldura: apply="
                   + describeRect(rectIn(apply, dialog.background)))
            console.log("MEDIDA largo moldura="
                        + Math.round(dialog.background.width) + "x"
                        + Math.round(dialog.background.height) + " apply="
                        + describeRect(rectIn(apply, bandOf(apply))))
            closeIfOpen()
        }

        function test_10_as_acoes_tem_alvo_de_toque_minimo_48_px() {
            useViewport(949, 593)
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillName()
            settleLayout("alvos")
            const cancel = buttonNamed("themeImportEsdeCancel")
            const apply = panel.esdeImportApplyControl
            verify(cancel.height >= 48 && apply.height >= 48,
                   "UX-05: os alvos de ação precisam de 48 px de altura no shell — "
                   + "cancel=" + Math.round(cancel.height) + " apply="
                   + Math.round(apply.height) + " (medido aqui; a certificação dos 48 px "
                   + "no shell inteiro é o próximo recorte desta frente)")
            closeIfOpen()
        }

        function test_11_escala_de_texto_nao_corta_a_moldura() {
            useViewport(949, 593)
            panel.visualScale = 1.5
            openThroughTheRealButton()
            inspectThroughTheRealButton()
            fillName()
            settleLayout("escala 1.5")
            const apply = panel.esdeImportApplyControl
            verify(inFrame(apply),
                   "com escala de texto 1.5 as ações não podem sair da moldura: apply="
                   + describeRect(rectIn(apply, dialog.background)))
            assertNoCut("escala 1.5")
            panel.visualScale = 1.0
            closeIfOpen()
        }
    }
}
