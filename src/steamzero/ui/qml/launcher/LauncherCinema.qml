// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import ".."

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
    readonly property bool reducedMotion: !!accessibility.reducedMotion
    // A cena pode publicar o tier escolhido pelo Theme Engine. Até que o
    // contrato do catálogo publique a preferência, balanced é o fallback
    // seguro: mantém profundidade sem depender de vídeo ou shader externo.
    readonly property string performanceTier: scene && scene.performanceTier
        ? String(scene.performanceTier) : "balanced"
    readonly property bool backdropEffects: !highContrast && performanceTier !== "low"
    readonly property color accentColor: highContrast ? "#55d8ff" : "#22d3ee"
    readonly property string connectionState: scene && scene.connectionState
        ? String(scene.connectionState) : "connected"
    property int clockTick: 0
    readonly property string clockLabel: {
        clockTick;
        return Qt.formatTime(new Date(), "hh:mm");
    }
    readonly property var metadataParts: {
        const game = cinema.selectedGame;
        const parts = [];
        if (game.releaseDate)
            parts.push(String(game.releaseDate).slice(0, 4));
        if (game.genres && game.genres.length)
            parts.push(game.genres.slice(0, 2).join(" / "));
        if (game.players !== undefined)
            parts.push(qsTr("%1 jogador(es)").arg(game.players));
        if (game.rating !== undefined)
            parts.push(qsTr("★ %1").arg(game.rating));
        if (game.playtime !== undefined)
            parts.push(qsTr("%1 min").arg(Math.floor(game.playtime / 60)));
        return parts;
    }
    signal activated

    Timer {
        id: clockRefresh
        interval: 30000
        repeat: true
        running: true
        onTriggered: ++cinema.clockTick
    }

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

    Rectangle {
        anchors.fill: parent
        color: cinema.highContrast ? "#000000" : "#071019"
    }
    // Uma única textura para o backdrop: o renderer aplica blur/vignette
    // somente quando o tier permite. Sem arte, a base sólida continua legível.
    MediaEffectLayer {
        id: backdrop
        anchors.fill: parent
        visible: cinema.backdropEffects && String(cinema.selectedGame.fanartUrl || "") !== ""
        source: cinema.backdropEffects ? String(cinema.selectedGame.fanartUrl || "") : ""
        decodeSize: Qt.size(Math.ceil(width), Math.ceil(height))
        fillMode: Image.PreserveAspectCrop
        opacity: 0.34
        effects: [
            {"type": "blur", "parameters": {"radius": cinema.performanceTier === "cinematic" ? 28 : 18}},
            {"type": "vignette", "parameters": {"color": "#02060b", "strength": 0.72}}
        ]
    }
    // Véus de leitura: mantém arte como elemento principal, mas protege
    // título, chips e rodapé em capas claras ou sem paleta publicada.
    Rectangle {
        anchors.fill: parent
        color: "#071019"
        opacity: cinema.highContrast ? 1 : 0.48
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#02060bdd" }
            GradientStop { position: 0.42; color: "#07101944" }
            GradientStop { position: 1.0; color: "#02060bcf" }
        }
    }
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Math.max(112, parent.height * 0.18)
        color: "#02060b"
        opacity: cinema.highContrast ? 1 : 0.58
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#02060b00" }
            GradientStop { position: 1.0; color: "#02060bcc" }
        }
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
                    border.color: modelData.highlighted ? cinema.accentColor : "#667789"
                    Behavior on scale {
                        enabled: !cinema.reducedMotion
                        NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
                    }
                    Behavior on opacity {
                        enabled: !cinema.reducedMotion
                        NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
                    }
                    Accessible.name: String(game.title || "")
                    Accessible.role: Accessible.Button
                    Accessible.description: qsTr("Abrir os detalhes do jogo selecionado")
                    MediaEffectLayer {
                        id: cover
                        anchors.fill: parent
                        anchors.margins: 4
                        source: card.modelData.source || ""
                        decodeSize: Qt.size(Math.ceil(width), Math.ceil(height))
                        fillMode: Image.PreserveAspectFit
                        effects: !card.modelData.highlighted && cinema.performanceTier !== "low"
                            ? [{"type": "blur", "parameters": {"radius": 12}}] : []
                    }
                    Text {
                        anchors.fill: parent
                        anchors.margins: 20
                        visible: cover.sourceStatus !== Image.Ready
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
        objectName: "cinemaHeader"
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 24
        text: "AURA  /  CINEMA  ·  " + String(cinema.scene ? cinema.scene.collection || "" : "")
        textFormat: Text.PlainText
        width: parent.width - 48
        elide: Text.ElideRight
        color: "#ffffff"
        font.pixelSize: 18 * cinema.textScale
    }
    Row {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 24
        spacing: 16
        Text {
            objectName: "cinemaConnection"
            text: (cinema.connectionState === "connected" ? "● ONLINE" : "● OFFLINE")
            color: cinema.connectionState === "connected" ? "#7be47f" : "#ff8e94"
            font.pixelSize: 14 * cinema.textScale
            Accessible.name: qsTr("Estado da ponte: %1").arg(text)
        }
        Text {
            objectName: "cinemaClock"
            text: cinema.clockLabel
            color: "#ffffff"
            font.pixelSize: 18 * cinema.textScale
            font.bold: true
            Accessible.name: qsTr("Hora atual %1").arg(text)
        }
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
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: selectedTitle.top
        anchors.bottomMargin: 8
        width: Math.min(parent.width * 0.28, 320)
        height: 3
        radius: 2
        color: cinema.accentColor
        visible: cinema.selectionReady && !cinema.highContrast
    }
    Item {
        id: metadataRail
        anchors.bottom: footer.top
        anchors.bottomMargin: 12
        anchors.horizontalCenter: parent.horizontalCenter
        width: parent.width - 48
        height: 32 * cinema.textScale
        Accessible.name: cinema.selectionReady ? cinema.metadataText : ""
        Row {
            anchors.centerIn: parent
            spacing: 8
            Repeater {
                model: cinema.selectionReady ? cinema.metadataParts : []
                delegate: Rectangle {
                    required property string modelData
                    height: 28 * cinema.textScale
                    width: metadataLabel.implicitWidth + 20 * cinema.textScale
                    radius: height / 2
                    color: cinema.highContrast ? "#000000" : "#071019cc"
                    border.width: 1
                    border.color: cinema.highContrast ? "#ffffff" : "#526779"
                    Text {
                        id: metadataLabel
                        anchors.centerIn: parent
                        text: modelData
                        color: "#ffffff"
                        font.pixelSize: 12 * cinema.textScale
                    }
                }
            }
        }
    }
    Text {
        id: footer
        objectName: "cinemaFooter"
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: 24
        text: qsTr("← → Jogos    ↑ ↓ Coleções    Enter Detalhes    F Buscar    Esc Voltar")
        width: parent.width - 48
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        color: "#ffffff"
        font.pixelSize: 16 * cinema.textScale
    }
}
