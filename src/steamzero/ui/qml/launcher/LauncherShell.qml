// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Shell do AURA Launcher: home e página de jogo no mesmo processo.
//
// O shell guarda de onde o usuário saiu e devolve exatamente ali na volta. Cair
// no topo da home depois de fechar um jogo é o defeito que faz o usuário
// percorrer a biblioteca de novo a cada partida.
//
// Ele não resolve foco nem decide ações: a home aplica o mapa do domínio e a
// página recebe as ações já decididas. Aqui só há a costura entre as duas e o
// contexto de retorno.

import QtQuick

Item {
    id: shell

    required property var focusMap
    required property var sections
    property var catalogSummary: ({})
    // Preferências de acessibilidade herdadas do host (highContrast etc.).
    property var accessibility: ({"highContrast": false, "visualScale": 1.0, "reducedMotion": false})
    // Função que devolve a página de um jogo, injetada por quem monta o shell.
    property var resolveGamePage: null
    // Contexto gravado antes do lançamento, lido na inicialização.
    property var returnContext: null

    readonly property string screen: gamePage !== null ? "game" : "home"
    readonly property var launchStates: ["idle", "preparing", "launching",
        "emulator-visible", "returning", "recovered", "failed"]
    property string launchState: "idle"
    property string launchError: ""
    property var gamePage: null
    property string homeFocus: _restoredFocus()
    // De onde o jogo foi aberto. É isto que a volta restaura.
    property string exitFocus: ""

    signal launchRequested(string gameId, string focusId)
    signal searchRequested()
    signal actionRequested(string actionId)
    signal feedbackRequested(string kind)
    signal launchStateRequested(string state)

    Timer {
        id: launchTimeout
        interval: 10000
        repeat: false
        running: shell.launchState === "launching"
        onTriggered: shell.failLaunch("O lançamento demorou mais que o esperado.")
    }

    function _restoredFocus() {
        const fallback = focusMap && focusMap.initial ? focusMap.initial : ""
        if (!returnContext || !focusMap || !focusMap.nodes)
            return fallback
        const saved = returnContext.focusId
        // Item que saiu da biblioteca enquanto o jogo rodava não pode deixar o
        // shell sem foco; o domínio já trata o caso, e aqui a defesa é a mesma.
        if (typeof saved !== "string" || focusMap.nodes[saved] === undefined)
            return fallback
        return saved
    }

    function moveHome(direction) {
        return home.move(direction)
    }

    function openGame(gameId) {
        if (typeof resolveGamePage !== "function")
            return false
        const page = resolveGamePage(gameId)
        if (!page)
            return false
        exitFocus = homeFocus
        gamePage = page
        return true
    }

    function launchFocused() {
        if (gamePage === null || (launchState !== "idle" && launchState !== "recovered"
                                  && launchState !== "failed"))
            return false
        launchError = ""
        launchState = "preparing"
        launchStateRequested("preparing")
        launchState = "launching"
        launchStateRequested("launching")
        // O foco de saída viaja junto: é ele que o contexto de retorno grava.
        shell.launchRequested(gamePage.gameId, exitFocus)
        return true
    }

    function markEmulatorVisible() {
        if (launchState !== "launching")
            return false
        launchState = "emulator-visible"
        launchStateRequested("emulator-visible")
        return true
    }

    function markReturning() {
        if (launchState !== "emulator-visible")
            return false
        launchState = "returning"
        launchStateRequested("returning")
        return true
    }

    function recoverLaunch() {
        launchError = ""
        launchState = "recovered"
        launchStateRequested("recovered")
        return true
    }

    function failLaunch(reason) {
        launchError = String(reason || "Não foi possível iniciar o jogo.")
        launchState = "failed"
        launchStateRequested("failed")
        shell.feedbackRequested("launch-failed")
        return false
    }

    function back() {
        if (gamePage === null)
            return false
        if (launchState === "emulator-visible")
            markReturning()
        gamePage = null
        if (exitFocus !== "")
            homeFocus = exitFocus
        if (launchState === "returning")
            recoverLaunch()
        return true
    }

    Keys.onEscapePressed: back()
    Keys.onPressed: function(event) {
        // 'F' abre a busca (rota de entrada por teclado/controle); o Steam Input
        // emula teclado, então esta é a via do "controle" também.
        if (event.text === "f" || event.text === "F") {
            shell.searchRequested()
            event.accepted = true
        }
    }
    focus: true

    LauncherHome {
        id: home
        objectName: "launcherHome"
        anchors.fill: parent
        visible: shell.screen === "home"
        focusMap: shell.focusMap
        sections: shell.sections
        catalogSummary: shell.catalogSummary
        currentFocus: shell.homeFocus
        accessibility: shell.accessibility
        onCurrentFocusChanged: shell.homeFocus = currentFocus
        onGameActivated: function(gameId) {
            if (!shell.openGame(gameId))
                shell.feedbackRequested("activation-failed")
        }
        onActionActivated: function(actionId) { shell.actionRequested(actionId) }
        onFeedbackRequested: function(kind) { shell.feedbackRequested(kind) }
    }

    LauncherGamePage {
        id: page
        anchors.fill: parent
        visible: shell.screen === "game"
        model: shell.gamePage !== null
            ? shell.gamePage
            : ({"gameId": "", "title": "", "platform": "", "lastPlayed": null,
                "initialFocus": "", "actions": []})
        accessibility: shell.accessibility
        onActivated: function(actionId) {
            if (actionId === "play")
                shell.launchFocused()
        }
    }

    Rectangle {
        id: launchOverlay
        anchors.fill: parent
        z: 10
        visible: shell.launchState === "preparing"
            || shell.launchState === "launching" || shell.launchState === "failed"
        color: "#071019ee"
        opacity: visible ? 1 : 0
        Behavior on opacity {
            NumberAnimation {
                duration: shell.accessibility && shell.accessibility.reducedMotion ? 0 : 180
            }
        }
        Accessible.name: shell.launchState === "failed"
            ? qsTr("Falha ao iniciar o jogo") : qsTr("Preparando o jogo")
        Accessible.description: shell.launchState === "failed"
            ? shell.launchError : qsTr("Aguarde enquanto o jogo é iniciado")

        Column {
            anchors.centerIn: parent
            width: Math.min(parent.width - 48, 520)
            spacing: 16

            Text {
                width: parent.width
                text: shell.launchState === "failed"
                    ? shell.launchError
                    : qsTr("Preparando %1…").arg(shell.gamePage
                        ? shell.gamePage.title : qsTr("o jogo"))
                color: "#f2f6fb"
                font.pixelSize: 22
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }

            Rectangle {
                id: recoverButton
                anchors.horizontalCenter: parent.horizontalCenter
                visible: shell.launchState === "failed"
                width: 220
                height: 48
                radius: 8
                color: "#0b1622"
                border.width: activeFocus ? 3 : 1
                border.color: activeFocus ? "#55d8ff" : "#68839b"
                focus: visible
                Accessible.name: qsTr("Voltar para a página do jogo")
                Accessible.role: Accessible.Button
                Accessible.description: qsTr("Dispensar a falha e tentar novamente")
                Text {
                    anchors.centerIn: parent
                    text: qsTr("Voltar e tentar")
                    color: "#ffffff"
                    font.pixelSize: 14
                }
                TapHandler { onTapped: shell.recoverLaunch() }
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                            || event.key === Qt.Key_Space) {
                        shell.recoverLaunch()
                        event.accepted = true
                    }
                }
            }
        }
    }
}
