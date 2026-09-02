// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
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
    property var localPath: function(url) {
        const value = String(url || "")
        return value.startsWith("file://")
            ? decodeURIComponent(value.replace(/^file:\/\/(?:localhost)?/, ""))
            : ""
    }

    property bool compactLayout: false
    // Tema ativo no host (dashboard.theme.activeId). Main.qml deve vincular.
    property string activeThemeId: ""
    property var applyPlan: null
    property var exportPlan: null

    signal applied()
    signal exported(string destination)

    color: panel.backgroundColor
    // Garante altura mínima útil quando embutido em ScrollView do shell.
    implicitHeight: 560

    // -- state --------------------------------------------------------------
    property string editorSessionId: ""
    property var editorManifest: ({})
    property var editorTokens: ({})
    property bool editorReadOnly: false
    property bool editorDirty: false
    property var editorThemeList: []
    property string esdeImportSource: ""
    property var esdeImportSchemes: []
    property int esdeImportSchemeIndex: -1
    property string esdeImportName: ""
    property bool esdeImportBusy: false
    property string esdeImportNotice: ""
    property bool esdeImportNoticeIsError: false
    // Objeto QML completo do tema (themeId/themeVersion/resolved/effects), na
    // forma exata de ``to_theme_qml_object``. O ThemeBridge espera esse formato
    // em ``_source.resolved`` — alimentá-lo com o dicionário de tokens puro
    // fazia o preview cair no fallback claro e publicar binding warnings.
    property var editorPreviewObject: null
    property string assetRecipeSelection: "original"
    readonly property bool assetRecipeDemoActive:
        editorManifest.id === "org.steamzero.asset-recipes-demo"
        && Object.keys(_previewBridge.assetRecipes).length > 0
    readonly property url assetRecipeSource: assetRecipeDemoActive
        ? Qt.resolvedUrl("../../themes/org.steamzero.asset-recipes-demo/assets/source.svg")
        : ""
    readonly property bool assetRecipePreviewReady:
        assetRecipeDemoActive && assetRecipePreview.sourceStatus === Image.Ready
    readonly property int assetRecipePreviewDecodeCount: assetRecipePreview.sourceDecodeCount
    readonly property var sceneLayoutPreview: _previewBridge.sceneLayoutPreview.layouts
        ? _previewBridge.sceneLayoutPreview.layouts.previewTitles : null
    readonly property bool sceneLayoutPreviewActive:
        assetRecipeDemoActive && sceneLayoutPreview !== null
    readonly property int sceneLayoutPreviewEntryCount:
        sceneLayoutPreviewActive ? sceneLayoutRepeater.entryCount : 0

    function sceneLayoutPreviewEntryAt(index) {
        return sceneLayoutPreviewActive ? sceneLayoutRepeater.entryAt(index) : null
    }

    readonly property var dynamicPalettePreview: _previewBridge.dynamicPalette.swatches
        ? _previewBridge.dynamicPalette.swatches : null
    readonly property bool dynamicPalettePreviewActive:
        assetRecipeDemoActive && dynamicPalettePreview !== null
    readonly property var glassPreview: _previewBridge.glassPreview.panels
        ? _previewBridge.glassPreview.panels.previewCard : null
    readonly property bool glassPreviewActive:
        assetRecipeDemoActive && glassPreview !== null
    readonly property var sceneMotionPreview: _previewBridge.sceneMotionPreview.states
        ? _previewBridge.sceneMotionPreview : null
    readonly property bool sceneMotionPreviewActive:
        assetRecipeDemoActive && sceneMotionPreview !== null
    readonly property int sceneMotionFocusDuration:
        sceneMotionPreviewActive && sceneMotionPreview.transitions
            && sceneMotionPreview.transitions.focusIn
            ? Number(sceneMotionPreview.transitions.focusIn.duration) : 0
    readonly property var sceneSurfacePreview: _previewBridge.sceneSurfacePreview.slots
        ? _previewBridge.sceneSurfacePreview : null
    readonly property bool sceneSurfacePreviewActive:
        assetRecipeDemoActive && sceneSurfacePreview !== null
    readonly property int sceneSurfaceSaveCount:
        sceneSurfacePreviewActive && sceneSurfaceRepeater.saveCount
            ? sceneSurfaceRepeater.saveCount : 0
    readonly property bool sceneSurfaceThumbnailFallback:
        sceneSurfacePreviewActive && sceneSurfaceRepeater.thumbnailFallback
    readonly property bool sceneSurfaceCriticalVisible:
        sceneSurfacePreviewActive && sceneSurfaceRepeater.criticalVisible
    readonly property var studioGraph: _previewBridge.studioGraph.nodes
        ? _previewBridge.studioGraph : null
    readonly property bool studioGraphActive:
        assetRecipeDemoActive && studioGraph !== null
    readonly property int studioGraphNodeCount:
        studioGraphActive ? studioCanvas.nodeCount : 0
    readonly property string studioGraphSelectedId:
        studioGraphActive ? studioCanvas.selectedId : ""
    readonly property string studioGraphSelectedKind:
        studioGraphActive ? studioCanvas.selectedKind : ""
    readonly property int studioGraphConstraintCount:
        studioGraphActive ? studioCanvas.selectedConstraintCount : 0
    readonly property string studioGraphConstraintCode:
        studioGraphActive ? studioCanvas.selectedConstraintCode : ""
    readonly property int studioGraphTimelineDuration:
        studioGraphActive ? studioCanvas.selectedTimelineDuration : 0
    readonly property int studioGraphDeclaredCost:
        studioGraphActive ? studioCanvas.declaredCost : 0
    readonly property bool studioGraphWithinBudget:
        studioGraphActive && studioCanvas.withinBudget
    readonly property bool studioGraphBudgetMeasured:
        studioGraphActive && studioCanvas.budgetMeasured
    readonly property string studioGraphBindingPath:
        studioGraphActive ? studioCanvas.selectedBindingPath : ""

    function studioGraphSelect(nodeId) {
        return studioGraphActive ? studioCanvas.select(nodeId) : false
    }

    readonly property var editorDiagnostics: _previewBridge.editorDiagnostics
    readonly property bool editorDiagnosticsActive:
        editorDiagnostics && editorDiagnostics.length > 0
    readonly property string editorDiagnosticCode:
        editorDiagnosticsActive ? String(editorDiagnostics[0].code) : ""

    property var _previewBridge: ThemeBridge {
        // O ThemeBridge espera em ``_source.resolved`` o objeto QML completo do
        // tema (themeId/themeVersion/resolved/effects), como o Main.qml entrega
        // o ``dashboard.resolved``. Alimentá-lo com o dicionário de tokens puro
        // fazia o preview cair no fallback claro e publicar binding warnings.
        _source: panel.editorPreviewObject ? {"resolved": panel.editorPreviewObject} : null
    }

    function isActiveTheme(themeId) {
        return themeId && panel.activeThemeId && themeId === panel.activeThemeId
    }

    function refreshThemeList() {
        panel.request("GET", "/theme/list", {}, function(resp) {
            panel.editorThemeList = resp.themes || []
        })
    }

    function resetEsdeImport() {
        panel.esdeImportSource = ""
        panel.esdeImportSchemes = []
        panel.esdeImportSchemeIndex = -1
        panel.esdeImportName = ""
        panel.esdeImportBusy = false
        panel.esdeImportNotice = ""
        panel.esdeImportNoticeIsError = false
    }

    function inspectEsdeImport() {
        const source = panel.esdeImportSource.trim()
        if (source === "")
            return
        panel.esdeImportBusy = true
        panel.esdeImportNotice = ""
        panel.esdeImportNoticeIsError = false
        panel.requestAction("theme.import.esde.inspect", {source: source},
            function(response) {
                panel.esdeImportBusy = false
                panel.esdeImportSchemes = response && response.schemes
                    ? response.schemes : []
                panel.esdeImportSchemeIndex = panel.esdeImportSchemes.length > 0 ? 0 : -1
                panel.esdeImportNotice = panel.esdeImportSchemes.length > 0
                    ? qsTr("Escolha um esquema e dê um nome ao tema editável.")
                    : qsTr("Nenhum esquema de cor importável foi encontrado.")
                panel.esdeImportNoticeIsError = panel.esdeImportSchemes.length === 0
            },
            function(message) {
                panel.esdeImportBusy = false
                panel.esdeImportSchemes = []
                panel.esdeImportSchemeIndex = -1
                panel.esdeImportNotice = String(message || qsTr("Não foi possível examinar o tema."))
                panel.esdeImportNoticeIsError = true
            })
    }

    function applyEsdeImport() {
        if (panel.esdeImportSchemeIndex < 0 || panel.esdeImportName.trim() === "")
            return
        const selected = panel.esdeImportSchemes[panel.esdeImportSchemeIndex]
        const scheme = selected && selected.scheme
            ? String(selected.scheme) : String(selected || "")
        if (scheme === "")
            return
        panel.esdeImportBusy = true
        panel.esdeImportNotice = ""
        panel.esdeImportNoticeIsError = false
        panel.requestAction("theme.import.esde.apply", {
            source: panel.esdeImportSource.trim(),
            scheme: scheme,
            name: panel.esdeImportName.trim()
        }, function(response) {
            panel.esdeImportBusy = false
            panel.refreshThemeList()
            panel.esdeImportNotice = qsTr("Tema importado como editável; ele ainda não foi aplicado.")
            panel.esdeImportNoticeIsError = false
            panel.esdeImportSchemes = []
            panel.esdeImportSchemeIndex = -1
            panel.esdeImportName = ""
        }, function(message) {
            panel.esdeImportBusy = false
            panel.esdeImportNotice = String(message || qsTr("Não foi possível importar o tema."))
            panel.esdeImportNoticeIsError = true
        })
    }

    function _mergeTokens(category, values) {
        var copy = JSON.parse(JSON.stringify(panel.editorTokens))
        if (!copy[category]) copy[category] = {}
        for (var k in values)
            copy[category][k] = values[k]
        return copy
    }

    function setMetadata(field, value) {
        if (panel.editorReadOnly || !panel.editorSessionId)
            return
        panel.requestAction("theme.editor.set-metadata", {
            "sessionId": panel.editorSessionId,
            "field": field,
            "value": value
        }, function(response) {
            if (response.manifest)
                panel.editorManifest = response.manifest
            panel.editorDirty = true
        })
    }

    function _openEditor(sessionId, manifest, preview) {
        panel.editorSessionId = sessionId
        panel.editorManifest = manifest
        panel.editorPreviewObject = preview
        panel.editorTokens = preview && preview.resolved ? preview.resolved : {}
        panel.assetRecipeSelection = "original"
        panel.editorDirty = false
        panel.editorReadOnly = manifest.readOnly === true
    }

    function _closeEditor() {
        if (panel.editorSessionId && panel.editorDirty) {
            panel.requestAction("theme.editor.cancel", {sessionId: panel.editorSessionId}, function() {})
        }
        panel.editorSessionId = ""
        panel.editorManifest = {}
        panel.editorPreviewObject = null
        panel.editorTokens = {}
        panel.editorDirty = false
        panel.editorReadOnly = false
    }

    function beginApply(themeId) {
        if (!themeId || panel.isActiveTheme(themeId))
            return
        panel.requestAction("theme.apply", {themeId: themeId}, function(r) {
            if (r.alreadyActive === true) {
                panel.applyPlan = null
                return
            }
            panel.applyPlan = {
                "planId": r.planId,
                "confirmToken": r.confirmToken,
                "preview": r.preview || "",
                "rollbackGuarantee": r.rollbackGuarantee || "",
                "themeId": themeId
            }
            applyDialog.open()
        })
    }

    function confirmApply() {
        if (!panel.applyPlan)
            return
        panel.requestAction("theme.apply.confirm", {
            "planId": panel.applyPlan.planId,
            "confirmToken": panel.applyPlan.confirmToken
        }, function(_r) {
            panel.applyPlan = null
            applyDialog.close()
            // activeThemeId vem do shell (binding); applied() dispara refresh.
            panel.refreshThemeList()
            panel.applied()
        })
    }

    function beginExport() {
        if (!panel.editorSessionId)
            return
        exportDialog.open()
    }

    function confirmExport() {
        if (!panel.exportPlan)
            return
        panel.requestAction("theme.editor.export.apply", {
            "planId": panel.exportPlan.planId,
            "confirmToken": panel.exportPlan.confirmToken
        }, function(_r) {
            const destination = panel.exportPlan.destination || ""
            panel.exportPlan = null
            exportPreviewDialog.close()
            panel.exported(destination)
        })
    }

    function duplicateAndEdit(sourceId, sourceName) {
        var base = sourceName || sourceId || qsTr("Tema")
        var name = qsTr("%1 (cópia)").arg(base)
        panel.requestAction("theme.editor.create",
            {name: name, extends: sourceId},
            function(r) {
                panel._openEditor(r.sessionId, r.manifest, r.preview)
            })
    }

    Component.onCompleted: refreshThemeList()

    // =====================================================================
    // THEME LIST (no active session)
    // =====================================================================
    ColumnLayout {
        id: listColumn
        visible: panel.editorSessionId === ""
        anchors.fill: parent
        spacing: 0

        Item { Layout.minimumHeight: 16 }

        Label {
            text: qsTr("Editor de Temas")
            color: panel.textColor
            font.pixelSize: 24
            font.weight: Font.Bold
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.fillWidth: true
            elide: Text.ElideRight
        }

        Item { Layout.minimumHeight: 8 }

        Label {
            text: qsTr("Crie ou edite temas visuais do SteamZero")
            color: panel.mutedColor
            font.pixelSize: 14
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }

        Item { Layout.minimumHeight: 20 }

        Button {
            text: qsTr("Criar Novo Tema")
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.minimumHeight: 48
            Layout.preferredWidth: 260
            Accessible.name: text
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

        RowLayout {
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.minimumHeight: 48
            spacing: 12

            Button {
                objectName: "themeImportEsdeButton"
                text: qsTr("Importar tema ES-DE")
                Layout.minimumHeight: 48
                Layout.preferredWidth: 220
                Accessible.name: text
                Accessible.description: qsTr("Examina um tema ES-DE e o converte em tema editável")
                onClicked: esdeImportDialog.open()
                background: Rectangle {
                    color: parent.hovered ? panel.cyanColor : panel.surfaceColor
                    radius: 8
                    border.color: parent.activeFocus ? panel.textColor : panel.cyanColor
                    border.width: parent.activeFocus ? 2 : 1
                }
                contentItem: Label {
                    text: parent.text
                    color: parent.hovered ? "#071019" : panel.cyanColor
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.weight: Font.Medium
                }
            }

            Label {
                text: qsTr("ES-DE → tema editável, sem aplicar automaticamente")
                color: panel.mutedColor
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
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
            Layout.fillWidth: true
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
                width: parent.availableWidth > 0 ? parent.availableWidth : panel.width - 40
                spacing: 8

                Repeater {
                    model: panel.editorThemeList
                    delegate: Rectangle {
                        required property var modelData
                        id: themeCard
                        readonly property bool isBuiltin: modelData.origin === "builtin"
                        readonly property bool isActive: panel.isActiveTheme(modelData.id)
                        // Reserva espaço para badge + Aplicar + Editar/Duplicar
                        // sem dependência circular com o RowLayout interno.
                        implicitHeight: panel.compactLayout ? 96 : 72
                        Layout.minimumHeight: 72
                        radius: 10
                        color: panel.surfaceColor
                        border.color: themeCard.isActive ? panel.cyanColor : panel.borderColor
                        border.width: themeCard.isActive ? 2 : 1
                        Layout.fillWidth: true

                        RowLayout {
                            id: themeCardRow
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 12

                            // Swatch opcional (accent do catálogo quando existir).
                            Rectangle {
                                visible: Boolean(modelData.accent || (modelData.colors && modelData.colors.accent))
                                implicitWidth: 12
                                implicitHeight: 40
                                radius: 4
                                color: modelData.accent
                                    || (modelData.colors && modelData.colors.accent)
                                    || panel.cyanColor
                                Layout.alignment: Qt.AlignVCenter
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 120
                                Layout.alignment: Qt.AlignVCenter
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
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Label {
                                    text: modelData.origin === "builtin"
                                        ? qsTr("Tema nativo") : qsTr("Tema do usuário")
                                    color: panel.cyanColor
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }

                            // Ações: badge Em uso | Aplicar | Editar/Ver | Duplicar.
                            // Sem fillWidth: o nome/autor elidem na coluna à esquerda.
                            RowLayout {
                                Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
                                Layout.fillWidth: false
                                spacing: 8

                                Label {
                                    visible: themeCard.isActive
                                    text: qsTr("Já está em uso")
                                    color: panel.greenColor
                                    font.pixelSize: 12
                                    font.weight: Font.Medium
                                    padding: 6
                                    background: Rectangle {
                                        color: panel.greenColor
                                        opacity: 0.15
                                        radius: 4
                                    }
                                    Accessible.name: qsTr("Tema em uso")
                                }

                                Button {
                                    visible: !themeCard.isActive
                                    text: qsTr("Aplicar")
                                    implicitWidth: 88
                                    implicitHeight: 36
                                    Accessible.name: qsTr("Aplicar tema %1").arg(modelData.name || modelData.id)
                                    onClicked: panel.beginApply(modelData.id)
                                    background: Rectangle {
                                        color: parent.hovered ? panel.cyanColor : panel.raisedColor
                                        radius: 6
                                        border.color: parent.activeFocus ? panel.textColor : panel.cyanColor
                                        border.width: parent.activeFocus ? 2 : 1
                                    }
                                    contentItem: Label {
                                        text: parent.text
                                        color: parent.hovered ? "#071019" : panel.cyanColor
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                        font.pixelSize: 13
                                        font.weight: Font.Medium
                                    }
                                }

                                Button {
                                    text: themeCard.isBuiltin
                                        ? qsTr("Ver (somente leitura)")
                                        : qsTr("Editar")
                                    implicitWidth: themeCard.isBuiltin
                                        ? (panel.compactLayout ? 120 : 150)
                                        : 88
                                    implicitHeight: 36
                                    Accessible.name: text + " " + (modelData.name || modelData.id)
                                    onClicked: {
                                        // Via envelope de ações: URL/método vêm do
                                        // contrato do backend, não são montados aqui.
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
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                    }
                                }

                                Button {
                                    visible: themeCard.isBuiltin
                                    text: qsTr("Duplicar e editar")
                                    implicitWidth: panel.compactLayout ? 120 : 140
                                    implicitHeight: 36
                                    Accessible.name: qsTr("Duplicar e editar %1").arg(modelData.name || modelData.id)
                                    onClicked: panel.duplicateAndEdit(modelData.id, modelData.name)
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
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }
                    }
                }

                Item { Layout.minimumHeight: 24 }
            }
        }
    }

    Dialog {
        id: esdeImportDialog
        objectName: "themeImportEsdeDialog"
        modal: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(panel.width - 24, 640)
        height: Math.min(panel.height - 24, 560)
        x: (panel.width - width) / 2
        y: (panel.height - height) / 2
        title: qsTr("Importar tema ES-DE")
        standardButtons: Dialog.NoButton
        onOpened: importSourceField.forceActiveFocus()
        onClosed: panel.resetEsdeImport()

        contentItem: ColumnLayout {
            spacing: 10

            Label {
                text: qsTr("Examine primeiro. A importação cria um tema editável e não altera o tema ativo.")
                color: panel.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            RowLayout {
                Layout.fillWidth: true
                TextField {
                    id: importSourceField
                    objectName: "themeImportEsdeSource"
                    text: panel.esdeImportSource
                    placeholderText: qsTr("Pasta do tema ES-DE")
                    Accessible.name: qsTr("Pasta do tema ES-DE")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onTextChanged: panel.esdeImportSource = text
                }
                Button {
                    objectName: "themeImportEsdeBrowse"
                    text: qsTr("Escolher")
                    Accessible.name: text
                    Layout.minimumHeight: 48
                    onClicked: esdeImportFolderDialog.open()
                }
                Button {
                    objectName: "themeImportEsdeInspect"
                    text: qsTr("Examinar")
                    enabled: !panel.esdeImportBusy && panel.esdeImportSource.trim() !== ""
                    Accessible.name: text
                    Accessible.description: enabled
                        ? qsTr("Lê os esquemas sem gravar arquivos")
                        : qsTr("Informe a pasta do tema antes de examinar")
                    Layout.minimumHeight: 48
                    onClicked: panel.inspectEsdeImport()
                }
            }

            Label {
                text: panel.esdeImportNotice
                visible: panel.esdeImportNotice !== ""
                color: panel.esdeImportNoticeIsError ? panel.redColor : panel.greenColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            Label {
                text: qsTr("Esquemas encontrados")
                visible: panel.esdeImportSchemes.length > 0
                color: panel.textColor
                font.weight: Font.Medium
            }

            ScrollView {
                visible: panel.esdeImportSchemes.length > 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.availableWidth
                    spacing: 4
                    Repeater {
                        model: panel.esdeImportSchemes
                        delegate: RowLayout {
                            required property int index
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.minimumHeight: 48
                            RadioButton {
                                text: modelData && modelData.scheme
                                    ? String(modelData.scheme) : qsTr("Esquema")
                                checked: panel.esdeImportSchemeIndex === index
                                Accessible.name: qsTr("Esquema %1").arg(text)
                                onClicked: panel.esdeImportSchemeIndex = index
                            }
                            Label {
                                text: modelData && modelData.isMonochrome
                                    ? qsTr("monocromático; derivação limitada")
                                    : qsTr("paleta convertível")
                                color: modelData && modelData.isMonochrome
                                    ? panel.amberColor : panel.mutedColor
                                font.pixelSize: 11
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }

            TextField {
                id: importNameField
                objectName: "themeImportEsdeName"
                text: panel.esdeImportName
                visible: panel.esdeImportSchemes.length > 0
                placeholderText: qsTr("Nome do tema importado")
                Accessible.name: qsTr("Nome do tema importado")
                Layout.fillWidth: true
                Layout.minimumHeight: 48
                onTextChanged: panel.esdeImportName = text
            }

            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Accessible.name: text
                    Layout.minimumHeight: 48
                    onClicked: esdeImportDialog.close()
                }
                Item { Layout.fillWidth: true }
                Button {
                    objectName: "themeImportEsdeApply"
                    text: panel.esdeImportBusy ? qsTr("Importando…") : qsTr("Importar como editável")
                    enabled: !panel.esdeImportBusy
                        && panel.esdeImportSchemeIndex >= 0
                        && panel.esdeImportName.trim() !== ""
                    Accessible.name: text
                    Accessible.description: enabled
                        ? qsTr("Cria o tema e deixa o tema ativo inalterado")
                        : qsTr("Examine um esquema e informe um nome")
                    Layout.minimumHeight: 48
                    onClicked: panel.applyEsdeImport()
                }
            }
        }
    }

    FolderDialog {
        id: esdeImportFolderDialog
        title: qsTr("Escolher pasta do tema ES-DE")
        onAccepted: panel.esdeImportSource = panel.localPath(selectedFolder)
    }

    // =====================================================================
    // EDITOR VIEW (active session)
    // =====================================================================
    ColumnLayout {
        id: editorColumn
        visible: panel.editorSessionId !== ""
        anchors.fill: parent
        spacing: 0

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
                    objectName: "themeEditorExport"
                    text: qsTr("Exportar")
                    enabled: panel.editorSessionId !== ""
                    implicitHeight: 36
                    implicitWidth: 90
                    Accessible.name: text
                    onClicked: panel.beginExport()
                    background: Rectangle {
                        color: parent.enabled ? panel.surfaceColor : panel.borderColor
                        radius: 6
                        border.color: parent.activeFocus ? panel.cyanColor : panel.borderColor
                        border.width: 1
                    }
                    contentItem: Label {
                        text: parent.text
                        color: parent.enabled ? panel.cyanColor : panel.mutedColor
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

                    Label {
                        text: qsTr("Metadados do tema")
                        color: panel.textColor
                        font.pixelSize: 16
                        font.weight: Font.Medium
                        Layout.leftMargin: 12
                        Layout.rightMargin: 12
                        Layout.fillWidth: true
                    }

                    Label {
                        text: qsTr("Nome, autoria e licença são preservados no pacote exportado.")
                        color: panel.mutedColor
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.leftMargin: 12
                        Layout.rightMargin: 12
                        Layout.fillWidth: true
                    }

                    Repeater {
                        model: ["name", "author", "license", "description"]
                        delegate: ColumnLayout {
                            required property string modelData
                            Layout.leftMargin: 12
                            Layout.rightMargin: 12
                            Layout.fillWidth: true
                            spacing: 3

                            Label {
                                text: {
                                    if (modelData === "name") return qsTr("Nome")
                                    if (modelData === "author") return qsTr("Autoria")
                                    if (modelData === "license") return qsTr("Licença SPDX")
                                    return qsTr("Descrição")
                                }
                                color: panel.mutedColor
                                font.pixelSize: 11
                            }

                            TextField {
                                objectName: "themeMetadata_" + modelData
                                text: panel.editorManifest[modelData] || ""
                                enabled: !panel.editorReadOnly
                                Layout.fillWidth: true
                                Layout.minimumHeight: 36
                                color: panel.textColor
                                placeholderText: modelData === "license"
                                    ? qsTr("Ex.: MIT ou GPL-3.0-or-later") : ""
                                Accessible.name: parent.children[0].text
                                background: Rectangle {
                                    color: panel.surfaceColor
                                    radius: 6
                                    border.color: parent.activeFocus
                                        ? panel.cyanColor : panel.borderColor
                                    border.width: parent.activeFocus ? 2 : 1
                                }
                                onEditingFinished: panel.setMetadata(modelData, text.trim())
                            }
                        }
                    }

                    Item { Layout.minimumHeight: 16 }

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
                                    if (r.preview && r.preview.resolved) {
                                        panel.editorPreviewObject = r.preview
                                        panel.editorTokens = r.preview.resolved
                                    }
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
                                    if (r.preview && r.preview.resolved) {
                                        panel.editorPreviewObject = r.preview
                                        panel.editorTokens = r.preview.resolved
                                    }
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
                                    if (r.preview && r.preview.resolved) {
                                        panel.editorPreviewObject = r.preview
                                        panel.editorTokens = r.preview.resolved
                                    }
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
                                    if (r.preview && r.preview.resolved) {
                                        panel.editorPreviewObject = r.preview
                                        panel.editorTokens = r.preview.resolved
                                    }
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

                    Rectangle {
                        visible: panel.editorDiagnosticsActive
                        objectName: "editorDiagnosticsBanner"
                        color: panel.amberColor
                        radius: panel._previewBridge.radiusMedium
                        Layout.fillWidth: true
                        implicitHeight: visible ? 40 : 0
                        Label {
                            anchors.fill: parent
                            anchors.margins: 10
                            text: panel.editorDiagnosticCode
                            color: "#1a1a1a"
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                    }

                    Rectangle {
                        visible: panel.assetRecipeDemoActive
                        color: panel._previewBridge.surface
                        radius: panel._previewBridge.radiusMedium
                        Layout.fillWidth: true
                        implicitHeight: visible ? 260 : 0
                        border.color: panel._previewBridge.border
                        border.width: 1

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    text: qsTr("Asset único · receita em runtime")
                                    color: panel._previewBridge.text
                                    font.pixelSize: 14
                                    font.weight: Font.Medium
                                    Layout.fillWidth: true
                                }
                                ComboBox {
                                    id: assetRecipePicker
                                    model: [
                                        "original", "colored", "grayscale", "black", "white",
                                        "outlineThin", "outlineThick", "outlineInner",
                                        "outlinedGlow", "outlinedShadow"
                                    ]
                                    implicitWidth: 150
                                    Accessible.name: qsTr("Variante do asset")
                                    onActivated: panel.assetRecipeSelection = model[index]
                                }
                            }

                            AssetRecipePreview {
                                id: assetRecipePreview
                                objectName: "assetRecipePreview"
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.margins: 12
                                source: panel.assetRecipeSource
                                recipe: panel._previewBridge.assetRecipes[
                                    panel.assetRecipeSelection] || ({
                                        "source": "logo", "nodes": [], "fallback": "source"
                                    })
                            }

                            Label {
                                text: assetRecipePreview.fallbackActive
                                    ? qsTr("Efeito indisponível; fonte segura exibida")
                                    : qsTr("Fonte decodificada uma vez · cache por hash e tier")
                                color: assetRecipePreview.fallbackActive
                                    ? panel.amberColor : panel._previewBridge.textMuted
                                font.pixelSize: 11
                                Layout.alignment: Qt.AlignHCenter
                            }
                        }
                    }

                    Rectangle {
                        visible: panel.sceneLayoutPreviewActive
                        color: panel._previewBridge.surface
                        radius: panel._previewBridge.radiusMedium
                        Layout.fillWidth: true
                        implicitHeight: visible ? 112 : 0
                        border.color: panel._previewBridge.border
                        border.width: 1

                        Label {
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.margins: 12
                            text: qsTr("Grid responsivo · bindings materializados")
                            color: panel._previewBridge.textMuted
                            font.pixelSize: 11
                        }

                        SceneRepeater {
                            id: sceneLayoutRepeater
                            objectName: "sceneLayoutRepeater"
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.top: parent.top
                            anchors.margins: 12
                            anchors.topMargin: 32
                            layout: panel.sceneLayoutPreview
                        }
                    }

                    Rectangle {
                        visible: panel.dynamicPalettePreviewActive || panel.glassPreviewActive
                        color: panel._previewBridge.surface
                        radius: panel._previewBridge.radiusMedium
                        Layout.fillWidth: true
                        implicitHeight: visible ? 96 : 0
                        border.color: panel._previewBridge.border
                        border.width: 1

                        Label {
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.margins: 12
                            text: qsTr("Paleta extraída · vidro com fallback")
                            color: panel._previewBridge.textMuted
                            font.pixelSize: 11
                        }

                        Row {
                            id: paletteSwatches
                            objectName: "paletteSwatches"
                            anchors.left: parent.left
                            anchors.bottom: parent.bottom
                            anchors.margins: 12
                            spacing: 6
                            Repeater {
                                model: panel.dynamicPalettePreviewActive
                                    ? ["accent", "vibrant", "muted", "background", "contrastText"]
                                    : []
                                delegate: Rectangle {
                                    required property string modelData
                                    width: 18
                                    height: 18
                                    radius: 4
                                    color: panel.dynamicPalettePreview[modelData]
                                    border.color: panel._previewBridge.border
                                    border.width: 1
                                }
                            }
                        }

                        GlassPanel {
                            id: glassPreviewPanel
                            objectName: "glassPreviewPanel"
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.margins: 12
                            width: 120
                            height: 48
                            visible: panel.glassPreviewActive
                            panel: panel.glassPreview
                        }
                    }

                    Rectangle {
                        visible: panel.sceneMotionPreviewActive
                        color: panel._previewBridge.surface
                        radius: panel._previewBridge.radiusMedium
                        Layout.fillWidth: true
                        implicitHeight: visible ? 112 : 0
                        border.color: panel._previewBridge.border
                        border.width: 1

                        Label {
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.margins: 12
                            text: qsTr("Estados nativos · timeline materializada")
                            color: panel._previewBridge.textMuted
                            font.pixelSize: 11
                        }

                        SceneMotionPreview {
                            id: sceneMotionNormal
                            objectName: "sceneMotionNormal"
                            anchors.left: parent.left
                            anchors.bottom: parent.bottom
                            anchors.margins: 12
                            width: 88
                            height: 56
                            motion: panel.sceneMotionPreview
                            stateName: "normal"
                        }

                        SceneMotionPreview {
                            id: sceneMotionFocused
                            objectName: "sceneMotionFocused"
                            anchors.left: sceneMotionNormal.right
                            anchors.leftMargin: 16
                            anchors.bottom: parent.bottom
                            anchors.margins: 12
                            width: 88
                            height: 56
                            motion: panel.sceneMotionPreview
                            stateName: "focused"
                        }
                    }

                    Rectangle {
                        visible: panel.sceneSurfacePreviewActive
                        color: panel._previewBridge.surface
                        radius: panel._previewBridge.radiusMedium
                        Layout.fillWidth: true
                        implicitHeight: visible ? 112 : 0
                        border.color: panel._previewBridge.border
                        border.width: 1

                        Label {
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.margins: 12
                            text: qsTr("Saves e OSD por contrato")
                            color: panel._previewBridge.textMuted
                            font.pixelSize: 11
                        }

                        SceneSurfacePreview {
                            id: sceneSurfaceRepeater
                            objectName: "sceneSurfaceRepeater"
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.top: parent.top
                            anchors.margins: 12
                            anchors.topMargin: 32
                            surfaces: panel.sceneSurfacePreview
                        }
                    }

                    Rectangle {
                        visible: panel.studioGraphActive
                        color: panel._previewBridge.surface
                        radius: panel._previewBridge.radiusMedium
                        Layout.fillWidth: true
                        implicitHeight: visible ? 180 : 0
                        border.color: panel._previewBridge.border
                        border.width: 1

                        Label {
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.margins: 12
                            text: qsTr("Theme Studio · árvore e inspector")
                            color: panel._previewBridge.textMuted
                            font.pixelSize: 11
                        }

                        ThemeStudioCanvas {
                            id: studioCanvas
                            objectName: "studioCanvas"
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.top: parent.top
                            anchors.margins: 12
                            anchors.topMargin: 32
                            graph: panel.studioGraph
                            // A mesma cena resolvida que a interface desenha:
                            // o canvas do Studio não recebe uma versão própria.
                            scene: panel._previewBridge.sceneLayoutPreview
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
    // THEME EXPORT
    // =====================================================================
    FileDialog {
        id: exportDialog
        title: qsTr("Salvar tema exportado")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("Pacote de tema (*.zip)")]
        defaultSuffix: "zip"
        onAccepted: {
            const destination = panel.localPath(selectedFile)
            if (!destination)
                return
            panel.requestAction("theme.editor.export", {
                "sessionId": panel.editorSessionId,
                "destination": destination
            }, function(response) {
                panel.exportPlan = Object.assign({}, response.plan || {}, {
                    "destination": destination,
                    "filename": response.filename || destination.split("/").pop(),
                    "size": response.size || 0
                })
                exportPreviewDialog.open()
            })
        }
    }

    Dialog {
        id: exportPreviewDialog
        title: qsTr("Revisar exportação do tema")
        modal: true
        width: Math.min(panel.width > 0 ? panel.width - 32 : 720, 620)
        x: panel.width > 0 ? (panel.width - width) / 2 : 0
        y: panel.height > 0 ? Math.max((panel.height - height) / 2, 24) : 24
        standardButtons: Dialog.NoButton

        background: Rectangle {
            color: panel.raisedColor
            radius: 12
            border.color: panel.cyanDarkColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: qsTr("O pacote será gravado somente após a confirmação.")
                color: panel.textColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            TextArea {
                readOnly: true
                text: panel.exportPlan
                    ? qsTr("Arquivo: %1\nTamanho: %2 bytes\nGarantia: %3")
                        .arg(panel.exportPlan.filename || "tema.zip")
                        .arg(panel.exportPlan.size || 0)
                        .arg(panel.exportPlan.rollbackGuarantee || "G-FULL")
                    : ""
                color: panel.textColor
                wrapMode: TextEdit.WrapAnywhere
                Layout.fillWidth: true
                Layout.minimumHeight: 92
                background: Rectangle {
                    color: panel.backgroundColor
                    radius: 8
                    border.color: panel.borderColor
                }
                Accessible.name: qsTr("Prévia da exportação do tema")
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 44
                    onClicked: {
                        panel.exportPlan = null
                        exportPreviewDialog.close()
                    }
                }
                Button {
                    text: qsTr("Confirmar exportação")
                    enabled: panel.exportPlan !== null
                    Layout.fillWidth: true
                    Layout.minimumHeight: 44
                    onClicked: panel.confirmExport()
                }
            }
        }
    }

    // =====================================================================
    // APPLY THEME CONFIRMATION
    // =====================================================================
    Dialog {
        id: applyDialog
        title: qsTr("Aplicar tema")
        modal: true
        width: Math.min(panel.width > 0 ? panel.width - 32 : 720, 560)
        x: panel.width > 0 ? (panel.width - width) / 2 : 0
        y: panel.height > 0 ? Math.max((panel.height - height) / 2, 24) : 24
        standardButtons: Dialog.NoButton

        background: Rectangle {
            color: panel.raisedColor
            radius: 12
            border.color: panel.cyanDarkColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 14

            Label {
                text: qsTr("Revise o plano antes de ativar o tema. A preferência é gravada com rollback.")
                color: panel.textColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.minimumHeight: 120
                Layout.preferredHeight: 160
                clip: true
                TextArea {
                    text: panel.applyPlan ? String(panel.applyPlan.preview || "") : ""
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.WrapAnywhere
                    color: panel.textColor
                    background: Rectangle {
                        color: panel.backgroundColor
                        radius: 8
                        border.color: panel.borderColor
                    }
                    Accessible.name: qsTr("Prévia da aplicação do tema")
                }
            }

            Label {
                visible: panel.applyPlan && panel.applyPlan.rollbackGuarantee
                text: qsTr("Rollback: %1").arg(
                    panel.applyPlan ? (panel.applyPlan.rollbackGuarantee || "") : "")
                color: panel.mutedColor
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 44
                    Accessible.name: text
                    onClicked: {
                        panel.applyPlan = null
                        applyDialog.close()
                    }
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
                    text: qsTr("Confirmar aplicação")
                    enabled: panel.applyPlan !== null
                        && panel.applyPlan.planId
                        && panel.applyPlan.confirmToken
                    Layout.fillWidth: true
                    Layout.minimumHeight: 44
                    Accessible.name: text
                    onClicked: panel.confirmApply()
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
