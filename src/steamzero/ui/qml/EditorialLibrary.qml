// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Vertical slice editorial: Sistema → Biblioteca → Dossiê → Jogar.
//
// Este componente só consome os read models já publicados pela dashboard. Ele
// nunca varre diretórios, infere compatibilidade nem tenta iniciar emulação sem
// um contrato de launcher. O tema fornece uma composição; a verdade continua
// pertencendo ao domínio.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var steamGames
    required property var emulation
    required property var playtime
    property var collections: ({})
    property var steamGameplay: ({})
    property var sync: ({})
    property var effectStacks: ({})
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
    required property color redColor
    property bool reducedMotion: false
    property bool highContrast: false
    property int themeMinimumTarget: 48
    property real themeFocusedScale: 1.05
    property real themePeripheralOpacity: 0.58

    signal launchSteamRequested(string gameId)
    signal openSteamConfigurationRequested(string gameId)

    // `systems` é a primeira vista da jornada. A entrada Steam é construída
    // apenas quando o read model existe; as demais vêm do catálogo de
    // plataformas já composto pelo domínio.
    readonly property var systems: {
        const rows = []
        const steam = steamGames || []
        rows.push({
            "id": "steam",
            "name": qsTr("Steam"),
            "kind": "steam",
            "gameCount": steam.length,
            "state": steam.length > 0 ? "ready" : "unavailable",
            "statusLabel": steam.length > 0 ? qsTr("Biblioteca disponível")
                : qsTr("Nenhum jogo Steam instalado foi publicado"),
            "readiness": {"percent": steam.length > 0 ? 100 : 0},
            "subsystems": [],
            "requirements": ({})
        })
        const platforms = emulation && emulation.platforms ? emulation.platforms : []
        for (let i = 0; i < platforms.length; ++i) {
            const platform = platforms[i]
            rows.push({
                "id": String(platform.id || "platform-" + i),
                "name": String(platform.name || platform.shortName || qsTr("Sistema")),
                "kind": "emulation",
                "gameCount": platform.games ? platform.games.length : 0,
                "state": String(platform.state || "unverified"),
                "statusLabel": String(platform.statusLabel || qsTr("Não verificado")),
                "readiness": platform.readiness || ({"percent": 0}),
                "subsystems": Array.isArray(platform.subsystems) ? platform.subsystems : [],
                "requirements": platform.requirements || ({})
            })
        }
        return rows
    }

    // Um catálogo unificado, preservando a origem e os estados reais. Não
    // contém descrição, score, gênero ou artwork inventados.
    readonly property var games: {
        const rows = []
        const steam = steamGames || []
        for (let i = 0; i < steam.length; ++i) {
            const game = steam[i]
            rows.push({
                "id": String(game.id || ""),
                "gameRef": "steam:" + String(game.id || ""),
                "name": String(game.name || qsTr("Jogo sem título")),
                "source": "steam",
                "systemId": "steam",
                "systemName": qsTr("Steam"),
                "coverUrl": String(game.coverUrl || ""),
                "heroUrl": String(game.heroUrl || game.fanartUrl || ""),
                "screenshotUrl": String(game.screenshotUrl || ""),
                "screenshotUrls": Array.isArray(game.screenshotUrls) ? game.screenshotUrls
                    : (Array.isArray(game.screenshots) ? game.screenshots : []),
                "bannerUrl": String(game.bannerUrl || ""),
                "genre": String(game.genre || ""),
                "year": String(game.year || game.releaseYear || ""),
                "developer": String(game.developer || ""),
                "state": String(game.state || "unverified"),
                "launchable": /^[0-9]+$/.test(String(game.id || "")),
                "launchReason": ""
            })
        }
        const platforms = emulation && emulation.platforms ? emulation.platforms : []
        for (let p = 0; p < platforms.length; ++p) {
            const platform = platforms[p]
            const platformGames = platform.games || []
            for (let g = 0; g < platformGames.length; ++g) {
                const game = platformGames[g]
                rows.push({
                    "id": String(game.id || game.path || ""),
                    "gameRef": "emulation:" + String(game.id || game.path || ""),
                    "name": String(game.name || game.title || qsTr("Jogo sem título")),
                    "source": "emulation",
                    "systemId": String(platform.id || ""),
                    "systemName": String(platform.name || platform.shortName || qsTr("Emulação")),
                    "coverUrl": String(game.coverUrl || game.artworkUrl || ""),
                    "heroUrl": String(game.heroUrl || game.fanartUrl || ""),
                    "screenshotUrl": String(game.screenshotUrl || ""),
                    "screenshotUrls": Array.isArray(game.screenshotUrls) ? game.screenshotUrls
                        : (Array.isArray(game.screenshots) ? game.screenshots : []),
                    "bannerUrl": String(game.bannerUrl || game.fallbackArtworkUrl || ""),
                    "genre": String(game.genre || ""),
                    "year": String(game.year || game.releaseYear || ""),
                    "developer": String(game.developer || ""),
                    "state": String(platform.state || "unverified"),
                    "launchable": false,
                    "launchReason": qsTr("O launcher seguro desta plataforma ainda não foi publicado.")
                })
            }
        }
        return rows
    }

    readonly property var baseVisibleGames: games.filter(function(game) {
        if (root.systemFilter !== "all" && game.systemId !== root.systemFilter)
            return false
        if (root.collectionFilter !== "" && !root.isInCollection(game.gameRef))
            return false
        return root.initialFilter === "" || root.matchesInitial(game.name)
    })
    readonly property var visibleGames: baseVisibleGames.filter(function(game) {
        return root.matchesMetadata(game)
    })
    readonly property var selectedGame: selectedIndex >= 0 && selectedIndex < visibleGames.length
        ? visibleGames[selectedIndex] : ({})
    readonly property var selectedSystem: selectedSystemIndex >= 0 && selectedSystemIndex < systems.length
        ? systems[selectedSystemIndex] : ({})
    readonly property var selectedPlaytime: root.playtimeEntryFor(selectedGame)
    readonly property bool compact: width < 1080 || height < 680
    readonly property bool wide: width >= 2200
    readonly property int gutter: compact ? 16 : wide ? 56 : 32
    readonly property int focusDuration: reducedMotion ? 0 : 140
    readonly property int viewDuration: reducedMotion ? 0 : 280
    readonly property int minimumTarget: Math.max(48, themeMinimumTarget)
    readonly property bool contextualBackdropVisible: contextualBackdrop.visible

    property string view: "systems"
    property string systemFilter: "all"
    property string collectionFilter: ""
    property string initialFilter: ""
    property string genreFilter: ""
    property string yearFilter: ""
    property string developerFilter: ""
    property string libraryView: "carousel"
    property int selectedIndex: 0
    property int systemIndex: 0
    property int selectedSystemIndex: 0
    property alias systemRepeaterControl: systemRepeater
    property alias carouselControl: carousel
    property alias gridControl: gameGrid
    property alias listControl: gameList
    property alias primaryActionControl: primaryAction
    readonly property var alphabetFilters: ["Todos", "#", "A", "B", "C", "D", "E", "F", "G",
        "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V",
        "W", "X", "Y", "Z"]
    readonly property var collectionItems: collections && collections.collections
        ? collections.collections : []

    // Os controles de navegação pertencem à mesma superfície mineral dos
    // cards. O estilo padrão da plataforma não participa desta composição e
    // poderia introduzir botões claros ou métricas diferentes entre sistemas.
    component EditorialButton: Button {
        property bool primaryAction: false
        padding: 14
        font.pixelSize: 14
        contentItem: Label {
            text: parent.text
            color: !parent.enabled ? root.mutedColor
                : parent.primaryAction ? "#ffffff" : root.textColor
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            font: parent.font
        }
        background: Rectangle {
            radius: 10
            color: !parent.enabled ? root.surfaceColor
                : parent.primaryAction ? (parent.down ? root.cyanDarkColor : root.cyanColor)
                : parent.checked || parent.down ? root.raisedColor : root.surfaceColor
            border.color: parent.activeFocus ? root.cyanColor
                : parent.primaryAction ? root.cyanDarkColor : root.borderColor
            border.width: parent.activeFocus ? 3 : 1
        }
    }

    function stateColor(state) {
        if (state === "ready" || state === "installed")
            return greenColor
        if (state === "attention" || state === "blocked" || state === "unavailable")
            return amberColor
        return mutedColor
    }

    function stateLabel(state) {
        if (state === "installed")
            return qsTr("Instalado")
        if (state === "ready")
            return qsTr("Pronto")
        if (state === "attention")
            return qsTr("Atenção necessária")
        if (state === "blocked")
            return qsTr("Bloqueado")
        if (state === "unavailable")
            return qsTr("Indisponível")
        if (state === "unverified")
            return qsTr("Não verificado")
        return state ? String(state) : qsTr("Não verificado")
    }

    function openSystem(system) {
        systemFilter = system.id
        collectionFilter = ""
        initialFilter = ""
        resetMetadataFilters()
        selectedIndex = 0
        view = "library"
    }

    function openSystemDetails(index) {
        selectedSystemIndex = index
        view = "system"
    }

    function matchesInitial(name) {
        const initial = String(name || "").charAt(0).toUpperCase()
        if (initialFilter === "#")
            return !/^[A-Z]$/.test(initial)
        return initial === initialFilter
    }

    function metadataValues(field) {
        const values = []
        const seen = ({})
        for (let i = 0; i < baseVisibleGames.length; ++i) {
            const value = String(baseVisibleGames[i][field] || "").trim()
            if (value !== "" && !seen[value]) {
                seen[value] = true
                values.push(value)
            }
        }
        return values.sort(function(left, right) { return left.localeCompare(right) })
    }

    function metadataFilter(field) {
        if (field === "genre")
            return genreFilter
        if (field === "year")
            return yearFilter
        return developerFilter
    }

    function matchesMetadata(game) {
        return (genreFilter === "" || game.genre === genreFilter)
            && (yearFilter === "" || game.year === yearFilter)
            && (developerFilter === "" || game.developer === developerFilter)
    }

    function cycleMetadataFilter(field) {
        const values = metadataValues(field)
        if (values.length === 0)
            return
        const current = metadataFilter(field)
        const nextIndex = values.indexOf(current) + 1
        const next = nextIndex >= values.length ? "" : values[nextIndex]
        if (field === "genre")
            genreFilter = next
        else if (field === "year")
            yearFilter = next
        else
            developerFilter = next
        selectedIndex = 0
    }

    function resetMetadataFilters() {
        genreFilter = ""
        yearFilter = ""
        developerFilter = ""
    }

    // A seleção é declarativa e determinística: um read model pode publicar
    // mídia adicional, mas o componente nunca a procura em disco nem cria um
    // segundo catálogo. Boxart ainda precede screenshot/banner porque é a
    // única mídia que a biblioteca atual garante como identificador do jogo.
    function contextualMediaSource(game) {
        return String(game.heroUrl || game.fanartUrl || game.coverUrl
            || game.screenshotUrl || game.bannerUrl || "")
    }

    function screenshotSources(game) {
        const rows = []
        const values = game.screenshotUrls || []
        for (let i = 0; i < values.length; ++i) {
            const candidate = values[i]
            const source = typeof candidate === "string" ? candidate
                : String(candidate && (candidate.url || candidate.source) || "")
            if (source !== "" && rows.indexOf(source) < 0)
                rows.push(source)
        }
        if (rows.length === 0 && game.screenshotUrl)
            rows.push(String(game.screenshotUrl))
        return rows
    }

    function isInCollection(gameRef) {
        const collection = root.collectionItems.find(function(item) {
            return item.id === root.collectionFilter
        })
        return collection && collection.members
            ? collection.members.indexOf(gameRef) >= 0 : false
    }

    function playtimeEntryFor(game) {
        const entries = playtime && playtime.games ? playtime.games : []
        for (let i = 0; i < entries.length; ++i) {
            const entry = entries[i]
            if (String(entry.gameId || "") === String(game.id || "")
                    && String(entry.source || "") === String(game.source || ""))
                return entry
        }
        return ({})
    }

    function playtimeLabel(seconds) {
        const minutes = Math.floor(Math.max(0, Number(seconds || 0)) / 60)
        if (minutes < 60)
            return qsTr("%1 min").arg(minutes)
        return qsTr("%1 h %2 min").arg(Math.floor(minutes / 60)).arg(minutes % 60)
    }

    function requirementText(kind) {
        const requirement = selectedSystem.requirements
            ? selectedSystem.requirements[kind] : null
        if (!requirement)
            return qsTr("Não publicado")
        if (requirement.status === "not-required")
            return qsTr("Não exigido")
        return String(requirement.detail || requirement.status || qsTr("Não publicado"))
    }

    function requirementState(kind) {
        const requirement = selectedSystem.requirements
            ? selectedSystem.requirements[kind] : null
        if (!requirement)
            return "unverified"
        // O workspace publica ``ok`` para um requisito compatível. A camada
        // editorial pode aceitar o sinônimo ``ready`` para contratos futuros,
        // mas não pode rebaixar um `ok` real a “não verificado”.
        if (["ok", "ready", "installed", "not-required"].indexOf(requirement.status) >= 0)
            return "ready"
        if (requirement.blocksPlay === true || requirement.status === "missing")
            return "blocked"
        if (["outdated", "attention"].indexOf(requirement.status) >= 0)
            return "attention"
        return "unverified"
    }

    function openDossier(index) {
        selectedIndex = index
        view = "dossier"
    }

    function showLibrary() {
        view = "library"
    }

    function openLaunchReview() {
        if (!selectedGame || Object.keys(selectedGame).length === 0)
            return
        view = "launch"
    }

    function goBack() {
        if (view === "launch")
            view = "dossier"
        else if (view === "dossier")
            view = "library"
        else if (view === "library")
            view = "systems"
        else if (view === "system")
            view = "systems"
    }

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
    }

    // O fundo mantém profundidade quando houver mídia. Sem arte, a superfície
    // mineral permanece intencional; não há imagem de placeholder fingindo ser
    // conteúdo do usuário.
    MediaEffectLayer {
        id: contextualBackdrop
        anchors.fill: parent
        visible: !root.highContrast && root.contextualMediaSource(root.selectedGame) !== ""
        source: root.contextualMediaSource(root.selectedGame)
        fillMode: Image.PreserveAspectCrop
        effects: root.effectStacks.contextualBackdrop || []
        opacity: root.highContrast ? 0 : 0.34
    }
    Rectangle {
        anchors.fill: parent
        // A camada de legibilidade participa do tema. Uma cor mineral fixa
        // aqui deixava temas escuros com texto claro sobre fundo claro.
        color: root.highContrast ? "#000000" : root.backgroundColor
        opacity: root.highContrast ? 1 : 0.91
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: root.gutter
        anchors.rightMargin: root.gutter
        anchors.topMargin: root.compact ? 14 : 24
        anchors.bottomMargin: root.compact ? 14 : 24
        spacing: root.compact ? 10 : 18

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            EditorialButton {
                visible: root.view !== "systems"
                text: qsTr("Voltar")
                Layout.minimumWidth: root.minimumTarget
                Layout.minimumHeight: root.minimumTarget
                Accessible.name: qsTr("Voltar para a etapa anterior")
                onClicked: root.goBack()
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Label {
                    text: root.view === "systems" ? qsTr("Sistemas")
                        : root.view === "system" ? root.selectedSystem.name
                        : root.view === "library" ? qsTr("Biblioteca")
                        : root.view === "dossier" ? qsTr("Dossiê") : qsTr("Preparar para jogar")
                    color: root.textColor
                    font.pixelSize: root.compact ? 25 : 36
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                Label {
                    text: root.view === "systems"
                        ? qsTr("Escolha uma plataforma para explorar sua biblioteca")
                        : root.view === "system"
                            ? root.selectedSystem.statusLabel || qsTr("Estado ainda não publicado")
                        : root.view === "library"
                            ? qsTr("%1 · %2 jogo(s)").arg(root.systemFilter === "all"
                                ? qsTr("Todos os sistemas") : root.selectedSystemName()).arg(root.visibleGames.length)
                            : root.selectedGame.systemName || qsTr("Informação publicada")
                    color: root.mutedColor
                    font.pixelSize: root.compact ? 13 : 15
                    Layout.fillWidth: true
                }
            }
        }

        StackLayout {
            id: journey
            currentIndex: root.view === "systems" ? 0 : root.view === "system" ? 1
                : root.view === "library" ? 2 : root.view === "dossier" ? 3 : 4
            Layout.fillWidth: true
            Layout.fillHeight: true

            // Sistemas -----------------------------------------------------
            Flickable {
                clip: true
                contentWidth: width
                contentHeight: systemsGrid.implicitHeight + 16
                boundsBehavior: Flickable.StopAtBounds
                GridLayout {
                    id: systemsGrid
                    width: parent.width
                    columns: root.compact ? 1 : root.wide ? 4 : 3
                    columnSpacing: root.compact ? 10 : 16
                    rowSpacing: root.compact ? 10 : 16
                    Repeater {
                        id: systemRepeater
                        model: root.systems
                        delegate: Button {
                            required property int index
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredHeight: root.compact ? 126 : 182
                            Layout.columnSpan: root.compact ? 1 : 1
                            Accessible.name: qsTr("%1, %2 jogos, %3")
                                .arg(modelData.name).arg(modelData.gameCount).arg(modelData.statusLabel)
                            onClicked: root.openSystemDetails(index)
                            background: Rectangle {
                                color: parent.down ? root.raisedColor : root.surfaceColor
                                border.color: parent.activeFocus ? root.cyanColor : root.borderColor
                                border.width: parent.activeFocus ? 3 : 1
                                radius: 16
                            }
                            contentItem: ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: root.compact ? 14 : 20
                                spacing: 6
                                NavigationIcon {
                                    glyph: modelData.kind === "steam" ? "steam" : "emulators"
                                    iconColor: root.stateColor(modelData.state)
                                    Layout.preferredWidth: 30
                                    Layout.preferredHeight: 30
                                }
                                Label {
                                    text: modelData.name
                                    color: root.textColor
                                    font.pixelSize: root.compact ? 20 : 24
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Label {
                                    text: qsTr("%1 jogo(s)").arg(modelData.gameCount)
                                    color: root.mutedColor
                                    font.pixelSize: 14
                                }
                                Item { Layout.fillHeight: true }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label {
                                        text: modelData.statusLabel
                                        color: root.stateColor(modelData.state)
                                        font.pixelSize: 12
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        text: modelData.gameCount > 0 ? "›" : "—"
                                        color: root.cyanColor
                                        font.pixelSize: 24
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Sistema ------------------------------------------------------
            Flickable {
                clip: true
                contentWidth: width
                contentHeight: systemDetail.implicitHeight + 8
                boundsBehavior: Flickable.StopAtBounds
                ColumnLayout {
                    id: systemDetail
                    width: parent.width
                    spacing: root.compact ? 14 : 22
                    Rectangle {
                        color: root.surfaceColor
                        radius: 16
                        border.color: root.borderColor
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.compact ? 220 : 260
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: root.compact ? 18 : 26
                            spacing: 8
                            NavigationIcon {
                                glyph: root.selectedSystem.id === "steam" ? "steam" : "emulators"
                                iconColor: root.stateColor(root.selectedSystem.state)
                                Layout.preferredWidth: 36
                                Layout.preferredHeight: 36
                            }
                            Label {
                                text: root.selectedSystem.name || qsTr("Sistema")
                                color: root.textColor
                                font.pixelSize: root.compact ? 25 : 34
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                            }
                            Label {
                                text: qsTr("%1 jogo(s) · %2").arg(root.selectedSystem.gameCount || 0)
                                    .arg(root.selectedSystem.statusLabel || qsTr("Não verificado"))
                                color: root.stateColor(root.selectedSystem.state)
                                Layout.fillWidth: true
                            }
                            Item { Layout.fillHeight: true }
                            EditorialButton {
                                text: qsTr("Explorar biblioteca")
                                primaryAction: true
                                Layout.minimumHeight: root.minimumTarget
                                Layout.minimumWidth: 220
                                onClicked: root.openSystem(root.selectedSystem)
                            }
                        }
                    }
                    Label {
                        text: qsTr("Requisitos da plataforma")
                        color: root.textColor
                        font.pixelSize: 21
                        font.weight: Font.DemiBold
                    }
                    GridLayout {
                        columns: root.compact ? 1 : 3
                        Layout.fillWidth: true
                        Repeater {
                            model: [
                                {"kind": "bios", "title": qsTr("BIOS")},
                                {"kind": "keys", "title": qsTr("Keys")},
                                {"kind": "firmware", "title": qsTr("Firmware")}
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                color: root.surfaceColor
                                radius: 12
                                border.color: root.stateColor(root.requirementState(modelData.kind))
                                Layout.fillWidth: true
                                Layout.minimumHeight: 92
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 14
                                    Label { text: modelData.title; color: root.textColor; font.weight: Font.DemiBold }
                                    Label {
                                        text: root.requirementText(modelData.kind)
                                        color: root.stateColor(root.requirementState(modelData.kind))
                                        wrapMode: Text.WordWrap
                                        maximumLineCount: 2
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                        }
                    }
                    Label {
                        text: qsTr("Subsistemas e variantes")
                        color: root.textColor
                        font.pixelSize: 21
                        font.weight: Font.DemiBold
                    }
                    Rectangle {
                        color: root.surfaceColor
                        radius: 12
                        border.color: root.borderColor
                        Layout.fillWidth: true
                        Layout.minimumHeight: 112
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            Label {
                                text: root.selectedSystem.subsystems && root.selectedSystem.subsystems.length > 0
                                    ? qsTr("Variantes publicadas") : qsTr("Ainda não publicado")
                                color: root.selectedSystem.subsystems && root.selectedSystem.subsystems.length > 0
                                    ? root.greenColor : root.mutedColor
                                font.weight: Font.DemiBold
                            }
                            Label {
                                text: root.selectedSystem.subsystems && root.selectedSystem.subsystems.length > 0
                                    ? root.selectedSystem.subsystems.map(function(item) {
                                        return String(item.name || item.id || qsTr("Variante"))
                                    }).join(" · ")
                                    : qsTr("Esta área receberá famílias, regiões, formatos e cores quando a fonte gerenciada publicar o contrato. Nenhum título foi duplicado.")
                                color: root.mutedColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                    ScreenshotRail {
                        id: screenshotRail
                        sources: root.screenshotSources(root.selectedGame)
                        highContrast: root.highContrast
                        compact: root.compact
                        surfaceColor: root.surfaceColor
                        raisedColor: root.raisedColor
                        borderColor: root.borderColor
                        textColor: root.textColor
                        mutedColor: root.mutedColor
                        cyanColor: root.cyanColor
                        Layout.fillWidth: true
                    }
                }
            }

            // Biblioteca ---------------------------------------------------
            Item {
                ColumnLayout {
                    anchors.fill: parent
                    spacing: root.compact ? 10 : 18
                    RowLayout {
                        Layout.fillWidth: true
                        EditorialButton {
                            text: qsTr("Todos")
                            checkable: true
                            checked: root.systemFilter === "all"
                            Layout.minimumHeight: root.minimumTarget
                            onClicked: {
                                root.systemFilter = "all"
                                root.collectionFilter = ""
                                root.initialFilter = ""
                                root.resetMetadataFilters()
                                root.selectedIndex = 0
                            }
                        }
                        Repeater {
                            model: root.systems
                            delegate: EditorialButton {
                                required property var modelData
                                visible: !root.compact || modelData.id === root.systemFilter
                                text: modelData.name
                                checkable: true
                                checked: root.systemFilter === modelData.id
                                Layout.minimumHeight: root.minimumTarget
                                onClicked: {
                                    root.systemFilter = modelData.id
                                    root.collectionFilter = ""
                                    root.initialFilter = ""
                                    root.resetMetadataFilters()
                                    root.selectedIndex = 0
                                }
                            }
                        }
                        Item { Layout.fillWidth: true }
                        Row {
                            spacing: 6
                            EditorialButton {
                                text: qsTr("Carrossel")
                                checkable: true
                                checked: root.libraryView === "carousel"
                                Layout.minimumHeight: root.minimumTarget
                                onClicked: root.libraryView = "carousel"
                            }
                            EditorialButton {
                                text: qsTr("Grade")
                                checkable: true
                                checked: root.libraryView === "grid"
                                Layout.minimumHeight: root.minimumTarget
                                onClicked: root.libraryView = "grid"
                            }
                            EditorialButton {
                                text: qsTr("Lista")
                                checkable: true
                                checked: root.libraryView === "list"
                                Layout.minimumHeight: root.minimumTarget
                                onClicked: root.libraryView = "list"
                            }
                        }
                    }
                    Flickable {
                        visible: root.collectionItems.length > 0
                        clip: true
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.minimumTarget
                        contentWidth: collectionRow.width
                        contentHeight: height
                        boundsBehavior: Flickable.StopAtBounds
                        flickableDirection: Flickable.HorizontalFlick
                        Row {
                            id: collectionRow
                            spacing: 8
                            EditorialButton {
                                text: qsTr("Coleções: todas")
                                checkable: true
                                checked: root.collectionFilter === ""
                                height: root.minimumTarget
                                onClicked: {
                                    root.collectionFilter = ""
                                    root.resetMetadataFilters()
                                    root.selectedIndex = 0
                                }
                            }
                            Repeater {
                                model: root.collectionItems
                                delegate: EditorialButton {
                                    required property var modelData
                                    text: qsTr("%1 · %2").arg(modelData.name)
                                        .arg(modelData.members ? modelData.members.length : 0)
                                    checkable: true
                                    checked: root.collectionFilter === modelData.id
                                    height: root.minimumTarget
                                    Accessible.name: qsTr("Coleção %1, %2 jogo(s)")
                                        .arg(modelData.name).arg(modelData.members ? modelData.members.length : 0)
                                    onClicked: {
                                        root.collectionFilter = modelData.id
                                        root.resetMetadataFilters()
                                        root.selectedIndex = 0
                                    }
                                }
                            }
                        }
                    }
                    Flickable {
                        visible: !root.compact && root.width >= 1500
                        clip: true
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.minimumTarget
                        contentWidth: alphabetRow.width
                        contentHeight: height
                        boundsBehavior: Flickable.StopAtBounds
                        flickableDirection: Flickable.HorizontalFlick
                        Row {
                            id: alphabetRow
                            spacing: 6
                            Repeater {
                                model: root.alphabetFilters
                                delegate: EditorialButton {
                                    required property string modelData
                                    text: modelData
                                    checkable: true
                                    checked: modelData === "Todos"
                                        ? root.initialFilter === "" : root.initialFilter === modelData
                                    width: modelData === "Todos" ? 72 : 38
                                    height: root.minimumTarget
                                    Accessible.name: modelData === "Todos"
                                        ? qsTr("Mostrar todos os títulos")
                                        : qsTr("Filtrar títulos pela letra %1").arg(modelData)
                                    onClicked: {
                                        root.initialFilter = modelData === "Todos" ? "" : modelData
                                        root.selectedIndex = 0
                                    }
                                }
                            }
                        }
                    }
                    Flickable {
                        clip: true
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.minimumTarget
                        contentWidth: metadataRow.width
                        contentHeight: height
                        boundsBehavior: Flickable.StopAtBounds
                        flickableDirection: Flickable.HorizontalFlick
                        Row {
                            id: metadataRow
                            spacing: 8
                            Label {
                                text: qsTr("Metadados")
                                color: root.mutedColor
                                height: root.minimumTarget
                                verticalAlignment: Text.AlignVCenter
                            }
                            Repeater {
                                model: [
                                    {"field": "genre", "label": qsTr("Gênero")},
                                    {"field": "year", "label": qsTr("Ano")},
                                    {"field": "developer", "label": qsTr("Desenvolvedor")}
                                ]
                                delegate: EditorialButton {
                                    required property var modelData
                                    readonly property var values: root.metadataValues(modelData.field)
                                    readonly property string selectedValue: root.metadataFilter(modelData.field)
                                    text: values.length === 0
                                        ? qsTr("%1: não publicado").arg(modelData.label)
                                        : qsTr("%1: %2").arg(modelData.label)
                                            .arg(selectedValue === "" ? qsTr("todos") : selectedValue)
                                    enabled: values.length > 0
                                    width: root.compact ? 180 : 220
                                    height: root.minimumTarget
                                    Accessible.name: text
                                    Accessible.description: values.length === 0
                                        ? qsTr("A fonte ainda não publicou este metadado")
                                        : qsTr("Alterna o filtro pelos valores publicados")
                                    onClicked: root.cycleMetadataFilter(modelData.field)
                                }
                            }
                        }
                    }
                    Item {
                        visible: root.visibleGames.length === 0
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ColumnLayout {
                            anchors.centerIn: parent
                            width: Math.min(parent.width, 460)
                            spacing: 12
                            NavigationIcon {
                                glyph: "emulators"
                                iconColor: root.mutedColor
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: 42
                                Layout.preferredHeight: 42
                            }
                            Label {
                                text: qsTr("Nenhum jogo publicado nesta biblioteca")
                                color: root.textColor
                                font.pixelSize: 20
                                font.weight: Font.DemiBold
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Label {
                                text: qsTr("Quando a fonte gerenciada publicar jogos, eles aparecerão aqui sem criar cópias de mídia.")
                                color: root.mutedColor
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                    ListView {
                        id: carousel
                        visible: root.visibleGames.length > 0 && root.libraryView === "carousel"
                        clip: true
                        Layout.fillWidth: true
                        Layout.fillHeight: false
                        Layout.preferredHeight: root.coverHeight()
                        Layout.maximumHeight: root.coverHeight()
                        orientation: ListView.Horizontal
                        model: root.visibleGames
                        spacing: root.compact ? 12 : 22
                        cacheBuffer: root.coverWidth() * 2
                        reuseItems: true
                        boundsBehavior: Flickable.StopAtBounds
                        header: Item {
                            width: Math.max(0, (carousel.width - root.coverWidth()) / 2)
                            height: 1
                        }
                        footer: Item {
                            width: Math.max(0, (carousel.width - root.coverWidth()) / 2)
                            height: 1
                        }
                        delegate: Button {
                            required property int index
                            required property var modelData
                            width: index === root.selectedIndex ? root.coverWidth()
                                : root.neighborCoverWidth()
                            height: root.coverHeight()
                            topPadding: 0
                            bottomPadding: 0
                            leftPadding: 0
                            rightPadding: 0
                            Accessible.name: qsTr("%1, %2").arg(modelData.name).arg(modelData.systemName)
                            onClicked: {
                                if (root.selectedIndex === index)
                                    root.openDossier(index)
                                else {
                                    root.selectedIndex = index
                                    carousel.positionViewAtIndex(index, ListView.Contain)
                                }
                            }
                            scale: index === root.selectedIndex ? root.themeFocusedScale : 1
                            Behavior on width { NumberAnimation { duration: root.focusDuration } }
                            Behavior on scale { NumberAnimation { duration: root.focusDuration } }
                            background: Rectangle {
                                color: root.raisedColor
                                radius: 14
                                border.color: parent.activeFocus || index === root.selectedIndex
                                    ? root.cyanColor : root.borderColor
                                border.width: parent.activeFocus || index === root.selectedIndex ? 3 : 1
                                clip: true
                                MediaEffectLayer {
                                    anchors.fill: parent
                                    source: modelData.coverUrl
                                    visible: modelData.coverUrl !== ""
                                    fillMode: Image.PreserveAspectCrop
                                    effects: index === root.selectedIndex
                                        ? (root.effectStacks.focusedCover || [])
                                        : (root.effectStacks.peripheralCover || [])
                                    opacity: index === root.selectedIndex ? 1 : root.themePeripheralOpacity
                                }
                                NavigationIcon {
                                    anchors.centerIn: parent
                                    visible: modelData.coverUrl === ""
                                    glyph: modelData.source === "steam" ? "steam" : "emulators"
                                    iconColor: index === root.selectedIndex ? root.cyanColor : root.mutedColor
                                    width: 50
                                    height: 50
                                }
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    height: parent.height * 0.32
                                    color: "#081018"
                                    opacity: index === root.selectedIndex ? 0.78 : 0.88
                                }
                                Label {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    anchors.margins: 12
                                    text: modelData.name
                                    color: "#ffffff"
                                    font.pixelSize: index === root.selectedIndex ? 18 : 14
                                    font.weight: Font.DemiBold
                                    maximumLineCount: 2
                                    wrapMode: Text.WordWrap
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                    GridView {
                        id: gameGrid
                        visible: root.visibleGames.length > 0 && root.libraryView === "grid"
                        clip: true
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.compact ? 330 : 430
                        model: root.visibleGames
                        cellWidth: root.compact ? Math.max(142, width / 2) : Math.max(190, width / 5)
                        cellHeight: root.compact ? 218 : 274
                        cacheBuffer: cellHeight * 2
                        reuseItems: true
                        delegate: Button {
                            required property int index
                            required property var modelData
                            width: gameGrid.cellWidth - 12
                            height: gameGrid.cellHeight - 12
                            topPadding: 0
                            bottomPadding: 0
                            leftPadding: 0
                            rightPadding: 0
                            Accessible.name: qsTr("%1, %2").arg(modelData.name).arg(modelData.systemName)
                            onClicked: root.openDossier(index)
                            background: Rectangle {
                                color: root.raisedColor
                                radius: 12
                                border.color: parent.activeFocus ? root.cyanColor : root.borderColor
                                border.width: parent.activeFocus ? 3 : 1
                                clip: true
                                MediaEffectLayer {
                                    anchors.fill: parent
                                    source: modelData.coverUrl
                                    visible: modelData.coverUrl !== ""
                                    fillMode: Image.PreserveAspectCrop
                                    effects: root.effectStacks.peripheralCover || []
                                }
                                NavigationIcon {
                                    anchors.centerIn: parent
                                    visible: modelData.coverUrl === ""
                                    glyph: modelData.source === "steam" ? "steam" : "emulators"
                                    iconColor: root.mutedColor
                                    width: 40
                                    height: 40
                                }
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    height: parent.height * 0.30
                                    color: "#081018"
                                    opacity: 0.86
                                }
                                Label {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    anchors.margins: 10
                                    text: modelData.name
                                    color: "#ffffff"
                                    font.weight: Font.DemiBold
                                    maximumLineCount: 2
                                    wrapMode: Text.WordWrap
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                    ListView {
                        id: gameList
                        visible: root.visibleGames.length > 0 && root.libraryView === "list"
                        clip: true
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.compact ? 330 : 430
                        model: root.visibleGames
                        spacing: 8
                        cacheBuffer: 480
                        reuseItems: true
                        delegate: EditorialButton {
                            required property int index
                            required property var modelData
                            width: gameList.width
                            height: root.minimumTarget + 16
                            Accessible.name: qsTr("%1, %2").arg(modelData.name).arg(modelData.systemName)
                            onClicked: root.openDossier(index)
                            contentItem: RowLayout {
                                spacing: 12
                                NavigationIcon {
                                    glyph: modelData.source === "steam" ? "steam" : "emulators"
                                    iconColor: root.cyanColor
                                    Layout.preferredWidth: 28
                                    Layout.preferredHeight: 28
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    Label { text: modelData.name; color: root.textColor; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Label { text: modelData.systemName; color: root.mutedColor; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                                }
                                Label { text: modelData.launchable ? qsTr("Disponível") : qsTr("Sem launcher"); color: modelData.launchable ? root.greenColor : root.mutedColor; font.pixelSize: 12 }
                            }
                        }
                    }
                    RowLayout {
                        visible: root.visibleGames.length > 0 && root.libraryView === "carousel"
                        Layout.fillWidth: true
                        Label {
                            text: root.selectedGame.name || ""
                            color: root.textColor
                            font.pixelSize: root.compact ? 21 : 28
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Label {
                            text: root.selectedGame.systemName || ""
                            color: root.mutedColor
                            font.pixelSize: 14
                        }
                        EditorialButton {
                            text: qsTr("Ver dossiê")
                            Layout.minimumHeight: root.minimumTarget
                            onClicked: root.openDossier(root.selectedIndex)
                        }
                    }
                }
            }

            // Dossiê -------------------------------------------------------
            Flickable {
                clip: true
                contentWidth: width
                contentHeight: dossierContent.implicitHeight + 8
                boundsBehavior: Flickable.StopAtBounds
                ColumnLayout {
                    id: dossierContent
                    width: parent.width
                    spacing: root.compact ? 14 : 24
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        spacing: root.compact ? 14 : 28
                        Rectangle {
                            color: root.raisedColor
                            radius: 14
                            border.color: root.borderColor
                            Layout.preferredWidth: root.compact ? 152 : 280
                            Layout.preferredHeight: root.compact ? 220 : 400
                            clip: true
                            Image {
                                anchors.fill: parent
                                source: root.selectedGame.coverUrl || ""
                                visible: root.selectedGame.coverUrl !== ""
                                fillMode: Image.PreserveAspectCrop
                            }
                            NavigationIcon {
                                anchors.centerIn: parent
                                visible: root.selectedGame.coverUrl === ""
                                glyph: root.selectedGame.source === "steam" ? "steam" : "emulators"
                                iconColor: root.cyanColor
                                width: 54
                                height: 54
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            Label {
                                text: root.selectedGame.name || qsTr("Jogo")
                                color: root.textColor
                                font.pixelSize: root.compact ? 25 : 36
                                font.weight: Font.DemiBold
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Label {
                                text: root.selectedGame.systemName || ""
                                color: root.cyanDarkColor
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                            }
                            RowLayout {
                                Label { text: qsTr("Estado"); color: root.mutedColor }
                                Label {
                                    text: root.stateLabel(root.selectedGame.state)
                                    color: root.stateColor(root.selectedGame.state)
                                    font.weight: Font.DemiBold
                                }
                            }
                            Label {
                                text: root.selectedGame.source === "steam"
                                    ? qsTr("A Steam publicou a instalação deste jogo. O dossiê mostrará metadados adicionais quando forem publicados pela fonte gerenciada.")
                                    : qsTr("O jogo foi publicado pela biblioteca de emulação. Metadados e lançamento dependem dos contratos da plataforma.")
                                color: root.mutedColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Item { Layout.fillHeight: true }
                            EditorialButton {
                                id: primaryAction
                                primaryAction: true
                                text: root.selectedGame.launchable ? qsTr("Preparar para jogar")
                                    : qsTr("Lançamento indisponível")
                                enabled: root.selectedGame.launchable === true
                                Layout.minimumHeight: root.minimumTarget
                                Layout.fillWidth: true
                                Accessible.description: root.selectedGame.launchable
                                    ? qsTr("Revise o lançamento antes de iniciar")
                                    : (root.selectedGame.launchReason || qsTr("Ação ainda não publicada"))
                                onClicked: root.openLaunchReview()
                            }
                            Label {
                                visible: !root.selectedGame.launchable
                                text: root.selectedGame.launchReason || qsTr("Ação ainda não publicada")
                                color: root.amberColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.borderColor }
                    Label { text: qsTr("Informação publicada"); color: root.textColor; font.pixelSize: 20; font.weight: Font.DemiBold }
                    GridLayout {
                        columns: root.compact ? 1 : 3
                        Layout.fillWidth: true
                        Repeater {
                            model: [
                                {"label": qsTr("Plataforma"), "value": root.selectedGame.systemName || "—"},
                                {"label": qsTr("Origem"), "value": root.selectedGame.source === "steam" ? qsTr("Steam") : qsTr("Emulação")},
                                {"label": qsTr("Mídia"), "value": root.selectedGame.heroUrl
                                    ? qsTr("Hero ou fanart publicada") : root.selectedGame.coverUrl
                                        ? qsTr("Capa local publicada") : root.selectedGame.screenshotUrl
                                            ? qsTr("Screenshot publicada") : root.selectedGame.bannerUrl
                                                ? qsTr("Banner publicado") : qsTr("Nenhuma mídia publicada")},
                                {"label": qsTr("Gênero"), "value": root.selectedGame.genre || qsTr("Ainda não publicado")},
                                {"label": qsTr("Ano"), "value": root.selectedGame.year || qsTr("Ainda não publicado")},
                                {"label": qsTr("Desenvolvedor"), "value": root.selectedGame.developer || qsTr("Ainda não publicado")},
                                {"label": qsTr("Tempo jogado"), "value": root.selectedPlaytime.playedSeconds !== undefined
                                    ? root.playtimeLabel(root.selectedPlaytime.playedSeconds) : qsTr("Ainda não publicado")},
                                {"label": qsTr("Sessões"), "value": root.selectedPlaytime.sessionCount !== undefined
                                    ? String(root.selectedPlaytime.sessionCount) : qsTr("Ainda não publicado")},
                                {"label": qsTr("Última sessão"), "value": root.selectedPlaytime.lastPlayedAt || qsTr("Ainda não publicada")}
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.minimumHeight: 88
                                color: root.surfaceColor
                                radius: 10
                                border.color: root.borderColor
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    Label { text: modelData.label; color: root.mutedColor; font.pixelSize: 12 }
                                    Label { text: modelData.value; color: root.textColor; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                }
                            }
                        }
                    }
                }
            }

            // Revisão e lançamento ----------------------------------------
            Item {
                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(parent.width, 620)
                    spacing: 16
                    Label {
                        text: root.selectedGame.name || qsTr("Jogo")
                        color: root.textColor
                        font.pixelSize: root.compact ? 26 : 36
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Rectangle {
                        color: root.surfaceColor
                        border.color: root.borderColor
                        radius: 12
                        Layout.fillWidth: true
                        Layout.minimumHeight: 118
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            Label { text: qsTr("Revisão de lançamento"); color: root.textColor; font.weight: Font.DemiBold; font.pixelSize: 18 }
                            Label {
                                text: root.selectedGame.source === "steam"
                                    ? qsTr("O Steam abrirá o jogo identificado por sua biblioteca local. Nenhuma opção de lançamento será modificada.")
                                    : qsTr("Nenhum launcher seguro foi publicado para este jogo.")
                                color: root.mutedColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                    Rectangle {
                        color: root.surfaceColor
                        border.color: root.borderColor
                        radius: 12
                        Layout.fillWidth: true
                        Layout.minimumHeight: 118
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            Label { text: qsTr("Disponibilidade"); color: root.textColor; font.weight: Font.DemiBold; font.pixelSize: 18 }
                            Label {
                                text: root.selectedGame.source === "steam"
                                    ? qsTr("O launcher Steam foi publicado. FPS, resolução e controles abaixo refletem o perfil atual quando disponível.")
                                    : root.selectedGame.launchReason || qsTr("A plataforma ainda não publicou launcher seguro para este título.")
                                color: root.selectedGame.launchable ? root.mutedColor : root.amberColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                    GridLayout {
                        columns: root.compact ? 1 : 3
                        Layout.fillWidth: true
                        Repeater {
                            model: [
                                {"label": qsTr("Preset"), "value": root.steamGameplay.currentProfile
                                    ? String(root.steamGameplay.currentProfile.profile || qsTr("Não publicado")) : qsTr("Não publicado")},
                                {"label": qsTr("FPS"), "value": root.steamGameplay.currentProfile
                                    && root.steamGameplay.currentProfile.fps !== undefined
                                    ? String(root.steamGameplay.currentProfile.fps) : qsTr("Não publicado")},
                                {"label": qsTr("Resolução"), "value": root.steamGameplay.impact
                                    ? String(root.steamGameplay.impact.resolution || qsTr("Não publicada")) : qsTr("Não publicada")},
                                {"label": qsTr("Controles"), "value": root.steamGameplay.currentProfile
                                    ? String(root.steamGameplay.currentProfile.controllerLayout || qsTr("Não publicado")) : qsTr("Não publicado")},
                                {"label": qsTr("Saves e sync"), "value": root.sync && root.sync.state
                                    ? String(root.sync.state) : qsTr("Ainda não publicado")},
                                {"label": qsTr("Compatibilidade"), "value": qsTr("Ainda não publicada")}
                            ]
                            delegate: Rectangle {
                                required property var modelData
                                color: root.surfaceColor
                                border.color: root.borderColor
                                radius: 10
                                Layout.fillWidth: true
                                Layout.minimumHeight: 78
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    Label { text: modelData.label; color: root.mutedColor; font.pixelSize: 12 }
                                    Label { text: modelData.value; color: root.textColor; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                }
                            }
                        }
                    }
                    EditorialButton {
                        primaryAction: true
                        text: qsTr("Jogar agora")
                        enabled: root.selectedGame.launchable === true
                        Layout.fillWidth: true
                        Layout.minimumHeight: 56
                        font.pixelSize: 18
                        Accessible.description: qsTr("Abre o launcher publicado; não altera configurações")
                        onClicked: root.launchSteamRequested(String(root.selectedGame.id || ""))
                    }
                    EditorialButton {
                        text: qsTr("Configurar antes de jogar")
                        visible: root.selectedGame.source === "steam"
                        Layout.fillWidth: true
                        Layout.minimumHeight: root.minimumTarget
                        onClicked: root.openSteamConfigurationRequested(String(root.selectedGame.id || ""))
                    }
                }
            }
        }
    }

    function coverWidth() {
        const widthLimit = compact ? Math.min(246, width * 0.68) : Math.min(390, width * 0.30)
        const heightLimit = Math.max(180, height * (compact ? 0.48 : 0.56) / 1.42)
        return Math.floor(Math.min(widthLimit, heightLimit))
    }

    function neighborCoverWidth() {
        return Math.floor(coverWidth() * (compact ? 0.66 : 0.60))
    }

    function coverHeight() {
        return Math.round(coverWidth() * 1.42)
    }

    function selectedSystemName() {
        const system = systems.find(function(item) { return item.id === systemFilter })
        return system ? system.name : qsTr("Sistema")
    }

}
