// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel

    property color backgroundColor: "#071019"
    property color surfaceColor: "#0d1924"
    property color raisedColor: "#122131"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color cyanColor: "#13bdf2"
    property color cyanDarkColor: "#0a5f85"
    property color greenColor: "#59d35d"
    property color amberColor: "#ff9f1a"
    property color redColor: "#ff6b73"

    property var requestAction: function(_ida, _payload, _cb, _ecb) {}
    property var request: function(_method, _path, _payload, _cb, _ecb) {}

    property bool compactLayout: false

    color: panel.backgroundColor

    // -- state --------------------------------------------------------------
    property string editorSessionId: ""
    property var editorManifest: ({})
    property var editorTokens: ({})
    property bool editorReadOnly: false
    property bool editorDirty: false
    property var editorThemeList: []

    property var _previewBridge: ThemeBridge {
        _source: editorTokens && Object.keys(editorTokens).length > 0
            ? {
                "schemaVersion": 1,
                "themeId": editorManifest.id || "editing",
                "themeVersion": editorManifest.version || "1.0.0",
                "highContrast": false,
                "reducedMotion": false,
                "resolved": editorTokens
            } : null
    }

    function refreshThemeList() {
        panel.request("GET", "/theme/list", {}, function(resp) {
            panel.editorThemeList = resp.themes || []
        })
    }

    function _mergeTokens(category, values) {
        var copy = JSON.parse(JSON.stringify(panel.editorTokens))
        if (!copy[category]) copy[category] = {}
        for (var k in values)
            copy[category][k] = values[k]
        return copy
    }

    function _openEditor(sessionId, manifest, preview) {
        panel.editorSessionId = sessionId
        panel.editorManifest = manifest
        panel.editorTokens = preview && preview.resolved ? preview.resolved : {}
        panel.editorDirty = false
        panel.editorReadOnly = manifest.readOnly === true
    }

    function _closeEditor() {
        if (panel.editorSessionId && panel.editorDirty) {
            panel.requestAction("theme.editor.cancel", {sessionId: panel.editorSessionId}, function() {})
        }
        panel.editorSessionId = ""
        panel.editorManifest = {}
        panel.editorTokens = {}
        panel.editorDirty = false
        panel.editorReadOnly = false
    }

    Component.onCompleted: refreshThemeList()

    // =====================================================================
    // THEME LIST (no active session)
    // =====================================================================
    ColumnLayout {
        visible: panel.editorSessionId === ""
        spacing: 0
        Layout.fillWidth: true
        Layout.fillHeight: true

        Item { Layout.minimumHeight: 16 }

        Label {
            text: qsTr("Editor de Temas")
            color: panel.textColor
            font.pixelSize: 24
            font.weight: Font.Bold
            Layout.leftMargin: 20
            Layout.rightMargin: 20
        }

        Item { Layout.minimumHeight: 8 }

        Label {
            text: qsTr("Crie ou edite temas visuais do SteamZero")
            color: panel.mutedColor
            font.pixelSize: 14
            Layout.leftMargin: 20
            Layout.rightMargin: 20
        }

        Item { Layout.minimumHeight: 20 }

        Button {
            text: qsTr("Criar Novo Tema")
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.minimumHeight: 48
            Layout.preferredWidth: 260
            icon.name: "document-save"
            icon.color: "#071019"
            onClicked: createDialog.open()
            background: Rectangle {
                color: panel.cyanColor
                radius: 8
                border.color: parent.activeFocus ? panel.textColor : "transparent"
                border.width: parent.activeFocus ? 2 : 0
            }
            contentItem: Label {
                text: parent.text
                color: "#071019"
                font.weight: Font.Medium
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }

        Item { Layout.minimumHeight: 20 }

        Label {
            text: qsTr("Temas instalados")
            color: panel.textColor
            font.pixelSize: 16
            font.weight: Font.Medium
            Layout.leftMargin: 20
            Layout.rightMargin: 20
        }

        Item { Layout.minimumHeight: 8 }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.availableWidth
                spacing: 8

                Repeater {
                    model: panel.editorThemeList
                    delegate: Rectangle {
                        required property var modelData
                        id: themeCard
                        implicitHeight: 72
                        radius: 10
                        color: panel.surfaceColor
                        border.color: panel.borderColor
                        border.width: 1
                        Layout.fillWidth: true

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 12

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Label {
                                    text: modelData.name || modelData.id
                                    color: panel.textColor
                                    font.pixelSize: 15
                                    font.weight: Font.Medium
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Label {
                                    text: (modelData.author ? modelData.author + " · " : "")
                                        + qsTr("v%1").arg(modelData.version || "0")
                                    color: panel.mutedColor
                                    font.pixelSize: 12
                                }
                                Label {
                                    text: modelData.origin === "builtin"
                                        ? qsTr("Tema nativo") : qsTr("Tema do usuário")
                                    color: panel.cyanColor
                                    font.pixelSize: 11
                                }
                            }

                            Button {
                                text: qsTr("Editar")
                                implicitWidth: 80
                                implicitHeight: 36
                                onClicked: {
                                    // Via envelope de ações, como todo o resto do
                                    // painel: a URL e o método vêm do contrato do
                                    // backend, não são montados aqui.
                                    panel.requestAction("theme.editor.load",
                                        {themeId: modelData.id}, function(r) {
                                            panel._openEditor(r.sessionId, r.manifest, r.preview)
                                        })
                                }
                                background: Rectangle {
                                    color: parent.hovered ? panel.cyanDarkColor : panel.raisedColor
                                    radius: 6
                                    border.color: parent.activeFocus ? panel.cyanColor : panel.borderColor
                                    border.width: parent.activeFocus ? 2 : 1
                                }
                                contentItem: Label {
                                    text: parent.text
                                    color: panel.cyanColor
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    font.pixelSize: 13
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // =====================================================================
    // EDITOR VIEW (active session)
    // =====================================================================
    ColumnLayout {
        visible: panel.editorSessionId !== ""
        spacing: 0
        Layout.fillWidth: true
        Layout.fillHeight: true

        // -- top bar -------------------------------------------------------
        Rectangle {
            color: panel.raisedColor
            Layout.fillWidth: true
            Layout.minimumHeight: 56
            border.color: panel.borderColor
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 20
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label {
                        text: panel.editorManifest.name || qsTr("Sem nome")
                        color: panel.textColor
                        font.pixelSize: 16
                        font.weight: Font.Medium
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Label {
                        text: panel.editorManifest.id || ""
                        color: panel.mutedColor
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }

                Label {
                    visible: panel.editorReadOnly
                    text: qsTr("Apenas leitura")
                    color: panel.amberColor
                    font.pixelSize: 12
                    font.weight: Font.Medium
                    padding: 6
                    background: Rectangle {
                        color: panel.amberColor
                        opacity: 0.15
                        radius: 4
                    }
                }

                Label {
                    visible: panel.editorDirty
                    text: qsTr("Não salvo")
                    color: panel.amberColor
                    font.pixelSize: 11
                    font.italic: true
                }

                Button {
                    text: qsTr("Salvar")
                    enabled: !panel.editorReadOnly && panel.editorDirty
                    implicitHeight: 36
                    implicitWidth: 90
                    onClicked: {
                        panel.requestAction("theme.editor.save",
                            {sessionId: panel.editorSessionId, overwrite: true},
                            function(r) {
                                panel.editorDirty = false
                                panel.refreshThemeList()
                            })
                    }
                    background: Rectangle {
                        color: parent.enabled ? panel.cyanColor : panel.borderColor
                        radius: 6
                        border.color: parent.activeFocus ? panel.textColor : "transparent"
                        border.width: parent.activeFocus ? 2 : 0
                    }
                    contentItem: Label {
                        text: parent.text
                        color: parent.enabled ? "#071019" : panel.mutedColor
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.weight: parent.enabled ? Font.Medium : Font.Normal
                    }
                }

                Button {
                    text: qsTr("Exportar")
                    implicitHeight: 36
                    implicitWidth: 90
                    onClicked: {
                        panel.requestAction("theme.editor.export",
                            {sessionId: panel.editorSessionId},
                            function(r) {
                                var link = document.createElement("a")
                                link.download = r.filename || "theme.zip"
                                link.href = "data:application/zip;base64," + r.zip
                                document.body.appendChild(link)
                                link.click()
                                document.body.removeChild(link)
                            })
                    }
                    background: Rectangle {
                        color: parent.hovered ? panel.raisedColor : panel.surfaceColor
                        radius: 6
                        border.color: parent.activeFocus ? panel.cyanColor : panel.borderColor
                        border.width: parent.activeFocus ? 2 : 1
                    }
                    contentItem: Label {
                        text: parent.text
                        color: panel.textColor
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                Button {
                    text: qsTr("Fechar")
                    implicitHeight: 36
                    implicitWidth: 80
                    onClicked: panel._closeEditor()
                    background: Rectangle {
                        color: parent.hovered ? panel.redColor : panel.surfaceColor
                        opacity: parent.hovered ? 0.15 : 1.0
                        radius: 6
                        border.color: parent.activeFocus ? panel.redColor : panel.borderColor
                        border.width: parent.activeFocus ? 2 : 1
                    }
                    contentItem: Label {
                        text: parent.text
                        color: panel.redColor
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        // -- editor body ---------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // LEFT: token editor
            ScrollView {
                Layout.fillHeight: true
                Layout.preferredWidth: panel.compactLayout ? parent.width * 0.5 : 380
                Layout.minimumWidth: 280
                clip: true
                contentWidth: availableWidth

                ColumnLayout {
                    width: parent.availableWidth
                    spacing: 0

                    Item { Layout.minimumHeight: 8 }

                    CategorySection {
                        title: qsTr("Cores")
                        categoryKey: "color"
                        tokenCount: 18
                        tokens: panel.editorTokens.color || {}
                        readOnly: panel.editorReadOnly
                        textColor: panel.textColor
                        mutedColor: panel.mutedColor
                        surfaceColor: panel.surfaceColor
                        borderColor: panel.borderColor
                        cyanColor: panel.cyanColor
                        onTokenChanged: {
                            panel.editorDirty = true
                            panel.requestAction("theme.editor.set-tokens",
                                {sessionId: panel.editorSessionId, category: "color", values: newValues},
                                function(r) {
                                    if (r.preview && r.preview.resolved)
                                        panel.editorTokens = r.preview.resolved
                                })
                        }
                    }

                    CategorySection {
                        title: qsTr("Geometria")
                        categoryKey: "geometry"
                        tokenCount: 9
                        tokens: panel.editorTokens.geometry || {}
                        readOnly: panel.editorReadOnly
                        textColor: panel.textColor
                        mutedColor: panel.mutedColor
                        surfaceColor: panel.surfaceColor
                        borderColor: panel.borderColor
                        cyanColor: panel.cyanColor
                        onTokenChanged: {
                            panel.editorDirty = true
                            panel.requestAction("theme.editor.set-tokens",
                                {sessionId: panel.editorSessionId, category: "geometry", values: newValues},
                                function(r) {
                                    if (r.preview && r.preview.resolved)
                                        panel.editorTokens = r.preview.resolved
                                })
                        }
                    }

                    CategorySection {
                        title: qsTr("Tipografia")
                        categoryKey: "typography"
                        tokenCount: 5
                        tokens: panel.editorTokens.typography || {}
                        readOnly: panel.editorReadOnly
                        textColor: panel.textColor
                        mutedColor: panel.mutedColor
                        surfaceColor: panel.surfaceColor
                        borderColor: panel.borderColor
                        cyanColor: panel.cyanColor
                        onTokenChanged: {
                            panel.editorDirty = true
                            panel.requestAction("theme.editor.set-tokens",
                                {sessionId: panel.editorSessionId, category: "typography", values: newValues},
                                function(r) {
                                    if (r.preview && r.preview.resolved)
                                        panel.editorTokens = r.preview.resolved
                                })
                        }
                    }

                    CategorySection {
                        title: qsTr("Movimento")
                        categoryKey: "motion"
                        tokenCount: 5
                        tokens: panel.editorTokens.motion || {}
                        readOnly: panel.editorReadOnly
                        textColor: panel.textColor
                        mutedColor: panel.mutedColor
                        surfaceColor: panel.surfaceColor
                        borderColor: panel.borderColor
                        cyanColor: panel.cyanColor
                        onTokenChanged: {
                            panel.editorDirty = true
                            panel.requestAction("theme.editor.set-tokens",
                                {sessionId: panel.editorSessionId, category: "motion", values: newValues},
                                function(r) {
                                    if (r.preview && r.preview.resolved)
                                        panel.editorTokens = r.preview.resolved
                                })
                        }
                    }

                    Item { Layout.minimumHeight: 40 }
                }
            }

            // RIGHT: live preview
            Rectangle {
                Layout.fillHeight: true
                Layout.fillWidth: true
                color: panel._previewBridge.background
                visible: !panel.compactLayout
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 24
                    spacing: 12

                    Label {
                        text: qsTr("Preview ao vivo")
                        color: panel._previewBridge.textMuted
                        font.pixelSize: 12
                    }

                    Rectangle {
                        color: panel._previewBridge.surface
                        radius: panel._previewBridge.radiusMedium
                        Layout.fillWidth: true
                        implicitHeight: 180
                        border.color: panel._previewBridge.border
                        border.width: 1

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 8

                            Label {
                                text: qsTr("Aparência do tema")
                                color: panel._previewBridge.text
                                font.pixelSize: 18
                                font.weight: Font.Bold
                            }

                            Label {
                                text: qsTr("Esta é uma amostra de como o tema ficará na interface.")
                                color: panel._previewBridge.textMuted
                                font.pixelSize: 13
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }

                            RowLayout {
                                spacing: 8
                                Rectangle {
                                    color: panel._previewBridge.accent
                                    radius: 6
                                    implicitWidth: 100
                                    implicitHeight: 32
                                    Label {
                                        anchors.centerIn: parent
                                        text: qsTr("Botão")
                                        color: "#071019"
                                        font.pixelSize: 13
                                        font.weight: Font.Medium
                                    }
                                }
                                Rectangle {
                                    color: panel._previewBridge.success
                                    radius: 6
                                    implicitWidth: 80
                                    implicitHeight: 32
                                    Label {
                                        anchors.centerIn: parent
                                        text: qsTr("Sucesso")
                                        color: "#071019"
                                        font.pixelSize: 13
                                    }
                                }
                                Rectangle {
                                    color: panel._previewBridge.warning
                                    radius: 6
                                    implicitWidth: 90
                                    implicitHeight: 32
                                    Label {
                                        anchors.centerIn: parent
                                        text: qsTr("Aviso")
                                        color: "#071019"
                                        font.pixelSize: 13
                                    }
                                }
                                Rectangle {
                                    color: panel._previewBridge.danger
                                    radius: 6
                                    implicitWidth: 80
                                    implicitHeight: 32
                                    Label {
                                        anchors.centerIn: parent
                                        text: qsTr("Erro")
                                        color: "#071019"
                                        font.pixelSize: 13
                                    }
                                }
                            }

                            Rectangle {
                                color: panel._previewBridge.surfaceRaised
                                radius: panel._previewBridge.radiusSmall
                                Layout.fillWidth: true
                                implicitHeight: 40
                                border.color: panel._previewBridge.border
                                border.width: 1
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 8
                                    Rectangle {
                                        implicitWidth: 12
                                        implicitHeight: 12
                                        radius: 6
                                        color: panel._previewBridge.accent
                                    }
                                    Label {
                                        text: qsTr("Superfície elevada com borda")
                                        color: panel._previewBridge.text
                                        font.pixelSize: 12
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        text: qsTr("muted")
                                        color: panel._previewBridge.textMuted
                                        font.pixelSize: 11
                                    }
                                }
                            }
                        }
                    }

                    // token summary
                    Rectangle {
                        color: panel._previewBridge.surface
                        radius: panel._previewBridge.radiusMedium
                        Layout.fillWidth: true
                        implicitHeight: 80
                        border.color: panel._previewBridge.border
                        border.width: 1

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 4
                            Label {
                                text: qsTr("Tokens ativos")
                                color: panel._previewBridge.textMuted
                                font.pixelSize: 11
                            }
                            Label {
                                text: {
                                    var c = panel.editorTokens.color || {}
                                    var g = panel.editorTokens.geometry || {}
                                    var parts = []
                                    if (Object.keys(c).length)
                                        parts.push(Object.keys(c).length + " cores")
                                    if (Object.keys(g).length)
                                        parts.push(Object.keys(g).length + " geometria")
                                    return parts.length ? parts.join(" · ") : qsTr("Padrão")
                                }
                                color: panel._previewBridge.text
                                font.pixelSize: 13
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }
                }
            }
        }
    }

    // =====================================================================
    // CREATE DIALOG
    // =====================================================================
    Dialog {
        id: createDialog
        title: qsTr("Criar Novo Tema")
        modal: true
        width: Math.min(panel.width > 0 ? panel.width : 800, 420)
        x: panel.width > 0 ? (panel.width - width) / 2 : 0
        y: panel.height > 0 ? Math.max((panel.height - height) / 2, 40) : 40
        standardButtons: Dialog.NoButton

        background: Rectangle {
            color: panel.raisedColor
            radius: 12
            border.color: panel.cyanDarkColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 16
            Layout.margins: 20

            Label {
                text: qsTr("Nome do novo tema")
                color: panel.mutedColor
                font.pixelSize: 12
            }
            TextField {
                id: createNameField
                placeholderText: qsTr("Meu Tema Personalizado")
                Layout.fillWidth: true
                Layout.minimumHeight: 44
                color: panel.textColor
                background: Rectangle {
                    color: panel.backgroundColor
                    radius: 6
                    border.color: panel.borderColor
                    border.width: 1
                }
                onAccepted: createConfirmButton.clicked()
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Item { Layout.fillWidth: true }
                Button {
                    text: qsTr("Cancelar")
                    Layout.minimumHeight: 44
                    Layout.preferredWidth: 120
                    onClicked: createDialog.close()
                    background: Rectangle {
                        color: panel.surfaceColor
                        radius: 8
                        border.color: panel.borderColor
                        border.width: 1
                    }
                    contentItem: Label {
                        text: parent.text
                        color: panel.textColor
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                Button {
                    id: createConfirmButton
                    text: qsTr("Criar")
                    enabled: createNameField.text.trim().length > 0
                    Layout.minimumHeight: 44
                    Layout.preferredWidth: 120
                    onClicked: {
                        panel.requestAction("theme.editor.create",
                            {name: createNameField.text.trim()},
                            function(r) {
                                panel._openEditor(r.sessionId, r.manifest, r.preview)
                                createDialog.close()
                                createNameField.text = ""
                            })
                    }
                    background: Rectangle {
                        color: parent.enabled ? panel.cyanColor : panel.borderColor
                        radius: 8
                        border.color: parent.activeFocus ? panel.textColor : "transparent"
                        border.width: parent.activeFocus ? 2 : 0
                    }
                    contentItem: Label {
                        text: parent.text
                        color: parent.enabled ? "#071019" : panel.mutedColor
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.weight: parent.enabled ? Font.Medium : Font.Normal
                    }
                }
            }
        }
    }

    // =====================================================================
    // INLINE CATEGORY SECTION COMPONENT
    // =====================================================================
    component CategorySection: Rectangle {
        id: catSection
        property string title: ""
        property string categoryKey: ""
        property int tokenCount: 0
        property var tokens: ({})
        property bool readOnly: false
        property color textColor: "#f2f6fb"
        property color mutedColor: "#9eabba"
        property color surfaceColor: "#0d1924"
        property color borderColor: "#2a3a49"
        property color cyanColor: "#13bdf2"

        signal tokenChanged(var newValues)

        property bool _expanded: false
        color: "transparent"
        implicitHeight: _header.height + (_expanded ? _body.implicitHeight + 8 : 0)
        Layout.fillWidth: true
        Layout.leftMargin: 12
        Layout.rightMargin: 12

        // header
        Rectangle {
            id: _header
            height: 40
            radius: 8
            color: catSection._expanded ? catSection.surfaceColor : "transparent"
            border.color: catSection._expanded ? catSection.borderColor : "transparent"
            border.width: 1
            anchors.left: parent.left
            anchors.right: parent.right

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 8
                spacing: 8
                Label {
                    text: catSection.title
                    color: catSection.textColor
                    font.pixelSize: 14
                    font.weight: Font.Medium
                    Layout.fillWidth: true
                }
                Label {
                    text: "%1 tokens".arg(catSection.tokenCount)
                    color: catSection.mutedColor
                    font.pixelSize: 11
                }
                Label {
                    text: catSection._expanded ? "▾" : "▸"
                    color: catSection.mutedColor
                    font.pixelSize: 14
                }
            }

            TapHandler {
                onTapped: catSection._expanded = !catSection._expanded
            }
        }

        // body
        ColumnLayout {
            id: _body
            anchors.top: _header.bottom
            anchors.topMargin: 4
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: 6
            visible: catSection._expanded

            // category-specific editors
            Loader {
                Layout.fillWidth: true
                sourceComponent: {
                    if (catSection.categoryKey === "color") return ColorEditorComp
                    if (catSection.categoryKey === "geometry") return GeometryEditorComp
                    if (catSection.categoryKey === "typography") return TypoEditorComp
                    if (catSection.categoryKey === "motion") return MotionEditorComp
                    return null
                }
            }
        }
    }

    // -- color editor -------------------------------------------------------
    component ColorEditorComp: ColumnLayout {
        spacing: 6
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: Object.keys(catSection.tokens).length > 0
                    ? Object.keys(catSection.tokens) : _COLOR_KEYS
                delegate: Rectangle {
                    required property string modelData
                    implicitWidth: 86
                    implicitHeight: 52
                    radius: 6
                    color: catSection.tokens[modelData]
                        ? Qt.darker(catSection.tokens[modelData], 1.0) : catSection.surfaceColor
                    border.color: catSection.readOnly ? catSection.borderColor : catSection.cyanColor
                    border.width: 1
                    Accessible.name: modelData
                    Accessible.role: Accessible.Button

                    Rectangle {
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        height: 22
                        radius: 6
                        color: catSection.tokens[modelData] || "#000000"
                    }
                    Label {
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 3
                        anchors.left: parent.left
                        anchors.leftMargin: 5
                        text: {
                            var label = modelData
                            return label.charAt(0).toUpperCase() + label.slice(1)
                        }
                        color: catSection.textColor
                        font.pixelSize: 9
                        elide: Text.ElideRight
                        width: parent.width - 10
                    }

                    TapHandler {
                        enabled: !catSection.readOnly
                        onTapped: {
                            var d = colorPickerComponent.createObject(panel, {
                                initialColor: catSection.tokens[modelData] || "#000000",
                                backgroundColor: panel.backgroundColor,
                                surfaceColor: panel.surfaceColor,
                                raisedColor: panel.raisedColor,
                                borderColor: panel.borderColor,
                                textColor: panel.textColor,
                                mutedColor: panel.mutedColor,
                                cyanColor: panel.cyanColor,
                                cyanDarkColor: panel.cyanDarkColor
                            })
                            d.colorPicked.connect(function(color) {
                                var vals = {}
                                vals[modelData] = color
                                catSection.tokenChanged(vals)
                            })
                            d.open()
                        }
                    }
                }
            }
        }
    }

    // -- geometry editor ----------------------------------------------------
    component GeometryEditorComp: ColumnLayout {
        spacing: 4
        Repeater {
            model: Object.keys(catSection.tokens).length > 0
                ? Object.keys(catSection.tokens) : _GEOMETRY_KEYS
            delegate: RowLayout {
                required property string modelData
                spacing: 8
                Layout.fillWidth: true
                Layout.minimumHeight: 36

                Label {
                    text: {
                        var label = modelData
                        return label.charAt(0).toUpperCase() + label.slice(1)
                    }
                    color: catSection.textColor
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                SpinBox {
                    from: 0
                    to: 120
                    value: catSection.tokens[modelData] !== undefined
                        ? Number(catSection.tokens[modelData]) : 0
                    editable: true
                    enabled: !catSection.readOnly
                    implicitWidth: 90
                    implicitHeight: 32
                    onValueModified: {
                        var vals = {}
                        vals[modelData] = value
                        catSection.tokenChanged(vals)
                    }
                    background: Rectangle {
                        color: catSection.surfaceColor
                        radius: 6
                        border.color: catSection.readOnly ? catSection.borderColor : parent.activeFocus ? catSection.cyanColor : catSection.borderColor
                        border.width: parent.activeFocus ? 2 : 1
                    }
                    contentItem: TextInput {
                        text: parent.text
                        color: catSection.textColor
                        font: parent.font
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                Label {
                    text: "px"
                    color: catSection.mutedColor
                    font.pixelSize: 11
                }
            }
        }
    }

    // -- typography editor --------------------------------------------------
    component TypoEditorComp: ColumnLayout {
        spacing: 6
        Repeater {
            model: Object.keys(catSection.tokens).length > 0
                ? Object.keys(catSection.tokens) : _TYPO_KEYS
            delegate: RowLayout {
                required property string modelData
                spacing: 8
                Layout.fillWidth: true
                Layout.minimumHeight: 36

                Label {
                    text: {
                        var label = modelData
                        return label.charAt(0).toUpperCase() + label.slice(1)
                    }
                    color: catSection.textColor
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                Loader {
                    Layout.preferredWidth: 120
                    Layout.minimumHeight: 32
                    sourceComponent: {
                        if (modelData === "scale")
                            return TypoScaleEditorComp
                        if (modelData === "family")
                            return TypoFamilyEditorComp
                        return TypoDefaultEditorComp
                    }
                }
            }
        }
    }

    component TypoScaleEditorComp: SpinBox {
        from: 50
        to: 200
        value: catSection.tokens.scale !== undefined
            ? Math.round(Number(catSection.tokens.scale) * 100) : 100
        editable: true
        enabled: !catSection.readOnly
        implicitHeight: 32
        onValueModified: {
            var vals = {}
            vals.scale = value / 100.0
            catSection.tokenChanged(vals)
        }
        background: Rectangle {
            color: catSection.surfaceColor
            radius: 6
            border.color: parent.activeFocus ? catSection.cyanColor : catSection.borderColor
            border.width: parent.activeFocus ? 2 : 1
        }
        contentItem: TextInput {
            text: parent.text
            color: catSection.textColor
            font: parent.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        Label {
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: "%"
            color: catSection.mutedColor
            font.pixelSize: 11
        }
    }

    component TypoFamilyEditorComp: TextField {
        text: catSection.tokens.family || ""
        placeholderText: qsTr("Fonte (ex: Noto Sans)")
        enabled: !catSection.readOnly
        implicitHeight: 32
        color: catSection.textColor
        background: Rectangle {
            color: catSection.surfaceColor
            radius: 6
            border.color: catSection.borderColor
            border.width: 1
        }
        onEditingFinished: {
            var vals = {}
            vals.family = text
            catSection.tokenChanged(vals)
        }
    }

    component TypoDefaultEditorComp: TextField {
        text: catSection.tokens[modelData] !== undefined
            ? String(catSection.tokens[modelData]) : ""
        enabled: !catSection.readOnly
        implicitHeight: 32
        color: catSection.textColor
        background: Rectangle {
            color: catSection.surfaceColor
            radius: 6
            border.color: catSection.borderColor
            border.width: 1
        }
        onEditingFinished: {
            var vals = {}
            vals[modelData] = text
            catSection.tokenChanged(vals)
        }
    }

    // -- motion editor ------------------------------------------------------
    component MotionEditorComp: ColumnLayout {
        spacing: 4
        Repeater {
            model: Object.keys(catSection.tokens).length > 0
                ? Object.keys(catSection.tokens) : _MOTION_KEYS
            delegate: RowLayout {
                required property string modelData
                spacing: 8
                Layout.fillWidth: true
                Layout.minimumHeight: 36

                Label {
                    text: {
                        var label = modelData
                        return label.charAt(0).toUpperCase() + label.slice(1)
                    }
                    color: catSection.textColor
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                SpinBox {
                    from: 0
                    to: 2000
                    value: catSection.tokens[modelData] !== undefined
                        ? Number(catSection.tokens[modelData]) : 0
                    editable: true
                    enabled: !catSection.readOnly
                    implicitWidth: 90
                    implicitHeight: 32
                    onValueModified: {
                        var vals = {}
                        vals[modelData] = value
                        catSection.tokenChanged(vals)
                    }
                    background: Rectangle {
                        color: catSection.surfaceColor
                        radius: 6
                        border.color: parent.activeFocus ? catSection.cyanColor : catSection.borderColor
                        border.width: parent.activeFocus ? 2 : 1
                    }
                    contentItem: TextInput {
                        text: parent.text
                        color: catSection.textColor
                        font: parent.font
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                Label {
                    text: modelData.indexOf("Duration") >= 0 || modelData.indexOf("duration") >= 0 ? "ms" : ""
                    color: catSection.mutedColor
                    font.pixelSize: 11
                }
            }
        }
    }

    // =====================================================================
    // STATIC DEFAULTS
    // =====================================================================
    readonly property var _COLOR_KEYS: [
        "background", "sidebar", "surface", "surfaceRaised", "surfaceSelected",
        "border", "text", "textMuted", "textDisabled",
        "accent", "accentStrong",
        "success", "successSurface", "warning", "warningSurface",
        "danger", "dangerSurface", "focus"
    ]
    readonly property var _GEOMETRY_KEYS: [
        "radiusSmall", "radiusMedium", "radiusLarge",
        "borderWidth", "focusWidth", "minimumTarget",
        "spacingSmall", "spacingMedium", "spacingLarge"
    ]
    readonly property var _TYPO_KEYS: ["scale", "weightBody", "weightStrong", "weightHeading", "family"]
    readonly property var _MOTION_KEYS: ["durationFast", "durationNormal", "durationLong", "hoverIntensity", "focusIntensity"]

    // =====================================================================
    // COLOR PICKER COMPONENT (dynamic creation)
    // =====================================================================
    Component {
        id: colorPickerComponent
        ColorPickerDialog {
            onClosed: destroy()
        }
    }
}
