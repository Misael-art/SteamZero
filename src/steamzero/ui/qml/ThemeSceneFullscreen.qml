// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Superfície de apresentação fullscreen para uma cena ES-DE compilada.
//
// Isto não é o AURA Launcher: não possui biblioteca, busca, página de jogo ou
// ciclo de lançamento. É a ponte visual que permite viver a cena selecionada
// antes de declarar que ela substitui alguma superfície do produto.
import QtQuick
import QtQuick.Controls
import QtQuick.Window

Window {
    id: fullscreen

    objectName: "themeSceneFullscreen"
    visible: false
    color: backgroundColor
    title: qsTr("Cena do tema — %1").arg(themeName)

    property string themeId: ""
    property string themeName: ""
    property var requestAction: function(_id, _payload, _cb, _ecb) {}
    property color backgroundColor: "#071019"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color focusColor: "#13bdf2"

    signal dismissed()

    function openScene(identifier, name) {
        fullscreen.themeId = identifier
        fullscreen.themeName = name
        fullscreen.showFullScreen()
        fullscreen.visible = true
        Qt.callLater(function() { scene.forceActiveFocus() })
    }

    function closeScene() {
        if (!fullscreen.visible)
            return
        fullscreen.close()
        fullscreen.dismissed()
    }

    // Esc funciona mesmo quando o foco está dentro do SceneEsdeView; a ação
    // semântica de saída não depende de o tema conhecer atalhos de janela.
    Shortcut {
        sequence: "Esc"
        context: Qt.ApplicationShortcut
        onActivated: fullscreen.closeScene()
    }

    ThemeScenePreview {
        id: scene
        anchors.fill: parent
        requestAction: fullscreen.requestAction
        themeId: fullscreen.themeId
        surfaceColor: fullscreen.backgroundColor
        borderColor: fullscreen.borderColor
        textColor: fullscreen.textColor
        mutedColor: fullscreen.mutedColor
        focusColor: fullscreen.focusColor
        immersive: true
    }

    Rectangle {
        id: chrome
        z: 20
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 64
        color: fullscreen.backgroundColor
        opacity: 0.94
        border.color: fullscreen.borderColor
        border.width: 1

        Row {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 12
            spacing: 16

            Label {
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr("Cena · %1").arg(fullscreen.themeName || fullscreen.themeId)
                color: fullscreen.textColor
                font.pixelSize: 20
                font.bold: true
                elide: Text.ElideRight
                width: Math.max(0, parent.width - exitButton.width - 48)
                Accessible.name: text
            }

            DarkButton {
                id: exitButton
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr("Sair  Esc")
                implicitWidth: 132
                implicitHeight: 48
                Accessible.name: qsTr("Sair da cena em tela cheia")
                Accessible.description: qsTr("Volta ao catálogo de temas")
                onClicked: fullscreen.closeScene()
            }
        }
    }
}
