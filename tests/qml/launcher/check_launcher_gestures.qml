// SPDX-License-Identifier: GPL-3.0-or-later
//
// Prova de GESTO do P0 do Launcher: uma tecla real e um clique real precisam
// chegar até a ativação do cartão.
//
// O harness irmão (`check_launcher_activation.qml`) chama `card.activate()` e
// `home.activateCurrent()` diretamente. Isso prova a função, não o caminho — e
// o caminho era exatamente o que estava quebrado: `LauncherShell.openGame()` já
// existia na release auditada, e mesmo assim Return e clique não abriam nada,
// porque nenhum handler ligava o gesto à função. Medido em 2026-09-02: com os
// `Keys.onPressed` do cartão e da home REMOVIDOS, aquele harness continuava
// passando.
//
// Por isso aqui não se chama função de ativação nenhuma. Só se pressiona e se
// clica, como o usuário faz.
import QtQuick
import QtQuick.Window
import QtTest
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    property var launched: []

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

    Window {
        id: stage
        visible: true
        width: 1280
        height: 800

        LauncherHome {
            id: home
            anchors.fill: parent
            focusMap: harness.focusMap
            sections: harness.sections
            onGameActivated: function(gameId, focusId) {
                harness.launched.push({"gameId": gameId, "focusId": focusId})
            }
        }
    }

    TestCase {
        name: "LauncherCardGestures"
        when: windowShown

        function findCard() {
            // O cartão é o delegate que carrega o nodeId do foco atual.
            function walk(item) {
                if (!item)
                    return null
                if (item.nodeId !== undefined && item.nodeId === home.currentFocus)
                    return item
                const kids = item.children || []
                for (let i = 0; i < kids.length; ++i) {
                    const found = walk(kids[i])
                    if (found !== null)
                        return found
                }
                return null
            }
            return walk(home)
        }

        function init() {
            harness.launched = []
            home.activationLocked = false
            stage.requestActivate()
            // Sem janela ativa não existe foco de teclado, e sem foco a tecla
            // não chega a controle nenhum — mesmo passo dos demais harnesses.
            tryVerify(function() { return stage.active }, 4000,
                      "a janela precisa ficar ativa para receber teclado")
        }

        function test_return_key_reaches_activation() {
            home.forceActiveFocus()
            tryVerify(function() { return home.activeFocus }, 2000,
                      "a home precisa ter foco para receber a tecla")
            keyClick(Qt.Key_Return)
            tryVerify(function() { return harness.launched.length === 1 }, 2000,
                      "Return pressionado de verdade não ativou o cartão focado")
            compare(harness.launched[0].gameId, "celeste",
                    "a tecla precisa ativar o jogo que está focado")
        }

        function test_space_key_reaches_activation() {
            home.forceActiveFocus()
            tryVerify(function() { return home.activeFocus }, 2000,
                      "a home precisa ter foco para receber a tecla")
            keyClick(Qt.Key_Space)
            tryVerify(function() { return harness.launched.length === 1 }, 2000,
                      "Space pressionado de verdade não ativou o cartão focado")
        }

        function test_pointer_click_reaches_activation() {
            const card = findCard()
            verify(card !== null, "o cartão focado precisa existir na cena")
            mouseClick(card)
            tryVerify(function() { return harness.launched.length === 1 }, 2000,
                      "clique real no cartão não ativou o jogo")
            compare(harness.launched[0].gameId, "celeste",
                    "o clique precisa ativar o jogo do próprio cartão")
        }

        function test_repeated_gesture_does_not_double_launch() {
            home.forceActiveFocus()
            tryVerify(function() { return home.activeFocus }, 2000,
                      "a home precisa ter foco para receber a tecla")
            keyClick(Qt.Key_Return)
            keyClick(Qt.Key_Return)
            tryVerify(function() { return harness.launched.length >= 1 }, 2000,
                      "a primeira tecla precisa ativar")
            compare(harness.launched.length, 1,
                    "duas teclas dentro do debounce não podem abrir o jogo duas vezes")
        }
    }
}
