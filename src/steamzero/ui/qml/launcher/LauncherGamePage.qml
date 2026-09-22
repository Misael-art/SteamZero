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

FocusScope {
    id: page

    // Vindo de `GamePage.to_qml_object()`.
    required property var model

    property string currentFocus: model && model.initialFocus ? model.initialFocus : ""
    // Preferências de acessibilidade herdadas do host (highContrast etc.).
    property var accessibility: ({"highContrast": false, "visualScale": 1.0, "reducedMotion": false})
    readonly property real textScale: Math.max(1, Number(accessibility.visualScale || 1))
    readonly property int actionReasonPixelSize: actionReason.font.pixelSize
    readonly property string description: model && model.description
        ? String(model.description) : qsTr("Descrição ainda não disponível para este jogo.")
    readonly property var screenshots: {
        const supplied = model && Array.isArray(model.screenshotUrls)
            ? model.screenshotUrls : []
        const result = supplied.map(function(value) { return String(value) }).filter(function(value) {
            return value.length > 0
        }).slice(0, 8)
        const legacy = model && model.screenshotUrl ? String(model.screenshotUrl) : ""
        if (result.length === 0 && legacy !== "")
            result.push(legacy)
        return result
    }
    readonly property var requirements: model && Array.isArray(model.requirements)
        ? model.requirements.filter(function(value) {
            return typeof value === "string" && value.length > 0
        }).slice(0, 16) : []
    readonly property var controls: model && Array.isArray(model.controls)
        ? model.controls.filter(function(value) {
            return typeof value === "string" && value.length > 0
        }).slice(0, 16) : []
    property alias detailScrollY: detailScroll.contentY

    function scrollDetails(delta) {
        detailScroll.contentY = Math.max(0, Math.min(
            Math.max(0, detailScroll.contentHeight - detailScroll.height),
            detailScroll.contentY + delta))
    }

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
    Keys.onDownPressed: scrollDetails(64 * page.textScale)
    Keys.onUpPressed: scrollDetails(-64 * page.textScale)
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                || event.key === Qt.Key_Space) {
            if (page.activateAction(page.focusedAction))
                event.accepted = true
        }
    }
    focus: true

    Rectangle {
        anchors.fill: parent
        color: page._hc("#071019", "#000000")
    }
    Image {
        anchors.fill: parent
        source: page.accessibility.highContrast ? "" : String(page.model.fanartUrl || "")
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        sourceSize: Qt.size(Math.ceil(width), Math.ceil(height))
        opacity: 0.12
    }
    Text {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: 32
        text: qsTr("AURA CINEMA · DETALHES")
        color: "#ffffff"
        font.pixelSize: 16 * page.textScale
    }
    Rectangle {
        id: poster
        x: 32
        y: 96
        width: Math.min(page.width * 0.32, 420)
        height: Math.max(96, page.height - 192)
        color: page._hc("#142332", "#000000")
        border.color: "#8a9baa"
        radius: 8
        Image {
            id: detailCover
            anchors.fill: parent
            anchors.margins: 4
            source: String(page.model.coverUrl || "")
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            sourceSize: Qt.size(Math.ceil(width), Math.ceil(height))
        }
        Text {
            anchors.fill: parent
            anchors.margins: 24
            visible: detailCover.status !== Image.Ready
            text: String(page.model.title || qsTr("Sem capa"))
            textFormat: Text.PlainText
            color: "#ffffff"
            font.pixelSize: 26 * page.textScale
            wrapMode: Text.Wrap
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }
    Column {
        id: info
        x: poster.x + poster.width + 32
        y: poster.y
        width: Math.max(100, page.width - x - 32)
        spacing: 14
        Text {
            id: titleLabel
            objectName: "gameTitle"
            width: parent.width
            text: String(page.model.title || "")
            textFormat: Text.PlainText
            color: "#ffffff"
            font.pixelSize: 32 * page.textScale
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
        }
        Text {
            id: platformLabel
            width: parent.width
            text: String(page.model.platform || "")
            textFormat: Text.PlainText
            color: page._hc("#c6d0db", "#ffffff")
            font.pixelSize: 16 * page.textScale
            wrapMode: Text.Wrap
        }
        Flow {
            id: gameFacts
            objectName: "gameFacts"
            width: parent.width
            spacing: 8
            Repeater {
                model: [
                    {"label": qsTr("Ano"), "value": String(page.model.releaseDate || "").slice(0, 4)},
                    {"label": qsTr("Gênero"), "value": page.model.genres && page.model.genres.length
                        ? page.model.genres.slice(0, 2).join(" · ") : ""},
                    {"label": qsTr("Jogadores"), "value": page.model.players > 0
                        ? String(page.model.players) : ""},
                    {"label": qsTr("Nota"), "value": page.model.rating !== undefined
                        ? (Number(page.model.rating) / 10).toFixed(1) : ""},
                    {"label": qsTr("Tempo"), "value": page.model.playtime > 0
                        ? Math.floor(Number(page.model.playtime) / 3600) + "h" : ""}
                ].filter(function(fact) { return fact.value !== "" })
                delegate: Rectangle {
                    required property var modelData
                    width: factLabel.width + 24
                    height: 32
                    radius: 16
                    color: page._hc("#173148cc", "#000000")
                    border.color: page._hc("#49657a", "#ffffff")
                    Text {
                        id: factLabel
                        anchors.centerIn: parent
                        text: modelData.label + "  " + modelData.value
                        textFormat: Text.PlainText
                        color: "#ffffff"
                        font.pixelSize: 12 * page.textScale
                    }
                }
            }
        }
        Row {
            id: details
            width: parent.width
            height: Math.max(80, poster.height - titleLabel.height - platformLabel.height - 150)
            spacing: 16
            Flickable {
                id: detailScroll
                objectName: "gameDescriptionScroll"
                width: parent.width - screenshotPanel.width - 16
                height: parent.height
                contentHeight: detailContent.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                Column {
                    id: detailContent
                    width: detailScroll.width
                    spacing: 18
                    Text {
                        id: descriptionText
                        objectName: "gameDescription"
                        width: parent.width
                        text: page.description
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: "#ffffff"
                        font.pixelSize: 18 * page.textScale
                        lineHeight: 1.2
                        Accessible.name: text
                    }
                    Row {
                        width: parent.width
                        spacing: 16
                        visible: page.requirements.length > 0 || page.controls.length > 0
                        Column {
                            objectName: "gameRequirements"
                            width: (parent.width - parent.spacing) / 2
                            spacing: 6
                            Text {
                                text: qsTr("REQUISITOS")
                                color: page._hc("#9ee8f4", "#ffffff")
                                font.pixelSize: 12 * page.textScale
                            }
                            Repeater {
                                model: page.requirements
                                delegate: Text {
                                    required property string modelData
                                    width: parent.width
                                    text: "• " + modelData
                                    textFormat: Text.PlainText
                                    wrapMode: Text.Wrap
                                    color: "#ffffff"
                                    font.pixelSize: 14 * page.textScale
                                }
                            }
                        }
                        Column {
                            objectName: "gameControls"
                            width: (parent.width - parent.spacing) / 2
                            spacing: 6
                            Text {
                                text: qsTr("CONTROLES")
                                color: page._hc("#9ee8f4", "#ffffff")
                                font.pixelSize: 12 * page.textScale
                            }
                            Repeater {
                                model: page.controls
                                delegate: Text {
                                    required property string modelData
                                    width: parent.width
                                    text: "• " + modelData
                                    textFormat: Text.PlainText
                                    wrapMode: Text.Wrap
                                    color: "#ffffff"
                                    font.pixelSize: 14 * page.textScale
                                }
                            }
                        }
                    }
                }
                Rectangle {
                    anchors.right: parent.right
                    y: detailScroll.contentY + (detailScroll.contentY / Math.max(1, detailScroll.contentHeight))
                       * detailScroll.height
                    width: 3
                    height: Math.max(12, detailScroll.height * detailScroll.height
                                     / Math.max(1, detailScroll.contentHeight))
                    color: "#ffffff"
                    visible: detailScroll.contentHeight > detailScroll.height
                }
            }
            Rectangle {
                id: screenshotPanel
                objectName: "gameScreenshots"
                width: parent.width * 0.32
                height: Math.min(parent.height, width * 9 / 16)
                color: page._hc("#142332cc", "#000000")
                border.color: page._hc("#49657a", "#ffffff")
                radius: 8
                Column {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 6
                    Repeater {
                        model: page.screenshots
                        delegate: Image {
                            required property string modelData
                            required property int index
                            objectName: index === 0 ? "gameScreenshot" : ""
                            width: parent.width
                            height: Math.max(1, (parent.height - 6 * (page.screenshots.length - 1))
                                             / Math.max(1, page.screenshots.length))
                            source: modelData
                            visible: status === Image.Ready
                            asynchronous: true
                            fillMode: Image.PreserveAspectFit
                            sourceSize: Qt.size(Math.ceil(width), Math.ceil(height))
                            Accessible.name: qsTr("Screenshot %1 de %2").arg(index + 1)
                                .arg(page.model.title || "")
                            Accessible.role: Accessible.Graphic
                        }
                    }
                    Text {
                        objectName: "gameScreenshotFallback"
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: page.screenshots.length === 0
                        text: qsTr("Screenshots não publicados")
                        textFormat: Text.PlainText
                        color: page._hc("#d8e4ed", "#ffffff")
                        font.pixelSize: 14 * page.textScale
                        wrapMode: Text.Wrap
                    }
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
                    height: Math.max(48, 40 * page.textScale)
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
                        font.pixelSize: 16 * page.textScale
                    }
                }
            }
        }

        Text {
            id: actionReason
            objectName: "gameActionReason"
            visible: text !== ""
            width: parent.width
            wrapMode: Text.Wrap
            color: page._hc("#ff8a90", "#ff8e94")
            font.pixelSize: 11 * page.textScale
            text: {
                for (let i = 0; i < page.actions.length; ++i)
                    if (!page.actions[i].enabled && page.actions[i].reason)
                        return page.actions[i].label + ": " + page.actions[i].reason
                return ""
            }
        }
    }
    Text {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.margins: 32
        text: qsTr("↑ ↓ Ler descrição    ← → Ações    Enter Confirmar    Esc Voltar")
        color: "#ffffff"
        font.pixelSize: 14 * page.textScale
    }
}
