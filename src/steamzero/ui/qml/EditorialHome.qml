// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Entrada editorial para dados que a dashboard já publica. Não cria um
// catálogo paralelo: títulos, favoritos, coleções e sistemas são projeções
// transitórias dos mesmos read models usados pelo restante da central.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: root

    required property var steamGames
    required property var emulation
    required property var playtime
    required property var collections
    property var components: []
    property var sync: ({})
    property var doctor: ({})
    property var libraryHealth: ({})
    property bool needsAttention: false
    property bool reducedMotion: false
    property bool highContrast: false
    property int themeMinimumTarget: 48
    property var typography: ({})
    required property color backgroundColor
    required property color surfaceColor
    required property color raisedColor
    required property color borderColor
    required property color textColor
    required property color mutedColor
    required property color cyanColor
    required property color cyanDarkColor
    required property color greenColor
    required property color amberColor

    signal libraryRequested(string systemId)
    signal collectionRequested(string collectionId)
    signal systemRequested()
    signal continueRequested(var game)
    signal maintenanceRequested(string area)

    // Mesmo LOD da biblioteca: a arte é a mesma, o teto de decode também.
    property CoverLod coverLod: CoverLod { devicePixelRatio: Screen.devicePixelRatio }

    function coverDecodeSize(logicalWidth, logicalHeight) {
        return coverLod.decodeSize(logicalWidth, logicalHeight)
    }

    readonly property int minimumTarget: Math.max(48, themeMinimumTarget)
    readonly property bool compact: width < 980
    readonly property var editorialPlatforms: emulation && emulation.editorialPlatforms
        ? emulation.editorialPlatforms : (emulation && emulation.platforms ? emulation.platforms : [])
    readonly property var catalog: {
        const rows = []
        const steam = steamGames || []
        for (let i = 0; i < steam.length; ++i) {
            const game = steam[i]
            rows.push({
                "gameRef": "steam:" + String(game.id || ""),
                "id": String(game.id || ""),
                "title": String(game.name || qsTr("Jogo sem título")),
                "systemId": "steam",
                "systemName": qsTr("Steam"),
                "coverUrl": String(game.coverUrl || ""),
                "launchable": /^[0-9]+$/.test(String(game.id || ""))
            })
        }
        const platforms = editorialPlatforms
        for (let p = 0; p < platforms.length; ++p) {
            const platform = platforms[p]
            const games = platform.games || []
            for (let g = 0; g < games.length; ++g) {
                const game = games[g]
                rows.push({
                    "gameRef": "emulation:" + String(game.id || game.path || ""),
                    "id": String(game.id || game.path || ""),
                    "title": String(game.name || game.title || qsTr("Jogo sem título")),
                    "systemId": String(platform.id || ""),
                    "systemName": String(platform.name || platform.shortName || qsTr("Emulação")),
                    "coverUrl": String(game.coverUrl || game.artworkUrl || ""),
                    "launchable": false
                })
            }
        }
        return rows
    }
    readonly property var favoriteRefs: collections && collections.favorites ? collections.favorites : []
    readonly property var collectionItems: collections && collections.collections
        ? collections.collections : []
    readonly property var primaryCollection: collectionItems.length > 0
        ? collectionItems[0] : null
    readonly property var favorites: catalog.filter(function(game) {
        return root.favoriteRefs.indexOf(game.gameRef) >= 0
    })
    readonly property var recent: playtime && playtime.games ? playtime.games : []
    readonly property var systems: {
        const rows = [{
            "id": "steam", "name": qsTr("Steam"), "gameCount": (steamGames || []).length,
            "state": (steamGames || []).length > 0 ? "ready" : "unavailable",
            "detail": (steamGames || []).length > 0 ? qsTr("Biblioteca disponível")
                : qsTr("Nenhum jogo Steam publicado")
        }]
        const platforms = editorialPlatforms
        for (let i = 0; i < platforms.length; ++i) {
            const platform = platforms[i]
            rows.push({
                "id": String(platform.id || "platform-" + i),
                "name": String(platform.name || platform.shortName || qsTr("Sistema")),
                "gameCount": platform.games ? platform.games.length : 0,
                "state": String(platform.state || "unverified"),
                "detail": String(platform.statusLabel || qsTr("Não verificado"))
            })
        }
        return rows
    }
    readonly property var attentionSystems: systems.filter(function(system) {
        return system.state !== "ready" && system.state !== "installed"
    })
    readonly property int componentAttention: (components || []).filter(function(component) {
        return component.state !== "installed" && component.state !== "ready"
    }).length
    readonly property int syncAttention: Number(sync && sync.pending || 0)
        + Number(sync && sync.conflicted || 0)
    readonly property int libraryAttention: Number(libraryHealth && libraryHealth.counts
        && libraryHealth.counts.suspect || 0) + Number(libraryHealth && libraryHealth.counts
        && libraryHealth.counts.missing || 0) + Number(libraryHealth && libraryHealth.counts
        && libraryHealth.counts.error || 0)
    readonly property var featured: recent.length > 0 ? recent[0]
        : favorites.length > 0 ? favorites[0] : catalog.length > 0 ? catalog[0] : null
    // EditorialHome é filho de um ColumnLayout no overview. Ancorar a coluna
    // nos quatro lados sem publicar implicitHeight fazia o layout pai reservar
    // altura zero e os blocos seguintes eram desenhados por cima dela.
    implicitHeight: homeContent.implicitHeight

    component EditorialButton: Button {
        property bool primaryAction: false
        padding: 14
        font.pixelSize: root.typeSize("controlHint")
        contentItem: Label {
            text: parent.text
            color: !parent.enabled ? root.mutedColor
                : parent.primaryAction ? "#ffffff" : root.textColor
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 10
            color: !parent.enabled ? root.surfaceColor
                : parent.primaryAction ? (parent.down ? root.cyanDarkColor : root.cyanColor)
                : parent.down ? root.raisedColor : root.surfaceColor
            border.color: parent.activeFocus ? root.cyanColor
                : parent.primaryAction ? root.cyanDarkColor : root.borderColor
            border.width: parent.activeFocus ? 3 : 1
        }
    }

    function playtimeLabel(seconds) {
        const minutes = Math.floor(Math.max(0, Number(seconds || 0)) / 60)
        if (minutes < 60)
            return qsTr("%1 min").arg(minutes)
        return qsTr("%1 h %2 min").arg(Math.floor(minutes / 60)).arg(minutes % 60)
    }

    function typeSize(role, compactFactor) {
        const fallback = {
            "display": 36, "heading": 24, "title": 20, "body": 16,
            "metadata": 14, "badge": 12, "caption": 12,
            "controlHint": 14, "diagnostic": 14
        }
        const base = Number(typography && typography[role]) || fallback[role] || fallback.body
        const scale = Number(typography && typography.scale) || 1
        return Math.round(base * scale * (compactFactor === undefined ? 1 : compactFactor))
    }

    function stateColor(state) {
        if (state === "ready" || state === "installed")
            return greenColor
        if (state === "attention" || state === "blocked" || state === "unavailable")
            return amberColor
        return mutedColor
    }

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
    }

    ColumnLayout {
        id: homeContent
        width: parent.width
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: root.compact ? 12 : 20

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: qsTr("Início")
                color: root.textColor
                font.pixelSize: root.typeSize("display", root.compact ? 0.72 : 1)
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            Label {
                text: qsTr("%1 títulos publicados").arg(root.catalog.length)
                color: root.mutedColor
                font.pixelSize: root.typeSize("metadata")
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: root.compact ? 184 : 220
            color: root.highContrast ? "#000000" : root.surfaceColor
            radius: 18
            border.color: root.borderColor
            clip: true
            Image {
                anchors.fill: parent
                source: root.featured && root.featured.coverUrl ? root.featured.coverUrl : ""
                visible: source !== "" && !root.highContrast
                // Fundo a 22% de opacidade: decodificar a arte inteira aqui
                // custaria o mesmo que uma capa em tela cheia para um efeito
                // que ninguém consegue ler em detalhe.
                sourceSize: root.coverDecodeSize(width, height)
                asynchronous: true
                fillMode: Image.PreserveAspectCrop
                opacity: 0.22
            }
            Rectangle {
                anchors.fill: parent
                color: root.highContrast ? "#000000" : root.backgroundColor
                opacity: root.highContrast ? 1 : 0.78
            }
            RowLayout {
                anchors.fill: parent
                anchors.margins: root.compact ? 18 : 28
                spacing: 18
                Rectangle {
                    visible: Boolean(root.featured && root.featured.coverUrl)
                    color: root.raisedColor
                    radius: 10
                    border.color: root.borderColor
                    clip: true
                    Layout.preferredWidth: root.compact ? 82 : 120
                    Layout.preferredHeight: root.compact ? 120 : 172
                    Image {
                        anchors.fill: parent
                        source: root.featured && root.featured.coverUrl ? root.featured.coverUrl : ""
                        sourceSize: root.coverDecodeSize(root.compact ? 82 : 120,
                            root.compact ? 120 : 172)
                        asynchronous: true
                        fillMode: Image.PreserveAspectCrop
                    }
                }
                Rectangle {
                    visible: !root.featured || !root.featured.coverUrl
                    color: root.raisedColor
                    radius: 10
                    border.color: root.borderColor
                    Layout.preferredWidth: root.compact ? 82 : 120
                    Layout.preferredHeight: root.compact ? 120 : 172
                    NavigationIcon {
                        anchors.centerIn: parent
                        glyph: root.featured && (root.featured.systemId === "steam"
                            || root.featured.source === "steam") ? "steam" : "emulators"
                        iconColor: root.cyanColor
                        width: root.compact ? 40 : 54
                        height: width
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Label {
                        text: root.recent.length > 0 ? qsTr("Continuar jogando")
                            : root.featured ? qsTr("Em destaque") : qsTr("Sua biblioteca")
                        color: root.cyanDarkColor
                        font.pixelSize: root.typeSize("controlHint")
                        font.weight: Font.DemiBold
                    }
                    Label {
                        text: root.featured ? String(root.featured.title || root.featured.name || qsTr("Jogo"))
                            : qsTr("Nenhum jogo publicado ainda")
                        color: root.textColor
                        font.pixelSize: root.typeSize("display", root.compact ? 0.64 : 0.89)
                        font.weight: Font.DemiBold
                        maximumLineCount: 2
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Label {
                        text: root.recent.length > 0
                            ? qsTr("%1 · %2").arg(String(root.featured.source || qsTr("Sessão")))
                                .arg(root.playtimeLabel(root.featured.playedSeconds))
                            : root.featured ? String(root.featured.systemName || qsTr("Biblioteca"))
                            : qsTr("Adicione uma fonte gerenciada para começar")
                        color: root.mutedColor
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Item { Layout.fillHeight: true }
                    EditorialButton {
                        readonly property bool canContinue: Boolean(root.featured && root.featured.action
                            && root.featured.action.enabled === true)
                        text: canContinue ? String(root.featured.action.label || qsTr("Continuar"))
                            : root.featured ? qsTr("Abrir na biblioteca") : qsTr("Explorar sistemas")
                        primaryAction: true
                        Layout.minimumHeight: root.minimumTarget
                        Layout.minimumWidth: 190
                        Accessible.name: text
                        onClicked: {
                            if (canContinue) {
                                root.continueRequested(root.featured)
                                return
                            }
                            root.libraryRequested(root.featured
                                ? String(root.featured.systemId || root.featured.source || "all") : "all")
                        }
                    }
                }
            }
        }

        GridLayout {
            columns: root.compact ? 1 : 2
            columnSpacing: 16
            rowSpacing: 16
            Layout.fillWidth: true

            Rectangle {
                color: root.surfaceColor
                radius: 14
                border.color: root.borderColor
                Layout.fillWidth: true
                Layout.preferredHeight: 164
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("Favoritos"); color: root.textColor; font.pixelSize: root.typeSize("title", 0.95); font.weight: Font.DemiBold; Layout.fillWidth: true }
                        Label { text: String(root.favorites.length); color: root.cyanDarkColor; font.weight: Font.DemiBold }
                    }
                    Label {
                        text: root.favorites.length > 0 ? root.favorites.slice(0, 3).map(function(game) { return game.title }).join(" · ")
                            : qsTr("Marque favoritos nas sessões e coleções gerenciadas.")
                        color: root.mutedColor
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        Layout.fillWidth: true
                    }
                    Item { Layout.fillHeight: true }
                    EditorialButton {
                        text: qsTr("Ver biblioteca")
                        objectName: "overview.open-library"
                        Accessible.name: text
                        Layout.minimumHeight: root.minimumTarget
                        onClicked: root.libraryRequested("all")
                    }
                }
            }

            Rectangle {
                color: root.surfaceColor
                radius: 14
                border.color: root.borderColor
                Layout.fillWidth: true
                Layout.preferredHeight: 164
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("Coleções"); color: root.textColor; font.pixelSize: root.typeSize("title", 0.95); font.weight: Font.DemiBold; Layout.fillWidth: true }
                        Label { text: String(root.collectionItems.length); color: root.cyanDarkColor; font.weight: Font.DemiBold }
                    }
                    Label {
                        text: root.primaryCollection
                            ? qsTr("%1 · %2 jogo(s)").arg(String(root.primaryCollection.name || qsTr("Coleção")))
                                .arg(root.primaryCollection.members ? root.primaryCollection.members.length : 0)
                            : qsTr("Nenhuma coleção foi publicada ainda.")
                        color: root.mutedColor
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        Layout.fillWidth: true
                    }
                    Item { Layout.fillHeight: true }
                    EditorialButton {
                        text: root.primaryCollection ? qsTr("Abrir coleção") : qsTr("Coleções indisponíveis")
                        enabled: root.primaryCollection !== null
                        Layout.minimumHeight: root.minimumTarget
                        Accessible.description: root.primaryCollection
                            ? qsTr("Filtra a biblioteca pela coleção publicada")
                            : qsTr("A fonte ainda não publicou coleções")
                        onClicked: root.collectionRequested(String(root.primaryCollection.id || ""))
                    }
                }
            }

            Rectangle {
                color: root.surfaceColor
                radius: 14
                border.color: root.needsAttention || root.attentionSystems.length > 0 ? root.amberColor : root.borderColor
                Layout.fillWidth: true
                Layout.preferredHeight: 164
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("Pendências"); color: root.textColor; font.pixelSize: root.typeSize("title", 0.95); font.weight: Font.DemiBold; Layout.fillWidth: true }
                        Label { text: root.needsAttention || root.attentionSystems.length > 0 ? qsTr("Revisar") : qsTr("Nenhuma"); color: root.needsAttention || root.attentionSystems.length > 0 ? root.amberColor : root.greenColor; font.weight: Font.DemiBold }
                    }
                    Label {
                        text: root.needsAttention ? qsTr("O estado do Desktop pede revisão antes de aplicar mudanças.")
                            : root.attentionSystems.length > 0
                                ? qsTr("%1 sistema(s) ainda exigem configuração ou verificação.").arg(root.attentionSystems.length)
                                : qsTr("Nenhuma ação operacional urgente foi publicada.")
                        color: root.mutedColor
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        Layout.fillWidth: true
                    }
                    Item { Layout.fillHeight: true }
                    EditorialButton {
                        text: qsTr("Abrir sistema")
                        objectName: "overview.open-system"
                        Accessible.name: text
                        Layout.minimumHeight: root.minimumTarget
                        onClicked: root.systemRequested()
                    }
                }
            }

            Rectangle {
                color: root.surfaceColor
                radius: 14
                border.color: root.borderColor
                Layout.fillWidth: true
                Layout.preferredHeight: 164
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("Recentes"); color: root.textColor; font.pixelSize: root.typeSize("title", 0.95); font.weight: Font.DemiBold; Layout.fillWidth: true }
                        Label { text: String(root.recent.length); color: root.cyanDarkColor; font.weight: Font.DemiBold }
                    }
                    Label {
                        text: root.recent.length > 0
                            ? root.recent.slice(0, 3).map(function(game) { return String(game.title || qsTr("Jogo")) }).join(" · ")
                            : qsTr("As sessões gerenciadas aparecerão aqui quando existirem.")
                        color: root.mutedColor
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        Layout.fillWidth: true
                    }
                    Item { Layout.fillHeight: true }
                    EditorialButton {
                        text: qsTr("Abrir recentes")
                        objectName: "overview.open-recent"
                        Accessible.name: text
                        Layout.minimumHeight: root.minimumTarget
                        onClicked: root.libraryRequested("all")
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Label { text: qsTr("Sistemas"); color: root.textColor; font.pixelSize: root.typeSize("heading", 0.92); font.weight: Font.DemiBold; Layout.fillWidth: true }
            EditorialButton {
                text: qsTr("Todos os sistemas")
                objectName: "overview.all-systems"
                Accessible.name: text
                Layout.minimumHeight: root.minimumTarget
                onClicked: root.libraryRequested("all")
            }
        }
        Flickable {
            clip: true
            Layout.fillWidth: true
            Layout.preferredHeight: root.compact ? 118 : 128
            contentWidth: systemRow.width
            contentHeight: height
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.HorizontalFlick
            Row {
                id: systemRow
                height: parent.height
                spacing: 12
                Repeater {
                    model: root.systems
                    delegate: Button {
                        required property var modelData
                        width: root.compact ? 190 : 230
                        height: parent.height
                        Accessible.name: qsTr("%1, %2 jogo(s), %3")
                            .arg(modelData.name).arg(modelData.gameCount).arg(modelData.detail)
                        onClicked: root.libraryRequested(modelData.id)
                        background: Rectangle {
                            color: parent.down ? root.raisedColor : root.surfaceColor
                            radius: 14
                            border.color: parent.activeFocus ? root.cyanColor : root.borderColor
                            border.width: parent.activeFocus ? 3 : 1
                        }
                        contentItem: ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            Label { text: modelData.name; color: root.textColor; font.pixelSize: root.typeSize("title", 0.95); font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                            Label { text: qsTr("%1 jogo(s)").arg(modelData.gameCount); color: root.mutedColor; font.pixelSize: root.typeSize("caption", 1.08) }
                            Item { Layout.fillHeight: true }
                            Label { text: modelData.detail; color: root.stateColor(modelData.state); font.pixelSize: root.typeSize("badge"); elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                    }
                }
            }
        }

        Label {
            text: qsTr("Sistema e manutenção")
            color: root.textColor
            font.pixelSize: root.typeSize("heading", 0.92)
            font.weight: Font.DemiBold
            Layout.topMargin: root.compact ? 4 : 10
        }
        GridLayout {
            columns: root.compact ? 1 : 3
            columnSpacing: 12
            rowSpacing: 12
            Layout.fillWidth: true
            Repeater {
                model: [
                    {"id": "emulators", "title": qsTr("Emuladores"),
                        "detail": root.componentAttention > 0
                            ? qsTr("%1 item(ns) exigem atenção").arg(root.componentAttention)
                            : qsTr("Nenhuma pendência publicada"),
                        "attention": root.componentAttention > 0},
                    {"id": "sync", "title": qsTr("Saves e sync"),
                        "detail": root.syncAttention > 0
                            ? qsTr("%1 item(ns) na fila ou em conflito").arg(root.syncAttention)
                            : qsTr("Nenhuma fila pendente publicada"),
                        "attention": root.syncAttention > 0},
                    {"id": "system", "title": qsTr("Diagnóstico e mídia"),
                        "detail": root.libraryAttention > 0
                            ? qsTr("%1 item(ns) de biblioteca exigem revisão").arg(root.libraryAttention)
                            : root.doctor && root.doctor.state === "healthy"
                                ? qsTr("Verificações publicadas sem alerta")
                                : qsTr("Estado detalhado disponível no Sistema"),
                        "attention": root.libraryAttention > 0 || (root.doctor
                            && (root.doctor.state === "failed" || root.doctor.state === "attention"))}
                ]
                delegate: EditorialButton {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.minimumHeight: root.minimumTarget + 32
                    Accessible.name: qsTr("%1: %2").arg(modelData.title).arg(modelData.detail)
                    onClicked: root.maintenanceRequested(modelData.id)
                    background: Rectangle {
                        radius: 12
                        color: parent.down ? root.raisedColor : root.surfaceColor
                        border.color: parent.activeFocus ? root.cyanColor
                            : modelData.attention ? root.amberColor : root.borderColor
                        border.width: parent.activeFocus ? 3 : 1
                    }
                    contentItem: ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        Label { text: modelData.title; color: root.textColor; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        Label { text: modelData.detail; color: modelData.attention ? root.amberColor : root.mutedColor; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
            }
        }
    }
}
