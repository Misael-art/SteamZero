// SPDX-License-Identifier: GPL-3.0-or-later
//
// Contrato da página de jogo: ação desabilitada aparece com motivo, o foco não
// repousa nela e o direcional não para nela.
import QtQuick
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 900
    height: 500

    property int failures: 0
    property int checkIndex: 0
    property int firstFail: -1
    function check(condition, message) {
        checkIndex += 1
        if (!condition) {
            failures += 1
            if (firstFail < 0)
                firstFail = checkIndex
            console.error("FAIL #" + checkIndex + ": " + message)
        }
    }

    property var activatedIds: []

    LauncherGamePage {
        id: playable
        anchors.fill: parent
        model: ({
            "gameId": "celeste", "title": "Celeste", "platform": "Steam",
            "screenshotUrl": Qt.resolvedUrl("fixtures/cover.png"),
            "requirements": ["Controle compatível"],
            "controls": ["A · confirmar", "Analógico · mover"],
            "releaseDate": "2018-01-25", "genres": ["Plataforma"],
            "players": 1, "rating": 92, "playtime": 7200,
            "lastPlayed": "2026-08-18T21:00:00Z", "initialFocus": "action:play",
            "actions": [
                {"id": "play", "focusId": "action:play", "label": "Jogar",
                 "enabled": true, "reason": ""},
                {"id": "favorite", "focusId": "action:favorite", "label": "Favoritar",
                 "enabled": true, "reason": ""},
                {"id": "details", "focusId": "action:details", "label": "Detalhes",
                 "enabled": true, "reason": ""}
            ]
        })
        onActivated: function(actionId) { harness.activatedIds.push(actionId) }
    }

    LauncherGamePage {
        id: blocked
        visible: false
        accessibility: ({"highContrast": false, "visualScale": 1.5, "reducedMotion": false})
        model: ({
            "gameId": "tunic", "title": "Tunic", "platform": "Steam",
            "lastPlayed": null, "initialFocus": "action:favorite",
            "actions": [
                {"id": "play", "focusId": "action:play", "label": "Jogar",
                 "enabled": false, "reason": "indisponível: instalação incompleta"},
                {"id": "favorite", "focusId": "action:favorite", "label": "Favoritar",
                 "enabled": true, "reason": ""}
            ]
        })
    }

    Timer {
        interval: 80
        running: true
        repeat: false
        onTriggered: {
            harness.check(playable.currentFocus === "action:play",
                          "a página precisa começar no foco resolvido")
            harness.check(playable.actionCount === 3, "as ações não chegaram ao QML")
            harness.check(playable.screenshots.length === 1,
                          "screenshot legada precisa virar galeria de um item")
            harness.check(playable.requirements.length === 1 && playable.controls.length === 2,
                          "requisitos e controles publicados precisam chegar à página")
            harness.check(playable.activate() === true, "ação habilitada precisa ativar")
            harness.check(harness.activatedIds.length === 1
                          && harness.activatedIds[0] === "play",
                          "a ativação precisa emitir o id da ação em foco")

            // Jogo bloqueado: botão visível, motivo publicado, foco fora dele.
            harness.check(blocked.actionCount === 2,
                          "ação desabilitada não pode sumir da página")
            harness.check(blocked.actionReasonPixelSize === 17,
                          "motivo da ação precisa respeitar visualScale")
            harness.check(blocked.screenshots.length === 0
                          && blocked.requirements.length === 0
                          && blocked.controls.length === 0,
                          "fallbacks não podem inventar mídia ou instruções")
            harness.check(blocked.focusOnDisabledAction === false,
                          "o foco não pode repousar numa ação desabilitada")
            // Força o foco na ação desabilitada para exercitar a guarda de
            // verdade. A versão anterior desta checagem usava `||` com uma
            // condição já verdadeira, então passava sem testar nada.
            blocked.currentFocus = "action:play"
            harness.check(blocked.focusOnDisabledAction === true,
                          "o cenário precisa colocar o foco na ação desabilitada")
            harness.check(blocked.activate() === false,
                          "ação desabilitada não pode ser ativada")
            harness.check(harness.activatedIds.length === 1,
                          "ação desabilitada não pode emitir sinal de ativação")
            blocked.currentFocus = "action:favorite"
            blocked.move(-1)
            harness.check(blocked.currentFocus !== "action:play",
                          "o direcional não pode parar numa ação desabilitada")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
