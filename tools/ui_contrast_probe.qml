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

    // Estar dentro dos limites da superfície não basta, e estar PARCIALMENTE
    // dentro tambem nao: um texto cortado pela borda de um ScrollView so mostra
    // a fatia visivel, e medir a caixa inteira mede o vazio junto. Foi assim que
    // "Parar transmissao" — em y=502 dentro de um Flickable de 518 de altura,
    // com 48 de altura — saiu como contraste 1,19 contra area quase toda cortada.
    //
    // Em vez de aceitar ou rejeitar, esta funcao INTERSECTA a caixa com o
    // viewport de cada ancestral que recorta, e devolve so o pedaco que a tela
    // realmente desenha. Caixa que sobra degenerada e descartada.
    function visibleRect(item, surface) {
        const origin = item.mapToItem(surface, 0, 0)
        let left = origin.x
        let top = origin.y
        let right = origin.x + item.width
        let bottom = origin.y + item.height
        let ancestor = item.parent
        let guard = 0
        while (ancestor && guard < 60) {
            if (ancestor.clip === true) {
                const corner = ancestor.mapToItem(surface, 0, 0)
                left = Math.max(left, corner.x)
                top = Math.max(top, corner.y)
                right = Math.min(right, corner.x + ancestor.width)
                bottom = Math.min(bottom, corner.y + ancestor.height)
            }
            ancestor = ancestor.parent
            guard += 1
        }
        return {"x": left, "y": top, "w": right - left, "h": bottom - top}
    }

    function walk(item, section, out, depth, page) {
        if (!item || depth > 40 || item.visible === false || item.opacity <= 0.05)
            return out
        if (isLegibleCandidate(item)) {
            const p = visibleRect(item, page)
            // Revelação PARCIAL não é promessa de legibilidade. "Parar
            // transmissão" tem 48 px de altura e a borda do ScrollView deixava
            // 12 visíveis — a fatia que sobra fica acima dos glifos, e medi-la
            // acusava 1,01 contra um branco vazio. Ou o controle aparece
            // inteiro o bastante para ser lido, ou não entra na conta.
            const revealed = (p.w * p.h) / Math.max(1, item.width * item.height)
            // Descarta o que caiu fora da janela ou sobrou degenerado: medir
            // pixel que não existe produziria acusação inventada.
            if (revealed >= 0.6 && p.w > 2 && p.h > 2 && p.x >= 0 && p.y >= 0
                    && p.x + p.w <= page.width && p.y + p.h <= page.height) {
                out.push({
                    "section": section,
                    "text": String(item.text).substring(0, 40),
                    "pixelSize": item.font.pixelSize || 0,
                    "bold": item.font.bold === true,
                    "x": Math.round(p.x), "y": Math.round(p.y),
                    "w": Math.round(p.w), "h": Math.round(p.h),
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
