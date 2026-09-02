// SPDX-License-Identifier: GPL-3.0-or-later
//
// Contrato P0 do Launcher: cartão focado ativa por teclado e toque, emite uma
// única intenção durante o debounce e a home abre a página do mesmo jogo.
import QtQuick
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    property int failures: 0
    property int checkIndex: 0
    property var activated: []
    property var feedback: []
    property var emptyActions: []

    function check(condition, message) {
        checkIndex += 1
        if (!condition) {
            failures += 1
            console.error("FAIL #" + checkIndex + ": " + message)
        }
    }

    readonly property var sections: [
        {"id": "library", "title": "Biblioteca", "items": [
            {"id": "celeste", "title": "Celeste", "coverUrl": ""}
        ]}
    ]

    readonly property var focusMap: ({
        "initial": "library:celeste",
        "rows": ["header:home", "library:celeste"],
        "diagnostics": [],
        "nodes": {
            "header:home": {"id": "header:home", "section": "header", "column": 0,
                            "up": null, "down": "library:celeste", "left": null,
                            "right": null, "action": null},
            "library:celeste": {"id": "library:celeste", "section": "library", "column": 0,
                                 "up": "header:home", "down": null, "left": null,
                                 "right": null, "action": null}
        }
    })

    function pageFor(gameId) {
        return {
            "gameId": gameId, "title": "Celeste", "platform": "Biblioteca",
            "lastPlayed": null, "initialFocus": "action:play",
            "actions": [
                {"id": "play", "focusId": "action:play", "label": "Jogar",
                 "enabled": true, "reason": ""}
            ]
        }
    }

    LauncherShell {
        id: shell
        anchors.fill: parent
        focusMap: harness.focusMap
        sections: harness.sections
        resolveGamePage: harness.pageFor
        onLaunchRequested: function(gameId, focusId) {
            harness.activated.push(gameId + "@" + focusId)
        }
        onFeedbackRequested: function(kind) { harness.feedback.push(kind) }
    }

    LauncherHome {
        id: emptyHome
        visible: false
        focusMap: ({
            "initial": "empty:action",
            "rows": ["header:home", "empty:action"],
            "diagnostics": [{"code": "LAUNCHER-FOCUS-EMPTY-001"}],
            "nodes": {
                "header:home": {"id": "header:home", "section": "header", "column": 0,
                                "up": null, "down": "empty:action", "left": null,
                                "right": null, "action": null},
                "empty:action": {"id": "empty:action", "section": "empty", "column": 0,
                                  "up": "header:home", "down": null, "left": null,
                                  "right": null, "action": "library.retry"}
            }
        })
        sections: []
        onActionActivated: function(actionId) { harness.emptyActions.push(actionId) }
    }

    function findByObjectName(node, name) {
        if (node === null || node === undefined)
            return null
        if (node.objectName === name)
            return node
        for (var i = 0; i < node.children.length; ++i) {
            var found = findByObjectName(node.children[i], name)
            if (found !== null)
                return found
        }
        return null
    }

    Timer {
        interval: 100
        running: true
        repeat: false
        onTriggered: {
            var home = findByObjectName(shell, "launcherHome")
            harness.check(home !== null, "o shell precisa expor a home do Launcher")
            if (home === null) {
                Qt.exit(1)
                return
            }

            harness.check(home.currentFocus === "library:celeste",
                          "o cartão precisa começar focado")
            var card = findByObjectName(home, "launcherItem")
            harness.check(card !== null, "o cartão precisa ser um alvo de interação")
            if (card !== null) {
                harness.check(card.Accessible.role === Accessible.Button,
                              "o cartão precisa anunciar papel de botão")
                harness.check(card.Accessible.name.indexOf("Celeste") >= 0,
                              "o cartão precisa anunciar o título do jogo")
                card.keyboardPressed = true
                harness.check(card.pressed === true,
                              "o cartão precisa mostrar o estado pressionado")
                card.keyboardPressed = false
                harness.check(card.activate() === true,
                              "clique/toque precisa ter uma rota de ativação")
            }
            harness.check(shell.screen === "game",
                          "ativar o cartão precisa abrir a página do jogo")
            harness.check(shell.gamePage.gameId === "celeste",
                          "a página aberta precisa corresponder ao cartão")
            harness.check(harness.feedback.length === 1
                          && harness.feedback[0] === "card-activated",
                          "a ativação precisa emitir feedback uma vez")
            harness.check(home.activateCurrent() === false,
                          "duplo disparo imediato precisa ser bloqueado")
            harness.check(harness.feedback.length === 1,
                          "duplo disparo não pode emitir feedback duplicado")
            shell.back()
            cooldown.start()
        }
    }

    Timer {
        id: cooldown
        interval: 220
        repeat: false
        onTriggered: {
            var home = findByObjectName(shell, "launcherHome")
            harness.check(home.activateCurrent() === true,
                          "Return/Enter/Space precisam compartilhar a rota do cartão")
            harness.check(shell.screen === "game",
                          "a rota de teclado também precisa abrir a página")
            harness.check(harness.feedback.length === 2,
                          "a rota de teclado precisa emitir feedback uma vez")

            harness.check(emptyHome.empty === true,
                          "home sem biblioteca precisa expor um estado vazio")
            harness.check(emptyHome.activateCurrent() === true,
                          "a ação vazia/retry precisa ser ativável")
            harness.check(harness.emptyActions.length === 1
                          && harness.emptyActions[0] === "library.retry",
                          "a ação vazia precisa chegar ao shell")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
