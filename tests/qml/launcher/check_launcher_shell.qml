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

            harness.check(shell.observeSession({gameId: "other", sessionId: "x",
                                                state: "running"}) === false,
                          "sessão de outro jogo não pode confirmar o lançamento")
            harness.check(shell.observeSession({gameId: "hades", sessionId: null,
                                                state: "awaiting"}) === false,
                          "aceitar o pedido não confirma processo em execução")
            harness.check(shell.launchState === "launching", "aguardar mantém launching")
            harness.check(shell.markUnconfirmed(), "timeout deve registrar ausência de confirmação")
            harness.check(shell.launchState === "launching", "timeout não prova falha")
            harness.check(shell.launchFocused() === false, "timeout não libera lançamento duplicado")

            // Recibo do contrato de confirmação: falha sem sessionId só vale
            // para o pedido atual, e unconfirmed nunca fabrica conclusão.
            shell.expectedRequestId = "req-current"
            harness.check(shell.observeSession({gameId: "hades", state: "failed",
                                                attempt: {requestId: "req-old",
                                                          state: "notStarted"}}) === false,
                          "recibo notStarted de outra tentativa não encerra o pedido atual")
            harness.check(shell.launchState === "launching",
                          "recibo de tentativa antiga não altera o lançamento")
            shell.expectedRequestId = ""
            harness.check(shell.observeSession({gameId: "hades", state: "failed",
                                                attempt: {requestId: "req-current",
                                                          state: "notStarted"}}) === false,
                          "falha sem sessionId exige o requestId publicado pelo POST")
            shell.expectedRequestId = "req-current"
            harness.check(shell.observeSession({gameId: "hades", state: "failed",
                                                attempt: {requestId: "req-current",
                                                          state: "unconfirmed"}}) === false,
                          "recibo unconfirmed não pode fabricar falha")
            harness.check(shell.launchState === "launching",
                          "unconfirmed mantém a observação canônica como árbitro")
            harness.check(shell.observeSession({gameId: "hades", state: "failed",
                                                attempt: {requestId: "req-current",
                                                          state: "notStarted",
                                                          error: {code: "E-COMPONENT-DEGRADED",
                                                                  manualAction: "defina o emulador"}}}) === true,
                          "notStarted confirmado precisa falhar o lançamento")
            harness.check(shell.launchState === "failed",
                          "notStarted precisa terminar no estado failed")
            harness.check(shell.launchError.indexOf("E-COMPONENT-DEGRADED") >= 0
                          && shell.launchError.indexOf("defina o emulador") >= 0,
                          "o erro projetado precisa aparecer na área de falha")
            const overlay = shell.children[shell.children.length - 1]
            const errorColumn = overlay.children[0]
            const errorText = errorColumn.children[0]
            const retry = errorColumn.children[1]
            harness.check(overlay.objectName === "launchFailureOverlay" && overlay.color.a >= 0.9,
                          "a falha precisa ocultar a página, não sobrepor texto translúcido")
            harness.check(errorText.objectName === "launchFailureText"
                          && retry.objectName === "launchFailureRetry"
                          && errorText.height <= overlay.height - retry.height - 96,
                          "a mensagem precisa caber na área reservada acima do retry")
            harness.check(shell.launchFocused() === true,
                          "falha confirmada antes do spawn libera nova tentativa")
            harness.check(harness.launched.length === 2, "a nova tentativa precisa chegar à ponte")

            harness.check(shell.observeSession({gameId: "hades", sessionId: "new-session",
                                                state: "running"}) === true,
                          "a sessão canônica precisa confirmar a execução")
            harness.check(shell.launchState === "emulator-visible",
                          "o estado emulator-visible não foi publicado")
            harness.check(shell.launchFocused() === false,
                          "um segundo lançamento não pode acontecer durante a sessão")
            harness.check(shell.recoverLaunch() === false,
                          "recuperação não pode desbloquear sessão ativa")
            harness.check(shell.openGame("celeste") === false,
                          "sessão ativa não pode trocar seu contexto por outro jogo")

            // Voltar: mesma tela e MESMO foco, não o topo da home.
            harness.check(shell.observeSession({gameId: "hades", sessionId: "old-session",
                                                state: "closed"}) === false,
                          "fechamento de outra partida não pode provocar retorno")
            harness.check(shell.screen === "game", "sessão antiga alterou a tela")
            harness.check(shell.observeSession({gameId: "hades", sessionId: "new-session",
                                                state: "closed"}) === true,
                          "fechamento canônico precisa provocar retorno")
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
