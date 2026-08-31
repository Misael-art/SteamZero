// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Página de jogo do AURA Launcher.
//
// As ações chegam decididas: qual existe, qual está habilitada e por que não.
// Este componente não avalia se o jogo pode rodar — se avaliasse, a regra
// viveria em dois lugares e um dia divergiria da que o domínio aplica.
//
// Ação desabilitada continua visível, com o motivo ao lado. Esconder faria o
// usuário procurar o que não está lá; mostrar sem explicação faria ele apertar
// e não entender o silêncio.

import QtQuick

Item {
    id: page

    // Vindo de `GamePage.to_qml_object()`.
    required property var model

    property string currentFocus: model && model.initialFocus ? model.initialFocus : ""

    readonly property var actions: model && model.actions ? model.actions : []
    readonly property int actionCount: actions.length
    readonly property var focusedAction: {
        for (let i = 0; i < actions.length; ++i)
            if (actions[i].focusId === currentFocus)
                return actions[i]
        return undefined
    }
    // O foco nunca deve repousar numa ação desabilitada; se repousar, é defeito
    // de quem resolveu a página, e o consumidor precisa conseguir apontar isso.
    readonly property bool focusOnDisabledAction:
        focusedAction !== undefined && focusedAction.enabled === false

    signal activated(string actionId)

    function move(delta) {
        if (actions.length === 0)
            return false
        let index = -1
        for (let i = 0; i < actions.length; ++i)
            if (actions[i].focusId === currentFocus)
                index = i
        if (index < 0)
            return false
        // Só para em ação habilitada: passar o foco por um botão morto obriga
        // o usuário a apertar direcional duas vezes sem saber por quê.
        for (let step = 1; step <= actions.length; ++step) {
            const candidate = actions[(index + delta * step + actions.length * step)
                                      % actions.length]
            if (candidate.enabled) {
                currentFocus = candidate.focusId
                return true
            }
        }
        return false
    }

    function activate() {
        if (focusedAction === undefined || focusedAction.enabled === false)
            return false
        page.activated(focusedAction.id)
        return true
    }

    Keys.onLeftPressed: move(-1)
    Keys.onRightPressed: move(1)
    Keys.onReturnPressed: activate()
    focus: true

    Column {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 12

        Text {
            objectName: "gameTitle"
            text: page.model ? page.model.title : ""
            color: "#f2f6fb"
            font.pixelSize: 28
        }
        Text {
            text: page.model
                ? page.model.platform + (page.model.lastPlayed
                    ? " · jogado em " + page.model.lastPlayed : "")
                : ""
            color: "#8b93a8"
            font.pixelSize: 13
        }

        Row {
            spacing: 12
            Repeater {
                model: page.actions
                delegate: Rectangle {
                    required property var modelData
                    objectName: "gameAction"
                    width: 170
                    height: 46
                    radius: 8
                    color: modelData.enabled ? "#0b1622" : "#0a0f16"
                    border.width: page.currentFocus === modelData.focusId ? 3 : 1
                    border.color: page.currentFocus === modelData.focusId
                        ? "#22d3ee" : "#243044"
                    Text {
                        anchors.centerIn: parent
                        text: modelData.label
                        color: modelData.enabled ? "#f2f6fb" : "#8b93a8"
                        font.pixelSize: 14
                    }
                }
            }
        }

        Text {
            objectName: "gameActionReason"
            visible: text !== ""
            width: parent.width
            wrapMode: Text.Wrap
            color: "#ff8a90"
            font.pixelSize: 11
            text: {
                for (let i = 0; i < page.actions.length; ++i)
                    if (!page.actions[i].enabled && page.actions[i].reason)
                        return page.actions[i].label + ": " + page.actions[i].reason
                return ""
            }
        }
    }
}
