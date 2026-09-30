// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// RC-01 (UX-05/UX-07, corte ES-DE na shell) — a resposta TARDIA do importador ES-DE.
//
// Este arquivo é o irmão de `check_shell_retrofe_import_late_response.qml`: mesmo
// harness (raiz `Item { Main {} }`, ponte HTTP real em loopback com atraso, oráculo
// `shell.pendingRequests`). As cenas 01-06 andam pela rota real do PAINEL (seção
// Temas → aba "Editar aparência" → botão "Importar tema ES-DE"; o trio
// `*EsdeImport()` de `ThemeEditorPanel.qml`); as cenas 07-10 pela rota RAIZ (seção
// Sistema → o mesmo botão, mas o `esdeImportDialog` de `Main.qml`, que despacha
// inline no próprio `onClicked`).
//
// O defeito, medido em `c4975979`: nenhuma das duas superfícies tinha o contrato de
// geração que a fatia RetroFE já estabeleceu no molde `*RetrofeImport()`. No painel,
// `grep -c esdeImportGeneration ThemeEditorPanel.qml` dava 0; na raiz não existia
// `esdeImportGeneration` nenhum. A resposta que chegasse depois do fechamento
// escrevia por cima de uma superfície que o usuário já tinha abandonado.
//
// Por que o shell e não o painel stubado: as fatias anteriores de ES-DE
// (`check_esde_import_dialog_compact_viewport.qml`,
// `check_shell_esde_import_dialog_journey.qml`) exercitam o diálogo RAIZ, o
// `esdeImportDialog` de `Main.qml`, ou injetam `requestAction` e chamam as callbacks
// dentro do stub. Sincronia não exercita atraso: no painel stubado a resposta chega
// antes de qualquer mudança de superfície e por construção não pode ser tardia. Aqui
// o importador é o `XMLHttpRequest` do produto — o `request()` de `Main.qml`, com
// seu `xhr.timeout` — falando com um servidor que DORME antes de responder.
//
// O contrato, uma frase por cena (o número da cena é o número do teste):
//   1. a rota real do shell anda: aba → botão → examinar → importar, e importa sem
//      aplicar (o aviso do produto diz "ele ainda não foi aplicado", escrito na
//      callback de sucesso de `applyEsdeImport`) — e a ponte TEM de registrar
//      `GET /theme/list` depois daquele apply, ali mesmo; sem esta as seguintes
//      provariam apenas que um atraso chegou;
//   2. fechar o diálogo com um pedido em voo não pode reabrir estado: a resposta que
//      chega depois do `onClosed` do painel encontra esquemas, aviso e bandeira
//      vazios e assim os deve deixar. Em `c4975979` o callback escrevia por cima da
//      superfície fechada;
//   3. um pedido mais novo não pode perder para o anterior: examinaram-se origens
//      diferentes, os dois estão em voo juntos (o `requestAction` de `Main.qml` só
//      deduplica payload IDÊNTICO) e o que responde por último não é o que o usuário
//      pediu por último;
//   4. importar com resposta tardia não pode anunciar sucesso nem re-listar temas
//      depois de a superfície ter fechado (o aviso e o `refreshThemeList()` são a
//      mesma callback de `applyEsdeImport`);
//   5. a recusa por dedup: um clique recusado pelo `requestAction` tem de devolver a
//      bandeira ao que ela era ANTES do clique (`ocupadoAntes` no molde RetroFE), e
//      a resposta do pedido recusado não pode substituir o resultado do pedido que
//      realmente produziu algo;
//   6. o MESMO clique recusado, agora com o único pedido em voo já REVOGADO pelo
//      fechamento: a superfície acaba ociosa e utilizável (nada mais vai abaixar a
//      bandeira), e o aviso não pode alegar um erro que não aconteceu. É o pino que
//      impede a correção da 05 de resolver escrevendo `true` sempre.
//   7-10. as quatro asserções anteriores na rota RAIZ: examinar e importar andam com
//      eventos reais; fechar com pedido em voo não recebe a resposta tardia; o apply
//      tardio não anuncia sucesso numa superfície fechada (o testemunho é o
//      `shell.lastRequest`, único lugar onde o `notify` do apply aparece) e não mexe
//      na bandeira da raiz; a recusa devolve `ocupadoAntes` e não trava o diálogo.
//
// Divergência declarada frente ao molde RetroFE (medida, não narrada): o diálogo
// ES-DE do painel NÃO tem segunda porta de despacho. O campo de origem
// (`themeImportEsdeSource`) não tem `onAccepted` — ao contrário do campo RetroFE,
// que despacha no Enter — e os dois botões despachantes estão gated por
// `esdeImportBusy` (`themeImportEsdeInspect`, `themeImportEsdeApply`). Logo, um
// clique recusado com a bandeira JÁ armada é fisicamente inalcançável aqui: recusar
// exige botão habilitado, botão habilitado exige bandeira baixada, e a única coisa
// que baixa a bandeira com o pedido vivo é o fechamento. A cena 05 mede exatamente
// o que a produção alcança: a recusa chega com `ocupadoAntes = false`, e a correção
// tem de RESTAURAR esse valor (não deixá-la armada, como `inspectEsdeImport`
// fazia em `c4975979`) sem deixar o pedido recusado reescrever o resultado corrente
// quando ele aterrassar.
//
// O oráculo de "a resposta chegou" é `shell.pendingRequests` (`Main.qml`, somado e
// descontado dentro do próprio `request()`). Não há margem fixa depois
// dele: `finish()` decrementa e a callback escreve no MESMO turno. Antes de cada
// alegação de "resposta tardia" a cena afirma `shell.pendingRequests >= 1` com o
// pedido em voo — sem essa testemunha a cena poderia passar porque a cena andou
// devagar, não porque o atraso existiu.
//
// O que NÃO é provado aqui, e por quê: "importar tarde não re-lista os temas" é
// invisível na superfície. A prova é a LOG ORDENADA DA PONTE, lida pelo gate Python:
// nenhum `GET /theme/list` depois do apply daquela origem. O mesmo contador, na
// jornada do test_01, TEM de registrar o re-lista — contrafactual que impede a
// asserção de ser satisfeita por ausência de medição.
//
// Fatos de bancada reutilizados das fatias anteriores (não redescobertos):
//   • `qmltestrunner` hospeda a raiz em QQuickView, que REJEITA raiz Window — daí
//     `Item { Main {} }`, como em `check_shell_esde_import_dialog_journey.qml`;
//   • `Item.childItems` é undefined neste runtime Qt 6.11.2: a varredura une
//     `children` e `childItems`;
//   • Popup não é Item: o corpo do diálogo é varrido a partir de
//     `dialog.contentItem` + `dialog.footer`;
//   • o oráculo de foco é `shell.activeFocusItem`;
//   • `keyPress` de letra chega sem `text` neste runtime, então o conteúdo entra
//     pela propriedade do próprio campo — e navegação/ativação/edição são medidas
//     com tecla real;
//   • revelar pelo foco é o mecanismo do produto; o teste ESPERA o efeito da banda,
//     nunca escreve `contentY`.

