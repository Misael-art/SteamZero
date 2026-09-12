// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick

Item {
    id: cinema
    property var scene: null
    property string currentFocus: ""
    readonly property bool selectionReady: scene !== null && scene.focusId === currentFocus
    readonly property var selectedGame: scene && scene.items ? scene.items[Number(scene.selected || 0)] || ({}) : ({})
    property var accessibility: ({})
    readonly property var entries: scene && scene.layouts && scene.layouts.covers ? scene.layouts.covers.entries : []
    readonly property real textScale: Math.max(1, Number(accessibility.visualScale || 1))
    readonly property bool highContrast: !!accessibility.highContrast
    signal activated

    readonly property string metadataText: {
        const game = cinema.selectedGame;
        const parts = [];
        if (game.releaseDate)
            parts.push(String(game.releaseDate).slice(0, 4));
        if (game.genres && game.genres.length)
            parts.push(game.genres.join(" / "));
        if (game.players !== undefined)
            parts.push(qsTr("%1 jogador(es)").arg(game.players));
        if (game.rating !== undefined)
            parts.push(qsTr("Nota %1/100").arg(game.rating));
        if (game.playtime !== undefined)
            parts.push(qsTr("%1 min jogados").arg(Math.floor(game.playtime / 60)));
        return parts.join(" · ");
    }

    Image {
        anchors.fill: parent
        source: cinema.highContrast ? "" : String(cinema.selectedGame.fanartUrl || "")
        asynchronous: true
        sourceSize: Qt.size(Math.ceil(width), Math.ceil(height))
        fillMode: Image.PreserveAspectCrop
        opacity: 0.15
    }

    function activateSelection() {
        if (!cinema.selectionReady)
            return false;
        cinema.activated();
        return true;
    }

    Item {
        id: coverViewport
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.topMargin: 16
        anchors.bottom: selectedTitle.top
        anchors.bottomMargin: 16
        clip: true

        Item {
            id: coverCanvas
            anchors.centerIn: parent
            width: cinema.scene && cinema.scene.viewport ? cinema.scene.viewport.width : cinema.width
            height: cinema.scene && cinema.scene.viewport ? cinema.scene.viewport.height : cinema.height
            scale: Math.min(coverViewport.width / Math.max(1, width), Math.max(0, coverViewport.height) / Math.max(1, height))

            Repeater {
                model: cinema.entries
                delegate: Rectangle {
                    id: card
                    objectName: modelData.highlighted ? "cinemaSelectedCover" : "cinemaNeighbourCover"
                    required property var modelData
                    required property int index
                    readonly property var game: cinema.scene.items[index] || ({})
                    x: modelData.x
                    y: modelData.y
                    width: modelData.width
                    height: modelData.height
                    scale: modelData.scale
                    opacity: cinema.highContrast ? 1 : modelData.opacity
                    z: modelData.z
                    color: cinema.highContrast ? "#000000" : "#142332"
                    radius: 8
                    border.width: modelData.highlighted ? 3 : 1
                    border.color: modelData.highlighted ? "#ffffff" : "#667789"
                    Accessible.name: String(game.title || "")
                    Accessible.role: Accessible.Button
                    Accessible.description: qsTr("Abrir os detalhes do jogo selecionado")
                    Image {
                        id: cover
                        anchors.fill: parent
                        anchors.margins: 4
                        source: card.modelData.source || ""
                        asynchronous: true
                        fillMode: Image.PreserveAspectFit
                        sourceSize.width: Math.ceil(width)
                        sourceSize.height: Math.ceil(height)
                    }
                    Text {
                        anchors.fill: parent
                        anchors.margins: 20
                        visible: cover.status !== Image.Ready
                        text: String(card.game.title || qsTr("Sem capa"))
                        textFormat: Text.PlainText
                        color: "#ffffff"
                        font.pixelSize: 22 * cinema.textScale
                        wrapMode: Text.Wrap
                        elide: Text.ElideRight
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    TapHandler {
                        enabled: card.modelData.highlighted && cinema.selectionReady
                        onTapped: cinema.activateSelection()
                    }
                }
            }
        }
    }
    Text {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 24
        text: "AURA CINEMA · " + String(cinema.scene ? cinema.scene.collection || "" : "")
        textFormat: Text.PlainText
        width: parent.width - 48
        elide: Text.ElideRight
        color: "#ffffff"
        font.pixelSize: 18 * cinema.textScale
    }
    Text {
        id: selectedTitle
        objectName: "cinemaSelectedTitle"
        anchors.bottom: metadataRail.top
        anchors.bottomMargin: 16
        anchors.horizontalCenter: parent.horizontalCenter
        width: parent.width - 48
        text: cinema.selectionReady ? String(cinema.selectedGame.title || "") : qsTr("Atualizando seleção…")
        textFormat: Text.PlainText
        color: "#ffffff"
        font.pixelSize: 24 * cinema.textScale
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }
    Text {
        id: metadataRail
        anchors.bottom: footer.top
        anchors.bottomMargin: 12
        anchors.horizontalCenter: parent.horizontalCenter
        width: parent.width - 48
        text: cinema.selectionReady ? cinema.metadataText : ""
        textFormat: Text.PlainText
        color: "#ffffff"
        font.pixelSize: 14 * cinema.textScale
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }
    Text {
        id: footer
        objectName: "cinemaFooter"
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: 24
        text: qsTr("← → Jogos    ↑ ↓ Coleções    Enter Detalhes    F Buscar")
        width: parent.width - 48
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        color: "#ffffff"
        font.pixelSize: 16 * cinema.textScale
    }
}
