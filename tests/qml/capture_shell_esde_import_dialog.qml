// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// RC-01 (4ª fatia) — capturas do diálogo "Importar tema ES-DE" do SHELL.
//
// Prova de comportamento é `tests/qml/check_shell_esde_import_dialog_journey.qml`
// (teclas reais, foco alcançado, retângulo inteiro na banda), executada por
// `tests/integration/test_ui_shell_esde_import_dialog.py`. Este arquivo SÓ produz
// imagem: nenhuma asserção de contrato vive aqui.
//
// O que é local, e por que a cena não precisa de nada além disso: a ponte é o
// servidor em loopback que o teste Python levanta — o mesmo `/status` que publica
// os contratos reais de `desktop_contracts`, a mesma rota real de
// `theme.import.esde.inspect`/`apply`. Nada é baixado da rede, nenhum dado de
// usuário aparece aqui, e o único caminho escrito é o `--output-dir=` pedido pelo
// teste. As capturas provam geometria offscreen, não a release instalada no host.
//
// Cada cenário roda como um processo separado (a ponte responde de forma diferente
// a cada um), e por isso a lista de cenas depende de `--cenario=`:
//   tipico        → 1-compacto-aberto, 2-compacto-24-esquemas
//   nomes-longos  → 3-compacto-nome-focado
//   aviso-longo   → 4-compacto-recusa-com-aviso, 5-largo-recusa-com-aviso
//
// As cinco fases foram escolhidas para existirem NA FORMA ANTIGA e NA CORRIGIDA:
// cada espera é uma condição presente nas duas árvores (campo de origem, botão
// habilitado, contagem de esquemas, aviso no corpo, altura implícita do rótulo).
// Por isso a mesma cena documenta o vermelho e o verde sem duplicar nada.
//
// A origem, o esquema e o nome entram pelas propriedades do shell, e a ação é
// disparada por `clicked()` no controle real. Num cenário de captura isso é
// aceitável — e é exatamente o que a digitação produziria — porque a imagem não
// prova entrada: ela prova onde a tinta cai. A entrada real é medida no harness.
import QtQuick
import QtQuick.Controls
import "../../src/steamzero/ui/qml"

