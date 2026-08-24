// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Sonda de contraste por PIXEL RENDERIZADO.
//
// A tentativa anterior adivinhava o fundo pela árvore de objetos ("o ancestral
// opaco mais próximo") e errava em Button com `background` próprio: o mesmo
// rótulo saía com razão 13,69 e 1,0 ao mesmo tempo. Adivinhar fundo pela árvore
// é o mesmo erro de classificar ação por forma.
//
// Aqui a sonda não opina sobre cor: captura o que a tela realmente desenhou e
// publica a caixa de cada texto. Quem calcula a razão é `ui_contrast_inventory`,
// lendo os pixels do PNG.
//
// Duas armadilhas já pagas por este repositório e respeitadas aqui:
//  - `grabToImage` exige frame de verdade; `onAfterRendering` é o sinal, não um
//    timer fixo (curto captura tela incompleta, longo esconde o problema);
//  - sair de dentro do callback de `grabToImage` derruba o processo por sinal
//    (causa do qmlReturncode=-11 de 2026-08-11), então a saída atravessa o
//    event loop.

import QtQuick
import "../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 1280
    height: 800

    property string outDir: "build/ui-contrast"
    property var rows: []
    property int cursor: -1
    property int frames: 0
    property bool busy: false
    property int pendingExitCode: 0
    //: Seções que não fecharam frame ou não devolveram captura. Ficam
    //: REGISTRADAS como não medidas: uma sonda que trava esconde o buraco, e
    //: uma que pula em silêncio inventa cobertura.
    property var unmeasured: []

    function isText(item) {
        return item.text !== undefined && item.font !== undefined
            && item.color !== undefined && String(item.text).trim().length > 0
    }

    // Só entra na conta o texto que o usuário realmente enxerga: invisível,
    // transparente ou de área nula não é promessa de legibilidade.
    function isLegibleCandidate(item) {
        return isText(item) && item.visible && item.opacity > 0.5
            && item.width > 1 && item.height > 1
    }

    // Estar dentro dos limites da superfície não basta: um texto rolado para
    // fora de um ScrollView continua posicionado, e simplesmente não é
    // desenhado. Medir a caixa dele mediria fundo vazio e acusaria contraste
    // 1,0 contra um texto que a tela nem mostrou.
    function isClippedAway(item) {
        // Mapeia sempre o ITEM ORIGINAL para o ancestral que recorta. A primeira
        // versao mapeava o ancestral intermediario, e por isso nunca via o caso
        // real: o contentItem de um Flickable comeca em (0,0) e cabe sempre,
        // enquanto o texto la dentro pode estar rolado muito abaixo do viewport.
        // Foi assim que "Clock da GPU", em y=709 dentro de um Flickable de 456
        // de altura, passou pela checagem e foi medido contra area vazia.
        let ancestor = item.parent
        let guard = 0
        while (ancestor && guard < 60) {
            if (ancestor.clip === true) {
                const topLeft = item.mapToItem(ancestor, 0, 0)
                if (topLeft.x + item.width <= 0 || topLeft.y + item.height <= 0
                        || topLeft.x >= ancestor.width || topLeft.y >= ancestor.height)
                    return true
            }
            ancestor = ancestor.parent
            guard += 1
        }
        return false
    }

    // Captura a SUPERFÍCIE do shell: um Item que pinta o próprio fundo opaco e
    // contém o conteúdo. Duas coisas que não funcionam e já custaram tentativa:
    // `window.contentItem` é recusado ("item has no QML engine"), e capturar a
    // página da seção devolve conteúdo sem fundo, achatado sobre preto de forma
    // não determinística. As caixas saem relativas à mesma superfície do PNG.
    function walk(item, section, out, depth, page) {
        if (!item || depth > 40 || item.visible === false || item.opacity <= 0.05)
            return out
        if (isLegibleCandidate(item) && !isClippedAway(item)) {
            const p = item.mapToItem(page, 0, 0)
            // Descarta o que caiu fora da janela: medir pixel que não existe
            // produziria acusação inventada.
            if (p.x >= 0 && p.y >= 0
                    && p.x + item.width <= page.width
                    && p.y + item.height <= page.height) {
                out.push({
                    "section": section,
                    "text": String(item.text).substring(0, 40),
                    "pixelSize": item.font.pixelSize || 0,
                    "bold": item.font.bold === true,
                    "x": Math.round(p.x), "y": Math.round(p.y),
                    "w": Math.round(item.width), "h": Math.round(item.height),
                    "image": section + ".png"
                })
            }
        }
        const kids = item.children || []
        for (let i = 0; i < kids.length; i++)
            walk(kids[i], section, out, depth + 1, page)
        return out
    }

    function requestExit(code) {
        pendingExitCode = code
        exitTimer.restart()
    }

    Timer {
        id: exitTimer
        interval: 0
        repeat: false
        onTriggered: Qt.exit(window.pendingExitCode)
    }

    function advance() {
        cursor += 1
        frames = 0
        busy = false
        if (cursor >= navigationSections.length) {
            watchdog.stop()
            // O PNG sai com alpha: a pagina nao pinta o proprio fundo, quem
            // pinta e um ancestral. Sem informar a cor de fundo do shell, o
            // analisador comporia sobre preto e mediria um fundo que a tela
            // nunca mostrou.
            console.log("CONTRAST-BACKGROUND " + String(window.backgroundColor))
            console.log("CONTRAST-UNMEASURED " + JSON.stringify(window.unmeasured))
            console.log("CONTRAST-ROWS " + JSON.stringify(window.rows))
            requestExit(0)
            return
        }
        sectionIndex = cursor
        watchdog.restart()
        // Offscreen a cena só fica suja quando algo pede desenho, e contar
        // `afterRendering` deixava sete das nove seções sem frame nenhum. O
        // próprio `grabToImage` agenda um passe de render e chama de volta
        // quando ele fecha, então é ele que dirige a captura. Os dois
        // `callLater` dão ao layout a chance de assentar antes.
        Qt.callLater(function() { Qt.callLater(window.captureCurrent) })
    }

    // Offscreen, `afterRendering` só dispara com a cena suja. Se um frame não
    // vier, ou se `grabToImage` não chamar de volta, a seção é registrada como
    // não medida e a sonda segue — travar não é resultado.
    Timer {
        id: watchdog
        interval: 6000
        repeat: false
        onTriggered: {
            const section = window.navigationSections[window.cursor]
            if (!section)
                return
            window.unmeasured.push({
                "section": section.id,
                "reason": window.busy ? "grabToImage não devolveu"
                                      : "nenhum frame renderizado"
            })
            window.busy = false
            Qt.callLater(window.advance)
        }
    }

    function captureCurrent() {
        if (busy || cursor < 0 || cursor >= navigationSections.length)
            return
        busy = true
        const section = navigationSections[cursor]
        const surface = shellSurfaceControl
        const page = responsiveContent.children[cursor]
        const found = walk(page, section.id, [], 0, surface)
        const ok = surface.grabToImage(function(result) {
            if (result === null || result.image.width === 0) {
                console.error("CONTRAST-FAIL imagem vazia em " + section.id)
                window.requestExit(1)
                return
            }
            if (!result.saveToFile(window.outDir + "/" + section.id + ".png")) {
                console.error("CONTRAST-FAIL saveToFile em " + section.id)
                window.requestExit(1)
                return
            }
            watchdog.stop()
            for (let i = 0; i < found.length; i++)
                window.rows.push(found[i])
            Qt.callLater(window.advance)
        })
        if (!ok) {
            console.error("CONTRAST-FAIL grabToImage recusou " + section.id)
            requestExit(1)
        }
    }

    Component.onCompleted: Qt.callLater(window.advance)
}
