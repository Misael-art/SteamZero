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
    // Preferências de acessibilidade herdadas do host (highContrast etc.).
    property var accessibility: ({"highContrast": false, "visualScale": 1.0, "reducedMotion": false})

    function _hc(lightValue, highContrastValue) {
        return page.accessibility && page.accessibility.highContrast
            ? highContrastValue : lightValue
    }

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

    function activateAction(action) {
        if (action === undefined || action === null || action.enabled === false)
            return false
        page.activated(String(action.id))
        return true
    }

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
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                || event.key === Qt.Key_Space) {
            if (page.activateAction(page.focusedAction))
                event.accepted = true
        }
    }
    focus: true

    Column {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 12

        Row {
            spacing: 16

            Rectangle {
                width: 220
                height: 132
                radius: 8
                color: page._hc("#0b1622", "#03080c")
                border.color: page._hc("#243044", "#68839b")
                border.width: 1
                clip: true
                Accessible.name: qsTr("Capa de %1").arg(page.model ? page.model.title : "")
                Accessible.role: Accessible.Graphic

                Image {
                    anchors.fill: parent
                    visible: !!(page.model && page.model.coverUrl)
                    source: page.model && page.model.coverUrl ? page.model.coverUrl : ""
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    sourceSize.width: width * 2
                    sourceSize.height: height * 2
                }
                Text {
                    anchors.fill: parent
                    visible: !(page.model && page.model.coverUrl)
                    text: page.model && page.model.title
                        ? String(page.model.title).charAt(0) : "?"
                    color: page._hc("#8b93a8", "#c6d0db")
                    font.pixelSize: 48
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Column {
                spacing: 8

        Text {
            objectName: "gameTitle"
            text: page.model ? page.model.title : ""
            color: page._hc("#f2f6fb", "#ffffff")
            font.pixelSize: 28
        }
        Text {
            text: page.model
                ? page.model.platform + (page.model.lastPlayed
                    ? " · jogado em " + page.model.lastPlayed : "")
                : ""
            color: page._hc("#8b93a8", "#c6d0db")
            font.pixelSize: 13
        }
            }
        }

        Row {
            spacing: 12
            Repeater {
                model: page.actions
                delegate: Rectangle {
                    id: actionButton
                    required property var modelData
                    objectName: "gameAction"
                    width: 170
                    height: 46
                    radius: 8
                    property bool keyboardPressed: false
                    readonly property bool pressed:
                        tapHandler.pressed || keyboardPressed
                    color: modelData.enabled
                        ? page._hc("#0b1622", "#03080c") : page._hc("#0a0f16", "#0a141d")
                    border.width: page.currentFocus === modelData.focusId ? 3 : 1
                    border.color: page.currentFocus === modelData.focusId
                        ? page._hc("#22d3ee", "#55d8ff") : page._hc("#243044", "#68839b")
                    scale: pressed ? 0.98 : 1.0
                    focus: page.currentFocus === modelData.focusId
                    activeFocusOnTab: true
                    Accessible.name: modelData.label
                    Accessible.role: Accessible.Button
                    Accessible.description: modelData.enabled
                        ? qsTr("Ativar %1").arg(modelData.label)
                        : (modelData.reason || qsTr("Ação indisponível"))

                    TapHandler { id: tapHandler; onTapped: page.activateAction(modelData) }
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                                || event.key === Qt.Key_Space) {
                            actionButton.keyboardPressed = true
                            if (page.activateAction(modelData))
                                event.accepted = true
                        }
                    }
                    Keys.onReleased: function(event) {
                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                                || event.key === Qt.Key_Space)
                            actionButton.keyboardPressed = false
                    }
                    Text {
                        anchors.centerIn: parent
                        text: modelData.label
                        color: modelData.enabled
                            ? page._hc("#f2f6fb", "#ffffff") : page._hc("#8b93a8", "#c6d0db")
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
            color: page._hc("#ff8a90", "#ff8e94")
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