import QtQuick
import QtQuick.Controls
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 1280
    height: 800

    /// Configuração efêmera escrita pelo teste em `build/`: endereço e token da
    /// ponte, as alavancas por origem e o viewport.
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
        name: "ShellEsdeImportLateResponse"
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
        /// contentItem e do footer, como no harness RetroFE.
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

        /// A banda que clipa — o Flickable interno, não o ScrollView que o embrulha.
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
        /// materializam. Estabilizar por observable, não por intervalo fixo.
        function signature() {
            if (!harness.dialog || !harness.dialog.visible || !harness.dialog.background)
                return ""
            const nodes = bodyNodes()
            const origem = named(nodes, "themeImportEsdeSource")
            const importar = named(nodes, "themeImportEsdeApply")
            if (!origem || origem.width <= 0 || !importar || importar.width <= 0)
                return ""
            const moldura = harness.dialog.background
            return Math.round(moldura.width) + "x" + Math.round(moldura.height)
                    + "|origem=" + describeRect(rectIn(origem, moldura))
                    + "|importar=" + describeRect(rectIn(importar, moldura))
                    + "|esquemas=" + harness.panel.esdeImportSchemes.length
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
            verify(stable, "o layout do diálogo ES-DE não estabilizou observavelmente em "
                            + budget + " ms ('" + tag + "'); última assinatura: "
                            + (previous === "" ? "controles ainda ausentes" : previous))
            console.log("ESTABILIZOU '" + tag + "' em " + elapsed + " ms :: " + previous)
        }

        // -------------------------------------------------------------- observáveis

        /// Linha de estado no instante pedido. Existe para o log do CI ser
        /// independente da narração e do veredito do QtTest: quem audita lê `OBS|...`
        /// e reconcile com os contadores da ponte.
        function observar(tag) {
            const p = harness.panel
            console.log("OBS|" + tag
                        + "|dialogo=" + (harness.dialog && harness.dialog.visible ? "aberto" : "fechado")
                        + "|pendentes=" + shell.pendingRequests
                        + "|ocupado=" + (p.esdeImportBusy ? 1 : 0)
                        + "|esquemas=" + p.esdeImportSchemes.length
                        + "|indice=" + p.esdeImportSchemeIndex
                        + "|aviso=" + String(p.esdeImportNotice).length
                        + "|erro=" + (p.esdeImportNoticeIsError ? 1 : 0)
                        + "|origem=" + String(p.esdeImportSource).length
                        + "|nome=" + String(p.esdeImportName).length)
        }

        // ------------------------------------------------------------------ bancada

        function config() {
            const request = new XMLHttpRequest()
            request.open("GET", Qt.resolvedUrl("../../build/ui-shell-esde-import-late.json"), false)
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
        /// alcançável de fora do arquivo. A sonda exige as DUAS propriedades do
        /// estado ES-DE para não casar com nada além do painel.
        function panelDoShell() {
            var found = null
            until(function() {
                found = findInShell(shell.contentItem, function(node) {
                    return node.esdeImportBusy !== undefined
                        && node.esdeImportSchemes !== undefined
                })
                return found !== null
            }, 5000, "o painel de edição de tema não apareceu na árvore do shell")
            harness.panel = found
            harness.dialog = found.esdeImportDialogControl
            verify(harness.dialog !== null,
                   "o painel precisa expor o diálogo como superfície de teste, como já "
                   + "expõe `esdeImportDialogControl` de `ThemeEditorPanel.qml`")
        }

        /// Limpeza controlada, não prova. A ordem é a do molde RetroFE: QUIESCER
        /// antes de fechar — com o contrato atual uma resposta que chega depois do
        /// `onClosed` repõe esquemas e aviso, e a cena seguinte nasceria suja por
        /// culpa da ordem do teste, não do produto. Depois de fechar, o neutralizador
        /// é chamado direto: é o mesmo `resetEsdeImport()` que o `onClosed`
        /// (`esdeImportDialog.onClosed` do painel) executa, invocado aqui para que o vermelho
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
                harness.panel.resetEsdeImport()
            until(function() {
                return harness.panel.esdeImportBusy === false
                    && harness.panel.esdeImportSchemes.length === 0
                    && harness.panel.esdeImportNotice === ""
            }, 3000, "limpeza: o estado do importador ES-DE não voltou ao neutro")
            /// A outra superfície: as cenas da rota raiz deixam o diálogo do
            /// `Main.qml` aberto se uma cena morrer no meio, e o `onClosed` é o que
            /// limpa `shell.esdeImport*`. Fechar por aqui não é prova — é bancada.
            if (shell.esdeImportDialogControl && shell.esdeImportDialogControl.visible) {
                shell.esdeImportDialogControl.close()
                until(function() {
                    return shell.esdeImportDialogControl.visible === false
                }, 3000, "limpeza: o diálogo raiz não fechou")
            }
            until(function() {
                return shell.esdeImportBusy === false
                    && shell.esdeImportSchemes.length === 0
                    && shell.esdeImportNotice === ""
            }, 3000, "limpeza: o estado do importador ES-DE raiz não voltou ao neutro")
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
                    && shell.uiContracts.byId["theme.import.esde.inspect"] !== undefined
                    && shell.uiContracts.byId["theme.import.esde.apply"] !== undefined
            }, 5000, "a ponte real não publicou os contratos do importador ES-DE")
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

        /// A rota real até o botão do importador, idêntica à do molde RetroFE: a
        /// seção é Temas (`Main.qml:107`), e o botão mora na aba "Editar aparência"
        /// (índice 1 do `themeTabs`), então o clique na aba é parte da jornada.
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
                    return node.objectName === "themeImportEsdeButton"
                        && node.width > 0 && effectivelyVisible(node)
                })
                return gatilho !== null
            }, 5000, "o botão real 'Importar tema ES-DE' não apareceu no painel")
            clicarAlvo(gatilho, "botaoImportarEsde")
            until(function() { return harness.dialog.visible === true }, 3000,
                  "o clique real no botão não abriu o diálogo")
            verify(harness.dialog.modal === true,
                   "o diálogo precisa continuar modal — fechar modal por conveniência "
                   + "de teste mudaria o comportamento")
            settleLayout("aberto")
        }

        /// Escrever o MESMO texto não dispara `onTextChanged`, e o importador lê o
        /// estado do painel (`panel.esdeImportSource`), não o pixel do campo. Por
        /// isso o valor é limpo antes quando preciso, e a propagação ao estado é
        /// conferida — sem essa conferência o vermelho nasceria mudo.
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
            if (nome === "themeImportEsdeSource") return "esdeImportSource"
            if (nome === "themeImportEsdeName") return "esdeImportName"
            verify(false, "campo sem par no estado do importador ES-DE: " + nome)
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

        /// O examine pela rota real. Sem `onAccepted` no campo
        /// `themeImportEsdeSource` — ao contrário do campo RetroFE —, o clique no
        /// "Examinar" é a ÚNICA
        /// porta de despacho alcançável por evento neste diálogo.
        function examinar(alavanca, sufixo) {
            escrever("themeImportEsdeSource", origem(alavanca, sufixo))
            until(function() {
                return named(bodyNodes(), "themeImportEsdeInspect").enabled === true
            }, 3000, "'Examinar' não habilitou com a origem informada")
            clicarControle("themeImportEsdeInspect", "examinar-" + alavanca)
        }

        function escreverNome(sufixo) {
            escrever("themeImportEsdeName", "Tema importado " + sufixo)
        }

        // ------------------------------------------------------------ rota raiz

        /// O SEGUNDO importador ES-DE do shell: o diálogo raiz de `Main.qml`
        /// (`theme-import-esde-dialog`), aberto pelo botão real da seção Sistema, com
        /// estado próprio (`shell.esdeImport*`) e despacho inline nos dois
        /// botões (`esdeInspectButton`, `esdeApplyButton`). Não é o painel: aqui o
        /// aviso de sucesso é um `root.notify` no apply, e a origem mora no campo,
        /// não numa propriedade.
        /// Medido antes de escrever esta cena: `grep -c esdeImportGeneration Main.qml`
        /// = 0, e o `esdeImportDialog.onClosed` limpa o estado sem revogar pedido
        /// algum.
        function nodesRaiz() {
            const out = []
            const popup = shell.esdeImportDialogControl
            if (!popup || !popup.contentItem)
                return out
            descendants(popup.contentItem, out, 0)
            if (popup.footer)
                descendants(popup.footer, out, 0)
            return out
        }

        function namedRaiz(nome) {
            const nodes = nodesRaiz()
            for (let index = 0; index < nodes.length; index++)
                if (nodes[index].objectName === nome)
                    return nodes[index]
            return null
        }

        /// Abertura pelo botão REAL, na mesma rota que a jornada do diálogo raiz
        /// (`check_shell_esde_import_dialog_journey.qml`, em `triggerButton()`)
        /// percorre: a seção é
        /// Sistema e os dois botões do produto têm o MESMO rótulo, então é a seção
        /// ativa que desambigua — varrer o shell inteiro casaria com o do painel.
        function abrirDialogoRaiz() {
            shell.sectionIndex = shell.sectionIndexOf("system")
            until(function() {
                return shell.responsiveContent.currentIndex === shell.sectionIndex
            }, 4000, "a seção Sistema não ficou ativa")
            var gatilho = null
            until(function() {
                gatilho = findInShell(shell.contentItem, function(node) {
                    return node instanceof Button
                        && String(node.text) === "Importar tema ES-DE"
                        && node.width > 0 && node.height > 0
                        && effectivelyVisible(node)
                })
                return gatilho !== null
            }, 6000, "o botão real do importador ES-DE da seção Sistema não apareceu")
            clicarAlvo(gatilho, "botaoImportarEsdeRaiz")
            until(function() {
                return shell.esdeImportDialogControl && shell.esdeImportDialogControl.visible
            }, 3000, "o clique real não abriu o diálogo raiz")
            verify(shell.esdeImportDialogControl.modal === true,
                   "o diálogo raiz precisa continuar modal")
        }

        /// No diálogo raiz o campo É o estado (o campo `esdeImportSourceField` lê
        /// `esdeImportSourceField.text`, não uma propriedade), então não há propagação
        /// a conferir além da própria escrita.
        function escreverRaiz(nome, texto) {
            const campo = namedRaiz(nome)
            verify(campo !== null, "raiz: o controle '" + nome + "' não está no corpo")
            if (campo.text === texto)
                campo.text = ""
            campo.text = texto
            until(function() { return String(campo.text) === texto }, 3000,
                  "raiz: o texto '" + texto + "' não ficou no campo '" + nome + "'")
            return campo
        }

        function examinarRaiz(alavanca, sufixo) {
            escreverRaiz("theme-import-esde-source", origem(alavanca, sufixo))
            until(function() {
                const botao = namedRaiz("theme-import-esde-inspect")
                return botao !== null && botao.enabled === true
            }, 3000, "raiz: 'Examinar' não habilitou com a origem informada")
            const alvo = namedRaiz("theme-import-esde-inspect")
            mouseClick(alvo, alvo.width / 2, alvo.height / 2, Qt.LeftButton)
        }

        function escreverNomeRaiz(sufixo) {
            escreverRaiz("theme-import-esde-name", "Tema raiz " + sufixo)
        }

        function importarRaiz() {
            until(function() {
                const botao = namedRaiz("theme-import-esde-apply")
                return botao !== null && botao.enabled === true
            }, 6000, "raiz: 'Importar' não habilitou com esquema e nome")
            const alvo = namedRaiz("theme-import-esde-apply")
            mouseClick(alvo, alvo.width / 2, alvo.height / 2, Qt.LeftButton)
        }

        /// Leitura do estado neutro na rota raiz, com a testemunha no log.
        function verificarEstadoRaizNeutro(tag) {
            observarRaiz(tag)
            verify(shell.esdeImportSchemes.length === 0,
                   "a rota raiz guardou " + shell.esdeImportSchemes.length
                   + " esquemas de um pedido encerrado")
            verify(shell.esdeImportNotice === "",
                   "a rota raiz guardou aviso de um pedido encerrado: '"
                   + shell.esdeImportNotice + "'")
            verify(shell.esdeImportBusy === false,
                   "a bandeira da rota raiz não está baixada com nada em voo")
        }

        /// `notify` escreve em `shell.lastRequest`, estado GLOBAL do shell que o
        /// `feedbackTimer` limpa cinco segundos depois. Entre cenas, o texto da cena
        /// 07 ainda pode estar na tela, e aí o `toast=1` da cena 09 não diria nada
        /// sobre o apply tardio dela — diria algo sobre a jornada. Medido na corrida
        /// anterior: `raiz-antes-do-escape` (cena 08, onde nenhum apply acontece) já
        /// registrou `toast=1`. A cena espera o próprio produto desarmar o aviso antes
        /// de clicar, então o que se mede passa a ser a transição, e a ausência depois
        /// do fechamento volta a ser uma afirmação sobre este apply.
        function semAvisoDeImportacaoNaTela(tag) {
            until(function() {
                return shell.lastRequest !== "Tema ES-DE importado."
            }, 12000, "o aviso da cena anterior nunca saiu da tela: sem esse chão o "
                      + "testemunho '" + tag + "' não distingue o apply desta cena do "
                      + "notify de outra ('" + shell.lastRequest + "')")
            observarRaiz(tag)
        }

        /// As linhas da rota raiz usam os CAMPOS do painel (`ocupado`, `esquemas`,
        /// `indice`, `aviso`) com o estado do `shell`: é o mesmo oráculo que as
        /// recusas das cenas 05/06 lêem, só que lido na outra superfície.
        function observarRaiz(tag) {
            const avisoImportacao = String(shell.lastRequest) === "Tema ES-DE importado."
            console.log("OBS|" + tag
                        + "|dialogo=" + (shell.esdeImportDialogControl.visible ? "aberto" : "fechado")
                        + "|pendentes=" + shell.pendingRequests
                        + "|ocupado=" + (shell.esdeImportBusy ? 1 : 0)
                        + "|esquemas=" + shell.esdeImportSchemes.length
                        + "|indice=" + shell.esdeImportSchemeIndex
                        + "|aviso=" + String(shell.esdeImportNotice).length
                        + "|toast=" + (avisoImportacao ? 1 : 0)
                        + "|origem=" + String(namedRaiz("theme-import-esde-source")
                                              ? namedRaiz("theme-import-esde-source").text : "").length)
        }

        // ------------------------------------------------------------------- opções

        /// Cada esquema que a ponte publicou precisa aparecer como opção real do
        /// `Repeater` (o `Repeater` de `esdeImportSchemes`): é o texto `modelData.scheme`
        /// que distingue a opção de um filtro que não casa com nada. O diálogo ES-DE
        /// NÃO tem caixa de sobrescrita (ao contrário do RetroFE): a testemunha de
        /// não-vacuidade aqui é dupla — a contagem casada TEM de bater com o array do
        /// estado E com o esperado da configuração (> 0).
        function opcoesDeEsquema(alavanca) {
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

        function verificarCadaEsquemaComoOpcaoSelecionavel(alavanca) {
            const radios = opcoesDeEsquema(alavanca)
            const esperado = harness.cfg.origens[alavanca].esquemas
            verify(esperado > 0, "a alavanca '" + alavanca
                   + "' não publica esquemas; nada seria contado")
            verify(radios.length === harness.panel.esdeImportSchemes.length,
                   "cada esquema publicado precisa aparecer como opção selecionável no "
                   + "diálogo (opções=" + radios.length + ", esquemas="
                   + harness.panel.esdeImportSchemes.length + ")")
            verify(radios.length === esperado,
                   "a ponte publicou " + esperado + " esquemas e apareceram "
                   + radios.length + " opções")
        }

        function verificarCadaEsquemaNaoReaparece() {
            const radios = []
            const nodes = bodyNodes()
            for (let index = 0; index < nodes.length; index++) {
                const node = nodes[index]
                if (node.checkable === true && effectivelyVisible(node))
                    radios.push(node)
            }
            verify(radios.length === 0,
                   "a reabertura mostrou " + radios.length
                   + " opções de esquema vindas de um pedido já encerrado")
        }

        function nomesDosEsquemas() {
            const nomes = []
            const lista = harness.panel.esdeImportSchemes
            for (let index = 0; index < lista.length; index++)
                nomes.push(String(lista[index] && lista[index].scheme
                                    ? lista[index].scheme : ""))
            return nomes.join("|")
        }

        function verificarCadaNomeTemMarcador(alavanca, nomes) {
            verify(nomes.length > 0, "nenhum esquema publicado; nada a comparar")
            const marcador = harness.cfg.origens[alavanca].prefixo
            const partes = nomes.split("|")
            for (let index = 0; index < partes.length; index++) {
                verify(partes[index].indexOf(marcador) === 0,
                       "o esquema " + index + " não veio da origem '" + alavanca + "': '"
                       + partes[index] + "'")
            }
        }

        // ------------------------------------------------------------------- testes

        /// 1 — a jornada dentro do shell, pela rota real: aba → botão → examinar →
        /// importar. Sem esta cena as cinco seguintes não teriam ponto de partida
        /// verificado, e o contrafactual da re-listagem (`GET /theme/list` depois do
        /// apply, lido pelo gate Python) não existiria.
        function test_01_a_rota_real_do_shell_examina_e_importa_como_editavel() {
            abrirAbaEditor()
            abrirDialogo()
            examinar("curta", "jornada")
            until(function() {
                return harness.panel.esdeImportBusy === false
                    && harness.panel.esdeImportSchemes.length
                        === harness.cfg.origens.curta.esquemas
            }, 8000, "a rota real não publicou os esquemas ES-DE no diálogo do shell")
            settleLayout("esquemas-publicados")
            verificarCadaEsquemaComoOpcaoSelecionavel("curta")
            verify(harness.panel.esdeImportSchemeIndex === 0,
                   "o examine precisa pré-selecionar o primeiro esquema (índice "
                   + harness.panel.esdeImportSchemeIndex + ")")
            escreverNome("jornada")
            const importar = named(bodyNodes(), "themeImportEsdeApply")
            until(function() { return importar.enabled === true }, 3000,
                  "'Importar como editável' não habilitou com esquema e nome")
            clicarControle("themeImportEsdeApply", "importar-jornada")
            until(function() {
                return harness.panel.esdeImportBusy === false
                    && String(harness.panel.esdeImportNotice).length > 0
            }, 8000, "a rota real respondeu 200 ao apply e nada apareceu no corpo")
            observar("jornada-importada")
            verify(named(bodyNodes(), "themeImportEsdeNotice") !== null,
                   "o aviso precisa aparecer no corpo do diálogo, não só no estado")
            verify(harness.panel.esdeImportNoticeIsError === false,
                   "o import bem-sucedido não pode anunciar erro: aviso='"
                   + harness.panel.esdeImportNotice + "' com erro="
                   + harness.panel.esdeImportNoticeIsError)
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou depois de importar")
        }

        /// 2 — a resposta chega depois do fechamento. Este é o vermelho da fatia:
        /// em `c4975979` o callback de `inspectEsdeImport` escrevia em cima de uma
        /// superfície fechada, sem conferir geração nenhuma.
        function test_02_fechar_com_pedido_em_voo_nao_recebe_a_resposta_tardia() {
            abrirAbaEditor()
            abrirDialogo()
            examinar("lenta", "tardia")
            until(function() { return harness.panel.esdeImportBusy === true }, 3000,
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
                return harness.panel.esdeImportBusy === false
                    && harness.panel.esdeImportSchemes.length === 0
                    && harness.panel.esdeImportNotice === ""
            }, 3000, "o fechamento não limpou o estado do importador")

            until(function() { return shell.pendingRequests === 0 }, 10000,
                  "a ponte nunca respondeu ao examine")
            observar("depois-da-resposta-tardia")
            verify(harness.panel.esdeImportSchemes.length === 0,
                   "a resposta tardia reescreveu " + harness.panel.esdeImportSchemes.length
                   + " esquemas num diálogo fechado — o aviso e a seleção renascem na "
                   + "reabertura com dados que ninguém pediu")
            verify(harness.panel.esdeImportNotice === "",
                   "a resposta tardia escreveu aviso num diálogo fechado: '"
                   + harness.panel.esdeImportNotice + "'")
            verify(harness.panel.esdeImportBusy === false,
                   "a resposta tardia mexeu na bandeira de ocupado")

            abrirDialogo()
            verificarCadaEsquemaNaoReaparece()
            verify(harness.panel.esdeImportNotice === "",
                   "a reabertura mostrou aviso '" + harness.panel.esdeImportNotice
                   + "' de um pedido já encerrado")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        /// 3 — a corrida fora de ordem, do jeito que o usuário realmente a produz
        /// (idêntica ao molde RetroFE): examinar, FECHAR (o
        /// `esdeImportDialog.onClosed` do painel roda `resetEsdeImport()`, que limpa a
        /// bandeira), reabrir e examinar outra origem. Os dois pedidos ficam em voo
        /// juntos (o `requestAction` só deduplica payload IDÊNTICO) e o anterior
        /// responde por último.
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
            verify(harness.panel.esdeImportBusy === false,
                   "o fechamento deixou a bandeira de ocupado armada: sem limpá-la o "
                   + "'Examinar' da cena seguinte nasceria desabilitado, e a corrida "
                   + "seria inatingível também para o usuário")
            abrirDialogo()
            examinar("rapida", "mais-novo")
            until(function() {
                return harness.panel.esdeImportBusy === false
                    && harness.panel.esdeImportSchemes.length
                        === harness.cfg.origens.rapida.esquemas
            }, 8000, "o examine mais novo não publicou seus esquemas")
            verificarCadaNomeTemMarcador("rapida", nomesDosEsquemas())
            const nomesNovos = nomesDosEsquemas()
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
            verify(harness.panel.esdeImportSchemes.length === harness.cfg.origens.rapida.esquemas,
                   "a resposta do pedido ANTERIOR substituiu o resultado do pedido mais "
                   + "novo: esquemas=" + harness.panel.esdeImportSchemes.length
                   + ", esperado " + harness.cfg.origens.rapida.esquemas)
            verify(nomesDosEsquemas() === nomesNovos,
                   "o conteúdo dos esquemas veio do pedido anterior: antes '" + nomesNovos
                   + "', agora '" + nomesDosEsquemas() + "'")
            verify(harness.panel.esdeImportBusy === false,
                   "a resposta anterior mexeu na bandeira de ocupado do pedido corrente")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        /// 4 — importar com resposta tardia: o aviso de sucesso e a re-listagem de
        /// temas são efeitos que só fazem sentido na superfície que pediu.
        function test_04_publicar_em_voo_e_fechar_nao_anuncia_sucesso_tardio() {
            abrirAbaEditor()
            abrirDialogo()
            examinar("lenta", "aplicar-tardio")
            until(function() {
                return harness.panel.esdeImportBusy === false
                    && harness.panel.esdeImportSchemes.length
                        === harness.cfg.origens.lenta.esquemas
            }, 8000, "o examine não publicou esquemas para a cena de aplicação")
            escreverNome("aplicar-tardio")
            until(function() {
                return named(bodyNodes(), "themeImportEsdeApply").enabled === true
            }, 3000, "'Importar como editável' não habilitou")
            clicarControle("themeImportEsdeApply", "publicar-tardio")
            until(function() { return harness.panel.esdeImportBusy === true }, 3000,
                  "o apply não marcou a requisição como em voo")
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "nenhum POST saiu para /theme/import/esde/apply")
            keyPress(Qt.Key_Escape)
            keyRelease(Qt.Key_Escape)
            until(function() { return harness.dialog.visible === false }, 3000,
                  "Escape real não fechou o diálogo durante a importação")
            verify(shell.pendingRequests >= 1,
                   "o apply respondeu ANTES do fechamento (pendentes="
                   + shell.pendingRequests + "): o cenário não exercitou atraso")
            until(function() { return shell.pendingRequests === 0 }, 12000,
                  "a ponte nunca respondeu ao apply")
            observar("depois-do-apply-tardio")
            verify(harness.panel.esdeImportNotice === "",
                   "a resposta tardia do apply anunciou '"
                   + harness.panel.esdeImportNotice + "' num diálogo fechado")
            verify(harness.panel.esdeImportBusy === false,
                   "a resposta tardia do apply mexeu na bandeira de ocupado")
            verify(harness.panel.esdeImportSchemes.length === 0,
                   "o estado do importador guarda " + harness.panel.esdeImportSchemes.length
                   + " esquemas depois de fechar o pedido")
            // O terceiro efeito do apply tardio é invisível na superfície: a
            // re-listagem de temas (`applyEsdeImport`, `refreshThemeList()`
            // → `GET /theme/list`). A prova é a LOG ORDENADA DA PONTE lida pelo gate
            // Python — nenhum GET /theme/list depois daquele POST — com a jornada do
            // test_01 como contrafactual.
            abrirDialogo()
            const aviso = named(bodyNodes(), "themeImportEsdeNotice")
            verify(aviso !== null, "o aviso precisa existir no corpo para ser medido")
            verify(aviso.visible === false,
                   "a reabertura exibiu o aviso de um pedido encerrado: '" + aviso.text + "'")
            verificarCadaEsquemaNaoReaparece()
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        /// 5 — a recusa por dedup com OUTRO pedido (payload diferente) já resolvido.
        /// O `requestAction` recusa payload idêntico já em voo devolvendo `false` sem
        /// disparar callback nenhuma; o pedido recusado é um não-acontecimento: a
        /// superfície tem de voltar ao que era antes do clique. A rota de examine
        /// (`inspectEsdeImport`) arma a bandeira ANTES de despachar e em
        /// `c4975979` não tinha rollback nenhum (o molde RetroFE,
        /// `inspectRetrofeImport()`, tinha) — o clique recusado deixava
        /// "Importando…" armado sem nenhum pedido seu por trás, e a resposta do
        /// pedido antigo (que a recusa tentava repetir) ainda reescrevia o
        /// resultado do pedido que produzia algo.
        function test_05_a_recusa_devolve_a_bandeira_e_nao_descarta_o_resultado_corrente() {
            abrirAbaEditor()
            abrirDialogo()
            examinar("revogada", "recusada")
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "o primeiro examine não saiu pela rota real")
            keyPress(Qt.Key_Escape)
            keyRelease(Qt.Key_Escape)
            until(function() { return harness.dialog.visible === false }, 3000,
                  "Escape real não fechou o diálogo com o examine em voo")
            abrirDialogo()
            examinar("rapida", "recusa-nova")
            until(function() {
                return harness.panel.esdeImportBusy === false
                    && harness.panel.esdeImportSchemes.length
                        === harness.cfg.origens.rapida.esquemas
            }, 8000, "o examine de payload DIFERENTE não publicou seus esquemas — sem "
                   + "resultado corrente a recusa não teria o que preservar")
            escrever("themeImportEsdeSource", origem("revogada", "recusada"))
            until(function() {
                return named(bodyNodes(), "themeImportEsdeInspect").enabled === true
            }, 3000, "'Examinar' não habilitou com a repetição digitada (ocupado="
                   + harness.panel.esdeImportBusy + ")")
            clicarControle("themeImportEsdeInspect", "repetir-origem-do-anterior")
            observar("instante-da-recusa-com-outro-pedido-resolvido")
            verify(shell.pendingRequests >= 1,
                   "não havia nenhum pedido em voo no instante da recusa (pendentes="
                   + shell.pendingRequests + "): sem voo não há dedup, e a cena "
                   + "exerceitou outra coisa")
            verify(shell.pendingRequests === 1,
                   "o clique recusado NÃO foi recusado: saiu um SEGUNDO pedido pela "
                   + "ponte (pendentes=" + shell.pendingRequests + ")")
            verify(harness.panel.esdeImportBusy === false,
                   "a recusa deixou a bandeira ARMADA: 'Importando…' sobre um pedido "
                   + "que a ponte nunca viu. A correção tem de devolver a bandeira ao "
                   + "valor de antes do clique (`ocupadoAntes`, como no par "
                   + "`*RetrofeImport()`), não deixá-la no `true` que o despacho "
                   + "armou")
            until(function() { return shell.pendingRequests === 0 }, 12000,
                  "a ponte nunca respondeu ao examine antigo")
            observar("depois-da-resposta-do-recusado")
            verify(harness.panel.esdeImportSchemes.length === harness.cfg.origens.rapida.esquemas,
                   "a resposta do pedido que apenas foi REPETIDO (e recusado) "
                   + "substituiu o resultado do pedido corrente: esquemas="
                   + harness.panel.esdeImportSchemes.length + ", esperado "
                   + harness.cfg.origens.rapida.esquemas)
            verify(nomesDosEsquemas().indexOf(harness.cfg.origens.rapida.prefixo) === 0,
                   "o conteúdo dos esquemas não veio mais do pedido corrente: '"
                   + nomesDosEsquemas() + "'")
            verify(harness.panel.esdeImportNoticeIsError === false,
                   "a recusa não pode alegar um erro que não aconteceu: aviso='"
                   + harness.panel.esdeImportNotice + "' com erro="
                   + harness.panel.esdeImportNoticeIsError)
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        /// 6 — a MESMA origem pedida duas vezes, com a primeira já REVOGADA pelo
        /// fechamento, e nada mais despachado no meio. A superfície tem de acabar
        /// OCIOSA e utilizável: o clique recusado arma a bandeira no despacho e, sem
        /// rollback do molde RetroFE, quem a abaixa é a resposta do pedido revogado —
        /// que ainda por cima reabre estado. É o pino contra a correção que escreve
        /// `true` sempre: se a recusa rearma o que o fechamento baixou, `pendentes=0`
        /// com bandeira armada congela o diálogo para sempre.
        function test_06_a_repeticao_recusada_com_pedido_revogado_nao_trava_o_dialogo() {
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
            escrever("themeImportEsdeSource", origem("revogada", "revogada"))
            until(function() {
                return named(bodyNodes(), "themeImportEsdeInspect").enabled === true
            }, 3000, "'Examinar' não reabilitou depois do fechamento (ocupado="
                   + harness.panel.esdeImportBusy + "): sem isso a repetição seria "
                   + "inatingível também para o usuário")
            clicarControle("themeImportEsdeInspect", "repetir-revogada")
            observar("instante-da-recusa-com-pedido-revogado")
            verify(shell.pendingRequests >= 1,
                   "o examine em voo já tinha respondido quando a repetição foi "
                   + "clicada (pendentes=" + shell.pendingRequests + "): nada aqui "
                   + "exercitou payload idêntico recusado")
            until(function() { return shell.pendingRequests === 0 }, 12000,
                  "a ponte nunca respondeu ao examine em voo")
            verificarCadaEsquemaNaoReaparece()
            verify(harness.panel.esdeImportBusy === false,
                   "o diálogo ficou preso em 'Importando…': com o pedido revogado "
                   + "nada mais vai abaixar a bandeira")
            verify(harness.panel.esdeImportSchemes.length === 0,
                   "a resposta de um pedido revogado reabriu estado no diálogo "
                   + "reaberto: " + harness.panel.esdeImportSchemes.length + " esquemas")
            verify(harness.panel.esdeImportNotice === "",
                   "a recusa/pedido revogado anunciou alguma coisa: '"
                   + harness.panel.esdeImportNotice + "'")
            verify(harness.panel.esdeImportNoticeIsError === false,
                   "a recusa não pode alegar um erro que não aconteceu (erro="
                   + harness.panel.esdeImportNoticeIsError + ", aviso='"
                   + harness.panel.esdeImportNotice + "')")
            verify(named(bodyNodes(), "themeImportEsdeInspect").enabled === true,
                   "com origem preenchida e nada em voo o 'Examinar' tem de estar "
                   + "disponível: o usuário precisa conseguir continuar sem fechar")
            harness.dialog.close()
            until(function() { return harness.dialog.visible === false }, 3000,
                  "o diálogo não fechou ao fim da cena")
        }

        /// 7 — a CONTRAFACTUAL da rota raiz, e o chão das três cenas seguintes: o
        /// botão real da seção Sistema abre o diálogo, o examine publica esquemas de
        /// verdade e o apply tardece um aviso de sucesso. Sem esta as cenas 08/09/10
        /// provariam apenas que uma resposta chegou a uma superfície que não existia:
        /// aqui o atraso é curto e tudo o que as outras negam TEM de acontecer.
        function test_07_a_rota_raiz_examina_e_importa_com_o_aviso_de_sucesso() {
            abrirDialogoRaiz()
            examinarRaiz("curta", "raiz-jornada")
            until(function() {
                return shell.esdeImportBusy === false
                    && shell.esdeImportSchemes.length === harness.cfg.origens.curta.esquemas
            }, 8000, "o examine da rota raiz não publicou os esquemas da ponte")
            const radios = []
            const nodes = nodesRaiz()
            for (let index = 0; index < nodes.length; index++)
                if (nodes[index].checkable === true && effectivelyVisible(nodes[index]))
                    radios.push(nodes[index])
            verify(radios.length === harness.cfg.origens.curta.esquemas,
                   "cada esquema publicado precisa aparecer como opção selecionável no "
                   + "diálogo raiz (opções=" + radios.length + ", esquemas="
                   + shell.esdeImportSchemes.length + ")")
            escreverNomeRaiz("jornada")
            semAvisoDeImportacaoNaTela("raiz-antes-do-apply-da-jornada")
            importarRaiz()
            /// O oráculo de "o callback rodou" é o FECHAMENTO (`esdeImportDialog.close()`), não
            /// `lastRequest != ""`: este último poderia casar com um aviso de cena
            /// anterior e a contrafactual nasceria antes do apply aterrassar.
            until(function() {
                return shell.esdeImportDialogControl.visible === false
            }, 10000, "o apply bem-sucedido fecha o diálogo raiz (`esdeImportDialog.close()`)")
            observarRaiz("raiz-jornada")
            verify(shell.lastRequest === "Tema ES-DE importado.",
                   "o aviso de sucesso da rota raiz mudou: '" + shell.lastRequest
                   + "' — a cena 09 nega este mesmo texto, então ele tem de ser este")
            verify(shell.esdeImportBusy === false,
                   "o apply deixou a bandeira armada depois do sucesso")
        }

        /// 8 — fechar a rota raiz com o examine em voo: a resposta que chega depois
        /// do `onClosed` (`esdeImportDialog.onClosed`) encontra `shell.esdeImport*` limpos e
        /// assim os deve deixar. Em `c4975979` o callback de sucesso do examine da
        /// raiz escrevia por cima.
        function test_08_fechar_a_rota_raiz_com_pedido_em_voo_nao_recebe_a_resposta_tardia() {
            abrirDialogoRaiz()
            examinarRaiz("lenta", "raiz-tardia")
            until(function() { return shell.esdeImportBusy === true }, 3000,
                  "o examine raiz não marcou a requisição como em voo")
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "nenhuma requisição saiu pela rota raiz")
            observarRaiz("raiz-antes-do-escape")
            keyPress(Qt.Key_Escape)
            keyRelease(Qt.Key_Escape)
            until(function() {
                return shell.esdeImportDialogControl.visible === false
            }, 3000, "Escape real não fechou o diálogo raiz com o examine em voo")
            verify(shell.pendingRequests >= 1,
                   "a resposta chegou ANTES do fechamento (pendentes="
                   + shell.pendingRequests + "): nada aqui exercitou atraso")
            until(function() {
                return shell.esdeImportBusy === false
                    && shell.esdeImportSchemes.length === 0
                    && shell.esdeImportNotice === ""
            }, 3000, "o fechamento da rota raiz não limpou o estado")
            until(function() { return shell.pendingRequests === 0 }, 10000,
                  "a ponte nunca respondeu ao examine raiz")
            observarRaiz("raiz-depois-da-resposta-tardia")
            verify(shell.esdeImportSchemes.length === 0,
                   "a resposta tardia reescreveu " + shell.esdeImportSchemes.length
                   + " esquemas num diálogo raiz fechado: a reabertura mostraria dados "
                   + "que ninguém pediu")
            verify(shell.esdeImportSchemeIndex === -1,
                   "a resposta tardia rearmou a seleção do diálogo fechado (indice="
                   + shell.esdeImportSchemeIndex + ")")
            verify(shell.esdeImportNotice === "",
                   "a resposta tardia escreveu aviso num diálogo raiz fechado: '"
                   + shell.esdeImportNotice + "'")
            verify(shell.esdeImportBusy === false,
                   "a resposta tardia mexeu na bandeira de ocupado da rota raiz")
            abrirDialogoRaiz()
            const reaberto = []
            const nodes = nodesRaiz()
            for (let index = 0; index < nodes.length; index++)
                if (nodes[index].checkable === true && effectivelyVisible(nodes[index]))
                    reaberto.push(nodes[index])
            verify(reaberto.length === 0,
                   "a reabertura do diálogo raiz mostrou " + reaberto.length
                   + " opções de um pedido já encerrado")
            shell.esdeImportDialogControl.close()
            until(function() {
                return shell.esdeImportDialogControl.visible === false
            }, 3000, "o diálogo raiz não fechou ao fim da cena")
        }

        /// 9 — o apply tardio na rota raiz: o único efeito visível ali é o `notify`
        /// (o `root.notify` do apply) e o reabrir de estado. A cena 07 acabou de mostrar que
        /// com a superfície aberta o texto aparece; aqui, com ela fechada, ele não
        /// pode aparecer — anúncio de sucesso de uma importação que o usuário
        /// abandonou é exatamente o que o contrato proíbe.
        function test_09_aplicar_na_rota_raiz_em_voo_e_fechar_nao_anuncia_sucesso_tardio() {
            abrirDialogoRaiz()
            examinarRaiz("lenta", "raiz-aplicar")
            until(function() {
                return shell.esdeImportBusy === false
                    && shell.esdeImportSchemes.length === harness.cfg.origens.lenta.esquemas
            }, 10000, "o examine raiz não publicou os esquemas antes do apply")
            escreverNomeRaiz("aplicar-tardio")
            // Chão do testemunho: sem o aviso da cena 07 fora da tela, o `toast=0`
            // depois do fechamento não diria nada sobre ESTE apply.
            semAvisoDeImportacaoNaTela("raiz-antes-do-apply-tardio")
            importarRaiz()
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "o apply da rota raiz não saiu pela ponte")
            observarRaiz("raiz-antes-do-escape-do-apply")
            keyPress(Qt.Key_Escape)
            keyRelease(Qt.Key_Escape)
            until(function() {
                return shell.esdeImportDialogControl.visible === false
            }, 3000, "Escape real não fechou o diálogo raiz com o apply em voo")
            verify(shell.pendingRequests >= 1,
                   "o apply respondeu ANTES do fechamento (pendentes="
                   + shell.pendingRequests + "): a cena não exercitou tardiança")
            until(function() { return shell.pendingRequests === 0 }, 12000,
                  "a ponte nunca respondeu ao apply raiz")
            verificarEstadoRaizNeutro("raiz-depois-do-apply-tardio")
            verify(shell.lastRequest !== "Tema ES-DE importado.",
                   "a resposta tardia do apply anunciou sucesso numa superfície fechada: "
                   + "o shell mostra '" + shell.lastRequest + "' — e a cena 07 provou, na "
                   + "mesma rota e com o mesmo texto, que ele só nasce do callback do "
                   + "apply com a superfície aberta")
            verify(shell.esdeImportSchemes.length === 0,
                   "o apply tardio reabriu estado no diálogo raiz: "
                   + shell.esdeImportSchemes.length + " esquemas")
            verify(shell.esdeImportBusy === false,
                   "a resposta tardia mexeu na bandeira de ocupado da rota raiz")
        }

        /// 10 — a recusa na rota raiz, o caso que congela a superfície: o clique com
        /// payload idêntico em voo é devolvido por `actionIsPending` sem callback, e
        /// o clique em `esdeInspectButton` já armou `esdeImportBusy = true`. Com o
        /// pedido revogado pelo
        /// fechamento nada mais abaixa a bandeira — o diálogo reaberto fica preso em
        /// "Importando…" para sempre, com os dois botões desabilitados. A correção é
        /// a mesma do molde: devolver a bandeira ao `ocupadoAntes`.
        function test_10_a_recusa_na_rota_raiz_devolve_a_bandeira_e_nao_trava_o_dialogo() {
            abrirDialogoRaiz()
            examinarRaiz("revogada", "raiz-recusada")
            until(function() { return shell.pendingRequests >= 1 }, 3000,
                  "o primeiro examine raiz não saiu pela rota real")
            keyPress(Qt.Key_Escape)
            keyRelease(Qt.Key_Escape)
            until(function() {
                return shell.esdeImportDialogControl.visible === false
            }, 3000, "Escape real não fechou o diálogo raiz com o examine em voo")
            abrirDialogoRaiz()
            escreverRaiz("theme-import-esde-source", origem("revogada", "raiz-recusada"))
            until(function() {
                const botao = namedRaiz("theme-import-esde-inspect")
                return botao !== null && botao.enabled === true
            }, 3000, "raiz: o 'Examinar' não reabilitou depois do fechamento — sem isso "
                   + "a repetição seria inatingível também para o usuário")
            const alvo = namedRaiz("theme-import-esde-inspect")
            mouseClick(alvo, alvo.width / 2, alvo.height / 2, Qt.LeftButton)
            observarRaiz("instante-da-recusa-na-raiz")
            verify(shell.pendingRequests >= 1,
                   "não havia pedido em voo no instante da recusa (pendentes="
                   + shell.pendingRequests + "): sem voo não há dedup")
            verify(shell.pendingRequests === 1,
                   "o clique recusado NÃO foi recusado: saiu um SEGUNDO pedido pela "
                   + "ponte (pendentes=" + shell.pendingRequests + ")")
            verify(shell.esdeImportBusy === false,
                   "a recusa deixou a bandeira ARMADA na rota raiz: nada mais a abaixa "
                   + "depois do fechamento, e o diálogo congela em 'Importando…' — a "
                   + "correção tem de devolver a bandeira ao valor de antes do clique")
            until(function() { return shell.pendingRequests === 0 }, 12000,
                  "a ponte nunca respondeu ao examine em voo")
            verificarEstadoRaizNeutro("depois-da-resposta-do-recusado-na-raiz")
            verify(namedRaiz("theme-import-esde-inspect").enabled === true,
                   "com origem preenchida e nada em voo o 'Examinar' raiz tem de estar "
                   + "disponível: o usuário precisa conseguir continuar sem fechar")
            shell.esdeImportDialogControl.close()
            until(function() {
                return shell.esdeImportDialogControl.visible === false
            }, 3000, "o diálogo raiz não fechou ao fim da cena")
        }
    }
}
