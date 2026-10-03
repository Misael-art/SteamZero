// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "sizes.js" as Sizes

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
    property real visualScale: 1.0
    readonly property int minimumInteractiveTarget: 48
    readonly property int titlePixelSize: editorTitle.font.pixelSize

    property var requestAction: function(_ida, _payload, _cb, _ecb) {}
    property var request: function(_method, _path, _payload, _cb, _ecb) {}
    property var localPath: function(url) {
        const value = String(url || "")
        return value.startsWith("file://")
            ? decodeURIComponent(value.replace(/^file:\/\/(?:localhost)?/, ""))
            : ""
    }

    property bool compactLayout: false
    property bool journeyMode: false
    // Tema ativo no host (dashboard.theme.activeId). Main.qml deve vincular.
    property string activeThemeId: ""
    // Nome de apresentacao do tema em vigor. Vazio significa "o tema
    // preferido nao esta disponivel no catalogo" — a UI diz isso, em vez de
    // cair para o ID tecnico.
    property string activeThemeName: ""

    // O ID tecnico (org.steamzero.aura) nunca e o titulo apresentado. Quando o
    // pacote nao declara nome, a UI diz que o nome falta em vez de exibir o ID
    // como se fosse o nome do tema; o ID continua visivel no detalhe tecnico.
    function themeLabel(entry) {
        if (!entry)
            return qsTr("Tema sem nome")
        return String(entry.displayName || entry.name || qsTr("Tema sem nome"))
    }
    property var applyPlan: null
    property var exportPlan: null

    property alias retrofeImportDialogControl: retrofeImportDialog
    property alias retrofeImportApplyControl: retrofeImportApplyButton
    property alias esdeImportDialogControl: esdeImportDialog
    property alias esdeImportApplyControl: esdeImportApplyButton
    property alias applyConfirmControl: applyConfirmButton
    property alias journeyPanelControl: journeyPanel
    property var effectColorDialogControl: null

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
    // Histórico de autoria devolvido pelo backend (V3). Nunca é calculado aqui:
    // undo/redo e `dirty` vêm do documento, para o preview não divergir dele.
    property var editorHistory: ({canUndo: false, canRedo: false})
    // Slot de mídia em edição no inspector de enquadramento.
    property string mediaRecipeRole: "focusedCover"
    property string effectStackName: "focusedCover"
    property string motionTimelineName: "entrada"
    property string motionNewTimelineKind: "sequence"
    property string motionStateName: "focused"
    readonly property var motionStateOptions: editorMotionSchema.states || ["normal", "focused",
        "selected", "pressed", "disabled", "loading", "missing", "error", "offline",
        "playing", "idle", "menuOpen"]
    property string bindingLayoutName: ""
    property string bindingPropName: ""
    // Declaração do tema (cadeia extends + rascunho), sem negociação por tier ou
    // acessibilidade: base dos inspetores. O preview pode omitir efeitos; isto não.
    property var editorDeclared: ({effects: ({}), sceneMotion: null})
    property var editorEffectSchema: ({})
    property var editorMotionSchema: ({})
    property string authoringNotice: ""
    // Sobe quando uma edição é recusada: os campos reconstroem e voltam ao valor
    // declarado, em vez de continuar exibindo o texto rejeitado.
    property int authoringRevision: 0
    property var editorThemeList: []
    property int effectColorIndex: -1
    property string effectColorParameter: ""
    property string esdeImportSource: ""
    property var esdeImportSchemes: []
    property int esdeImportSchemeIndex: -1
    property string esdeImportName: ""
    property bool esdeImportBusy: false
    property string esdeImportNotice: ""
    property bool esdeImportNoticeIsError: false
    /// Geração do pedido de importação ES-DE: cada disparo e cada fechamento
    /// incrementam, e a resposta só escreve na superfície se carregar a geração
    /// corrente. O pedido em voo não é cancelado — o que se descarta é o efeito
    /// dele. Molde: `retrofeImportGeneration`, abaixo.
    property int esdeImportGeneration: 0
    property string packageImportSource: ""
    property var packageImportPreview: null
    property bool packageImportOverwrite: false
    property bool packageImportBusy: false
    property string packageImportNotice: ""
    property bool packageImportNoticeIsError: false
    property string retrofeImportSource: ""
    property var retrofeImportLayouts: []
    property int retrofeImportLayoutIndex: -1
    property string retrofeImportSceneId: ""
    property string retrofeImportName: ""
    property string retrofeImportAuthor: ""
    property string retrofeImportLicense: ""
    property bool retrofeImportOverwrite: false
    property bool retrofeImportBusy: false
    property string retrofeImportNotice: ""
    property bool retrofeImportNoticeIsError: false
    /// Geração do pedido de importação RetroFE. Cada disparo e cada fechamento
    /// incrementam; a resposta só escreve na superfície se carregar a geração
    /// corrente. Sem isto, um `inspect`/`apply` que chega depois de a superfície
    /// ter mudado reabre estado que o usuário já abandonou — e o pedido mais novo
    /// perde para o anterior, porque os dois voam juntos (o `requestAction` de
    /// `Main.qml`, via `actionIsPending`, só deduplica payload idêntico). O pedido
    /// em voo NÃO é cancelado: o que se descarta é o efeito dele.
    property int retrofeImportGeneration: 0
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
        // Fechar revoga o pedido em voo: a resposta que chegar depois daqui não tem
        // mais superfície a que pertencer. Molde: `resetRetrofeImport()`, abaixo.
        panel.esdeImportGeneration += 1
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
        const ocupadoAntes = panel.esdeImportBusy
        const geracao = panel.esdeImportGeneration + 1
        panel.esdeImportGeneration = geracao
        panel.esdeImportBusy = true
        panel.esdeImportNotice = ""
        panel.esdeImportNoticeIsError = false
        const despachado = panel.requestAction("theme.import.esde.inspect", {source: source},
            function(response) {
                if (geracao !== panel.esdeImportGeneration)
                    return
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
                if (geracao !== panel.esdeImportGeneration)
                    return
                panel.esdeImportBusy = false
                panel.esdeImportSchemes = []
                panel.esdeImportSchemeIndex = -1
                panel.esdeImportNotice = String(message || qsTr("Não foi possível examinar o tema."))
                panel.esdeImportNoticeIsError = true
            })
        // Mesmo vínculo do molde RetroFE: `requestAction` devolve `false` sem callback
        // quando `actionIsPending` já conhece aquele payload, e a recusa é um
        // não-acontecimento — devolve a superfície ao que ela era antes do clique.
        // Ver `inspectRetrofeImport`.
        if (!despachado) {
            panel.esdeImportGeneration = geracao - 1
            panel.esdeImportBusy = ocupadoAntes
        }
    }

    function applyEsdeImport() {
        if (panel.esdeImportSchemeIndex < 0 || panel.esdeImportName.trim() === "")
            return
        const selected = panel.esdeImportSchemes[panel.esdeImportSchemeIndex]
        const scheme = selected && selected.scheme
            ? String(selected.scheme) : String(selected || "")
        if (scheme === "")
            return
        const ocupadoAntes = panel.esdeImportBusy
        const geracao = panel.esdeImportGeneration + 1
        panel.esdeImportGeneration = geracao
        panel.esdeImportBusy = true
        panel.esdeImportNotice = ""
        panel.esdeImportNoticeIsError = false
        const despachado = panel.requestAction("theme.import.esde.apply", {
            source: panel.esdeImportSource.trim(),
            scheme: scheme,
            name: panel.esdeImportName.trim()
        }, function(response) {
            if (geracao !== panel.esdeImportGeneration)
                return
            panel.esdeImportBusy = false
            panel.refreshThemeList()
            panel.esdeImportNotice = qsTr("Tema importado como editável; ele ainda não foi aplicado.")
            panel.esdeImportNoticeIsError = false
            panel.esdeImportSchemes = []
            panel.esdeImportSchemeIndex = -1
            panel.esdeImportName = ""
        }, function(message) {
            if (geracao !== panel.esdeImportGeneration)
                return
            panel.esdeImportBusy = false
            panel.esdeImportNotice = String(message || qsTr("Não foi possível importar o tema."))
            panel.esdeImportNoticeIsError = true
        })
        // ver `inspectEsdeImport`, acima: a recusa por payload idêntico tem de devolver
        // a bandeira ao que ela era antes do clique, senão "Importar" habilita sobre um
        // importador que ainda vai responder — ou prende o diálogo se o pedido já tiver
        // sido revogado pelo fechamento.
        if (!despachado) {
            panel.esdeImportGeneration = geracao - 1
            panel.esdeImportBusy = ocupadoAntes
        }
    }

    function resetPackageImport() {
        panel.packageImportSource = ""
        panel.packageImportPreview = null
        panel.packageImportOverwrite = false
        panel.packageImportBusy = false
        panel.packageImportNotice = ""
        panel.packageImportNoticeIsError = false
    }

    function inspectPackageImport() {
        const source = panel.packageImportSource.trim()
        if (source === "")
            return
        panel.packageImportBusy = true
        panel.packageImportNotice = ""
        panel.packageImportNoticeIsError = false
        panel.requestAction("theme.import.package.inspect", {source: source},
            function(response) {
                panel.packageImportBusy = false
                panel.packageImportPreview = response || null
                panel.packageImportOverwrite = false
                panel.packageImportNotice = response && response.alreadyInstalled
                    ? qsTr("Este tema já está instalado. Marque substituir somente se deseja trocar a versão atual.")
                    : qsTr("Pacote validado. Confirme para instalar; o tema ativo não será alterado.")
                panel.packageImportNoticeIsError = false
            },
            function(message) {
                panel.packageImportBusy = false
                panel.packageImportPreview = null
                panel.packageImportNotice = String(message || qsTr("Não foi possível examinar o pacote."))
                panel.packageImportNoticeIsError = true
            })
    }

    function applyPackageImport() {
        if (!panel.packageImportPreview || panel.packageImportSource.trim() === "")
            return
        panel.packageImportBusy = true
        panel.packageImportNotice = ""
        panel.packageImportNoticeIsError = false
        panel.requestAction("theme.import.package.apply", {
            source: panel.packageImportSource.trim(),
            overwrite: panel.packageImportOverwrite
        }, function(_response) {
            panel.packageImportBusy = false
            panel.refreshThemeList()
            panel.packageImportNotice = qsTr("Pacote importado. O tema ativo não foi alterado.")
            panel.packageImportNoticeIsError = false
        }, function(message) {
            panel.packageImportBusy = false
            panel.packageImportNotice = String(message || qsTr("Não foi possível importar o pacote."))
            panel.packageImportNoticeIsError = true
        })
    }

    function resetRetrofeImport() {
        // Fechar revoga o pedido em voo: a resposta que chegar depois daqui não tem
        // mais superfície a que pertencer.
        panel.retrofeImportGeneration += 1
        panel.retrofeImportSource = ""
        panel.retrofeImportLayouts = []
        panel.retrofeImportLayoutIndex = -1
        panel.retrofeImportSceneId = ""
        panel.retrofeImportName = ""
        panel.retrofeImportAuthor = ""
        panel.retrofeImportLicense = ""
        panel.retrofeImportOverwrite = false
        panel.retrofeImportBusy = false
        panel.retrofeImportNotice = ""
        panel.retrofeImportNoticeIsError = false
    }

    function inspectRetrofeImport() {
        const source = panel.retrofeImportSource.trim()
        if (source === "")
            return
        const ocupadoAntes = panel.retrofeImportBusy
        const geracao = panel.retrofeImportGeneration + 1
        panel.retrofeImportGeneration = geracao
        panel.retrofeImportBusy = true
        panel.retrofeImportNotice = ""
        panel.retrofeImportNoticeIsError = false
        const despachado = panel.requestAction("theme.import.retrofe.inspect", {source: source},
            function(response) {
                if (geracao !== panel.retrofeImportGeneration)
                    return
                panel.retrofeImportBusy = false
                panel.retrofeImportLayouts = response && response.layouts
                    ? response.layouts : []
                panel.retrofeImportLayoutIndex = panel.retrofeImportLayouts.length > 0 ? 0 : -1
                panel.retrofeImportNotice = panel.retrofeImportLayouts.length > 0
                    ? qsTr("Escolha um layout e confirme os créditos antes de publicar a cena.")
                    : qsTr("Nenhum layout RetroFE importável foi encontrado.")
                panel.retrofeImportNoticeIsError = panel.retrofeImportLayouts.length === 0
            },
            function(message) {
                if (geracao !== panel.retrofeImportGeneration)
                    return
                panel.retrofeImportBusy = false
                panel.retrofeImportLayouts = []
                panel.retrofeImportLayoutIndex = -1
                panel.retrofeImportNotice = String(message || qsTr("Não foi possível examinar a cena RetroFE."))
                panel.retrofeImportNoticeIsError = true
            })
        // O `requestAction` de `Main.qml` recusa payload idêntico já em voo (via
        // `actionIsPending`) sem disparar nenhuma
        // callback. A recusa é um não-acontecimento: ela devolve a superfície ao que
        // ela era antes do clique, e só `ocupadoAntes` diz a verdade sobre isso.
        //   - pedido ainda corrente (`ocupadoAntes` verdadeiro): baixá-la aqui deixaria
        //     "Importando…" sumido e "Publicar cena" habilitado sobre um importador que
        //     ainda vai responder; o rollback de geração é o que faz a resposta dele
        //     chegar a uma superfície que ainda é dele.
        //   - pedido revogado pelo fechamento: o `onClosed` já baixou a bandeira, então
        //     `ocupadoAntes` é falso e nada rearma — manter a bandeira armada seria o
        //     diálogo preso para sempre, porque a resposta revogada não a abaixa mais.
        if (!despachado) {
            panel.retrofeImportGeneration = geracao - 1
            panel.retrofeImportBusy = ocupadoAntes
        }
    }

    function applyRetrofeImport() {
        if (panel.retrofeImportLayoutIndex < 0
                || panel.retrofeImportSceneId.trim() === ""
                || panel.retrofeImportName.trim() === ""
                || panel.retrofeImportAuthor.trim() === ""
                || panel.retrofeImportLicense.trim() === "")
            return
        const selected = panel.retrofeImportLayouts[panel.retrofeImportLayoutIndex]
        const layout = selected && selected.id ? String(selected.id) : ""
        if (layout === "")
            return
        const ocupadoAntes = panel.retrofeImportBusy
        panel.retrofeImportBusy = true
        panel.retrofeImportNotice = ""
        panel.retrofeImportNoticeIsError = false
        const geracao = panel.retrofeImportGeneration + 1
        panel.retrofeImportGeneration = geracao
        const despachado = panel.requestAction("theme.import.retrofe.apply", {
            source: panel.retrofeImportSource.trim(),
            layout: layout,
            sceneId: panel.retrofeImportSceneId.trim(),
            name: panel.retrofeImportName.trim(),
            author: panel.retrofeImportAuthor.trim(),
            license: panel.retrofeImportLicense.trim(),
            overwrite: panel.retrofeImportOverwrite
        }, function(_response) {
            if (geracao !== panel.retrofeImportGeneration)
                return
            panel.retrofeImportBusy = false
            panel.retrofeImportNotice = qsTr("Cena RetroFE publicada com assets validados; ela ainda não foi ativada.")
            panel.retrofeImportNoticeIsError = false
            panel.refreshThemeList()
        }, function(message) {
            if (geracao !== panel.retrofeImportGeneration)
                return
            panel.retrofeImportBusy = false
            panel.retrofeImportNotice = String(message || qsTr("Não foi possível importar a cena RetroFE."))
            panel.retrofeImportNoticeIsError = true
        })
        // ver `inspectRetrofeImport`: payload idêntico já em voo devolve `false` sem
        // callback, e a recusa tem de devolver a bandeira ao que ela era antes do
        // clique — a mesma regra nos dois despachantes, para o "Importando…" significar
        // a mesma coisa nas duas rotas.
        if (!despachado) {
            panel.retrofeImportGeneration = geracao - 1
            panel.retrofeImportBusy = ocupadoAntes
        }
    }

    /// O corpo do diálogo é rolável e as ações ficam no rodapé: antes de revelar
    /// um item é preciso saber se ele pertence ao diálogo aberto.
    function itemInRetrofeImportDialog(item) {
        let current = item
        while (current) {
            if (current === retrofeImportScroll || current === retrofeImportFooter)
                return true
            current = current.parent
        }
        return false
    }

    function revealRetrofeImportItem(item) {
        if (!panel.itemInRetrofeImportDialog(item))
            return
        const scroll = retrofeImportScroll.contentItem
        if (!scroll || !scroll.contentItem || !item.height)
            return
        const point = item.mapToItem(scroll.contentItem, 0, 0)
        if (point.y < 0 || point.y > scroll.contentHeight)
            return
        const top = point.y - 12
        const bottom = point.y + item.height + 12
        if (top < scroll.contentY)
            scroll.contentY = Math.max(0, top)
        else if (bottom > scroll.contentY + scroll.height)
            scroll.contentY = Math.min(
                Math.max(0, scroll.contentHeight - scroll.height),
                bottom - scroll.height
            )
    }

    function itemInEsdeImportDialog(item) {
        let current = item
        while (current) {
            if (current === esdeImportScroll || current === esdeImportFooter)
                return true
            current = current.parent
        }
        return false
    }

    function revealEsdeImportItem(item) {
        if (!panel.itemInEsdeImportDialog(item))
            return
        const scroll = esdeImportScroll.contentItem
        if (!scroll || !scroll.contentItem || !item.height)
            return
        const point = item.mapToItem(scroll.contentItem, 0, 0)
        if (point.y < 0 || point.y > scroll.contentHeight)
            return
        const top = point.y - 12
        const bottom = point.y + item.height + 12
        if (top < scroll.contentY)
            scroll.contentY = Math.max(0, top)
        else if (bottom > scroll.contentY + scroll.height)
            scroll.contentY = Math.min(
                Math.max(0, scroll.contentHeight - scroll.height),
                bottom - scroll.height
            )
    }

    function _mergeTokens(category, values) {
        var copy = JSON.parse(JSON.stringify(panel.editorTokens))
        if (!copy[category]) copy[category] = {}
        for (var k in values)
            copy[category][k] = values[k]
        return copy
    }

    function _applyEditorResult(r) {
        if (r.preview) {
            panel.editorPreviewObject = r.preview
            panel.editorTokens = r.preview.resolved || {}
        }
        if (r.manifest)
            panel.editorManifest = r.manifest
        if (r.declared)
            panel.editorDeclared = r.declared
        if (r.effectSchema)
            panel.editorEffectSchema = r.effectSchema
        if (r.motionSchema)
            panel.editorMotionSchema = r.motionSchema
        panel.authoringNotice = ""
        if (r.history) {
            panel.editorHistory = r.history
            panel.editorDirty = r.history.dirty === true
        }
    }

    function editorUndo() {
        panel.requestAction("theme.editor.undo", {sessionId: panel.editorSessionId},
            panel._applyEditorResult)
    }

    function editorRedo() {
        panel.requestAction("theme.editor.redo", {sessionId: panel.editorSessionId},
            panel._applyEditorResult)
    }

    function setMediaRecipe(field, value) {
        panel.requestAction("theme.editor.set-media-recipe", {
            sessionId: panel.editorSessionId,
            role: panel.mediaRecipeRole,
            field: field,
            value: value
        }, panel._applyEditorResult)
    }

    function editEffect(op, extra) {
        if (panel.editorReadOnly || !panel.editorSessionId)
            return
        var body = {sessionId: panel.editorSessionId, stack: panel.effectStackName, op: op}
        for (var k in extra)
            body[k] = extra[k]
        panel.requestAction("theme.editor.edit-effect", body, panel._applyEditorResult,
            function(message) { panel.authoringNotice = String(message); panel.authoringRevision += 1 })
    }

    function effectParameterSpec(effectType, parameter) {
        const entry = panel.editorEffectSchema[effectType] || ({})
        const specified = (entry.parameters || ({}))[parameter]
        if (specified)
            return specified
        return parameter === "color"
            ? {kind: "color", default: "#000000"}
            : {kind: "number", minimum: -1000000, maximum: 1000000, step: 1, decimals: 2}
    }

    function effectFallbackOptions(effectType) {
        const entry = panel.editorEffectSchema[effectType] || ({})
        return Array.isArray(entry.fallbacks) && entry.fallbacks.length
            ? entry.fallbacks : ["omit", "minimal"]
    }

    function motionKeyframeSpec(field) {
        const keyframes = panel.editorMotionSchema.keyframes || ({})
        return keyframes[field] || {minimum: -256, maximum: 256, step: 1, decimals: 2}
    }

    function rejectEditorNumber(field, minimum, maximum) {
        panel.authoringNotice = qsTr("%1 precisa ficar entre %2 e %3.")
            .arg(field).arg(minimum).arg(maximum)
        panel.authoringRevision += 1
    }

    function effectColorHex(value) {
        const raw = String(value || "").toLowerCase()
        const hex = raw.startsWith("#") ? raw.slice(1) : raw
        if (/^[0-9a-f]{8}$/.test(hex))
            return "#" + hex.slice(-6)
        if (/^[0-9a-f]{6}$/.test(hex))
            return "#" + hex
        return "#000000"
    }

    function formatEffectNumber(value, locale, decimals) {
        let formatted = Number(value).toLocaleString(locale, "f", decimals)
        const sample = Number(1.1).toLocaleString(locale, "f", 1)
        const separator = sample.charAt(1)
        if (separator && formatted.indexOf(separator) >= 0) {
            while (formatted.endsWith("0"))
                formatted = formatted.slice(0, -1)
            if (formatted.endsWith(separator))
                formatted = formatted.slice(0, -1)
        }
        return formatted
    }

    function openEffectColor(index, parameter, value) {
        panel.effectColorIndex = index
        panel.effectColorParameter = parameter
        const dialog = colorPickerComponent.createObject(panel, {
            objectName: "effectColorDialog",
            initialColor: panel.effectColorHex(value),
            backgroundColor: panel.backgroundColor,
            surfaceColor: panel.surfaceColor,
            raisedColor: panel.raisedColor,
            borderColor: panel.borderColor,
            textColor: panel.textColor,
            mutedColor: panel.mutedColor,
            cyanColor: panel.cyanColor,
            cyanDarkColor: panel.cyanDarkColor,
            visualScale: panel.visualScale
        })
        if (!dialog) {
            panel.authoringNotice = qsTr("Não foi possível abrir o seletor de cor.")
            panel.authoringRevision += 1
            return
        }
        panel.effectColorDialogControl = dialog
        dialog.colorPicked.connect(panel.acceptEffectColor)
        dialog.closed.connect(function() {
            if (panel.effectColorDialogControl === dialog)
                panel.effectColorDialogControl = null
        })
        dialog.open()
    }

    function acceptEffectColor(value) {
        if (panel.effectColorIndex < 0 || panel.effectColorParameter === "")
            return
        panel.editEffect("set", {
            index: panel.effectColorIndex,
            param: panel.effectColorParameter,
            value: panel.effectColorHex(value)
        })
    }

    function editMotion(op, timeline, extra) {
        if (panel.editorReadOnly || !panel.editorSessionId)
            return
        var body = {sessionId: panel.editorSessionId, op: op, timeline: timeline}
        for (var k in extra)
            body[k] = extra[k]
        panel.requestAction("theme.editor.edit-motion", body, panel._applyEditorResult,
            function(message) { panel.authoringNotice = String(message); panel.authoringRevision += 1 })
    }

    function keyframeText(stateName, key) {
        var st = ((editorDeclared.sceneMotion || {}).states || {})[stateName] || {}
        var d = {opacity: 1, scale: 1, translateX: 0, translateY: 0}
        return String(st[key] !== undefined ? st[key] : d[key])
    }

    function repeatText(timelineName) {
        var tl = (((editorDeclared.sceneMotion || {}).timelines || {})[timelineName] || {})
        return String(tl.repeat || 0)
    }

    function editBinding(binding, fallback) {
        if (panel.editorReadOnly || !panel.editorSessionId || panel.bindingLayoutName === ""
                || panel.bindingPropName === "")
            return
        var body = {
            sessionId: panel.editorSessionId,
            layoutId: panel.bindingLayoutName,
            prop: panel.bindingPropName,
            fallback: fallback
        }
        if (binding !== null)
            body.binding = binding
        panel.requestAction("theme.editor.edit-binding", body, panel._applyEditorResult,
            function(message) { panel.authoringNotice = String(message); panel.authoringRevision += 1 })
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

    function _openEditor(sessionId, manifest, preview, declared, effectSchema, motionSchema) {
        panel.editorSessionId = sessionId
        panel.editorDeclared = declared || ({effects: ({}), sceneMotion: null})
        panel.editorEffectSchema = effectSchema || ({})
        panel.editorMotionSchema = motionSchema || ({})
        panel.authoringNotice = ""
        panel.editorHistory = ({canUndo: false, canRedo: false})
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
        panel.editorEffectSchema = ({})
        panel.editorMotionSchema = ({})
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
                "preview": ((r.scope ? r.scope + "\n" : "") + (r.preview || "")),
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
                panel._openEditor(r.sessionId, r.manifest, r.preview, r.declared,
                                  r.effectSchema, r.motionSchema)
            })
    }

    Component.onCompleted: refreshThemeList()

    // =====================================================================
    // THEME LIST (no active session)
    // =====================================================================
    ColumnLayout {
        id: listColumn
        visible: panel.editorSessionId === "" && !panel.journeyMode
        anchors.fill: parent
        spacing: 0

        Item { Layout.minimumHeight: 16 }

        Label {
            id: editorTitle
            text: qsTr("Editor de Temas")
            color: panel.textColor
            font.pixelSize: Math.round(24 * panel.visualScale)
            font.weight: Font.Bold
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.fillWidth: true
            elide: Text.ElideRight
        }

        Item { Layout.minimumHeight: 8 }

        // Qual tema esta EM VIGOR, pelo nome. Sem isto a tela mostrava a lista
        // de temas instalados sem dizer qual deles esta aplicado, e instalar
        // parecia ativar.
        Label {
            objectName: "activeThemeLabel"
            visible: panel.activeThemeName !== "" || panel.activeThemeId !== ""
            text: panel.activeThemeName !== ""
                ? qsTr("Tema ativo: %1").arg(panel.activeThemeName)
                : qsTr("Tema ativo: indisponível no catálogo")
            color: panel.activeThemeName !== "" ? panel.cyanColor : panel.amberColor
            font.pixelSize: Math.round(14 * panel.visualScale)
            font.weight: Font.Medium
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.fillWidth: true
            elide: Text.ElideRight
        }

        Item { Layout.minimumHeight: 8 }

        Label {
            text: qsTr("Crie ou edite temas visuais do SteamZero")
            color: panel.mutedColor
            font.pixelSize: Math.round(14 * panel.visualScale)
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }

        Button {
            objectName: "openExperienceJourneys"
            text: qsTr("Abrir Jornadas")
            Accessible.name: qsTr("Abrir autoria de Jornadas")
            Accessible.description: qsTr("Crie menus conectados, filtros públicos e aparências por etapa")
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.fillWidth: true
            Layout.minimumHeight: panel.minimumInteractiveTarget
            enabled: panel.editorSessionId === ""
            onClicked: panel.journeyMode = true
            background: Rectangle {
                color: parent.hovered ? panel.cyanDarkColor : panel.surfaceColor
                radius: 8
                border.color: parent.activeFocus ? panel.textColor : panel.cyanColor
                border.width: parent.activeFocus ? 2 : 1
            }
            contentItem: Label {
                text: parent.text
                color: panel.textColor
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.weight: Font.Medium
            }
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
                font.pixelSize: Math.round(12 * panel.visualScale)
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        RowLayout {
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.minimumHeight: 48
            spacing: 12

            Button {
                objectName: "themeImportRetrofeButton"
                text: qsTr("Importar cena RetroFE")
                Layout.minimumHeight: 48
                Layout.preferredWidth: 220
                Accessible.name: text
                Accessible.description: qsTr("Examina um layout RetroFE e publica uma cena com assets validados")
                onClicked: retrofeImportDialog.open()
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
                text: qsTr("RetroFE → cena IR, créditos e assets verificados antes de publicar")
                color: panel.mutedColor
                font.pixelSize: Math.round(12 * panel.visualScale)
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        RowLayout {
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.minimumHeight: 48
            spacing: 12

            Button {
                objectName: "themeImportPackageButton"
                text: qsTr("Importar pacote")
                Layout.minimumHeight: 48
                Layout.preferredWidth: 220
                Accessible.name: text
                Accessible.description: qsTr("Examina e instala um pacote de tema SteamZero")
                onClicked: packageImportDialog.open()
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
                text: qsTr("Pacote SteamZero → validação antes de instalar")
                color: panel.mutedColor
                font.pixelSize: Math.round(12 * panel.visualScale)
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        Item { Layout.minimumHeight: 20 }

        Label {
            text: qsTr("Temas instalados")
            color: panel.textColor
            font.pixelSize: Math.round(16 * panel.visualScale)
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
                                    text: panel.themeLabel(modelData)
                                    color: panel.textColor
                                    font.pixelSize: Math.round(15 * panel.visualScale)
                                    font.weight: Font.Medium
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Label {
                                    text: (modelData.author ? modelData.author + " · " : "")
                                        + qsTr("v%1").arg(modelData.version || "0")
                                    color: panel.mutedColor
                                    font.pixelSize: Math.round(12 * panel.visualScale)
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Label {
                                    text: modelData.origin === "builtin"
                                        ? qsTr("Tema nativo") : qsTr("Tema do usuário")
                                    color: panel.cyanColor
                                    font.pixelSize: Math.round(11 * panel.visualScale)
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
                                    font.pixelSize: Math.round(12 * panel.visualScale)
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
                                    objectName: "themeApplyButton_" + modelData.id
                                    text: qsTr("Aplicar")
                                    implicitWidth: 88
                                    implicitHeight: Math.max(panel.minimumInteractiveTarget, 36)
                                    Accessible.name: qsTr("Aplicar tema %1").arg(panel.themeLabel(modelData))
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
                                        font.pixelSize: Math.round(13 * panel.visualScale)
                                        font.weight: Font.Medium
                                    }
                                }

                                Button {
                                    objectName: "themeEditButton_" + modelData.id
                                    text: themeCard.isBuiltin
                                        ? qsTr("Ver (somente leitura)")
                                        : qsTr("Editar")
                                    implicitWidth: themeCard.isBuiltin
                                        ? (panel.compactLayout ? 120 : 150)
                                        : 88
                                    implicitHeight: Math.max(panel.minimumInteractiveTarget, 36)
                                    Accessible.name: text + " " + (panel.themeLabel(modelData))
                                    onClicked: {
                                        // Via envelope de ações: URL/método vêm do
                                        // contrato do backend, não são montados aqui.
                                        panel.requestAction("theme.editor.load",
                                            {themeId: modelData.id}, function(r) {
                                                panel._openEditor(r.sessionId, r.manifest, r.preview,
                                                                  r.declared, r.effectSchema,
                                                                  r.motionSchema)
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
                                        font.pixelSize: Math.round(12 * panel.visualScale)
                                        elide: Text.ElideRight
                                    }
                                }

                                Button {
                                    visible: themeCard.isBuiltin
                                    text: qsTr("Duplicar e editar")
                                    implicitWidth: panel.compactLayout ? 120 : 140
                                    implicitHeight: Math.max(panel.minimumInteractiveTarget, 36)
                                    Accessible.name: qsTr("Duplicar e editar %1").arg(panel.themeLabel(modelData))
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
                                        font.pixelSize: Math.round(12 * panel.visualScale)
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

    ExperienceJourneyPanel {
        id: journeyPanel
        objectName: "experienceJourneyPanel"
        anchors.fill: parent
        visible: panel.editorSessionId === "" && panel.journeyMode
        requestAction: panel.requestAction
        backgroundColor: panel.backgroundColor
        surfaceColor: panel.surfaceColor
        raisedColor: panel.raisedColor
        borderColor: panel.borderColor
        textColor: panel.textColor
        mutedColor: panel.mutedColor
        accentColor: panel.cyanColor
        amberColor: panel.amberColor
        errorColor: panel.redColor
        visualScale: panel.visualScale
        compactLayout: panel.compactLayout
        onCloseRequested: panel.journeyMode = false
    }

    ThemedDialog {
        id: esdeImportDialog
        surfaceColor: panel.surfaceColor
        raisedColor: panel.raisedColor
        borderColor: panel.borderColor
        textColor: panel.textColor
        mutedColor: panel.mutedColor
        accentColor: panel.cyanColor
        visualScale: panel.visualScale
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

        /// Up/Down percorrem o diálogo inteiro, exatamente como no modal RetroFE da
        /// fatia anterior. O rodapé não é descendente do corpo rolável, então as duas
        /// pontas chamam o mesmo passo. Andar só dentro do modal e pular o que não
        /// aceita foco: sem isso o D-pad atravessaria para os controles atrás do
        /// diálogo ou empacaria em um botão desabilitado.
        function moveVertical(event, forward) {
            const hostWindow = panel.Window.window
            const active = hostWindow ? hostWindow.activeFocusItem : null
            let next = active
            do {
                next = next ? next.nextItemInFocusChain(forward) : null
            } while (next && next !== active
                     && (!panel.itemInEsdeImportDialog(next) || next.enabled === false))
            if (!next || next === active)
                return
            next.forceActiveFocus(Qt.TabFocusReason)
            Qt.callLater(function() { panel.revealEsdeImportItem(next) })
        }

        contentItem: ScrollView {
            id: esdeImportScroll
            clip: true
            contentWidth: availableWidth
            focus: true
            // Setas verticais navegam o diálogo; as horizontais seguem editando.
            Keys.onUpPressed: function(event) {
                esdeImportDialog.moveVertical(event, false)
            }
            Keys.onDownPressed: function(event) {
                esdeImportDialog.moveVertical(event, true)
            }

            ColumnLayout {
                width: esdeImportScroll.availableWidth
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
                    objectName: "themeImportEsdeNotice"
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

                ColumnLayout {
                    visible: panel.esdeImportSchemes.length > 0
                    Layout.fillWidth: true
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
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
                                    onClicked: panel.esdeImportSchemeIndex = index
                                }
                            Label {
                                text: modelData && modelData.isMonochrome
                                    ? qsTr("monocromático; derivação limitada")
                                    : qsTr("paleta convertível")
                                color: modelData && modelData.isMonochrome
                                    ? panel.amberColor : panel.mutedColor
                                font.pixelSize: Math.round(11 * panel.visualScale)
                                Layout.fillWidth: true
                                elide: Text.ElideRight
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
            }
        }

        footer: RowLayout {
            id: esdeImportFooter
            Layout.fillWidth: true
            Keys.onUpPressed: function(event) {
                esdeImportDialog.moveVertical(event, false)
            }
            Keys.onDownPressed: function(event) {
                esdeImportDialog.moveVertical(event, true)
            }

            Button {
                objectName: "themeImportEsdeCancel"
                text: qsTr("Cancelar")
                Accessible.name: text
                Layout.minimumHeight: 48
                onClicked: esdeImportDialog.close()
            }
            Item { Layout.fillWidth: true }
            Button {
                id: esdeImportApplyButton
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

    ThemedDialog {
        id: retrofeImportDialog
        surfaceColor: panel.surfaceColor
        raisedColor: panel.raisedColor
        borderColor: panel.borderColor
        textColor: panel.textColor
        mutedColor: panel.mutedColor
        accentColor: panel.cyanColor
        visualScale: panel.visualScale
        objectName: "themeImportRetrofeDialog"
        modal: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(panel.width - 24, 700)
        height: Math.min(panel.height - 24, 650)
        x: (panel.width - width) / 2
        y: (panel.height - height) / 2
        title: qsTr("Importar cena RetroFE")
        standardButtons: Dialog.NoButton
        onOpened: retrofeImportSourceField.forceActiveFocus()
        onClosed: panel.resetRetrofeImport()

        /// Up/Down percorrem o diálogo inteiro. O rodapé não é descendente do
        /// corpo rolável, então as duas pontas chamam o mesmo passo. Andar só
        /// dentro do modal e pular o que não aceita foco: sem isso o D-pad
        /// atravessaria para os controles atrás do diálogo ou empacaria em um
        /// botão desabilitado.
        function moveVertical(event, forward) {
            const hostWindow = panel.Window.window
            const active = hostWindow ? hostWindow.activeFocusItem : null
            let next = active
            do {
                next = next ? next.nextItemInFocusChain(forward) : null
            } while (next && next !== active
                     && (!panel.itemInRetrofeImportDialog(next) || next.enabled === false))
            if (!next || next === active)
                return
            next.forceActiveFocus(Qt.TabFocusReason)
            Qt.callLater(function() { panel.revealRetrofeImportItem(next) })
        }

        contentItem: ScrollView {
            id: retrofeImportScroll
            clip: true
            contentWidth: availableWidth
            focus: true
            // Setas verticais navegam o diálogo; as horizontais seguem editando.
            Keys.onUpPressed: function(event) {
                retrofeImportDialog.moveVertical(event, false)
            }
            Keys.onDownPressed: function(event) {
                retrofeImportDialog.moveVertical(event, true)
            }

            ColumnLayout {
                width: retrofeImportScroll.availableWidth
                spacing: 10

                Label {
                    text: qsTr("Examine primeiro. A cena é compilada para o IR comum, assets são copiados para o store por conteúdo e nada é ativado automaticamente.")
                    color: panel.mutedColor
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                RowLayout {
                    Layout.fillWidth: true
                    TextField {
                        id: retrofeImportSourceField
                        objectName: "themeImportRetrofeSource"
                        text: panel.retrofeImportSource
                        placeholderText: qsTr("Pasta ou layout XML do RetroFE")
                        Accessible.name: qsTr("Pasta ou layout XML do RetroFE")
                        Layout.fillWidth: true
                        Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
                        onTextChanged: panel.retrofeImportSource = text
                        /// Enter examina. Num shell operado por controle, os dois
                        /// seletores nativos abaixo são becos: o pad não alcança a
                        /// janela de arquivo do sistema, e sem esta tecla o caminho
                        /// digitado nunca viraria pedido.
                        onAccepted: panel.inspectRetrofeImport()

                        /// Digitar INTERROMPE o vínculo declarativo de cima: o editor
                        /// escreve em `text`, e a partir daí quem muda o ESTADO (o
                        /// `resetRetrofeImport()` do `onClosed`, os dois seletores que
                        /// gravam `panel.localPath(...)`) não alcançaria mais o pixel.
                        /// Campo e botão leriam verdades diferentes — o "Examinar"
                        /// decide por `panel.retrofeImportSource` no `enabled` de
                        /// `themeImportRetrofeInspect`). Este
                        /// `Binding` é o espelho de mão única que sobrevive à edição;
                        /// escrever o valor que já está lá não emite `textChanged`,
                        /// então não há loop com o `onTextChanged` acima.
                        Binding {
                            target: retrofeImportSourceField
                            property: "text"
                            value: panel.retrofeImportSource
                        }
                    }
                    Button {
                        objectName: "themeImportRetrofeBrowseFolder"
                        text: qsTr("Pasta")
                        Accessible.name: text
                        Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
                        onClicked: retrofeImportFolderDialog.open()
                    }
                    Button {
                        objectName: "themeImportRetrofeBrowseFile"
                        text: qsTr("XML")
                        Accessible.name: text
                        Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
                        onClicked: retrofeImportFileDialog.open()
                    }
                    Button {
                        objectName: "themeImportRetrofeInspect"
                        text: qsTr("Examinar")
                        enabled: !panel.retrofeImportBusy && panel.retrofeImportSource.trim() !== ""
                        Accessible.name: text
                        Accessible.description: enabled
                            ? qsTr("Compila a prévia sem gravar arquivos")
                            : qsTr("Informe a origem antes de examinar")
                        Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
                        onClicked: panel.inspectRetrofeImport()
                    }
                }

                Label {
                    objectName: "themeImportRetrofeNotice"
                    text: panel.retrofeImportNotice
                    visible: panel.retrofeImportNotice !== ""
                    color: panel.retrofeImportNoticeIsError ? panel.redColor : panel.greenColor
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                Label {
                    text: qsTr("Layouts encontrados")
                    visible: panel.retrofeImportLayouts.length > 0
                    color: panel.textColor
                    font.weight: Font.Medium
                }

                ColumnLayout {
                    visible: panel.retrofeImportLayouts.length > 0
                    Layout.fillWidth: true
                    spacing: 4

                    Repeater {
                        model: panel.retrofeImportLayouts
                        delegate: RowLayout {
                            required property int index
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
                            RadioButton {
                                text: modelData && modelData.name
                                    ? String(modelData.name) : qsTr("Layout")
                                checked: panel.retrofeImportLayoutIndex === index
                                Accessible.name: qsTr("Layout %1").arg(text)
                                Layout.minimumHeight: panel.minimumInteractiveTarget
                                onClicked: panel.retrofeImportLayoutIndex = index
                            }
                            Label {
                                text: modelData && modelData.report
                                    ? qsTr("%1 elementos · %2 degradados").arg(modelData.report.elements)
                                        .arg(modelData.report.degraded)
                                    : qsTr("relatório indisponível")
                                color: panel.mutedColor
                                font.pixelSize: Math.round(11 * panel.visualScale)
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                        }
                    }
                }

                Label {
                    readonly property var selectedLayout: panel.retrofeImportLayoutIndex >= 0
                        ? panel.retrofeImportLayouts[panel.retrofeImportLayoutIndex] : null
                    text: selectedLayout && selectedLayout.assets
                        ? (selectedLayout.assets.ready
                            ? qsTr("Assets prontos: %1").arg(selectedLayout.assets.available.length)
                            : qsTr("Assets ausentes/recusados: %1").arg(
                                selectedLayout.assets.missing.length + selectedLayout.assets.refused.length))
                        : ""
                    visible: text !== ""
                    color: selectedLayout && selectedLayout.assets && selectedLayout.assets.ready
                        ? panel.greenColor : panel.amberColor
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                GridLayout {
                    columns: 2
                    visible: panel.retrofeImportLayouts.length > 0
                    Layout.fillWidth: true
                    columnSpacing: 10
                    rowSpacing: 8

                    Label { text: qsTr("ID da cena"); color: panel.mutedColor }
                    TextField {
                        id: retrofeImportSceneIdField
                        objectName: "themeImportRetrofeSceneId"
                        text: panel.retrofeImportSceneId
                        placeholderText: qsTr("org.exemplo.retrofe")
                        Accessible.name: qsTr("ID da cena RetroFE")
                        Layout.fillWidth: true
                        onTextChanged: panel.retrofeImportSceneId = text
                    }
                    Label { text: qsTr("Nome"); color: panel.mutedColor }
                    TextField {
                        id: retrofeImportNameField
                        objectName: "themeImportRetrofeName"
                        text: panel.retrofeImportName
                        placeholderText: qsTr("Nome da cena")
                        Accessible.name: qsTr("Nome da cena RetroFE")
                        Layout.fillWidth: true
                        onTextChanged: panel.retrofeImportName = text
                    }
                    Label { text: qsTr("Autor"); color: panel.mutedColor }
                    TextField {
                        id: retrofeImportAuthorField
                        objectName: "themeImportRetrofeAuthor"
                        text: panel.retrofeImportAuthor
                        placeholderText: qsTr("Autor do tema")
                        Accessible.name: qsTr("Autor do tema RetroFE")
                        Layout.fillWidth: true
                        onTextChanged: panel.retrofeImportAuthor = text
                    }
                    Label { text: qsTr("Licença"); color: panel.mutedColor }
                    TextField {
                        id: retrofeImportLicenseField
                        objectName: "themeImportRetrofeLicense"
                        text: panel.retrofeImportLicense
                        placeholderText: qsTr("SPDX, por exemplo CC0-1.0")
                        Accessible.name: qsTr("Licença do tema RetroFE")
                        Layout.fillWidth: true
                        onTextChanged: panel.retrofeImportLicense = text
                    }
                }

                CheckBox {
                    objectName: "themeImportRetrofeOverwrite"
                    text: qsTr("Substituir uma cena existente explicitamente")
                    checked: panel.retrofeImportOverwrite
                    visible: panel.retrofeImportLayouts.length > 0
                    Accessible.name: text
                    onToggled: panel.retrofeImportOverwrite = checked
                }
            }
        }

        footer: RowLayout {
            id: retrofeImportFooter
            Layout.fillWidth: true
            Keys.onUpPressed: function(event) {
                retrofeImportDialog.moveVertical(event, false)
            }
            Keys.onDownPressed: function(event) {
                retrofeImportDialog.moveVertical(event, true)
            }

            Button {
                objectName: "themeImportRetrofeCancel"
                text: qsTr("Cancelar")
                Accessible.name: text
                Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
                onClicked: retrofeImportDialog.close()
            }
            Item { Layout.fillWidth: true }
            Button {
                id: retrofeImportApplyButton
                objectName: "themeImportRetrofeApply"
                text: panel.retrofeImportBusy ? qsTr("Importando…") : qsTr("Publicar cena")
                enabled: !panel.retrofeImportBusy
                    && panel.retrofeImportLayoutIndex >= 0
                    && panel.retrofeImportSceneId.trim() !== ""
                    && panel.retrofeImportName.trim() !== ""
                    && panel.retrofeImportAuthor.trim() !== ""
                    && panel.retrofeImportLicense.trim() !== ""
                Accessible.name: text
                Accessible.description: enabled
                    ? qsTr("Grava a cena e seus assets no armazenamento gerenciado sem ativar")
                    : qsTr("Examine um layout e informe ID, nome, autor e licença")
                Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
                onClicked: panel.applyRetrofeImport()
            }
        }
    }

    // O foco pode mudar por Tab, por toque ou pelo D-pad; qualquer mudança precisa
    // revelar o destino dentro do corpo rolável do diálogo aberto.
    Connections {
        target: panel.Window.window
        enabled: target !== null
        ignoreUnknownSignals: true
        function onActiveFocusItemChanged() {
            if (!retrofeImportDialog.visible)
                return
            const item = target ? target.activeFocusItem : null
            if (item)
                Qt.callLater(function() { panel.revealRetrofeImportItem(item) })
        }
    }

    FolderDialog {
        id: esdeImportFolderDialog
        title: qsTr("Escolher pasta do tema ES-DE")
        onAccepted: panel.esdeImportSource = panel.localPath(selectedFolder)
    }

    FolderDialog {
        id: retrofeImportFolderDialog
        title: qsTr("Escolher pasta do tema RetroFE")
        onAccepted: panel.retrofeImportSource = panel.localPath(selectedFolder)
    }

    FileDialog {
        id: retrofeImportFileDialog
        title: qsTr("Escolher layout XML RetroFE")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Layouts RetroFE (*.xml)"), qsTr("Todos os arquivos (*)")]
        onAccepted: {
            panel.retrofeImportSource = panel.localPath(selectedFile)
            panel.inspectRetrofeImport()
        }
    }

    FileDialog {
        id: packageImportFileDialog
        title: qsTr("Escolher pacote de tema SteamZero")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Pacotes de tema (*.zip)"), qsTr("Todos os arquivos (*)")]
        onAccepted: {
            panel.packageImportSource = panel.localPath(selectedFile)
            panel.inspectPackageImport()
        }
    }

    ThemedDialog {
        id: packageImportDialog
        surfaceColor: panel.surfaceColor
        raisedColor: panel.raisedColor
        borderColor: panel.borderColor
        textColor: panel.textColor
        mutedColor: panel.mutedColor
        accentColor: panel.cyanColor
        visualScale: panel.visualScale
        objectName: "themeImportPackageDialog"
        modal: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(panel.width - 24, 640)
        height: Math.min(panel.height - 24, 500)
        x: (panel.width - width) / 2
        y: (panel.height - height) / 2
        title: qsTr("Importar pacote de tema")
        standardButtons: Dialog.NoButton
        onOpened: packageImportChoose.forceActiveFocus()
        onClosed: panel.resetPackageImport()

        contentItem: ColumnLayout {
            spacing: 10

            Label {
                text: qsTr("Examine o manifesto antes de instalar. O tema ativo só muda por uma ação separada de aplicar.")
                color: panel.mutedColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            RowLayout {
                Layout.fillWidth: true
                TextField {
                    id: packageImportSourceField
                    text: panel.packageImportSource
                    placeholderText: qsTr("Arquivo .zip do tema")
                    Accessible.name: qsTr("Arquivo do pacote de tema")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onTextChanged: panel.packageImportSource = text
                }
                Button {
                    id: packageImportChoose
                    text: qsTr("Escolher")
                    Accessible.name: text
                    Layout.minimumHeight: 48
                    onClicked: packageImportFileDialog.open()
                }
                Button {
                    text: qsTr("Examinar")
                    enabled: !panel.packageImportBusy && panel.packageImportSource.trim() !== ""
                    Accessible.name: text
                    Accessible.description: qsTr("Lê o manifesto sem instalar o pacote")
                    Layout.minimumHeight: 48
                    onClicked: panel.inspectPackageImport()
                }
            }

            Label {
                visible: panel.packageImportPreview !== null
                text: panel.packageImportPreview
                    ? qsTr("%1 · v%2\nAutor: %3\nLicença: %4\nID: %5")
                        .arg(panel.packageImportPreview.name || "Tema")
                        .arg(panel.packageImportPreview.version || "—")
                        .arg(panel.packageImportPreview.author || "—")
                        .arg(panel.packageImportPreview.license || "—")
                        .arg(panel.packageImportPreview.themeId || "—")
                    : ""
                color: panel.textColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            CheckBox {
                visible: panel.packageImportPreview !== null
                    && panel.packageImportPreview.alreadyInstalled === true
                text: qsTr("Substituir o tema instalado")
                checked: panel.packageImportOverwrite
                Accessible.name: text
                onToggled: panel.packageImportOverwrite = checked
            }

            Label {
                text: panel.packageImportNotice
                visible: panel.packageImportNotice !== ""
                color: panel.packageImportNoticeIsError ? panel.redColor : panel.greenColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Accessible.name: text
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onClicked: packageImportDialog.close()
                }
                Button {
                    text: panel.packageImportBusy
                        ? qsTr("Instalando…") : qsTr("Instalar pacote")
                    enabled: !panel.packageImportBusy
                        && panel.packageImportPreview !== null
                        && (!panel.packageImportPreview.alreadyInstalled
                            || panel.packageImportOverwrite)
                    Accessible.name: text
                    Accessible.description: enabled
                        ? qsTr("Instala o pacote sem aplicar automaticamente o tema")
                        : qsTr("Examine o pacote e confirme a substituição, se necessário")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onClicked: panel.applyPackageImport()
                }
            }
        }
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
                        font.pixelSize: Math.round(16 * panel.visualScale)
                        font.weight: Font.Medium
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Label {
                        text: panel.editorManifest.id || ""
                        color: panel.mutedColor
                        font.pixelSize: Math.round(11 * panel.visualScale)
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }

                Label {
                    visible: panel.editorReadOnly
                    text: qsTr("Apenas leitura")
                    color: panel.amberColor
                    font.pixelSize: Math.round(12 * panel.visualScale)
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
                    font.pixelSize: Math.round(11 * panel.visualScale)
                    font.italic: true
                }

                Button {
                    objectName: "themeEditorUndo"
                    text: qsTr("Desfazer")
                    enabled: !panel.editorReadOnly && panel.editorHistory.canUndo === true
                    implicitHeight: Math.max(panel.minimumInteractiveTarget, 36)
                    implicitWidth: 90
                    Accessible.name: text
                    onClicked: panel.editorUndo()
                    background: Rectangle {
                        color: parent.enabled ? panel.surfaceColor : panel.borderColor
                        radius: 6
                        border.color: parent.activeFocus ? panel.cyanColor : panel.borderColor
                        border.width: parent.activeFocus ? 2 : 1
                    }
                    contentItem: Label {
                        text: parent.text
                        color: parent.enabled ? panel.cyanColor : panel.mutedColor
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                Button {
                    objectName: "themeEditorRedo"
                    text: qsTr("Refazer")
                    enabled: !panel.editorReadOnly && panel.editorHistory.canRedo === true
                    implicitHeight: Math.max(panel.minimumInteractiveTarget, 36)
                    implicitWidth: 90
                    Accessible.name: text
                    onClicked: panel.editorRedo()
                    background: Rectangle {
                        color: parent.enabled ? panel.surfaceColor : panel.borderColor
                        radius: 6
                        border.color: parent.activeFocus ? panel.cyanColor : panel.borderColor
                        border.width: parent.activeFocus ? 2 : 1
                    }
                    contentItem: Label {
                        text: parent.text
                        color: parent.enabled ? panel.cyanColor : panel.mutedColor
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                Button {
                    objectName: "themeEditorSave"
                    text: qsTr("Salvar")
                    enabled: !panel.editorReadOnly && panel.editorDirty
                    implicitHeight: Math.max(panel.minimumInteractiveTarget, 36)
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
                    implicitHeight: Math.max(panel.minimumInteractiveTarget, 36)
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
                    objectName: "themeEditorClose"
                    text: qsTr("Fechar")
                    implicitHeight: Math.max(panel.minimumInteractiveTarget, 36)
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
                id: tokenScroll
                Layout.fillHeight: true
                Layout.preferredWidth: panel.compactLayout ? parent.width * 0.5 : 380
                Layout.minimumWidth: 280
                clip: true
                contentWidth: availableWidth

                ColumnLayout {
                    // `parent` aqui é o contentItem (sem availableWidth): a largura caía no
                    // implícito e a coluna estourava a viewport compacta, escondendo botões.
                    width: tokenScroll.availableWidth
                    spacing: 0

                    Item { Layout.minimumHeight: 8 }

                    Label {
                        text: qsTr("Metadados do tema")
                        color: panel.textColor
                        font.pixelSize: Math.round(16 * panel.visualScale)
                        font.weight: Font.Medium
                        Layout.leftMargin: 12
                        Layout.rightMargin: 12
                        Layout.fillWidth: true
                    }

                    Label {
                        text: qsTr("Nome, autoria e licença são preservados no pacote exportado.")
                        color: panel.mutedColor
                        font.pixelSize: Math.round(11 * panel.visualScale)
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
                                font.pixelSize: Math.round(11 * panel.visualScale)
                            }

                            TextField {
                                objectName: "themeMetadata_" + modelData
                                text: panel.editorManifest[modelData] || ""
                                enabled: !panel.editorReadOnly
                                Layout.fillWidth: true
                                Layout.minimumHeight: panel.minimumInteractiveTarget
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
                                    if (r.history)
                                        panel.editorHistory = r.history
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
                                    if (r.history)
                                        panel.editorHistory = r.history
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
                                    if (r.history)
                                        panel.editorHistory = r.history
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
                                    if (r.history)
                                        panel.editorHistory = r.history
                                    if (r.preview && r.preview.resolved) {
                                        panel.editorPreviewObject = r.preview
                                        panel.editorTokens = r.preview.resolved
                                    }
                                })
                        }
                    }

                    Rectangle {
                        objectName: "mediaRecipeInspector"
                        visible: panel.editorSessionId !== "" && !panel.editorReadOnly
                        color: panel.surfaceColor
                        radius: 8
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.maximumWidth: tokenScroll.availableWidth
                        implicitHeight: visible ? mediaColumn.implicitHeight + 24 : 0
                        border.color: panel.borderColor
                        border.width: 1

                        ColumnLayout {
                            id: mediaColumn
                            anchors.fill: parent
                            anchors.margins: 12
                            Flow {
                            id: mediaFlow
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: mediaColumn.width
                            Layout.maximumWidth: mediaColumn.width
                            Layout.preferredHeight: childrenRect.height
                            spacing: 10
                            Label {
                                text: qsTr("Enquadramento de mídia")
                                color: panel.mutedColor
                                font.pixelSize: Math.round(11 * panel.visualScale)
                            }
                            AuthCombo {
                                objectName: "mediaRecipeRole"
                                requestedImplicitHeight: 40
                                Accessible.name: qsTr("Slot de mídia")
                                model: ["focusedCover", "peripheralCover", "contextualBackdrop"]
                                onActivated: panel.mediaRecipeRole = currentText
                            }
                            AuthCombo {
                                objectName: "mediaRecipeFit"
                                requestedImplicitHeight: 40
                                Accessible.name: qsTr("Ajuste")
                                model: ["crop", "cover", "contain", "fill"]
                                onActivated: panel.setMediaRecipe("fit", currentText)
                            }
                            AuthCombo {
                                objectName: "mediaRecipeOrientation"
                                requestedImplicitHeight: 40
                                Accessible.name: qsTr("Orientação")
                                model: ["none", "auto", "portrait", "landscape"]
                                onActivated: panel.setMediaRecipe("orientation", currentText)
                            }
                            AuthCombo {
                                objectName: "mediaRecipeAlignH"
                                requestedImplicitHeight: 40
                                Accessible.name: qsTr("Alinhamento horizontal")
                                model: ["left", "center", "right"]
                                onActivated: panel.setMediaRecipe("alignH", currentText)
                            }
                            AuthCombo {
                                objectName: "mediaRecipeAlignV"
                                requestedImplicitHeight: 40
                                Accessible.name: qsTr("Alinhamento vertical")
                                model: ["top", "center", "bottom"]
                                onActivated: panel.setMediaRecipe("alignV", currentText)
                            }
                        }
                        }
                    }

                    Rectangle {
                        objectName: "effectStackInspector"
                        visible: panel.editorSessionId !== "" && !panel.editorReadOnly
                        color: panel.surfaceColor
                        radius: 8
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.maximumWidth: tokenScroll.availableWidth
                        implicitHeight: visible ? effectColumn.implicitHeight + 24 : 0
                        border.color: panel.borderColor
                        border.width: 1

                        ColumnLayout {
                            id: effectColumn
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8
                            Flow {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: effectColumn.width
                                Layout.maximumWidth: effectColumn.width
                                Layout.preferredHeight: childrenRect.height
                                spacing: 10
                                Label {
                                    text: qsTr("Efeitos")
                                    color: panel.mutedColor
                                    font.pixelSize: Math.round(11 * panel.visualScale)
                                }
                                AuthCombo {
                                    objectName: "effectStackName"
                                    requestedImplicitHeight: 40
                                    Accessible.name: qsTr("Pilha de efeitos")
                                    model: ["focusedCover", "peripheralCover", "contextualBackdrop"]
                                    onActivated: panel.effectStackName = currentText
                                }
                                AuthCombo {
                                    id: effectTypeCombo
                                    objectName: "effectTypeToAdd"
                                    requestedImplicitHeight: 40
                                    Accessible.name: qsTr("Tipo de efeito")
                                    model: ["blur", "saturation", "brightness", "contrast", "colorize", "opacity", "shadow", "glow", "reflection", "gradientMask", "vignette"]
                                }
                                AuthButton {
                                    objectName: "effectAdd"
                                    requestedImplicitHeight: 40
                                    text: qsTr("Adicionar efeito")
                                    Accessible.name: qsTr("Adicionar efeito à pilha")
                                    onClicked: panel.editEffect("add", {effectType: effectTypeCombo.currentText})
                                }
                            }
                            Label {
                                objectName: "effectEmpty"
                                visible: effectRepeater.count === 0
                                text: qsTr("Pilha vazia. Escolha um tipo e use Adicionar efeito.")
                                color: panel.mutedColor
                                font.pixelSize: Math.round(11 * panel.visualScale)
                            }
                            Repeater {
                                id: effectRepeater
                                objectName: "effectRepeater"
                                model: panel.authoringRevision < 0 ? [] : ((panel.editorDeclared.effects || {})[panel.effectStackName] || []).slice()
                                delegate: Rectangle {
                                    id: effectRow
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    implicitHeight: effectCard.implicitHeight + 16
                                    color: panel.raisedColor
                                    radius: 8
                                    border.color: panel.borderColor
                                    border.width: 1
                                    readonly property bool omittedInPreview: {
                                        var shown = ((panel.editorPreviewObject || {}).effects || {})[panel.effectStackName] || []
                                        return shown.length < ((panel.editorDeclared.effects || {})[panel.effectStackName] || []).length
                                    }
                                    ColumnLayout {
                                        id: effectCard
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        spacing: 6
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6
                                            Label {
                                                objectName: "effectType"
                                                Layout.fillWidth: true
                                                text: effectRow.modelData.type + (effectRow.omittedInPreview ? "  ·  " + qsTr("pode ser omitido neste preview") : "")
                                                color: panel.textColor
                                                font.pixelSize: Math.round(13 * panel.visualScale)
                                                font.bold: true
                                                elide: Text.ElideRight
                                            }
                                            AuthButton {
                                                objectName: "effectUp_" + effectRow.index
                                                text: "↑"
                                                requestedImplicitWidth: 40
                                                enabled: effectRow.index > 0
                                                Accessible.name: qsTr("Mover efeito para cima") + " " + effectRow.modelData.type
                                                onClicked: panel.editEffect("move", {index: effectRow.index, value: effectRow.index - 1})
                                            }
                                            AuthButton {
                                                objectName: "effectDown_" + effectRow.index
                                                text: "↓"
                                                requestedImplicitWidth: 40
                                                enabled: effectRow.index < effectRepeater.count - 1
                                                Accessible.name: qsTr("Mover efeito para baixo") + " " + effectRow.modelData.type
                                                onClicked: panel.editEffect("move", {index: effectRow.index, value: effectRow.index + 1})
                                            }
                                            AuthButton {
                                                objectName: "effectRemove_" + effectRow.index
                                                text: qsTr("Remover")
                                                Accessible.name: qsTr("Remover efeito") + " " + effectRow.modelData.type
                                                onClicked: panel.editEffect("remove", {index: effectRow.index})
                                            }
                                        }
                                        Flow {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            Layout.preferredWidth: effectCard.width
                                            Layout.maximumWidth: effectCard.width
                                            Layout.preferredHeight: childrenRect.height
                                            spacing: 8
                                            Label {
                                                text: qsTr("Fallback do efeito")
                                                color: panel.mutedColor
                                                font.pixelSize: Math.round(11 * panel.visualScale)
                                                Accessible.name: text
                                            }
                                            AuthCombo {
                                                objectName: "effectFallback_" + effectRow.index
                                                Accessible.name: qsTr("Fallback") + " " + effectRow.modelData.type
                                                model: panel.effectFallbackOptions(effectRow.modelData.type)
                                                currentIndex: model.indexOf(effectRow.modelData.fallback || "omit")
                                                onActivated: panel.editEffect("set", {
                                                    index: effectRow.index,
                                                    param: "fallback",
                                                    value: currentText
                                                })
                                            }
                                        }
                                        Flow {
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                            Layout.preferredWidth: effectCard.width
                                            Layout.maximumWidth: effectCard.width
                                            Layout.preferredHeight: childrenRect.height
                                            spacing: 8
                                            Repeater {
                                                model: Object.keys(effectRow.modelData).filter(function(k) { return k !== "type" && k !== "fallback" })
                                                delegate: ColumnLayout {
                                                    id: paramRow
                                                    required property string modelData
                                                    readonly property var specification:
                                                        panel.effectParameterSpec(effectRow.modelData.type,
                                                                                  paramRow.modelData)
                                                    spacing: 2
                                                    Label {
                                                        text: paramRow.modelData
                                                        color: panel.mutedColor
                                                        font.pixelSize: Math.round(11 * panel.visualScale)
                                                    }
                                                    AuthField {
                                                        visible: paramRow.specification.kind === "color"
                                                        objectName: "effectColorHex_" + effectRow.index + "_" + paramRow.modelData
                                                        Accessible.name: effectRow.modelData.type + " " + paramRow.modelData
                                                        Accessible.description: qsTr("Cor no formato #RRGGBB")
                                                        requestedImplicitWidth: 84
                                                        declaredText: String(effectRow.modelData[paramRow.modelData])
                                                        onEditingFinished: submit(function(t) {
                                                            panel.editEffect("set", {
                                                                index: effectRow.index,
                                                                param: paramRow.modelData,
                                                                value: t
                                                            })
                                                        })
                                                    }
                                                    AuthButton {
                                                        visible: paramRow.specification.kind === "color"
                                                        objectName: "effectColorOpen_" + effectRow.index + "_" + paramRow.modelData
                                                        text: qsTr("Escolher cor")
                                                        implicitWidth: 120
                                                        Accessible.name: qsTr("Escolher cor para") + " "
                                                            + effectRow.modelData.type + " " + paramRow.modelData
                                                        onClicked: panel.openEffectColor(effectRow.index,
                                                            paramRow.modelData,
                                                            effectRow.modelData[paramRow.modelData])
                                                        contentItem: RowLayout {
                                                            spacing: 6
                                                            Rectangle {
                                                                Layout.preferredWidth: 22
                                                                Layout.preferredHeight: 22
                                                                radius: 4
                                                                color: panel.effectColorHex(
                                                                    effectRow.modelData[paramRow.modelData])
                                                                border.color: panel.borderColor
                                                                border.width: 1
                                                            }
                                                            Label {
                                                                Layout.fillWidth: true
                                                                text: qsTr("Cor…")
                                                                color: panel.textColor
                                                                horizontalAlignment: Text.AlignHCenter
                                                                verticalAlignment: Text.AlignVCenter
                                                            }
                                                        }
                                                    }
                                                    AuthRangeSpinBox {
                                                        id: effectNumberEditor
                                                        visible: paramRow.specification.kind === "number"
                                                        objectName: "effectParam_" + effectRow.index + "_" + paramRow.modelData
                                                        Accessible.name: effectRow.modelData.type + " " + paramRow.modelData
                                                        Accessible.description: qsTr("Permitido de %1 a %2; passo %3")
                                                            .arg(paramRow.specification.minimum)
                                                            .arg(paramRow.specification.maximum)
                                                            .arg(paramRow.specification.step)
                                                        rangeMinimum: Number(paramRow.specification.minimum)
                                                        rangeMaximum: Number(paramRow.specification.maximum)
                                                        rangeStep: Number(paramRow.specification.step)
                                                        rangeDecimals: Number(paramRow.specification.decimals || 2)
                                                        declaredValue: Number(effectRow.modelData[paramRow.modelData])
                                                        fieldName: paramRow.modelData
                                                        requestedImplicitWidth: 116
                                                        onValueCommitted: function(nextValue) {
                                                            panel.editEffect("set", {
                                                                index: effectRow.index,
                                                                param: paramRow.modelData,
                                                                value: nextValue
                                                            })
                                                        }
                                                    }
                                                    Label {
                                                        visible: paramRow.specification.kind === "number"
                                                        text: qsTr("%1–%2")
                                                            .arg(paramRow.specification.minimum)
                                                            .arg(paramRow.specification.maximum)
                                                        color: panel.mutedColor
                                                        font.pixelSize: Math.round(10 * panel.visualScale)
                                                        Accessible.name: qsTr("Intervalo permitido") + " " + text
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            Label {
                                objectName: "authoringNotice"
                                visible: panel.authoringNotice !== ""
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: panel.authoringNotice
                                color: panel.amberColor
                                font.pixelSize: Math.round(12 * panel.visualScale)
                            }
                        }
                    }

                    Rectangle {
                        objectName: "motionInspector"
                        visible: panel.editorSessionId !== "" && !panel.editorReadOnly
                        color: panel.surfaceColor
                        radius: 8
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.maximumWidth: tokenScroll.availableWidth
                        implicitHeight: visible ? motionColumn.implicitHeight + 24 : 0
                        border.color: panel.borderColor
                        border.width: 1

                        ColumnLayout {
                            id: motionColumn
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8
                            Label {
                                text: qsTr("Movimento — keyframes de estado e timelines")
                                color: panel.mutedColor
                                font.pixelSize: Math.round(11 * panel.visualScale)
                            }
                            Flow {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: motionColumn.width
                                Layout.maximumWidth: motionColumn.width
                                Layout.preferredHeight: childrenRect.height
                                spacing: 8
                                AuthCombo {
                                    id: motionStateCombo
                                    objectName: "motionStateName"
                                    requestedImplicitHeight: 40
                                    Accessible.name: qsTr("Estado do keyframe")
                                    model: panel.motionStateOptions
                                    currentIndex: model.indexOf(panel.motionStateName)
                                    onActivated: panel.motionStateName = currentText
                                }
                                Repeater {
                                    model: ["opacity", "scale", "translateX", "translateY"]
                                    delegate: Row {
                                        id: keyframeRow
                                        required property string modelData
                                        spacing: 4
                                        Label {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: keyframeRow.modelData
                                            color: panel.mutedColor
                                            font.pixelSize: Math.round(11 * panel.visualScale)
                                        }
                                        AuthRangeSpinBox {
                                            objectName: "keyframe_" + keyframeRow.modelData
                                            Accessible.name: qsTr("Keyframe") + " " + panel.motionStateName + " " + keyframeRow.modelData
                                            readonly property var specification:
                                                panel.motionKeyframeSpec(keyframeRow.modelData)
                                            rangeMinimum: Number(specification.minimum)
                                            rangeMaximum: Number(specification.maximum)
                                            rangeStep: Number(specification.step)
                                            rangeDecimals: Number(specification.decimals || 2)
                                            fieldName: keyframeRow.modelData
                                            requestedImplicitWidth: 84
                                            declaredValue: Number(panel.keyframeText(
                                                panel.motionStateName, keyframeRow.modelData))
                                            onValueCommitted: function(nextValue) {
                                                panel.editMotion("set_state", panel.motionStateName,
                                                    {field: keyframeRow.modelData, value: nextValue})
                                            }
                                        }
                                    }
                                }
                            }
                            Flow {
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: motionColumn.width
                                Layout.maximumWidth: motionColumn.width
                                Layout.preferredHeight: childrenRect.height
                                spacing: 8
                                Repeater {
                                    id: timelineRepeater
                                    objectName: "motionTimelineList"
                                    model: Object.keys((panel.editorDeclared.sceneMotion || {}).timelines || {})
                                    delegate: AuthButton {
                                        id: timelineButton
                                        required property string modelData
                                        objectName: "motionTimeline_" + modelData
                                        text: modelData
                                        requestedImplicitHeight: 40
                                        checkable: true
                                        checked: panel.motionTimelineName === modelData
                                        Accessible.name: qsTr("Selecionar timeline") + " " + modelData
                                        onClicked: panel.motionTimelineName = modelData
                                    }
                                }
                                AuthField {
                                    id: timelineNameField
                                    objectName: "motionTimelineName"
                                    Accessible.name: qsTr("Nome da nova timeline")
                                    placeholderText: qsTr("nome da timeline")
                                    requestedImplicitWidth: 140
                                    requestedImplicitHeight: 40
                                }
                                AuthCombo {
                                    id: timelineKindCombo
                                    objectName: "motionTimelineKind"
                                    requestedImplicitHeight: 40
                                    Accessible.name: qsTr("Tipo de timeline")
                                    model: panel.editorMotionSchema.timelineKinds || ["sequence", "parallel"]
                                    currentIndex: {
                                        const timelines = ((panel.editorDeclared.sceneMotion || {}).timelines || ({}))
                                        const existing = timelines[panel.motionTimelineName]
                                        return model.indexOf(existing
                                            ? existing.kind : panel.motionNewTimelineKind)
                                    }
                                    onActivated: {
                                        const timelines = ((panel.editorDeclared.sceneMotion || {}).timelines || ({}))
                                        if (timelines[panel.motionTimelineName])
                                            panel.editMotion("set_timeline", panel.motionTimelineName,
                                                {field: "kind", value: currentText})
                                        else
                                            panel.motionNewTimelineKind = currentText
                                    }
                                }
                                AuthButton {
                                    objectName: "motionTimelineAdd"
                                    text: qsTr("Criar timeline")
                                    requestedImplicitHeight: 40
                                    onClicked: {
                                        panel.motionTimelineName = timelineNameField.text
                                        panel.editMotion("add_timeline", timelineNameField.text, {value: timelineKindCombo.currentText})
                                    }
                                }
                                AuthButton {
                                    objectName: "motionClipAdd"
                                    text: qsTr("Adicionar clip")
                                    requestedImplicitHeight: 40
                                    onClicked: panel.editMotion("add_clip", panel.motionTimelineName, {value: {state: panel.motionStateName, duration: 240}})
                                }
                                AuthRangeSpinBox {
                                    objectName: "motionTimelineRepeat"
                                    Accessible.name: qsTr("Repetições da timeline")
                                    rangeMinimum: Number((panel.editorMotionSchema.repeat || {}).minimum || 0)
                                    rangeMaximum: Number((panel.editorMotionSchema.repeat || {}).maximum || 8)
                                    rangeStep: Number((panel.editorMotionSchema.repeat || {}).step || 1)
                                    rangeDecimals: 0
                                    fieldName: qsTr("Repetições")
                                    requestedImplicitWidth: 64
                                    declaredValue: Number(panel.repeatText(panel.motionTimelineName))
                                    onValueCommitted: function(nextValue) {
                                        panel.editMotion("set_timeline", panel.motionTimelineName,
                                            {field: "repeat", value: nextValue})
                                    }
                                }
                                AuthButton {
                                    objectName: "motionTimelineRemove"
                                    text: qsTr("Remover timeline")
                                    requestedImplicitHeight: 40
                                    onClicked: panel.editMotion("remove_timeline", panel.motionTimelineName, ({}))
                                }
                            }
                            Label {
                                objectName: "motionEmpty"
                                visible: motionClipRepeater.count === 0
                                text: qsTr("Sem clips nesta timeline. Escreva um nome, escolha Criar timeline e depois Adicionar clip.")
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                color: panel.mutedColor
                                font.pixelSize: Math.round(11 * panel.visualScale)
                            }
                            Repeater {
                                id: motionClipRepeater
                                objectName: "motionClipRepeater"
                                model: panel.authoringRevision < 0 ? [] : ((((panel.editorDeclared.sceneMotion || {}).timelines || {})[panel.motionTimelineName] || {}).clips || []).slice()
                                delegate: Flow {
                                    id: clipRow
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    Layout.preferredWidth: motionColumn.width
                                    Layout.maximumWidth: motionColumn.width
                                    Layout.preferredHeight: childrenRect.height
                                    spacing: 8
                                    AuthCombo {
                                        visible: clipRow.modelData.state !== undefined
                                        objectName: "motionClipState_" + clipRow.index
                                        Accessible.name: qsTr("Estado do clip") + " " + (clipRow.index + 1)
                                        model: panel.motionStateOptions
                                        currentIndex: model.indexOf(clipRow.modelData.state || "normal")
                                        requestedImplicitWidth: 140
                                        onActivated: panel.editMotion("set_clip", panel.motionTimelineName,
                                            {index: clipRow.index, field: "state", value: currentText})
                                    }
                                    Label {
                                        visible: clipRow.modelData.transition !== undefined
                                        text: clipRow.modelData.transition || ""
                                        color: panel.textColor
                                        font.pixelSize: Math.round(12 * panel.visualScale)
                                    }
                                    AuthRangeSpinBox {
                                        objectName: "motionClipDuration_" + clipRow.index
                                        visible: clipRow.modelData.state !== undefined
                                        Accessible.name: qsTr("Duração do clip") + " " + (clipRow.index + 1)
                                        rangeMinimum: Number((panel.editorMotionSchema.duration || {}).minimum || 0)
                                        rangeMaximum: Number((panel.editorMotionSchema.duration || {}).maximum || 2000)
                                        rangeStep: Number((panel.editorMotionSchema.duration || {}).step || 1)
                                        rangeDecimals: 0
                                        fieldName: qsTr("Duração")
                                        requestedImplicitWidth: 72
                                        declaredValue: Number(clipRow.modelData.duration)
                                        onValueCommitted: function(nextValue) {
                                            panel.editMotion("set_clip", panel.motionTimelineName,
                                                {index: clipRow.index, field: "duration", value: nextValue})
                                        }
                                    }
                                    AuthButton {
                                        objectName: "motionClipUp_" + clipRow.index
                                        text: "↑"
                                        requestedImplicitWidth: 44
                                        enabled: clipRow.index > 0
                                        Accessible.name: qsTr("Mover clip para cima") + " " + (clipRow.index + 1)
                                        onClicked: panel.editMotion("move_clip", panel.motionTimelineName,
                                            {index: clipRow.index, value: clipRow.index - 1})
                                    }
                                    AuthButton {
                                        objectName: "motionClipDown_" + clipRow.index
                                        text: "↓"
                                        requestedImplicitWidth: 44
                                        enabled: clipRow.index < motionClipRepeater.count - 1
                                        Accessible.name: qsTr("Mover clip para baixo") + " " + (clipRow.index + 1)
                                        onClicked: panel.editMotion("move_clip", panel.motionTimelineName,
                                            {index: clipRow.index, value: clipRow.index + 1})
                                    }
                                    AuthButton {
                                        objectName: "motionClipRemove_" + clipRow.index
                                        text: qsTr("Remover")
                                        requestedImplicitHeight: 40
                                        Accessible.name: qsTr("Remover clip") + " " + (clipRow.index + 1)
                                        onClicked: panel.editMotion("remove_clip", panel.motionTimelineName, {index: clipRow.index})
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        objectName: "bindingInspector"
                        visible: panel.editorSessionId !== "" && !panel.editorReadOnly
                        color: panel.surfaceColor
                        radius: 8
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.maximumWidth: tokenScroll.availableWidth
                        implicitHeight: visible ? bindingColumn.implicitHeight + 24 : 0
                        border.color: panel.borderColor
                        border.width: 1

                        ColumnLayout {
                            id: bindingColumn
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8
                            readonly property var layouts: ((panel.editorDeclared.sceneLayouts || {}).layouts) || ({})
                            readonly property var layoutNames: Object.keys(layouts)
                            readonly property var template: (layouts[panel.bindingLayoutName] || {}).template || ({})
                            readonly property var boundProps: {
                                var props = template.properties || {}
                                return Object.keys(props).filter(function(k) {
                                    return typeof props[k] === "object" && props[k] !== null && props[k].binding !== undefined
                                })
                            }
                            onLayoutNamesChanged: {
                                if (layoutNames.length > 0 && layoutNames.indexOf(panel.bindingLayoutName) < 0)
                                    panel.bindingLayoutName = layoutNames[0]
                            }
                            Label {
                                text: qsTr("Bindings de layout — metadados públicos")
                                color: panel.mutedColor
                                font.pixelSize: Math.round(11 * panel.visualScale)
                            }
                            Label {
                                objectName: "bindingEmpty"
                                visible: bindingColumn.layoutNames.length === 0
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: qsTr("Este tema não declara layouts. Crie o tema a partir de um que tenha layouts (por exemplo, a demonstração de receitas) para ligar propriedades a metadados.")
                                color: panel.mutedColor
                                font.pixelSize: Math.round(11 * panel.visualScale)
                            }
                            Flow {
                                visible: bindingColumn.layoutNames.length > 0
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: bindingColumn.width
                                Layout.maximumWidth: bindingColumn.width
                                Layout.preferredHeight: childrenRect.height
                                spacing: 8
                                AuthCombo {
                                    objectName: "bindingLayout"
                                    requestedImplicitHeight: 40
                                    Accessible.name: qsTr("Layout")
                                    model: bindingColumn.layoutNames
                                    currentIndex: bindingColumn.layoutNames.indexOf(panel.bindingLayoutName)
                                    onActivated: panel.bindingLayoutName = currentText
                                }
                                AuthCombo {
                                    id: bindingPropCombo
                                    objectName: "bindingProp"
                                    requestedImplicitHeight: 40
                                    Accessible.name: qsTr("Propriedade")
                                    model: bindingColumn.boundProps
                                    onModelChanged: if (count > 0 && panel.bindingPropName === "") panel.bindingPropName = textAt(0)
                                    onActivated: panel.bindingPropName = currentText
                                    onCountChanged: if (count > 0 && bindingColumn.boundProps.indexOf(panel.bindingPropName) < 0) panel.bindingPropName = textAt(0)
                                }
                                AuthCombo {
                                    id: bindingFieldCombo
                                    objectName: "bindingField"
                                    requestedImplicitHeight: 40
                                    Accessible.name: qsTr("Metadado")
                                    model: ["title", "year", "developer", "publisher", "genre", "description", "rating", "players", "region", "language", "series"]
                                }
                                AuthField {
                                    id: bindingFallbackField
                                    objectName: "bindingFallback"
                                    requestedImplicitHeight: 40
                                    requestedImplicitWidth: 140
                                    placeholderText: qsTr("valor se ausente")
                                    Accessible.name: qsTr("Valor alternativo")
                                }
                                AuthButton {
                                    objectName: "bindingApply"
                                    requestedImplicitHeight: 40
                                    text: qsTr("Ligar")
                                    Accessible.name: qsTr("Ligar propriedade ao metadado")
                                    onClicked: panel.editBinding("item." + bindingFieldCombo.currentText, bindingFallbackField.text)
                                }
                                AuthButton {
                                    objectName: "bindingClear"
                                    requestedImplicitHeight: 40
                                    text: qsTr("Remover binding")
                                    Accessible.name: qsTr("Remover binding e usar valor fixo")
                                    onClicked: panel.editBinding(null, bindingFallbackField.text)
                                }
                            }
                            Repeater {
                                model: panel.authoringRevision < 0 ? [] : bindingColumn.boundProps
                                delegate: Label {
                                    required property string modelData
                                    objectName: "bindingCurrent_" + modelData
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                    text: modelData + " ← " + bindingColumn.template.properties[modelData].binding
                                    color: panel.textColor
                                    font.pixelSize: Math.round(12 * panel.visualScale)
                                }
                            }
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
                        font.pixelSize: Math.round(12 * panel.visualScale)
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
                                font.pixelSize: Math.round(18 * panel.visualScale)
                                font.weight: Font.Bold
                            }

                            Label {
                                text: qsTr("Esta é uma amostra de como o tema ficará na interface.")
                                color: panel._previewBridge.textMuted
                                font.pixelSize: Math.round(13 * panel.visualScale)
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
                                        font.pixelSize: Math.round(13 * panel.visualScale)
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
                                        font.pixelSize: Math.round(13 * panel.visualScale)
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
                                        font.pixelSize: Math.round(13 * panel.visualScale)
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
                                        font.pixelSize: Math.round(13 * panel.visualScale)
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
                                        font.pixelSize: Math.round(12 * panel.visualScale)
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        text: qsTr("muted")
                                        color: panel._previewBridge.textMuted
                                        font.pixelSize: Math.round(11 * panel.visualScale)
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
                            font.pixelSize: Math.round(12 * panel.visualScale)
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
                                    font.pixelSize: Math.round(14 * panel.visualScale)
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
                                    Layout.minimumHeight: panel.minimumInteractiveTarget
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
                                font.pixelSize: Math.round(11 * panel.visualScale)
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
                            font.pixelSize: Math.round(11 * panel.visualScale)
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
                            visualScale: panel.visualScale
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
                            font.pixelSize: Math.round(11 * panel.visualScale)
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
                            font.pixelSize: Math.round(11 * panel.visualScale)
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
                            font.pixelSize: Math.round(11 * panel.visualScale)
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
                            visualScale: panel.visualScale
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
                            font.pixelSize: Math.round(11 * panel.visualScale)
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
                            visualScale: panel.visualScale
                            readOnly: panel.editorReadOnly
                            onLayoutEditRequested: function(layoutId, field, value) {
                                panel.editorDirty = true
                                panel.requestAction("theme.editor.set-layout", {
                                    sessionId: panel.editorSessionId,
                                    layoutId: layoutId,
                                    field: field,
                                    value: value
                                }, function(r) {
                                    if (r.history)
                                        panel.editorHistory = r.history
                                    if (r.preview) {
                                        panel.editorPreviewObject = r.preview
                                        panel.editorTokens = r.preview.resolved || {}
                                    }
                                })
                            }
                            // A mesma cena resolvida que a interface desenha:
                            // o canvas do Studio não recebe uma versão própria.
                            scene: panel._previewBridge.sceneLayoutPreview
                            inspectorTextColor: panel.textColor
                            inspectorMutedColor: panel.mutedColor
                            inspectorSuccessColor: panel.greenColor
                            inspectorWarningColor: panel.amberColor
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
                                font.pixelSize: Math.round(11 * panel.visualScale)
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
                                font.pixelSize: Math.round(13 * panel.visualScale)
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

    ThemedDialog {
        id: exportPreviewDialog
        surfaceColor: panel.surfaceColor
        raisedColor: panel.raisedColor
        borderColor: panel.borderColor
        textColor: panel.textColor
        mutedColor: panel.mutedColor
        accentColor: panel.cyanColor
        visualScale: panel.visualScale
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
                    ? qsTr("Arquivo: %1\nTamanho: %2\nGarantia: %3")
                        .arg(panel.exportPlan.filename || "tema.zip")
                        .arg(Sizes.bytes(panel.exportPlan.size))
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
                    Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
                    onClicked: {
                        panel.exportPlan = null
                        exportPreviewDialog.close()
                    }
                }
                Button {
                    text: qsTr("Confirmar exportação")
                    enabled: panel.exportPlan !== null
                    Layout.fillWidth: true
                    Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
                    onClicked: panel.confirmExport()
                }
            }
        }
    }

    // =====================================================================
    // APPLY THEME CONFIRMATION
    // =====================================================================
    ThemedDialog {
        id: applyDialog
        surfaceColor: panel.surfaceColor
        raisedColor: panel.raisedColor
        borderColor: panel.borderColor
        textColor: panel.textColor
        mutedColor: panel.mutedColor
        accentColor: panel.cyanColor
        visualScale: panel.visualScale
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
                font.pixelSize: Math.round(12 * panel.visualScale)
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
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
                    id: applyConfirmButton
                    objectName: "themeApplyConfirm"
                    text: qsTr("Confirmar aplicação")
                    enabled: panel.applyPlan !== null
                        && panel.applyPlan.planId
                        && panel.applyPlan.confirmToken
                    Layout.fillWidth: true
                    Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
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
    ThemedDialog {
        id: createDialog
        surfaceColor: panel.surfaceColor
        raisedColor: panel.raisedColor
        borderColor: panel.borderColor
        textColor: panel.textColor
        mutedColor: panel.mutedColor
        accentColor: panel.cyanColor
        visualScale: panel.visualScale
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
                font.pixelSize: Math.round(12 * panel.visualScale)
            }
            TextField {
                id: createNameField
                placeholderText: qsTr("Meu Tema Personalizado")
                Layout.fillWidth: true
                Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
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
                    Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
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
                    Layout.minimumHeight: Math.max(panel.minimumInteractiveTarget, 44)
                    Layout.preferredWidth: 120
                    onClicked: {
                        panel.requestAction("theme.editor.create",
                            {name: createNameField.text.trim()},
                            function(r) {
                                panel._openEditor(r.sessionId, r.manifest, r.preview, r.declared,
                                                  r.effectSchema, r.motionSchema)
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
                    font.pixelSize: Math.round(14 * panel.visualScale)
                    font.weight: Font.Medium
                    Layout.fillWidth: true
                }
                Label {
                    text: "%1 tokens".arg(catSection.tokenCount)
                    color: catSection.mutedColor
                    font.pixelSize: Math.round(11 * panel.visualScale)
                }
                Label {
                    text: catSection._expanded ? "▾" : "▸"
                    color: catSection.mutedColor
                    font.pixelSize: Math.round(14 * panel.visualScale)
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
                        font.pixelSize: Math.round(9 * panel.visualScale)
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
                                cyanDarkColor: panel.cyanDarkColor,
                                visualScale: panel.visualScale
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
                Layout.minimumHeight: panel.minimumInteractiveTarget

                Label {
                    text: {
                        var label = modelData
                        return label.charAt(0).toUpperCase() + label.slice(1)
                    }
                    color: catSection.textColor
                    font.pixelSize: Math.round(12 * panel.visualScale)
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                AuthRangeSpinBox {
                    enabled: !catSection.readOnly
                    Accessible.name: modelData
                    rangeMinimum: 0
                    rangeMaximum: 120
                    rangeStep: 1
                    rangeDecimals: 0
                    fieldName: modelData
                    requestedImplicitWidth: 90
                    declaredValue: catSection.tokens[modelData] !== undefined
                        ? Number(catSection.tokens[modelData]) : 0
                    onValueCommitted: function(nextValue) {
                        var vals = {}
                        vals[modelData] = nextValue
                        catSection.tokenChanged(vals)
                    }
                }
                Label {
                    text: "px"
                    color: catSection.mutedColor
                    font.pixelSize: Math.round(11 * panel.visualScale)
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
                Layout.minimumHeight: panel.minimumInteractiveTarget

                Label {
                    text: {
                        var label = modelData
                        return label.charAt(0).toUpperCase() + label.slice(1)
                    }
                    color: catSection.textColor
                    font.pixelSize: Math.round(12 * panel.visualScale)
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                Loader {
                    Layout.preferredWidth: 120
                    Layout.minimumHeight: panel.minimumInteractiveTarget
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

    component TypoScaleEditorComp: AuthRangeSpinBox {
        enabled: !catSection.readOnly
        Accessible.name: qsTr("Escala tipográfica")
        rangeMinimum: 0.5
        rangeMaximum: 2
        rangeStep: 0.01
        rangeDecimals: 2
        fieldName: qsTr("Escala tipográfica")
        requestedImplicitWidth: 90
        declaredValue: catSection.tokens.scale !== undefined
            ? Number(catSection.tokens.scale) : 1
        onValueCommitted: function(nextValue) {
            var vals = {}
            vals.scale = nextValue
            catSection.tokenChanged(vals)
        }
        Label {
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: "%"
            color: catSection.mutedColor
            font.pixelSize: Math.round(11 * panel.visualScale)
        }
    }

    // Controles do editor (chrome do Studio): usam as cores do PAINEL, nunca as do tema
    // em edição — senão a interface do editor mudaria de aparência com o tema editado.
    component AuthField: TextField {
        id: authField
        property int requestedImplicitWidth: 0
        property int requestedImplicitHeight: 0
        // `declaredText` é o valor aceito pelo documento. Enter e perda de foco disparam
        // editingFinished; `committed` evita enviar a mesma edição duas vezes, e uma edição
        // recusada (authoringRevision) devolve o campo ao valor declarado.
        property string declaredText: ""
        property string committed: declaredText
        text: declaredText
        onDeclaredTextChanged: { text = declaredText; committed = declaredText }
        Connections {
            target: panel
            function onAuthoringRevisionChanged() { text = declaredText; committed = declaredText }
        }
        function submit(send) {
            if (text === committed)
                return
            committed = text
            send(text)
        }
        implicitWidth: Math.max(panel.minimumInteractiveTarget, requestedImplicitWidth,
            authField.contentItem
                ? authField.contentItem.implicitWidth + leftPadding + rightPadding : 0)
        implicitHeight: Math.max(panel.minimumInteractiveTarget, requestedImplicitHeight,
            authField.contentItem
                ? authField.contentItem.implicitHeight + topPadding + bottomPadding : 0)
        Layout.minimumWidth: panel.minimumInteractiveTarget
        Layout.minimumHeight: panel.minimumInteractiveTarget
        color: panel.textColor
        placeholderTextColor: panel.mutedColor
        selectedTextColor: "#071019"
        selectionColor: panel.cyanColor
        leftPadding: 10
        rightPadding: 10
        background: Rectangle {
            color: panel.surfaceColor
            radius: 8
            border.color: parent.activeFocus ? panel.cyanColor : panel.borderColor
            border.width: parent.activeFocus ? 2 : 1
        }
    }

    component AuthButton: Button {
        id: authButton
        property int requestedImplicitWidth: 0
        property int requestedImplicitHeight: 0
        implicitWidth: Math.max(panel.minimumInteractiveTarget, requestedImplicitWidth,
            authButton.contentItem
                ? authButton.contentItem.implicitWidth + leftPadding + rightPadding : 0)
        implicitHeight: Math.max(panel.minimumInteractiveTarget, requestedImplicitHeight,
            authButton.contentItem
                ? authButton.contentItem.implicitHeight + topPadding + bottomPadding : 0)
        Layout.minimumWidth: panel.minimumInteractiveTarget
        Layout.minimumHeight: panel.minimumInteractiveTarget
        leftPadding: 12
        rightPadding: 12
        Accessible.name: text
        background: Rectangle {
            color: !authButton.enabled ? panel.surfaceColor
                : (authButton.checked ? panel.cyanDarkColor : panel.raisedColor)
            radius: 8
            border.color: authButton.activeFocus ? panel.textColor
                : (authButton.checked ? panel.cyanColor : panel.borderColor)
            border.width: authButton.activeFocus ? 2 : 1
        }
        contentItem: Label {
            text: authButton.text
            color: authButton.enabled ? panel.textColor : panel.mutedColor
            font.pixelSize: Math.round(13 * panel.visualScale)
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    component AuthCombo: SteamComboBox {
        id: authCombo
        property int requestedImplicitWidth: 0
        property int requestedImplicitHeight: 0
        implicitWidth: Math.max(panel.minimumInteractiveTarget, requestedImplicitWidth,
            authCombo.contentItem
                ? authCombo.contentItem.implicitWidth + leftPadding + rightPadding : 0)
        implicitHeight: Math.max(panel.minimumInteractiveTarget, requestedImplicitHeight,
            authCombo.contentItem
                ? authCombo.contentItem.implicitHeight + topPadding + bottomPadding : 0)
        Layout.minimumWidth: panel.minimumInteractiveTarget
        Layout.minimumHeight: panel.minimumInteractiveTarget
        surfaceColor: panel.surfaceColor
        raisedColor: panel.raisedColor
        borderColor: panel.borderColor
        textColor: panel.textColor
        mutedColor: panel.mutedColor
        accentColor: panel.cyanColor
    }

    component AuthRangeSpinBox: SpinBox {
        id: rangeSpin
        property int requestedImplicitWidth: 0
        property int requestedImplicitHeight: 0
        property real rangeMinimum: 0
        property real rangeMaximum: 100
        property real rangeStep: 1
        property int rangeDecimals: 2
        property real declaredValue: 0
        property string fieldName: qsTr("Valor")
        readonly property real precisionFactor: Math.pow(10, rangeDecimals)
        signal valueCommitted(real value)

        from: Math.ceil(rangeMinimum * precisionFactor - 0.000001)
        to: Math.floor(rangeMaximum * precisionFactor + 0.000001)
        value: Math.max(from, Math.min(to, Math.round(Number(declaredValue) * precisionFactor)))
        stepSize: Math.max(1, Math.round(rangeStep * precisionFactor))
        editable: true
        inputMethodHints: Qt.ImhFormattedNumbersOnly
        implicitWidth: Math.max(
            panel.minimumInteractiveTarget + leftPadding + rightPadding,
            requestedImplicitWidth + 2 * panel.minimumInteractiveTarget,
            rangeSpin.contentItem
                ? rangeSpin.contentItem.implicitWidth + leftPadding + rightPadding : 0)
        implicitHeight: Math.max(panel.minimumInteractiveTarget, requestedImplicitHeight,
            rangeSpin.contentItem
                ? rangeSpin.contentItem.implicitHeight + topPadding + bottomPadding : 0)
        Layout.minimumWidth: panel.minimumInteractiveTarget
        Layout.minimumHeight: panel.minimumInteractiveTarget
        leftPadding: 8 + panel.minimumInteractiveTarget
        rightPadding: 8 + panel.minimumInteractiveTarget
        Accessible.description: qsTr("Permitido de %1 a %2; passo %3")
            .arg(rangeMinimum).arg(rangeMaximum).arg(rangeStep)

        up.indicator: Rectangle {
            objectName: rangeSpin.objectName + "_incrementTarget"
            Accessible.name: qsTr("Incrementar %1").arg(rangeSpin.fieldName)
            Accessible.role: Accessible.Button
            x: rangeSpin.mirrored ? 0 : rangeSpin.width - width
            y: 0
            implicitWidth: panel.minimumInteractiveTarget
            implicitHeight: panel.minimumInteractiveTarget
            width: implicitWidth
            height: rangeSpin.height
            color: rangeSpin.up.pressed ? panel.cyanDarkColor : panel.raisedColor
            border.color: rangeSpin.activeFocus ? panel.cyanColor : panel.borderColor
            radius: 4
            Rectangle {
                anchors.centerIn: parent
                width: Math.max(14, parent.width / 3)
                height: 2
                color: rangeSpin.up.enabled ? panel.textColor : panel.mutedColor
            }
            Rectangle {
                anchors.centerIn: parent
                width: 2
                height: Math.max(14, parent.width / 3)
                color: rangeSpin.up.enabled ? panel.textColor : panel.mutedColor
            }
        }

        down.indicator: Rectangle {
            objectName: rangeSpin.objectName + "_decrementTarget"
            Accessible.name: qsTr("Diminuir %1").arg(rangeSpin.fieldName)
            Accessible.role: Accessible.Button
            x: rangeSpin.mirrored ? rangeSpin.width - width : 0
            y: 0
            implicitWidth: panel.minimumInteractiveTarget
            implicitHeight: panel.minimumInteractiveTarget
            width: implicitWidth
            height: rangeSpin.height
            color: rangeSpin.down.pressed ? panel.cyanDarkColor : panel.raisedColor
            border.color: rangeSpin.activeFocus ? panel.cyanColor : panel.borderColor
            radius: 4
            Rectangle {
                anchors.centerIn: parent
                width: Math.max(14, parent.width / 3)
                height: 2
                color: rangeSpin.down.enabled ? panel.textColor : panel.mutedColor
            }
        }

        validator: DoubleValidator {
            bottom: -1000000
            top: 1000000
            decimals: rangeSpin.rangeDecimals
            locale: rangeSpin.locale.name
        }
        textFromValue: function(raw, locale) {
            return panel.formatEffectNumber(raw / rangeSpin.precisionFactor,
                locale, rangeSpin.rangeDecimals)
        }
        valueFromText: function(text, locale) {
            const parsed = Number.fromLocaleString(locale, text)
            if (!Number.isFinite(parsed) || parsed < rangeSpin.rangeMinimum
                    || parsed > rangeSpin.rangeMaximum
                    || (rangeSpin.rangeDecimals === 0 && !Number.isInteger(parsed))) {
                panel.rejectEditorNumber(rangeSpin.fieldName,
                    rangeSpin.rangeMinimum, rangeSpin.rangeMaximum)
                return rangeSpin.value
            }
            return Math.round(parsed * rangeSpin.precisionFactor)
        }
        onValueModified: valueCommitted(value / precisionFactor)

        background: Rectangle {
            color: panel.surfaceColor
            radius: 8
            border.color: rangeSpin.activeFocus ? panel.cyanColor : panel.borderColor
            border.width: rangeSpin.activeFocus ? 2 : 1
        }
        contentItem: TextInput {
            text: rangeSpin.displayText
            font: rangeSpin.font
            color: panel.textColor
            selectionColor: panel.cyanColor
            selectedTextColor: panel.backgroundColor
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            readOnly: !rangeSpin.editable
            validator: rangeSpin.validator
            inputMethodHints: rangeSpin.inputMethodHints
            selectByMouse: true
        }
    }

    component TypoFamilyEditorComp: TextField {
        text: catSection.tokens.family || ""
        placeholderText: qsTr("Fonte (ex: Noto Sans)")
        enabled: !catSection.readOnly
        implicitHeight: panel.minimumInteractiveTarget
        Layout.minimumHeight: panel.minimumInteractiveTarget
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
        implicitHeight: panel.minimumInteractiveTarget
        Layout.minimumHeight: panel.minimumInteractiveTarget
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
                Layout.minimumHeight: panel.minimumInteractiveTarget

                Label {
                    text: {
                        var label = modelData
                        return label.charAt(0).toUpperCase() + label.slice(1)
                    }
                    color: catSection.textColor
                    font.pixelSize: Math.round(12 * panel.visualScale)
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                AuthRangeSpinBox {
                    enabled: !catSection.readOnly
                    Accessible.name: modelData
                    rangeMinimum: 0
                    rangeMaximum: 2000
                    rangeStep: 1
                    rangeDecimals: 0
                    fieldName: modelData
                    requestedImplicitWidth: 90
                    declaredValue: catSection.tokens[modelData] !== undefined
                        ? Number(catSection.tokens[modelData]) : 0
                    onValueCommitted: function(nextValue) {
                        var vals = {}
                        vals[modelData] = nextValue
                        catSection.tokenChanged(vals)
                    }
                }
                Label {
                    text: modelData.indexOf("Duration") >= 0 || modelData.indexOf("duration") >= 0 ? "ms" : ""
                    color: catSection.mutedColor
                    font.pixelSize: Math.round(11 * panel.visualScale)
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
            id: effectPicker
            onClosed: {
                if (panel.effectColorDialogControl === effectPicker)
                    panel.effectColorDialogControl = null
                destroy()
            }
        }
    }
}