Main {
    id: shell
    visible: true
    width: 949
    height: 593
    // Fundo da cena: contra ele "imagem uniforme" deixa de ser imagem, no gate de
    // captura (`BACKGROUND` do teste). O shell pinta o tema por cima; o que o
    // contrato exige é tinta, não uma cor específica.
    color: "#071019"

    readonly property string outputDirectory: argument("--output-dir=", "/tmp")
    readonly property string cenario: argument("--cenario=", "tipico")

    property var cfg: ({})
    property var cenas: []
    property int captureIndex: 0
    property int phase: 0
    property int ticks: 0
    property int publicado: 0

    function argument(prefixo, fallback) {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; i++) {
            if (args[i].startsWith(prefixo))
                return args[i].slice(prefixo.length)
        }
        return fallback
    }

    function cenarioPara() {
        if (cenario === "nomes-longos")
            return ["3-compacto-nome-focado"]
        if (cenario === "aviso-longo")
            return ["4-compacto-recusa-com-aviso", "5-largo-recusa-com-aviso"]
        return ["1-compacto-aberto", "2-compacto-24-esquemas"]
    }

    // ------------------------------------------------------------------- utilidade

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

    function dialogNodes() {
        const out = []
        const dialog = shell.esdeImportDialogControl
        if (!dialog)
            return out
        descendants(dialog.contentItem, out, 0)
        if (dialog.footer)
            descendants(dialog.footer, out, 0)
        return out
    }

    function byObjectName(name) {
        const nodes = dialogNodes()
        for (let index = 0; index < nodes.length; index++)
            if (nodes[index].objectName === name)
                return nodes[index]
        return null
    }

    /// Região do rodapé: o `footer` declarado, ou — na forma antiga, sem rodapé —
    /// a linha de ações onde vive o botão Importar. A mesma região medida nas duas
    /// árvores é o que faz a geografia ser comparável antes e depois.
    function footerRegion() {
        const dialog = shell.esdeImportDialogControl
        if (!dialog)
            return null
        if (dialog.footer)
            return dialog.footer
        const apply = byObjectName("theme-import-esde-apply")
        return apply ? apply.parent : null
    }

    function bodyRegion() {
        const dialog = shell.esdeImportDialogControl
        if (!dialog || !dialog.contentItem)
            return null
        return dialog.contentItem.contentItem
            ? dialog.contentItem.contentItem : dialog.contentItem
    }

    function rectInWindow(item) {
        if (!item)
            return "ausente"
        const espaco = shell.captureSpace()
        const topLeft = item.mapToItem(espaco, 0, 0)
        const bottomRight = item.mapToItem(espaco, item.width, item.height)
        return Math.round(topLeft.x) + "," + Math.round(topLeft.y) + ","
            + Math.round(bottomRight.x - topLeft.x) + ","
            + Math.round(bottomRight.y - topLeft.y)
    }

    function geometryLine(nome) {
        const dialog = shell.esdeImportDialogControl
        const alvo = shell.captureTarget()
        return "GEOMETRIA|" + nome
            + "|capturado=" + (alvo ? alvo.objectName : "nenhum")
            + "|janela=" + Math.round(alvo.width) + "x" + Math.round(alvo.height)
            + "|moldura=" + rectInWindow(dialog ? dialog.background : null)
            + "|corpo=" + rectInWindow(bodyRegion())
            + "|rodape=" + rectInWindow(footerRegion())
            + "|acao=" + rectInWindow(byObjectName("theme-import-esde-apply"))
            + "|esquemas=" + shell.esdeImportSchemes.length
            + "|aviso=" + shell.esdeImportNotice.length
            + "|cenario=" + shell.cenario
    }

    /// Espera por condição observável com limite: estourar o limite é falha
    /// explícita (exit 1), não captura silenciosa pela metade.
    function until(condition) {
        if (condition()) {
            shell.ticks = 0
            return true
        }
        shell.ticks += 1
        if (shell.ticks > 400) {
            console.log("TIMEOUT na fase " + shell.phase + " do cenário " + shell.cenario)
            Qt.exit(1)
        }
        return false
    }

    /// Duas amostras iguais de geometria: estabilização por observable, não por
    /// intervalo fixo. Um quadro intermediário do layout não vira evidência.
    function signature() {
        const dialog = shell.esdeImportDialogControl
        if (!dialog || !dialog.visible || !dialog.background)
            return ""
        const apply = byObjectName("theme-import-esde-apply")
        if (!apply || apply.width <= 0 || apply.height <= 0)
            return ""
        return Math.round(dialog.background.width) + "x"
                + Math.round(dialog.background.height) + "/"
                + rectInWindow(footerRegion()) + "/" + shell.esdeImportSchemes.length
    }

    function settled() {
        const atual = signature()
        if (atual === "" || atual !== shell.ultimaAssinatura) {
            shell.ultimaAssinatura = atual
            shell.ticks = 0
            return false
        }
        shell.ticks = 0
        return true
    }

    property string ultimaAssinatura: ""

    /// A cadeia abaixo da janela, medida nesta bancada (Qt 6.11.2, offscreen):
    ///   shell.contentItem → QQuickContentItem("ApplicationWindow")
    ///   .parent           → QQuickControl("ApplicationWindowContentControl")
    ///   .parent           → QQuickRootItem("Main")  ← capturável, e o único item
    ///     que contém a janela inteira E o QQuickOverlay onde o Popup é pendurado.
    /// `contentItem.grabToImage` não falha por faltar o método — ele existe e é
    /// reportado como definido; falha por "item has no QML engine", sem imagem e
    /// sem sintoma, e a cena ficava na fase do grab até o limite global. Subir até
    /// o ancestral topo dispensa copiar a cadeia acima: se o Qt inserir ou remover
    /// um elo, a captura continua sendo a janela, e o `ALVO|` impresso junto de
    /// cada PNG diz qual item a produziu.
    function captureTarget() {
        let atual = shell.contentItem
        if (!atual)
            return null
        while (atual.parent)
            atual = atual.parent
        return atual
    }

    /// Região usada como espaço de coordenadas das capturas: o mesmo item que é
    /// capturado. Geometria e imagem compartilham origem, senão o `ação=` impresso
    /// não descreve o pixel publicado.
    function captureSpace() {
        return shell.captureTarget()
    }

    /// `grabToImage` é assíncrono: a fase vira 500 (grab em andamento, que nenhum
    /// ramo trata) até a imagem sair — medido na 3ª fatia, onde a ausência disso
    /// produziu capturas a mais com `undefined-<rotulo>.png` e rc=1.
    function capture(proximaFase) {
        shell.phase = 500
        const alvo = shell.captureTarget()
        if (!alvo) {
            console.log("FALHA a janela não expõe nenhum item capturável")
            Qt.exit(1)
            return
        }
        console.log("ALVO|" + shell.cenas[shell.captureIndex] + "|" + alvo.toString()
                    + "|" + Math.round(alvo.width) + "x" + Math.round(alvo.height))
        alvo.grabToImage(function(result) {
            const nome = shell.cenas[shell.captureIndex]
            const path = shell.outputDirectory + "/" + nome + ".png"
            // Uma única chamada: `saveToFile` escreve e devolve o resultado, e
            // chamá-la duas vezes publicaria a mesma imagem duas vezes enquanto o
            // contador diria outra coisa.
            const publicado = result.saveToFile(path)
            console.log((publicado ? "CAPTURADO " : "FALHA ") + path)
            console.log(shell.geometryLine(nome))
            shell.captureIndex += 1
            if (publicado)
                shell.publicado += 1
            shell.phase = proximaFase
        }, Qt.size(Math.round(alvo.width), Math.round(alvo.height)))
    }

    /// Conteúdo pelas propriedades do shell — o mesmo canal que a digitação usa.
    function examinar() {
        const source = byObjectName("theme-import-esde-source")
        if (!source)
            return false
        source.text = "/fixture/esde/tema-" + shell.cenario
        const inspect = byObjectName("theme-import-esde-inspect")
        if (!inspect || !inspect.enabled)
            return false
        inspect.clicked()
        return true
    }

    function preencherNome() {
        const field = byObjectName("theme-import-esde-name")
        if (!field)
            return false
        field.text = "Tema ES-DE do shell"
        return true
    }

    function publicar() {
        const apply = byObjectName("theme-import-esde-apply")
        if (!apply || !apply.enabled)
            return false
        apply.clicked()
        return true
    }

    Timer {
        id: maquina
        interval: 20
        running: true
        repeat: true
        onTriggered: {
            if (shell.phase === 0) {
                shell.cenas = shell.cenarioPara()
                const request = new XMLHttpRequest()
                request.open("GET", Qt.resolvedUrl("../../build/ui-shell-esde-import-dialog.json"), false)
                request.send()
                if (request.status !== 0 && request.status !== 200) {
                    console.log("FALHA leitura da configuração efêmera da bridge")
                    Qt.exit(1)
                }
                shell.cfg = JSON.parse(request.responseText)
                shell.apiUrl = shell.cfg.apiUrl
                shell.apiToken = shell.cfg.apiToken
                shell.refreshStatus("")
                shell.phase = 10
                return
            }
            if (shell.phase === 10) {
                if (!shell.until(function() {
                        return shell.uiContracts !== undefined
                            && shell.uiContracts.byId !== undefined
                            && shell.uiContracts.byId["theme.import.esde.inspect"] !== undefined
                    }))
                    return
                shell.sectionIndex = shell.sectionIndexOf("system")
                shell.phase = 20
                return
            }
            if (shell.phase === 20) {
                if (!shell.until(function() {
                        return shell.responsiveContent.currentIndex === shell.sectionIndex
                    }))
                    return
                shell.esdeImportDialogControl.open()
                shell.phase = 30
                return
            }
            if (shell.phase === 30) {
                if (!shell.until(function() { return shell.esdeImportDialogControl.visible === true }))
                    return
                if (shell.cenas[0] === "1-compacto-aberto") {
                    if (shell.settled())
                        shell.capture(40)
                    return
                }
                shell.phase = 40
                return
            }
            if (shell.phase === 40) {
                if (shell.examinar())
                    shell.phase = 50
                return
            }
            if (shell.phase === 50) {
                const esperado = Number(shell.cfg.esquemas)
                if (!shell.until(function() { return shell.esdeImportSchemes.length === esperado }))
                    return
                shell.phase = 60
                return
            }
            if (shell.phase === 60) {
                if (shell.preencherNome())
                    shell.phase = 70
                return
            }
            // 24 esquemas de 48 px: é aqui que o corpo passa da banda.
            if (shell.phase === 70) {
                if (shell.cenas[shell.captureIndex] === "2-compacto-24-esquemas") {
                    if (shell.settled())
                        shell.capture(80)
                    return
                }
                shell.phase = 80
                return
            }
            // Foco PROGRAMÁTICO de propósito: ele mostra o rodapé com o corpo ainda
            // acima da dobra, e é exatamente por isso que a imagem não prova rolagem
            // — revelar o destino focado é caminho de tecla real, medido no harness
            // (test_03), não aqui.
            if (shell.phase === 80) {
                if (shell.cenas[shell.captureIndex] === "3-compacto-nome-focado") {
                    const field = shell.byObjectName("theme-import-esde-name")
                    if (field && field.activeFocus !== true)
                        field.forceActiveFocus(Qt.TabFocusReason)
                    if (shell.until(function() { return field && field.activeFocus === true })) {
                        if (shell.settled())
                            shell.capture(90)
                    }
                    return
                }
                shell.phase = 90
                return
            }
            if (shell.phase === 90) {
                // Cenário sem recusa (publicação aceita): não há aviso a esperar, e
                // ficaria aqui até o limite do `until`. Se as cenas pedidas já saíram,
                // a jornada de captura terminou.
                if (shell.captureIndex >= shell.cenas.length) {
                    shell.phase = 120
                    return
                }
                if (shell.publicar())
                    shell.phase = 100
                return
            }
            if (shell.phase === 100) {
                if (!shell.until(function() { return shell.esdeImportNotice.length > 0 }))
                    return
                if (shell.settled())
                    shell.capture(110)
                return
            }
            if (shell.phase === 110) {
                if (shell.cenas[shell.captureIndex] === "5-largo-recusa-com-aviso") {
                    shell.width = 1280
                    shell.height = 800
                    if (shell.until(function() {
                            return Math.round(shell.width) === 1280
                                && shell.responsiveContent.width === 1280
                        })) {
                        if (shell.settled())
                            shell.capture(120)
                    }
                    return
                }
                shell.phase = 120
                return
            }
            if (shell.phase === 120) {
                console.log("capturas=" + shell.captureIndex + " de " + shell.cenas.length
                            + " (cenário " + shell.cenario + ", publicadas=" + shell.publicado + ")")
                Qt.exit(shell.captureIndex === shell.cenas.length
                        && shell.publicado === shell.cenas.length ? 0 : 1)
            }
        }
    }

    Timer {
        interval: 90000
        running: true
        onTriggered: {
            console.log("TIMEOUT geral na fase " + shell.phase + " do cenário "
                        + shell.cenario)
            Qt.exit(1)
        }
    }
}
