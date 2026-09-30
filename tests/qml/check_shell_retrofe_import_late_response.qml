// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// RC-01 (UX-05/UX-07, corte RetroFE na shell) — a resposta TARDIA do importador.
//
// O que aqui se prova é o que as três fatias anteriores não alcançaram: o diálogo
// "Importar cena RetroFE" exercitado DENTRO DO SHELL (seção Temas, aba "Editar
// aparência", `themeEditorTab` e `themeEditorPanel`), pela rota real, com o
// importador respondendo DEPOIS de a superfície ter mudado.
//
// Por que o shell e não o painel: as provas anteriores de RetroFE (`check_retrofe
// _import_dialog_compact_viewport.qml`, `check_theme_editor_import.qml`) injetam
// `requestAction` no painel e chamam as callbacks SINCRONICAMENTE dentro do stub.
// Sincronia não exercita atraso: no painel stubado a resposta chega antes de
// qualquer mudança de superfície, e por construção não pode ser tardia. Aqui o
// importador é um servidor HTTP real em loopback que dorme ANTES de responder, e o
// cliente é o `XMLHttpRequest` do produto (o `request()` de `Main.qml`, `xhr.timeout`).
//
// O contrato, uma frase por cena (o número da cena é o número do teste):
//   1. a rota real do shell anda: aba → botão → examinar → publicar, e publica sem
//      ativar (`theme_import_retrofe.apply` devolve `activated: false`,
//      `theme_import_retrofe.py:340`) — sem
//      esta as três seguintes provariam apenas que um atraso chegou;
//   2. fechar o diálogo com um pedido em voo não pode reabrir estado: a resposta que
//      chega depois do `onClosed` (`retrofeImportDialog.onClosed`) encontra layouts,
//      aviso e bandeira de ocupado vazios e assim os deixa;
//   3. um pedido mais novo não pode perder para o anterior: examinaram-se origens
//      diferentes, os dois estão em voo juntos (o `requestAction` só deduplica payload
//      IDÊNTICO) e o que responde por último não é o que o usuário pediu por último;
//   4. publicar com resposta tardia não pode anunciar sucesso nem re-listar temas
//      depois de a superfície ter fechado;
//   5. reabrir mostra o ESTADO, não o último texto editado — eixo distinto, com outra
//      raiz (a binding `text:`/`onTextChanged:` de `themeImportRetrofeSource` se
//      interrompe na primeira edição), declarado separado para não ser confundido com atraso;
//   6. a segunda porta de entrada do mesmo vínculo: quem escreve no ESTADO com o
//      diálogo aberto (`retrofeImportFolderDialog`, `retrofeImportFileDialog`) tem
//      de alcançar o campo.
//      Cena própria porque a `test_05` morre na primeira asserção e `verify()` do
//      QtTest interrompe a função — somada à 05 ela seria verde sem nunca ter medido.
//   7. Enter no campo de origem examina: é a porta que as cenas 08 e 09 usam para
//      recusar um clique, e sem ela o caminho DIGITADO nunca viraria pedido (num
//      `offscreen` o seletor nativo não tem árvore QML dirigível — medida, não
//      narrada);
//   8. o MESMO clique recusado, agora com o pedido em voo ainda CORRENTE: a recusa tem
//      de devolver a bandeira armada que estava antes do clique, senão "Publicar cena"
//      habilita sobre um importador que ainda não respondeu;
//   9. o clique RECUSADO por payload idêntico (`requestAction`), com o único pedido em
//      voo já REVOCADO pelo fechamento: a superfície acaba ociosa e utilizável, porque
//      nada mais vai abaixar a bandeira — é o pino que impede a correção da 08 de
//      resolver os dois casos escrevendo `true` sempre.

//
// O oráculo de "a resposta chegou" é `shell.pendingRequests`, o contador do
// `request()` de `Main.qml` — incrementado no despacho e decrementado no
// `finish()` dentro do próprio `onreadystatechange`. Não há margem fixa depois
// dele: `finish()` decrementa e a
// callback escreve no MESMO turno, então quando o contador lê 0 a escrita já
// aconteceu — se ela existir. Por isso a asserção vem imediatamente após a espera,
// e o vermelho desta fatia é lido ali.
//
// O que NÃO é provado aqui, e por quê: "publicar tarde não re-lista os temas" é um
// efeito invisível na superfície (a lista reescrita é `editorThemeList`, e ela não
// muda com os dados da ponte). A prova é a LOG ORDENADA DA PONTE, lida pelo gate
// Python: nenhum `GET /theme/list` depois do apply daquela origem. O mesmo
// contador, na jornada do test_01, TEM de registrar o re-lista — é a leitura
// contrafactual que impede a asserção de ser satisfeita por ausência de medição.
//
// Fatos de bancada reutilizados das fatias anteriores (não redescobertos):
//   • `qmltestrunner` hospeda a raiz em QQuickView, que REJEITA raiz Window — daí
//     `Item { Main {} }`, como em `check_shell_esde_import_dialog_journey.qml`;
//   • `Item.childItems` é undefined neste runtime: a varredura une `children` e
//     `childItems`;
//   • Popup não é Item: o corpo do diálogo é varrido a partir de
//     `dialog.contentItem` + `dialog.footer`;
//   • o oráculo de foco é `shell.activeFocusItem`;
//   • `keyPress` de letra chega sem `text` neste runtime, então o conteúdo entra
//     pela propriedade do próprio campo — e a navegação/ativação/edição são medidas
//     com tecla real;
//   • revelar pelo foco é o mecanismo do produto (`restoreDialogFocus()` liga
//     `onActiveFocusItemChanged` a `ensureFocusedItemVisible`); o teste ESPERA o
//     efeito, nunca escreve `contentY`.

