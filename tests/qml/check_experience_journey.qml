// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 640
    height: 720
    property var actionCalls: []
    property var actionHistory: []
    property string lastAction: ""
    property var lastPayload: ({})
    property int closeCount: 0
    property bool acceptPreviewActions: false
    property bool failEnginePreview: false
    property bool delayEnginePreview: false
    property var delayedEnginePreviewSuccess: null

    ExperienceJourneyPanel {
        id: journey
        objectName: "journeyPanel"
        anchors.fill: parent
        compactLayout: true
        requestAction: function(actionId, payload, success, failure) {
            harness.actionCalls = harness.actionCalls.concat([String(actionId)])
            harness.actionHistory = harness.actionHistory.concat([{
                actionId: String(actionId), payload: payload || ({})
            }])
            harness.lastAction = String(actionId)
            harness.lastPayload = payload || ({})
            if (harness.acceptPreviewActions) {
                if (actionId === "journey.studio.engine-preview") {
                    if (harness.failEnginePreview) {
                        failure({detail: "Theme Engine indisponível para esta sessão"})
                    } else if (harness.delayEnginePreview) {
                        harness.delayedEnginePreviewSuccess = success
                    } else {
                        success({
                            journeyGeneration: payload.expectedGeneration,
                            query: {
                                menuId: payload.menuId,
                                resultState: "results",
                                sourceState: "available",
                                totalCount: 1,
                                resultCount: 1,
                                returnedCount: 1,
                                rows: [{id: "journey-game", title: "Jogo da jornada", genre: "Ação"}],
                                unknownValueCounts: {},
                                diagnosticMessage: "",
                                recoveryAction: ""
                            },
                            themeId: "org.steamzero.default",
                            manifest: {id: "org.steamzero.default", assets: {}},
                            declared: {sceneLayouts: {layouts: {libraryGrid: {}}}},
                            preview: {
                                themeId: "org.steamzero.default",
                                themeVersion: "1.0.0",
                                highContrast: false,
                                reducedMotion: false,
                                resolved: {
                                    color: {background: "#071019", surface: "#0d1924",
                                        surfaceSelected: "#122131", accent: "#13bdf2",
                                        border: "#2a3a49", text: "#f2f6fb",
                                        textMuted: "#9eabba"},
                                    geometry: {}, typography: {}, motion: {},
                                    interaction: {}, stateVariants: {}, performance: {}
                                },
                                studioGraph: {
                                    nodes: [{id: "layout.libraryGrid", kind: "layout",
                                        label: "Biblioteca", depth: 0,
                                        properties: {previewKey: "libraryGrid"}}],
                                    budget: {withinBudget: true}
                                },
                                sceneLayoutPreview: {layouts: {
                                    libraryGrid: {entries: [{id: "preview-title", kind: "text",
                                        x: 8, y: 8, width: 120, height: 32,
                                        text: "Jogo da jornada", visible: true,
                                        opacity: 1.0, color: "#f2f6fb",
                                        fontFamily: "Sans Serif", fontPixelSize: 16,
                                        fontWeight: 400, fontItalic: false,
                                        horizontalAlignment: "AlignLeft",
                                        verticalAlignment: "AlignVCenter", wrapMode: "NoWrap",
                                        maximumLineCount: 1, elide: "ElideNone",
                                        fontSizeMode: "FixedSize", minimumPixelSize: 0,
                                        textFormat: "PlainText"}]}
                                }}
                            }
                        })
                    }
                } else if (actionId === "journey.studio.coverage") {
                    success({
                        stages: [{
                            stageId: "menu:platforms",
                            appearance: "inherited",
                            sourceThemeId: "org.steamzero.default",
                            sourceVersion: "1.1.0",
                            reason: "not-customized",
                            providedSceneElements: [],
                            missingSceneElements: []
                        }],
                        summary: {label: "Tema misto · AURA padrão"}
                    })
                }
                return true
            }
            return false
        }
        onCloseRequested: ++harness.closeCount
    }

    TestCase {
        name: "ExperienceJourneyPanel"
        when: windowShown

        function find(root, name) {
            if (!root)
                return null
            if (root.objectName === name)
                return root
            const objects = root.children !== undefined ? root.children : []
            for (let i = 0; i < objects.length; ++i) {
                const hit = find(objects[i], name)
                if (hit)
                    return hit
            }
            return null
        }

        function cleanup() {
            harness.acceptPreviewActions = false
            harness.failEnginePreview = false
            harness.delayEnginePreview = false
            harness.delayedEnginePreviewSuccess = null
        }

        function usePublishedFixture() {
            journey.session = {
                sessionId: "component-test-session",
                generation: 3,
                document: {
                    schemaVersion: 2,
                    kind: "steamzero-experience-journey-v2",
                    id: "org.steamzero.component-test",
                    name: "Teste de componente",
                    entryMenuId: "platforms",
                    organization: [
                        {id: "node-platforms", kind: "menu", label: "Plataformas",
                            parentId: null, menuId: "platforms"},
                        {id: "node-games", kind: "menu", label: "Jogos",
                            parentId: "node-platforms", menuId: "games"}
                    ],
                    menus: [
                        {id: "platforms", name: "Plataformas",
                            source: {readModelId: "library.platforms"}, filters: [], sort: [], groupBy: []},
                        {id: "games", name: "Jogos",
                            source: {readModelId: "library.games"}, filters: [], sort: [], groupBy: []}
                    ],
                    connections: [{
                        id: "platforms-games", label: "Plataformas para jogos",
                        from: {kind: "menu", id: "platforms"}, event: "select",
                        when: "user-input", action: "navigate",
                        to: {kind: "menu", id: "games"}, bindings: []
                    }],
                    sessionStages: []
                },
                history: {canUndo: false, canRedo: false},
                budgets: {maxMenus: 4096}
            }
            journey.catalog = {
                readModels: [
                    {id: "library.platforms", name: "Plataformas", fields: [
                        {id: "id", name: "Identificador", type: "string"}
                    ]},
                    {id: "library.games", name: "Jogos", fields: [
                        {id: "platformId", name: "Plataforma", type: "string"},
                        {id: "genre", name: "Gênero", type: "string"},
                        {id: "year", name: "Ano", type: "integer"}
                    ]}
                ],
                themes: []
            }
            journey.selectedMenuId = "platforms"
            journey.selectedTab = "menus"
            journey.compactPane = "tree"
            journey.bridgeAvailable = true
            journey.busy = false
            journey.notice = ""
        }

        function revealInScroll(item, flickable) {
            for (let attempt = 0; attempt < 3; ++attempt) {
                const point = item.mapToItem(flickable, 0, 0)
                if (point.y < 0)
                    flickable.contentY = Math.max(0, flickable.contentY + point.y)
                else if (point.y + item.height > flickable.height)
                    flickable.contentY = Math.min(flickable.contentHeight - flickable.height,
                        flickable.contentY + point.y + item.height - flickable.height)
                wait(40)
            }
            const point = item.mapToItem(flickable, 0, 0)
            return point.y >= 0 && point.y + item.height <= flickable.height
        }

        function test_bridge_absence_is_visible_and_writes_are_disabled() {
            tryVerify(function() { return harness.actionCalls.length > 0 })
            compare(harness.actionCalls[0], "journey.studio.list")
            compare(journey.bridgeAvailable, false)
            verify(journey.notice !== "")
            const createButton = find(journey, "journeyCreate")
            verify(createButton !== null)
            compare(createButton.enabled, false)
        }

        function test_import_dependency_summary_distinguishes_missing_and_unpinned_themes() {
            const available = journey.dependencyDescription({
                themeId: "org.example.theme", state: "available-unpinned",
                installedVersion: "2.3.1"
            })
            verify(available.indexOf("versão do pacote não fixada") >= 0, available)
            verify(available.indexOf("2.3.1") >= 0, available)
            const missing = journey.dependencyDescription({
                themeId: "org.example.absent", state: "missing"
            })
            verify(missing.indexOf("tema ausente") >= 0, missing)
            verify(missing.indexOf("AURA") >= 0, missing)
        }

        function test_public_field_labels_accept_the_catalog_contract_and_keep_controls_visible() {
            usePublishedFixture()
            compare(journey.publicFieldName({id: "genre", label: "Gênero principal"}),
                    "Gênero principal")
            compare(journey.publicFieldName({id: "year", name: "Ano de lançamento"}),
                    "Ano de lançamento")
            journey.catalog.themes = [{
                id: "org.steamzero.default", name: "AURA", version: "2.0.0"
            }]
            journey.selectedThemeId = "org.steamzero.default"
            journey.compactPane = "inspector"
            journey.selectedTab = "menus"
            const themePicker = find(journey, "journeyMenuThemePicker")
            const applyTheme = find(journey, "journeyApplyMenuTheme")
            verify(themePicker && applyTheme)
            verify(applyTheme.height >= journey.minimumInteractiveTarget)
            verify(applyTheme.x + applyTheme.width <= applyTheme.parent.width + 0.5,
                   "CTA Aplicar ao menu precisa caber ao lado do seletor em compacto")
        }

        function test_preview_sends_public_query_to_the_theme_engine() {
            usePublishedFixture()
            journey.compactPane = "inspector"
            harness.acceptPreviewActions = true
            harness.actionHistory = []
            const button = find(journey, "journeyPreviewButton")
            verify(button !== null)
            mouseClick(button)

            compare(journey.previewResult.menuId, "platforms")
            compare(journey.previewResult.rows[0].title, "Jogo da jornada")
            compare(journey.themePreviewThemeId, "org.steamzero.default")
            compare(journey.themePreviewMode, "native")
            compare(journey.themePreviewLoading, false)
            verify(find(journey, "journeyNativeThemePreview") !== null)
            verify(find(journey, "journeyNativeThemePreview").visible)
            const ids = harness.actionHistory.map(function(item) { return item.actionId })
            compare(ids.slice(-2), [
                "journey.studio.engine-preview",
                "journey.studio.coverage"
            ])
            compare(harness.actionHistory[ids.length - 2].payload.menuId, "platforms")
            compare(harness.actionHistory[ids.length - 2].payload.expectedGeneration, 3)
            harness.acceptPreviewActions = false
        }

        function test_late_engine_preview_is_ignored_after_menu_selection_changes() {
            usePublishedFixture()
            journey.compactPane = "inspector"
            harness.acceptPreviewActions = true
            harness.delayEnginePreview = true
            harness.delayedEnginePreviewSuccess = null
            const button = find(journey, "journeyPreviewButton")
            verify(button !== null)
            mouseClick(button)
            verify(typeof harness.delayedEnginePreviewSuccess === "function",
                "a resolução do Engine precisa permanecer pendente")
            verify(journey.themePreviewLoading)

            journey.selectMenu("games")
            compare(journey.themePreviewLoading, false)
            harness.delayedEnginePreviewSuccess({})

            compare(journey.selectedMenuId, "games")
            compare(journey.previewResult, null)
            compare(journey.themePreviewObject, null)
            compare(journey.themePreviewThemeId, "")
            compare(harness.lastAction, "journey.studio.engine-preview")
            harness.acceptPreviewActions = false
            harness.delayEnginePreview = false
        }

        function test_engine_preview_failure_is_visible_and_retries() {
            usePublishedFixture()
            journey.compactPane = "inspector"
            harness.acceptPreviewActions = true
            harness.failEnginePreview = true
            const button = find(journey, "journeyPreviewButton")
            verify(button !== null)
            mouseClick(button)

            compare(journey.themePreviewLoading, false)
            compare(journey.themePreviewError,
                    "Theme Engine indisponível para esta sessão")
            verify(find(journey, "journeyThemePreviewError").visible)
            compare(journey.previewResult, null)

            harness.failEnginePreview = false
            mouseClick(button)
            verify(journey.previewResult !== null)
            compare(journey.themePreviewError, "")
            compare(journey.themePreviewLoading, false)
            harness.acceptPreviewActions = false
        }

        function test_compact_toolbar_wraps_and_targets_remain_large() {
            usePublishedFixture()
            const childMenu = find(journey, "journeyMenu_games")
            verify(childMenu !== null)
            verify(childMenu.height >= 48)
            verify(childMenu.x > 0, "menu aninhado não exibe sua hierarquia")
            const showInspector = find(journey, "journeyShowInspector")
            verify(showInspector !== null)
            verify(showInspector.height >= 48)
            mouseClick(showInspector)
            compare(journey.compactPane, "inspector")

            const toolbar = find(journey, "journeyToolbar")
            verify(toolbar !== null)
            verify(toolbar.visible)
            const names = ["journeyUndo", "journeyRedo", "journeySave",
                "journeyExport", "journeyImport"]
            for (let i = 0; i < names.length; ++i) {
                const button = find(journey, names[i])
                verify(button !== null, names[i] + " missing")
                verify(button.height >= 48, names[i] + " is shorter than 48 px")
                verify(button.x + button.width <= toolbar.width + 0.5,
                    names[i] + " extends beyond the compact toolbar")
            }
            const showTree = find(journey, "journeyShowTree")
            verify(showTree !== null)
            mouseClick(showTree)
            compare(journey.compactPane, "tree")
        }

        function test_filter_forms_reject_empty_invalid_and_type_values() {
            usePublishedFixture()
            journey.selectedMenuId = "games"
            journey.compactPane = "inspector"
            const field = find(journey, "journeyFilterField")
            const operator = find(journey, "journeyFilterOperator")
            const value = find(journey, "journeyFilterValue")
            const add = find(journey, "journeyFilterAdd")
            verify(field && operator && value && add)
            const scroller = find(journey, "journeyInspectorScroll")
            verify(scroller !== null)
            const flickable = scroller.contentItem
            verify(flickable && flickable.contentY !== undefined,
                "inspetor precisa expor a área rolável dos controles")
            verify(revealInScroll(add, flickable), "botão de filtro fora da viewport")
            field.currentIndex = 2
            operator.currentIndex = 1
            journey.filterField = "year"
            journey.filterOperator = "oneOf"
            value.text = ""
            const beforeEmptyFilter = harness.lastAction
            mouseClick(add)
            verify(journey.notice.indexOf("oneOf") >= 0,
                "click sem validar: notice=" + journey.notice + " field="
                    + journey.filterField + " operator=" + journey.filterOperator
                    + " enabled=" + add.enabled + " visible=" + add.visible)
            compare(harness.lastAction, beforeEmptyFilter)

            operator.currentIndex = 3
            journey.filterOperator = "greaterThanOrEqual"
            value.text = "not-a-number"
            const beforeInvalidNumber = harness.lastAction
            mouseClick(add)
            verify(journey.notice.length > 0)
            compare(harness.lastAction, beforeInvalidNumber)

            operator.currentIndex = 1
            journey.filterOperator = "oneOf"
            value.text = "1992, 1994"
            mouseClick(add)
            compare(harness.lastAction, "journey.studio.transact")
            compare(harness.lastPayload.operation, "set-filters")
            compare(harness.lastPayload.payload.values[0].operator, "oneOf")
            compare(harness.lastPayload.payload.values[0].value[0], 1992)
            compare(harness.lastPayload.payload.values[0].value[1], 1994)
        }

        function test_referenced_menu_requires_visible_replacement() {
            usePublishedFixture()
            journey.selectedMenuId = "games"
            const showTree = find(journey, "journeyShowTree")
            verify(showTree !== null)
            mouseClick(showTree)
            const removeButton = find(journey, "journeyRemoveMenu")
            verify(removeButton !== null)
            verify(removeButton.height >= 48)
            mouseClick(removeButton)

            const dialog = journey.deleteMenuDialogControl
            tryVerify(function() { return dialog.visible })
            const impact = journey.deleteImpactControl
            verify(impact !== null)
            verify(impact.text.indexOf("Plataformas para jogos") >= 0)
            verify(journey.menuHasReferences("games"))
            const confirm = journey.deleteMenuConfirmControl
            const replacement = journey.replacementMenuControl
            verify(confirm !== null)
            verify(replacement !== null)
            verify(!confirm.enabled, "exclusão referenciada deve exigir substituição")
            verify(confirm.height >= 48)
            replacement.currentIndex = 0
            journey.pendingReplacementMenuId = replacement.model[0].id
            verify(confirm.enabled)
            mouseClick(confirm)
            tryVerify(function() { return harness.lastAction === "journey.studio.transact" })
            compare(harness.lastPayload.operation, "remove-menu")
            compare(harness.lastPayload.payload.replacementMenuId, "platforms")
            compare(journey.session.document.menus.length, 2,
                "bridge indisponível não deve mutar o rascunho local")
        }

        function test_close_returns_to_existing_studio_route() {
            usePublishedFixture()
            const closeButton = find(journey, "journeyClose")
            verify(closeButton !== null)
            verify(closeButton.height >= 48)
            mouseClick(closeButton)
            compare(harness.closeCount, 1)
        }

        function test_coverage_request_includes_menus_and_used_session_stages() {
            usePublishedFixture()
            const document = JSON.parse(JSON.stringify(journey.session.document))
            document.sessionStages = [{stageId: "pause",
                appearance: {mode: "inherit-aura"}}]
            document.connections = document.connections.concat([{
                id: "games-to-gameplay", label: "Jogar",
                from: {kind: "menu", id: "games"}, event: "play",
                when: "user-input", action: "launch",
                to: {kind: "stage", id: "gameplay"}, bindings: []
            }])
            journey.session = Object.assign({}, journey.session, {document: document})
            journey.inspectCoverage()
            compare(harness.lastAction, "journey.studio.coverage")
            compare(harness.lastPayload.sessionId, "component-test-session")
            compare(JSON.stringify(harness.lastPayload.usedStages),
                JSON.stringify(["menu:platforms", "menu:games", "pause", "gameplay"]))
            journey.selectedTab = "stages"
            journey.compactPane = "inspector"
            const notice = find(journey, "journeyImplicitAuraNotice")
            const implicitStages = journey.implicitAuraStageIds()
            verify(implicitStages.length === 3,
                "heranças implícitas: " + JSON.stringify(implicitStages)
                    + " used=" + JSON.stringify(journey.usedCoverageStages()))
            verify(notice !== null, "aviso de herança não foi criado")
            verify(notice.visible, "aviso de herança está oculto: " + notice.text)
            verify(notice.text.indexOf("3") >= 0, notice.text)
            compare(find(journey, "journeyStageAppearance_pause").text,
                "AURA · escolha explícita")
            compare(find(journey, "journeyStageAppearance_gameplay").text,
                "AURA · herança padrão")
        }
    }
}
