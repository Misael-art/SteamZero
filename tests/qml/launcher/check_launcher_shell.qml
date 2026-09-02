// SPDX-License-Identifier: GPL-3.0-or-later
//
// Contrato do shell: home e página de jogo no mesmo processo, e o retorno
// recai no foco exato de onde o usuário saiu — não no topo da home.
import QtQuick
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

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

    readonly property var sections: [
        {"id": "continue", "title": "Continuar",
         "items": [{"id": "celeste", "title": "Celeste"}, {"id": "hades", "title": "Hades"}]},
        {"id": "library", "title": "Biblioteca",
         "items": [{"id": "tunic", "title": "Tunic"}]}
    ]

    readonly property var focusMap: ({
        "initial": "continue:celeste",
        "rows": ["header:home", "continue:celeste", "library:tunic"],
        "diagnostics": [],
        "nodes": {
            "header:home": {"id": "header:home", "section": "header", "column": 0,
                            "up": null, "down": "continue:celeste", "left": null,
                            "right": null, "action": null},
            "continue:celeste": {"id": "continue:celeste", "section": "continue", "column": 0,
                                 "up": "header:home", "down": "library:tunic",
                                 "left": "continue:hades", "right": "continue:hades",
                                 "action": null},
            "continue:hades": {"id": "continue:hades", "section": "continue", "column": 1,
                               "up": "header:home", "down": "library:tunic",
                               "left": "continue:celeste", "right": "continue:celeste",
                               "action": null},
            "library:tunic": {"id": "library:tunic", "section": "library", "column": 0,
                              "up": "continue:celeste", "down": null,
                              "left": null, "right": null, "action": null}
        }
    })

    function pageFor(gameId) {
        return {
            "gameId": gameId, "title": gameId, "platform": "Steam", "lastPlayed": null,
            "initialFocus": "action:play",
            "actions": [
                {"id": "play", "focusId": "action:play", "label": "Jogar",
                 "enabled": true, "reason": ""},
                {"id": "details", "focusId": "action:details", "label": "Detalhes",
                 "enabled": true, "reason": ""}
            ]
        }
    }

    property var launched: []

    LauncherShell {
        id: shell
        anchors.fill: parent
        focusMap: harness.focusMap
        sections: harness.sections
        resolveGamePage: harness.pageFor
        onLaunchRequested: function(gameId, focusId) {
            harness.launched.push(gameId + "@" + focusId)
        }
    }

    LauncherShell {
        id: returning
        visible: false
        focusMap: harness.focusMap
        sections: harness.sections
        resolveGamePage: harness.pageFor
        // Contexto salvo antes do jogo: o shell precisa voltar exatamente aqui.
        returnContext: ({"gameId": "hades", "focusId": "continue:hades"})
    }

    LauncherShell {
        id: brokenReturn
        visible: false
        focusMap: harness.focusMap
        sections: harness.sections
        resolveGamePage: harness.pageFor
        returnContext: ({"focusId": "library:sumiu"})
    }

    Timer {
        interval: 100
        running: true
        repeat: false
        onTriggered: {
            harness.check(shell.screen === "home", "o shell precisa começar na home")
            harness.check(shell.homeFocus === "continue:celeste",
                          "sem contexto, começa no foco inicial")

            // Navega e abre um jogo: o lugar de saída tem de ser lembrado.
            shell.moveHome("right")
            harness.check(shell.homeFocus === "continue:hades", "o shell não moveu o foco")
            harness.check(shell.openGame("hades") === true, "abrir o jogo falhou")
            harness.check(shell.screen === "game", "o shell não trocou de tela")
            harness.check(shell.gamePage.gameId === "hades", "a página aberta é de outro jogo")

            // Lançar informa quem lançar e de onde, para o contexto ser salvo.
            harness.check(shell.launchFocused() === true, "lançar falhou")
            harness.check(shell.launchState === "launching",
                          "lançar precisa entrar no estado launching")
            harness.check(harness.launched.length === 1
                          && harness.launched[0] === "hades@continue:hades",
                          "o lançamento precisa levar o foco de saída junto")

            harness.check(shell.markEmulatorVisible() === true,
                          "o shell precisa aceitar a transição para emulador visível")
            harness.check(shell.launchState === "emulator-visible",
                          "o estado emulator-visible não foi publicado")
            harness.check(shell.launchFocused() === false,
                          "um segundo lançamento não pode acontecer durante a sessão")

            // Voltar: mesma tela e MESMO foco, não o topo da home.
            harness.check(shell.back() === true, "voltar falhou")
            harness.check(shell.screen === "home", "voltar não retornou à home")
            harness.check(shell.homeFocus === "continue:hades",
                          "o retorno precisa cair no foco de onde saiu")
            harness.check(shell.launchState === "recovered",
                          "o retorno precisa terminar no estado recovered")

            // Contexto salvo restaura o foco na inicialização.
            harness.check(returning.homeFocus === "continue:hades",
                          "o contexto de retorno precisa posicionar o foco")
            // Contexto apontando para item que sumiu não pode deixar sem foco.
            harness.check(brokenReturn.homeFocus === "continue:celeste",
                          "contexto inválido precisa cair no foco inicial")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
