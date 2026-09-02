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
    // Preferências de acessibilidade herdadas do host (highContrast etc.).
    property var accessibility: ({"highContrast": false, "visualScale": 1.0, "reducedMotion": false})
    // Função que devolve a página de um jogo, injetada por quem monta o shell.
    property var resolveGamePage: null
    // Contexto gravado antes do lançamento, lido na inicialização.
    property var returnContext: null

    readonly property string screen: gamePage !== null ? "game" : "home"
    property var gamePage: null
    property string homeFocus: _restoredFocus()
    // De onde o jogo foi aberto. É isto que a volta restaura.
    property string exitFocus: ""

    signal launchRequested(string gameId, string focusId)
    signal searchRequested()
    signal actionRequested(string actionId)
    signal feedbackRequested(string kind)

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
        if (gamePage === null)
            return false
        // O foco de saída viaja junto: é ele que o contexto de retorno grava.
        shell.launchRequested(gamePage.gameId, exitFocus)
        return true
    }

    function back() {
        if (gamePage === null)
            return false
        gamePage = null
        if (exitFocus !== "")
            homeFocus = exitFocus
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
}