import QtQuick
import QtQuick.Controls
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 1280
    height: 800

    /// Configuração efêmera escrita pelo teste em `build/`: endereço e token da
    /// ponte, as alavancas de atraso/contagem por origem e o viewport.
    property var cfg: ({})
    property var panel: null
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
        name: "ShellRetrofeImportLateResponse"
        when: windowShown

        // ------------------------------------------------------------------ árvores

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

        function descendants(raiz, out, depth) {
            if (!raiz || depth > 40)
                return out
            const kids = kidsOf(raiz)
            for (let index = 0; index < kids.length; index++) {
                out.push(kids[index])
                descendants(kids[index], out, depth + 1)
            }
            return out
        }

        function findInShell(raiz, test) {
            const nodes = descendants(raiz, [], 0)
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

        /// O corpo do diálogo: Popup não é Item, então a varredura parte do
        /// contentItem e do footer, exatamente como na 4ª fatia.
        function bodyNodes() {
            const out = []
            if (!harness.dialog || !harness.dialog.contentItem)
                return out
            descendants(harness.dialog.contentItem, out, 0)
            if (harness.dialog.footer)
                descendants(harness.dialog.footer, out, 0)
            return out
        }

        function named(nodes, name) {
            for (let index = 0; index < nodes.length; index++)
                if (nodes[index].objectName === name)
                    return nodes[index]
            return null
        }

        // ------------------------------------------------------------- geometria mínima

        function rectIn(item, ancestor) {
            if (!item || !ancestor)
                return null
            const topLeft = item.mapToItem(ancestor, 0, 0)
            const bottomRight = item.mapToItem(ancestor, item.width, item.height)
            return {"left": topLeft.x, "top": topLeft.y,
                    "right": bottomRight.x, "bottom": bottomRight.y}
        }

        /// A banda que clipa — o Flickable interno, não o ScrollView que o embrulha
        /// (medição da 4ª fatia: `ScrollView` nem expõe `contentY`).
        function bandOf(item) {
            let current = item ? item.parent : null
            let steps = 0
            while (current && steps < 40) {
                if (current.contentY !== undefined && current.contentHeight !== undefined
                        && current.height !== undefined && current.height > 0)
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

        // ------------------------------------------------------------------- espera

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

        function describeRect(rect) {
            if (!rect)
                return "sem-rect"
            return "(" + Math.round(rect.left) + "," + Math.round(rect.top)
                    + ")-(" + Math.round(rect.right) + "," + Math.round(rect.bottom) + ")"
        }

        /// Assinatura de geometria do diálogo aberto; "" enquanto os controles não
        /// materializam. Estabilizar por observable, não por intervalo fixo, é a
        /// correção da causa medida na 4ª fatia (o `sleep` virava corrida contra o
        /// layout sob a carga do gate).
        function signature() {
            if (!harness.dialog || !harness.dialog.visible || !harness.dialog.background)
                return ""
            const nodes = bodyNodes()
            const origem = named(nodes, "themeImportRetrofeSource")
            const publicar = named(nodes, "themeImportRetrofeApply")
            if (!origem || origem.width <= 0 || !publicar || publicar.width <= 0)
                return ""
            const moldura = harness.dialog.background
            return Math.round(moldura.width) + "x" + Math.round(moldura.height)
                    + "|origem=" + describeRect(rectIn(origem, moldura))
                    + "|publicar=" + describeRect(rectIn(publicar, moldura))
                    + "|layouts=" + harness.panel.retrofeImportLayouts.length
        }

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
            verify(stable, "o layout do diálogo RetroFE não estabilizou observavelmente em "
                            + budget + " ms ('" + tag + "'); última assinatura: "
                            + (previous === "" ? "controles ainda ausentes" : previous))
            console.log("ESTABILIZOU '" + tag + "' em " + elapsed + " ms :: " + previous)
        }

        // -------------------------------------------------------------- observáveis

        /// Linha de estado no instante pedido. Existe para o log do CI ser
        /// independente da narração: quem audita lê `OBS|...` e reconcile com os
        /// contadores da ponte.
        function observar(tag) {
            const p = harness.panel
            console.log("OBS|" + tag
                        + "|dialogo=" + (harness.dialog && harness.dialog.visible ? "aberto" : "fechado")
                        + "|pendentes=" + shell.pendingRequests
                        + "|ocupado=" + (p.retrofeImportBusy ? 1 : 0)
                        + "|layouts=" + p.retrofeImportLayouts.length
                        + "|indice=" + p.retrofeImportLayoutIndex
                        + "|aviso=" + String(p.retrofeImportNotice).length
                        + "|erro=" + (p.retrofeImportNoticeIsError ? 1 : 0)
                        + "|origem=" + String(p.retrofeImportSource).length)
        }

        // ------------------------------------------------------------------ bancada

        function config() {
            const request = new XMLHttpRequest()
            request.open("GET", Qt.resolvedUrl("../../build/ui-shell-retrofe-import-late.json"), false)
            request.send()
            verify(request.status === 0 || request.status === 200,
                   "a configuração efêmera da bridge não foi lida")
            return JSON.parse(request.responseText)
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

        /// O painel instanciado dentro do shell — procurado pela propriedade, não
        /// por id: `Main.qml` dá `id: themeEditorPanel`, mas id não é
        /// alcançável de fora do arquivo. A propriedade só existe no painel, então
        /// a sonda não pode achar outra coisa.
        function panelDoShell() {
            var found = null
            until(function() {
                found = findInShell(shell.contentItem, function(node) {
                    return node.retrofeImportBusy !== undefined
                        && node.retrofeImportLayouts !== undefined
                })
                return found !== null
            }, 5000, "o painel de edição de tema não apareceu na árvore do shell")
            harness.panel = found
            harness.dialog = found.retrofeImportDialogControl
            verify(harness.dialog !== null,
                   "o painel precisa expor o diálogo como superfície de teste, como já "
                   + "expõe `retrofeImportDialogControl` em `ThemeEditorPanel.qml:53`")
        }

        /// Limpeza controlada, não prova. A ordem é a da 4ª fatia (o
        /// `resetSurface` de `check_shell_esde_import_dialog_journey.qml`): QUIESCER
        /// antes de
        /// fechar — com o contrato atual uma resposta que chega depois do `onClosed`
        /// repõe layouts e aviso, e a cena seguinte nasceria suja por culpa da
        /// ordem do teste, não do produto. Depois de fechar, o neutralizador é
        /// chamado direto: é o mesmo `resetRetrofeImport()` que o `onClosed`
        /// (`retrofeImportDialog.onClosed`) executa, invocado aqui para que o vermelho
        /// apareça nas asserções das cenas e não na limpeza.
        function resetSurface() {
            until(function() { return shell.pendingRequests === 0 }, 12000,
                  "limpeza: sobrou requisição em voo entre cenas")
            if (harness.dialog && harness.dialog.visible) {
                harness.dialog.close()
                until(function() { return harness.dialog.visible === false }, 3000,
                      "limpeza: o diálogo não fechou")
            }
            if (harness.panel && harness.dialog && !harness.dialog.visible)
                harness.panel.resetRetrofeImport()
            until(function() {
                return harness.panel.retrofeImportBusy === false
                    && harness.panel.retrofeImportLayouts.length === 0
                    && harness.panel.retrofeImportNotice === ""
            }, 3000, "limpeza: o estado do importador não voltou ao neutro")
        }

        function init() {
            harness.cfg = config()
            activateWindowAndSize()
            shell.apiUrl = harness.cfg.apiUrl
            shell.apiToken = harness.cfg.apiToken
            shell.refreshStatus("")
            until(function() {
                return shell.uiContracts !== undefined
                    && shell.uiContracts.byId !== undefined
                    && shell.uiContracts.byId["theme.import.retrofe.inspect"] !== undefined
                    && shell.uiContracts.byId["theme.import.retrofe.apply"] !== undefined
            }, 5000, "a ponte real não publicou os contratos do importador RetroFE")
            until(function() {
                return Math.round(shell.visualScale * 100)
                    === Math.round(Number(harness.cfg.escala) * 100)
            }, 3000, "a escala publicada no /status não chegou ao shell (visualScale="
                       + shell.visualScale + ", esperado " + harness.cfg.escala + ")")
            panelDoShell()
            resetSurface()
        }

        function cleanup() {
            resetSurface()
        }

        // ------------------------------------------------------------ rota real

        /// Clique real num controle do shell: revelar pelo FOCO (mecanismo do
        /// produto) e esperar que o alvo caiba na banda que clipa antes de tocar.
        function clicarAlvo(alvo, tag) {
            verify(alvo !== null, tag + ": controle ausente")
            alvo.forceActiveFocus(Qt.TabFocusReason)
            until(function() { return shell.activeFocusItem === alvo }, 3000,
                  tag + ": o controle não aceitou o foco")
            const rolagem = bandOf(alvo)
            if (rolagem !== null) {
                until(function() { return inBand(alvo) }, 4000,
                      tag + ": o foco não revelou o controle dentro da banda que clipa ("
                      + Math.round(rolagem.height) + " px)")
            }
            mouseClick(alvo, alvo.width / 2, alvo.height / 2, Qt.LeftButton)
        }

        /// A rota real até o botão do importador. Dois saltos, medidos na bancada:
        /// a seção é **Temas** (`navigationSections[7]`, `Main.qml:107`), não Sistema
        /// — com índice 6 o `themeEditorTab` existe mas nasce `visible=false` porque
        /// pertence à página inativa do `contentStack`; e o botão está na ABA
        /// "Editar aparência" (índice 1 do `themeTabs`), então o clique na aba é
        /// parte da jornada, não um atalho do teste.
        function abrirAbaEditor() {
            shell.sectionIndex = shell.sectionIndexOf("themes")
            until(function() {
                return shell.responsiveContent.currentIndex === shell.sectionIndex
            }, 4000, "a seção Temas não ficou ativa")
            var aba = null
            until(function() {
                aba = findInShell(shell.contentItem, function(node) {
                    return node.objectName === "themeEditorTab"
                        && node.width > 0 && effectivelyVisible(node)
                })
                return aba !== null
            }, 5000, "a aba 'Editar aparência' não apareceu na seção Temas")
            clicarAlvo(aba, "abaEditarAparência")
            until(function() {
                return harness.panel !== null && effectivelyVisible(harness.panel)
            }, 3000, "a aba não revelou o painel de edição")
        }

        function abrirDialogo() {
            var gatilho = null
            until(function() {
                gatilho = findInShell(harness.panel, function(node) {
                    return node.objectName === "themeImportRetrofeButton"
                        && node.width > 0 && effectivelyVisible(node)
                })
                return gatilho !== null
            }, 5000, "o botão real 'Importar cena RetroFE' não apareceu no painel")
            clicarAlvo(gatilho, "botaoImportarRetrofe")
            until(function() { return harness.dialog.visible === true }, 3000,
                  "o clique real no botão não abriu o diálogo")
            verify(harness.dialog.modal === true,
                   "o diálogo precisa continuar modal — fechar modal por conveniência "
                   + "de teste mudaria o comportamento")
            settleLayout("aberto")
        }

        /// Escrever o MESMO texto não dispara `onTextChanged`, e o importador lê o
        /// estado do painel (`panel.retrofeImportSource`), não o pixel do campo: uma
        /// atribuição que não muda nada deixaria a origem vazia no estado e a cena
        /// seguinte falharia por culpa da ordem do teste, não do produto. Por isso o
        /// valor é limpo antes quando preciso, e a propagação ao estado é conferida —
        /// sem essa conferência o vermelho nasceria mudo.
        function escrever(nome, texto) {
            const campo = named(bodyNodes(), nome)
            verify(campo !== null, "o controle '" + nome + "' não está no corpo do diálogo")
            if (campo.text === texto)
                campo.text = ""
            campo.text = texto
            const estado = propriedadeDoEstado(nome)
            until(function() { return String(harness.panel[estado]) === texto }, 3000,
                  "o texto '" + texto + "' não chegou ao estado do painel (" + estado
                  + " = '" + harness.panel[estado] + "'): o campo mostra um valor que o "
                  + "importador não tem")
            return campo
        }

        function propriedadeDoEstado(nome) {
            if (nome === "themeImportRetrofeSource") return "retrofeImportSource"
            if (nome === "themeImportRetrofeSceneId") return "retrofeImportSceneId"
            if (nome === "themeImportRetrofeName") return "retrofeImportName"
            if (nome === "themeImportRetrofeAuthor") return "retrofeImportAuthor"
            if (nome === "themeImportRetrofeLicense") return "retrofeImportLicense"
            verify(false, "campo sem par no estado do importador: " + nome)
            return ""
        }

        function clicarControle(nome, tag) {
            const alvo = named(bodyNodes(), nome)
            verify(alvo !== null, tag + ": '" + nome + "' ausente do corpo medido")
            mouseClick(alvo, alvo.width / 2, alvo.height / 2, Qt.LeftButton)
            return alvo
        }

        function origem(alavanca, sufixo) {
            return harness.cfg.origens[alavanca].fonte + "-" + sufixo
        }

        function examinar(alavanca, sufixo) {
            escrever("themeImportRetrofeSource", origem(alavanca, sufixo))
            until(function() {
                return named(bodyNodes(), "themeImportRetrofeInspect").enabled === true
            }, 3000, "'Examinar' não habilitou com a origem informada")
            clicarControle("themeImportRetrofeInspect", "examinar-" + alavanca)
        }

        function esperaNeutra(sufixo) {
            escrever("themeImportRetrofeSceneId", "org.exemplo.retrofe-" + sufixo)
            escrever("themeImportRetrofeName", "Cena de exemplo " + sufixo)
            escrever("themeImportRetrofeAuthor", "Autor de exemplo")
            escrever("themeImportRetrofeLicense", "CC0-1.0")
        }

        // ------------------------------------------------------------------- testes

        /// 1 — a jornada dentro do shell, pela rota real: aba → botão → examinar →
        /// publicar. Sem esta cena as três seguintes não teriam ponto de partida
        /// verificado (e provavam apenas que o atraso chegou, não que a rota anda).
        function test_01_a_rota_real_do_shell_examina_e_publica_sem_ativar() {
            abrirAbaEditor()
            abrirDialogo()
            examinar("curta", "jornada")
            until(function() {
                return harness.panel.retrofeImportBusy === false
                    && harness.panel.retrofeImportLayouts.length
                        === harness.cfg.origens.curta.layouts
            }, 8000, "a rota real não publicou os layouts RetroFE no diálogo do shell")
            settleLayout("layouts-publicados")
            verificarCadaLayoutComoOpcaoSelecionavel("curta")
            verify(harness.panel.retrofeImportLayoutIndex === 0,
                   "o examine precisa pré-selecionar o primeiro layout (índice "
                   + harness.panel.retrofeImportLayoutIndex + ")")
            esperaNeutra("jornada")
            const publicar = named(bodyNodes(), "themeImportRetrofeApply")
            until(function() { return publicar.enabled === true }, 3000,
                  "'Publicar cena' não habilitou com layout, ID, nome, autor e licença")
            clicarControle("themeImportRetrofeApply", "publicar-jornada")
            until(function() {
                return harness.panel.retrofeImportBusy === false
                    && String(harness.panel.retrofeImportNotice).length > 0
            }, 8000, "a rota real respondeu 200 ao apply e nada apareceu no corpo")
            observar("jornada-publicada")
            verify(named(bodyNodes(), "themeImportRetrofeNotice") !== null,
                   "o aviso precisa aparecer no corpo do diálogo, não só no estado")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou depois de publicar")
        }

        /// Cada layout que a ponte publicou precisa aparecer como opção real do
        /// diálogo: o `Repeater` de `retrofeImportLayouts` monta um
        /// `RadioButton` por entrada, e é isso que torna a contagem visível — não o
        /// `length` de um array que ninguém vê.
        ///
        /// `checkable` sozinho NÃO basta: a caixa de sobrescrita
        /// (`themeImportRetrofeOverwrite`) também é marcável, e contá-la como
        /// opção deu `opções=3, layouts=2` na primeira execução desta fatia. O que
        /// distingue a opção de layout é o texto vir do `modelData.name` — isto é,
        /// carregar o prefixo da alavanca que a ponte publicou.
        function opcoesDeLayout(alavanca) {
            const prefixo = String(harness.cfg.origens[alavanca].prefixo)
            const radios = []
            const nodes = bodyNodes()
            for (let index = 0; index < nodes.length; index++) {
                const node = nodes[index]
                if (node.checkable === true && effectivelyVisible(node)
                        && String(node.text).indexOf(prefixo) === 0)
                    radios.push(node)
            }
            return radios
        }

        function verificarCadaLayoutComoOpcaoSelecionavel(alavanca) {
            const radios = opcoesDeLayout(alavanca)
            const esperado = harness.cfg.origens[alavanca].layouts
            const caixa = named(bodyNodes(), "themeImportRetrofeOverwrite")
            /// Testemunha de não-vacuidade da varredura: existe um OUTRO controle
            /// marcável no diálogo que ficou de fora da contagem. Sem ela, "n opções"
            /// poderia ser satisfeito por um filtro que não casa com nada.
            verify(caixa !== null && caixa.checkable === true,
                   "a caixa de sobrescrita precisa existir e ser checkable — é ela que "
                   + "mostra que a varredura separou opção de layout de outro controle "
                   + "marcável, em vez de contar qualquer coisa")
            verify(radios.length === harness.panel.retrofeImportLayouts.length,
                   "cada layout publicado precisa aparecer como opção selecionável no "
                   + "diálogo (opções=" + radios.length + ", layouts="
                   + harness.panel.retrofeImportLayouts.length + ")")
            verify(radios.length === esperado,
                   "a ponte publicou " + harness.panel.retrofeImportLayouts.length
                   + " layouts e apareceram " + radios.length + " opções (esperado "
                   + esperado + ")")
        }

        /// 2 — a resposta chega depois do fechamento. Este é o vermelho da fatia:
        /// antes desta fatia o callback escrevia em cima de uma superfície fechada,
        /// e o estado renascia sujo quando o usuário reabre.
        function test_02_fechar_com_pedido_em_voo_nao_recebe_a_resposta_tardia() {
            abrirAbaEditor()
            abrirDialogo()
            examinar("lenta", "tardia")
            until(function() { return harness.panel.retrofeImportBusy === true }, 3000,
                  "o examine não marcou a requisição como em voo")
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "nenhuma requisição saiu pela rota real")
            observar("antes-do-escape")
            keyPress(Qt.Key_Escape)
            keyRelease(Qt.Key_Escape)
            until(function() { return harness.dialog.visible === false }, 3000,
                  "Escape real não fechou o diálogo")
            // Testemunha de não-vacuidade: o pedido AINDA está em voo quando a
            // superfície fecha. Se a resposta já tivesse chegado, esta cena não
            // exercitaria resposta tardia nenhuma.
            verify(shell.pendingRequests >= 1,
                   "a resposta chegou ANTES do fechamento (pendentes="
                   + shell.pendingRequests + "): o cenário não exercitou atraso")
            until(function() {
                return harness.panel.retrofeImportBusy === false
                    && harness.panel.retrofeImportLayouts.length === 0
                    && harness.panel.retrofeImportNotice === ""
            }, 3000, "o fechamento não limpou o estado do importador")

            until(function() { return shell.pendingRequests === 0 }, 10000,
                  "a ponte nunca respondeu ao examine")
            observar("depois-da-resposta-tardia")
            verify(harness.panel.retrofeImportLayouts.length === 0,
                   "a resposta tardia reescreveu " + harness.panel.retrofeImportLayouts.length
                   + " layouts num diálogo fechado — o aviso e a seleção renascem na "
                   + "reabertura com dados que ninguém pediu")
            verify(harness.panel.retrofeImportNotice === "",
                   "a resposta tardia escreveu aviso num diálogo fechado: '"
                   + harness.panel.retrofeImportNotice + "'")
            verify(harness.panel.retrofeImportBusy === false,
                   "a resposta tardia mexeu na bandeira de ocupado")

            abrirDialogo()
            verificarCadaLayoutNaoReaparece()
            verify(harness.panel.retrofeImportNotice === "",
                   "a reabertura mostrou aviso '" + harness.panel.retrofeImportNotice
                   + "' de um pedido já encerrado")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        function verificarCadaLayoutNaoReaparece() {
            const radios = []
            const nodes = bodyNodes()
            for (let index = 0; index < nodes.length; index++) {
                const node = nodes[index]
                if (node.checkable === true && effectivelyVisible(node))
                    radios.push(node)
            }
            verify(radios.length === 0,
                   "a reabertura mostrou " + radios.length
                   + " opções de layout vindas de um pedido já encerrado")
        }

        /// 3 — a corrida fora de ordem, do jeito que o usuário realmente a produz.
        /// Dois cliques seguidos NÃO são a cena: "Examinar" está desabilitado enquanto
        /// há pedido em voo (`themeImportRetrofeInspect`). O que é alcançável é
        /// examinar, FECHAR (o `retrofeImportDialog.onClosed` roda
        /// `resetRetrofeImport()`, que limpa a bandeira), reabrir e examinar outra
        /// origem — e aí os dois
        /// pedidos estão em voo ao mesmo tempo, o `requestAction` só deduplica payload
        /// idêntico, e o que responde por último não é o que foi pedido por último.
        function test_03_o_pedido_mais_novo_nao_perde_para_o_anterior() {
            abrirAbaEditor()
            abrirDialogo()
            examinar("lenta", "anterior")
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "o primeiro examine não saiu pela rota real")
            keyPress(Qt.Key_Escape)
            keyRelease(Qt.Key_Escape)
            until(function() { return harness.dialog.visible === false }, 3000,
                  "Escape real não fechou o diálogo com o examine em voo")
            verify(harness.panel.retrofeImportBusy === false,
                   "o fechamento deixou a bandeira de ocupado armada: sem limpá-la o "
                   + "'Examinar' da cena seguinte nasceria desabilitado, e a corrida "
                   + "seria inatingível também para o usuário")
            abrirDialogo()
            examinar("rapida", "mais-novo")
            until(function() {
                return harness.panel.retrofeImportBusy === false
                    && harness.panel.retrofeImportLayouts.length
                        === harness.cfg.origens.rapida.layouts
            }, 8000, "o examine mais novo não publicou seus layouts")
            verificarCadaNomeTemMarcador("rapida", nomesDosLayouts())
            const nomesNovos = nomesDosLayouts()
            observar("depois-do-mais-novo")
            // Testemunha de não-vacuidade: quando o mais novo publicou, o ANTERIOR
            // ainda estava em voo. Sem isso a cena poderia passar simplesmente porque
            // a ordem nunca se inverteu.
            verify(shell.pendingRequests >= 1,
                   "o examine anterior já tinha respondido quando o mais novo publicou "
                   + "(pendentes=" + shell.pendingRequests + "): nada aqui exercitou "
                   + "resposta fora de ordem")

            until(function() { return shell.pendingRequests === 0 }, 12000,
                  "o examine anterior nunca respondeu")
            observar("depois-do-anterior-tardio")
            verify(harness.panel.retrofeImportLayouts.length === harness.cfg.origens.rapida.layouts,
                   "a resposta do pedido ANTERIOR substituiu o resultado do pedido mais "
                   + "novo: layouts=" + harness.panel.retrofeImportLayouts.length
                   + ", esperado " + harness.cfg.origens.rapida.layouts)
            verify(nomesDosLayouts() === nomesNovos,
                   "o conteúdo dos layouts veio do pedido anterior: antes '" + nomesNovos
                   + "', agora '" + nomesDosLayouts() + "'")
            verify(harness.panel.retrofeImportBusy === false,
                   "a resposta anterior mexeu na bandeira de ocupado do pedido corrente")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        function nomesDosLayouts() {
            const nomes = []
            const lista = harness.panel.retrofeImportLayouts
            for (let index = 0; index < lista.length; index++)
                nomes.push(String(lista[index] && lista[index].name ? lista[index].name : ""))
            return nomes.join("|")
        }

        function verificarCadaNomeTemMarcador(alavanca, nomes) {
            verify(nomes.length > 0, "nenhum layout publicado; nada a comparar")
            const marcador = harness.cfg.origens[alavanca].prefixo
            const partes = nomes.split("|")
            for (let index = 0; index < partes.length; index++) {
                verify(partes[index].indexOf(marcador) === 0,
                       "o layout " + index + " não veio da origem '" + alavanca + "': '"
                       + partes[index] + "'")
            }
        }

        /// 4 — publicar com resposta tardia: o aviso de sucesso e a re-listagem de
        /// temas são efeitos que só fazem sentido na superfície que pediu.
        function test_04_publicar_em_voo_e_fechar_nao_anuncia_sucesso_tardio() {
            abrirAbaEditor()
            abrirDialogo()
            examinar("curta", "aplicar-tardio")
            until(function() {
                return harness.panel.retrofeImportBusy === false
                    && harness.panel.retrofeImportLayouts.length
                        === harness.cfg.origens.curta.layouts
            }, 8000, "o examine não publicou layouts para a cena de aplicação")
            esperaNeutra("aplicar-tardio")
            until(function() {
                return named(bodyNodes(), "themeImportRetrofeApply").enabled === true
            }, 3000, "'Publicar cena' não habilitou")
            clicarControle("themeImportRetrofeApply", "publicar-tardio")
            until(function() { return harness.panel.retrofeImportBusy === true }, 3000,
                  "o apply não marcou a requisição como em voo")
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "nenhum POST saiu para /theme/import/retrofe/apply")
            keyPress(Qt.Key_Escape)
            keyRelease(Qt.Key_Escape)
            until(function() { return harness.dialog.visible === false }, 3000,
                  "Escape real não fechou o diálogo durante a publicação")
            verify(shell.pendingRequests >= 1,
                   "o apply respondeu ANTES do fechamento (pendentes="
                   + shell.pendingRequests + "): o cenário não exercitou atraso")
            until(function() { return shell.pendingRequests === 0 }, 12000,
                  "a ponte nunca respondeu ao apply")
            observar("depois-do-apply-tardio")
            verify(harness.panel.retrofeImportNotice === "",
                   "a resposta tardia do apply anunciou '"
                   + harness.panel.retrofeImportNotice + "' num diálogo fechado")
            verify(harness.panel.retrofeImportBusy === false,
                   "a resposta tardia do apply mexeu na bandeira de ocupado")
            verify(harness.panel.retrofeImportLayouts.length === 0,
                   "o estado do importador guarda " + harness.panel.retrofeImportLayouts.length
                   + " layouts depois de fechar o pedido")
            // O terceiro efeito do apply tardio é invisível na superfície: a re-listagem
            // de temas (`applyRetrofeImport`, `panel.refreshThemeList()`). A prova
            // é a LOG ORDENADA DA PONTE lida pelo gate Python — nenhum GET /theme/list
            // depois daquele POST — com a jornada do test_01 como contrafactual.
            abrirDialogo()
            const aviso = named(bodyNodes(), "themeImportRetrofeNotice")
            verify(aviso !== null, "o aviso precisa existir no corpo para ser medido")
            verify(aviso.visible === false,
                   "a reabertura exibiu o aviso de um pedido encerrado: '" + aviso.text + "'")
            verificarCadaLayoutNaoReaparece()
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        /// V — outro eixo, outra raiz, declarado separado: o campo de origem é ligado
        /// ao estado por `text: panel.retrofeImportSource` +
        /// `onTextChanged: panel.retrofeImportSource = text`
        /// (`themeImportRetrofeSource` e o `Binding` que o espelha). A primeira
        /// edição pelo teclado ou por atribuição INTERROMPE a binding, então o
        /// `resetRetrofeImport()` do `onClosed` limpa o estado e o pixel do campo
        /// continua mostrando a última origem. O botão "Examinar" lê o ESTADO
        /// (`enabled` de `themeImportRetrofeInspect`): o usuário reabre, vê um
        /// caminho no campo e um botão desabilitado que ele não sabe explicar. Não é
        /// a resposta tardia — é a superfície mentindo sobre o próprio estado.
        function test_05_reabrir_mostra_o_estado_e_nao_o_ultimo_texto_editado() {
            abrirAbaEditor()
            abrirDialogo()
            escrever("themeImportRetrofeSource", origem("curta", "reabertura"))
            verify(harness.panel.retrofeImportSource === origem("curta", "reabertura"),
                   "a edição não chegou ao estado do painel")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou")
            verify(harness.panel.retrofeImportSource === "",
                   "o fechamento não limpou a origem no estado — sem isso esta cena "
                   + "estaria testando outra coisa")
            abrirDialogo()
            const campo = named(bodyNodes(), "themeImportRetrofeSource")
            verify(campo.text === "",
                   "reabrir mostrou '" + campo.text + "' no campo de origem, sendo que o "
                   + "estado do importador está vazio: a binding do texto foi interrompida "
                   + "pela primeira edição e o onClosed não a reafirmou")
            verify(campo.text === harness.panel.retrofeImportSource,
                   "campo e estado divergem no instante da reabertura (campo='" + campo.text
                   + "', estado='" + harness.panel.retrofeImportSource + "')")
            const examinar_botao = named(bodyNodes(), "themeImportRetrofeInspect")
            verify(examinar_botao.enabled === false,
                   "com estado vazio o 'Examinar' precisa estar desabilitado; ele está "
                   + "habilitado sobre um texto que o importador não tem")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        /// VI — o mesmo vínculo, a segunda porta de entrada, medida à parte porque a
        /// cena anterior morre na primeira asserção: os dois seletores gravam no
        /// ESTADO (`retrofeImportFolderDialog`/`retrofeImportFileDialog`,
        /// `panel.retrofeImportSource = panel.localPath(...)`), nunca no campo. Morto o
        /// espelho pela digitação, quem
        /// digita algo e depois escolhe a pasta vê o texto antigo enquanto o painel tem
        /// uma origem válida — e é o ESTADO que habilita e despacha o "Examinar"
        /// (`enabled` de `themeImportRetrofeInspect`). Não se abre seletor nativo
        /// aqui: escreve-se o caminho exato que
        /// o seletor escreveria.
        function test_06_escrever_no_estado_alcanca_o_campo_com_o_dialogo_aberto() {
            abrirAbaEditor()
            abrirDialogo()
            escrever("themeImportRetrofeSource", origem("curta", "antes-do-seletor"))
            harness.panel.retrofeImportSource = origem("curta", "seletor")
            until(function() {
                return named(bodyNodes(), "themeImportRetrofeSource").text
                    === origem("curta", "seletor")
            }, 3000, "escrever no estado não chegou ao campo com o diálogo aberto (esperado '"
                + origem("curta", "seletor") + "')")
            const campoAposEstado = named(bodyNodes(), "themeImportRetrofeSource")
            observar("campo-espelho-do-estado")
            verify(campoAposEstado.text === origem("curta", "seletor"),
                   "o campo mostra '" + campoAposEstado.text + "' enquanto o estado vale '"
                   + origem("curta", "seletor") + "': quem escreve no painel não chega ao pixel")
            verify(named(bodyNodes(), "themeImportRetrofeInspect").enabled === true,
                   "com origem válida no estado o 'Examinar' tem de acompanhar; campo e botão "
                   + "não podem contar histórias diferentes")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        /// VII — a porta de teclado do exame. O campo de origem é onde o usuário
        /// digita ou cola um caminho, e num shell operado por controle o seletor nativo
        /// não é alcançável com o pad: sem Enter no campo, o caminho digitado nunca
        /// vira exame. A cena mede a alegação mais simples possível — tecla real, POST
        /// real na ponte, layouts publicados — porque as duas cenas de recusa abaixo
        /// só existem se houver uma segunda porta dirigível por evento.
        function test_07_a_tecla_enter_despacha_o_exame_pela_rota_real() {
            abrirAbaEditor()
            abrirDialogo()
            escrever("themeImportRetrofeSource", origem("curta", "teclado"))
            const campo = named(bodyNodes(), "themeImportRetrofeSource")
            campo.forceActiveFocus(Qt.ClickFocusReason)
            until(function() { return campo.activeFocus === true }, 3000,
                  "o campo de origem não recebeu foco ativo; sem foco a tecla não chega "
                  + "a nenhum tratador de Enter")
            keyPress(Qt.Key_Return)
            keyRelease(Qt.Key_Return)
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "Enter real no campo de origem não despachou nenhum pedido pela rota "
                  + "autenticada")
            observar("exame-por-teclado")
            until(function() {
                return harness.panel.retrofeImportBusy === false
                    && harness.panel.retrofeImportLayouts.length
                        === harness.cfg.origens.curta.layouts
            }, 8000, "a resposta do exame por teclado não publicou os layouts")
            verificarCadaNomeTemMarcador("curta", nomesDosLayouts())
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        /// VIII — o mesmo Enter, SEM fechamento no meio: aqui o POST em voo ainda é o
        /// pedido CORRENTE, e a recusa tem de devolver a superfície ao que ela era
        /// antes do clique. É o outro lado do contrato da bandeira:
        /// `retrofeImportBusy` diz se há algo em voo que ainda vai escrever. Quando o
        /// `onClosed` já revogou aquele pedido (cena 09) nada em voo resta e a bandeira
        /// tem de estar baixada; quando ele ainda é corrente, baixá-la faz o
        /// "Importando…" sumir e "Publicar cena" (`themeImportRetrofeApply`) habilitar
        /// sobre um importador que ainda não respondeu — e o usuário publica uma cena
        /// cuja origem ele não sabe se foi examinada.
        ///
        /// Por que o Enter e não o seletor: dos dois botões de seleção
        /// (`themeImportRetrofeBrowseFolder`, `themeImportRetrofeBrowseFile`) só o de
        /// arquivo despacha exame no `onAccepted`, mas a
        /// sonda medida nesta bancada mostra que, sob `offscreen`, o `FileDialog` abre
        /// SEM NENHUMA árvore QML dirigida (`contentItem` sem filhos) — não há botão a
        /// clicar, e um harness que o abrisse dependeria do tema de desktop da máquina.
        /// A porta de teclado da cena 07 é a segunda entrada dirigível por evento.
        function test_08_a_repeticao_recusada_com_pedido_corrente_nao_desarma_a_bandeira() {
            abrirAbaEditor()
            abrirDialogo()
            examinar("lenta", "corrente")
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "o examine não saiu pela rota real")
            verify(harness.panel.retrofeImportBusy === true,
                   "com um examine em voo a bandeira precisa estar armada; vale "
                   + harness.panel.retrofeImportBusy)
            const campo = named(bodyNodes(), "themeImportRetrofeSource")
            campo.forceActiveFocus(Qt.ClickFocusReason)
            until(function() { return campo.activeFocus === true }, 3000,
                  "o campo de origem não recebeu foco ativo; sem foco a tecla não chega "
                  + "ao tratador de Enter")
            keyPress(Qt.Key_Return)
            keyRelease(Qt.Key_Return)
            observar("pedido-recusado-com-pedido-corrente")
            verify(shell.pendingRequests >= 1,
                   "o POST corrente já tinha respondido antes da repetição (pendentes="
                   + shell.pendingRequests + "): sem voo não há recusa")
            verify(shell.pendingRequests === 1,
                   "a tecla não foi recusada: saiu um SEGUNDO pedido pela ponte "
                   + "(pendentes=" + shell.pendingRequests + "). A cena mede recusa de "
                   + "payload idêntico, e sem recusa as duas asserções abaixo não "
                   + "testam nada")
            verify(harness.panel.retrofeImportBusy === true,
                   "o Enter recusado DESARMou a bandeira de um pedido que ainda está em "
                   + "voo: 'Importando…' desaparece e 'Publicar cena' habilita sobre um "
                   + "importador que ainda não respondeu")
            until(function() { return shell.pendingRequests === 0 }, 12000,
                  "a ponte nunca respondeu ao examine corrente")
            verify(harness.panel.retrofeImportLayouts.length
                       === harness.cfg.origens.lenta.layouts,
                   "o resultado do pedido CORRENTE foi descartado pela geração do Enter "
                   + "recusado: layouts=" + harness.panel.retrofeImportLayouts.length
                   + ", esperado " + harness.cfg.origens.lenta.layouts)
            verificarCadaNomeTemMarcador("lenta", nomesDosLayouts())
            verify(harness.panel.retrofeImportBusy === false,
                   "a resposta chegou e a bandeira continua armada: nada em voo para "
                   + "baixá-la depois daqui")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        /// IX — a MESMA origem pedida duas vezes, com a primeira já REVOGADA pelo
        /// fechamento. `themeImportRetrofeInspect` desabilita "Examinar" enquanto
        /// `retrofeImportBusy`, mas o `retrofeImportDialog.onClosed` roda
        /// `resetRetrofeImport()` e a bandeira cai: fechar, reabrir e pedir a
        /// MESMA origem é alcançável por clique real, e `requestAction` recusa payload
        /// IDÊNTICO devolvendo `false` sem disparar nenhuma callback. O pedido recusado
        /// é um não-acontecimento: tem de acabar com a superfície ociosa e utilizável,
        /// porque o POST em voo foi revogado pelo fechamento e nada mais vai abaixar a
        /// bandeira. A alavanca `revogada` existe só para isto: reabrir, escrever e
        /// clicar leva mais que os 1 500 ms da `lenta`, e uma janela curta trocaria a
        /// cena por "o teste andou devagar".
        function test_09_a_repeticao_recusada_com_pedido_revogado_nao_trava_o_dialogo() {
            abrirAbaEditor()
            abrirDialogo()
            examinar("revogada", "revogada")
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "o primeiro examine não saiu pela rota real")
            keyPress(Qt.Key_Escape)
            keyRelease(Qt.Key_Escape)
            until(function() { return harness.dialog.visible === false }, 3000,
                  "Escape real não fechou o diálogo com o examine em voo")
            abrirDialogo()
            escrever("themeImportRetrofeSource", origem("revogada", "revogada"))
            until(function() {
                return named(bodyNodes(), "themeImportRetrofeInspect").enabled === true
            }, 3000, "'Examinar' não reabilitou depois do fechamento (ocupado="
                   + harness.panel.retrofeImportBusy + "): sem isso a repetição seria "
                   + "inatingível também para o usuário")
            clicarControle("themeImportRetrofeInspect", "repetir-revogada")
            observar("pedido-recusado-com-pedido-revogado")
            verify(shell.pendingRequests >= 1,
                   "o examine em voo já tinha respondido quando a repetição foi clicada "
                   + "(pendentes=" + shell.pendingRequests + "): nada aqui exercitou "
                   + "payload idêntico recusado")
            until(function() { return shell.pendingRequests === 0 }, 12000,
                  "a ponte nunca respondeu ao examine em voo")
            verify(harness.panel.retrofeImportBusy === false,
                   "o diálogo ficou preso em 'Importando…': o clique recusado armou a "
                   + "bandeira e o pedido, revogado pelo fechamento, não a baixa mais")
            verify(harness.panel.retrofeImportLayouts.length === 0,
                   "a resposta de um pedido revogado reabriu estado no diálogo reaberto: "
                   + harness.panel.retrofeImportLayouts.length + " layouts")
            verify(harness.panel.retrofeImportNotice === "",
                   "a recusa anunciou alguma coisa: '" + harness.panel.retrofeImportNotice
                   + "'")
            verify(named(bodyNodes(), "themeImportRetrofeInspect").enabled === true,
                   "com origem preenchida e nada em voo o 'Examinar' tem de estar "
                   + "disponível: o usuário precisa conseguir continuar sem fechar")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

    }
}
