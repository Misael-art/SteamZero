// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window

Item {
    id: page

    required property var emulation
    required property color backgroundColor
    required property color sidebarColor
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

    signal actionRequested(var action)
    signal componentActionRequested(var component)
    signal systemRequested()

    property int platformIndex: 0
    property int scopeIndex: 0
    property int areaIndex: 0
    property int emulatorIndex: 0
    property int gameIndex: 0
    property string synchronizedPlatformId: ""
    property var pendingAction: null
    property string pendingPath: ""
    property string gameSearchText: ""
    property string gameSortKey: "name"
    property bool gameSortAscending: true
    property bool gameDetailsOpen: false
    property string selectedGameId: ""
    property string pendingEmulatorGameId: ""
    property string pendingEmulatorId: ""
    property string steamUserId: ""
    readonly property bool compactLayout: width <= 1296 || height <= 720
    readonly property bool ultrawideLayout: width >= 1900
    readonly property int responsiveGutter: compactLayout ? 12 : 22
    readonly property int minimumTouchTarget: 48
    readonly property int contentMaxWidth: ultrawideLayout ? 1400 : 1800
    readonly property bool showAreaSidebar: !isGameLibrary() && !compactLayout
    readonly property bool showContextPanel: isGameLibrary()
        ? gameDetailsOpen && !compactLayout && width >= 900
        : !compactLayout && width >= 1500
    property alias compactPrimaryActionControl: compactPrimaryAction
    property alias libraryListControl: contentScroll
    property alias gameDetailsControl: contextPanel

    readonly property var defaultAreas: [
        {"id": "overview", "label": qsTr("Visão geral"), "icon": "view-dashboard"},
        {"id": "keysFirmware", "label": qsTr("Keys e firmware"), "icon": "document-encrypt"},
        {"id": "updatesDlc", "label": qsTr("Updates e DLC"), "icon": "download"},
        {"id": "modsCheats", "label": qsTr("Mods e cheats"), "icon": "extension"},
        {"id": "graphicsPerformance", "label": qsTr("Gráficos e fluidez"), "icon": "video-display"},
        {"id": "controls", "label": qsTr("Controles"), "icon": "input-gaming"},
        {"id": "saves", "label": qsTr("Saves"), "icon": "document-save"},
        {"id": "shaderCache", "label": qsTr("Shader cache"), "icon": "applications-graphics"},
        {"id": "media", "label": qsTr("Mídia"), "icon": "image-x-generic"},
        {"id": "storage", "label": qsTr("Armazenamento"), "icon": "drive-harddisk"},
        {"id": "advanced", "label": qsTr("Avançado"), "icon": "configure"}
    ]
    readonly property var defaultScopes: [
        {"id": "global", "label": qsTr("Global"), "icon": "globe"},
        {"id": "emulator", "label": qsTr("Emulador"), "icon": "applications-games"},
        {"id": "game", "label": qsTr("Por jogo"), "icon": "media-playback-start"},
        {"id": "handheld", "label": qsTr("Portátil"), "icon": "computer-laptop"},
        {"id": "dock", "label": qsTr("Dock"), "icon": "video-display"}
    ]
    readonly property var platforms: emulation && emulation.platforms
        && emulation.platforms.length > 0 ? emulation.platforms : []
    readonly property var selectedPlatform: platforms.length > 0
        && platformIndex < platforms.length ? platforms[platformIndex] : ({
            "id": "switch",
            "name": qsTr("Nintendo Switch"),
            "shortName": qsTr("Switch"),
            "iconKey": "switch",
            "state": "degraded",
            "statusLabel": qsTr("Aguardando dados da plataforma"),
            "readiness": {
                "percent": 0,
                "title": qsTr("Verificação ainda não disponível"),
                "detail": qsTr("A bridge local ainda não publicou o estado da emulação Switch."),
                "blockers": [qsTr("Backend de emulação ainda não conectado")]
            },
            "emulators": [],
            "games": []
        })
    readonly property var scopes: selectedPlatform.scopes && selectedPlatform.scopes.length > 0
        ? selectedPlatform.scopes : defaultScopes
    readonly property var areas: selectedPlatform.areas && selectedPlatform.areas.length > 0
        ? selectedPlatform.areas : defaultAreas
    readonly property var emulators: selectedPlatform.emulators || []
    readonly property var games: selectedPlatform.games || []
    readonly property var globalSettings: selectedPlatform.globalSettings || ({})
    readonly property var runtimeProfiles: selectedPlatform.runtimeProfiles || ({})
    readonly property int emulatorMaintenanceCount: emulatorMaintenanceRepeater.count
    readonly property var selectedEmulator: emulators.length > 0 && emulatorIndex < emulators.length
        ? emulators[emulatorIndex] : ({
            "id": "", "name": qsTr("Nenhum emulador verificado"), "state": "unsupported",
            "statusLabel": qsTr("Indisponível")
        })
    readonly property var selectedGame: games.length > 0 && gameIndex < games.length
        ? games[gameIndex] : ({
            "id": "", "titleId": "", "name": qsTr("Nenhum jogo detectado"),
            "state": "empty", "statusLabel": qsTr("Biblioteca vazia")
        })
    readonly property var selectedArea: areas.length > 0 && areaIndex < areas.length
        ? areas[areaIndex] : defaultAreas[0]
    readonly property var readiness: selectedPlatform.readiness || ({
        "percent": 0,
        "title": qsTr("Verificando plataforma"),
        "detail": qsTr("Nenhuma mudança será feita durante a verificação."),
        "blockers": []
    })
    readonly property var areaData: {
        const allData = selectedPlatform.areaData || {}
        return allData[selectedArea.id] || {}
    }

    function normalizedIndex(index, rows) {
        return rows.length > 0 ? Math.max(0, Math.min(index, rows.length - 1)) : 0
    }

    function resetContext() {
        scopeIndex = 0
        areaIndex = 0
        emulatorIndex = 0
        gameIndex = 0
    }

    function syncPublishedSelection() {
        const platformId = String(selectedPlatform.id || "")
        if (synchronizedPlatformId !== "" && synchronizedPlatformId === platformId) {
            scopeIndex = normalizedIndex(scopeIndex, scopes)
            areaIndex = normalizedIndex(areaIndex, areas)
            emulatorIndex = normalizedIndex(emulatorIndex, emulators)
            gameIndex = normalizedIndex(gameIndex, games)
            syncGameSelection()
            return
        }
        const scope = selectedPlatform.selectedScope || "global"
        const publishedScope = scopes.findIndex(function(item) { return item.id === scope })
        scopeIndex = publishedScope >= 0 ? publishedScope : 0
        const area = selectedPlatform.selectedArea || "overview"
        const publishedArea = areas.findIndex(function(item) { return item.id === area })
        areaIndex = publishedArea >= 0 ? publishedArea : 0
        emulatorIndex = normalizedIndex(emulatorIndex, emulators)
        gameIndex = normalizedIndex(gameIndex, games)
        synchronizedPlatformId = platformId
        syncGameSelection()
    }

    function syncGameSelection() {
        if (games.length === 0) {
            gameIndex = 0
            selectedGameId = ""
            return
        }
        const published = games.findIndex(function(game) { return game.id === selectedGameId })
        gameIndex = published >= 0 ? published : normalizedIndex(gameIndex, games)
        selectedGameId = String(games[gameIndex].id || "")
        if (pendingEmulatorGameId !== "") {
            const pendingGame = games.find(function(game) {
                return game.id === pendingEmulatorGameId
            })
            if (pendingGame && pendingGame.emulatorId === pendingEmulatorId) {
                pendingEmulatorGameId = ""
                pendingEmulatorId = ""
            }
        }
    }

    function cancelPendingEmulatorSelection() {
        pendingEmulatorGameId = ""
        pendingEmulatorId = ""
    }

    onSelectedPlatformChanged: Qt.callLater(syncPublishedSelection)
    onGamesChanged: Qt.callLater(syncGameSelection)
    Component.onCompleted: syncPublishedSelection()

    function moveVerticalFocus(forward) {
        const hostWindow = page.Window.window
        const active = hostWindow ? hostWindow.activeFocusItem : null
        const next = active ? active.nextItemInFocusChain(forward) : null
        if (next) {
            next.forceActiveFocus(Qt.TabFocusReason)
            Qt.callLater(function() { page.revealFocusedItem(next) })
        }
    }

    function revealInScroll(scroll, item) {
        if (!scroll || !scroll.contentItem || !item)
            return false
        const flickable = scroll.contentItem
        const point = item.mapToItem(flickable.contentItem, 0, 0)
        if (point.y < 0 || point.y > flickable.contentHeight)
            return false
        const top = point.y - 12
        const bottom = point.y + item.height + 12
        if (top < flickable.contentY)
            flickable.contentY = Math.max(0, top)
        else if (bottom > flickable.contentY + flickable.height)
            flickable.contentY = Math.min(
                Math.max(0, flickable.contentHeight - flickable.height),
                bottom - flickable.height
            )
        return true
    }

    function revealFocusedItem(item) {
        if (page.isGameLibrary() && page.gameDetailsOpen
                && page.revealInScroll(gamePanelScroll, item))
            return
        page.revealInScroll(contentScroll, item)
    }

    Keys.onUpPressed: function(event) {
        page.moveVerticalFocus(false)
        event.accepted = true
    }
    Keys.onDownPressed: function(event) {
        page.moveVerticalFocus(true)
        event.accepted = true
    }

    function stateColor(state) {
        if (["ready", "installed", "available", "healthy", "compatible", "active"]
                .indexOf(state) >= 0)
            return greenColor
        if (["attention", "degraded", "missing", "blocked", "stale", "incompatible", "unavailable"]
                .indexOf(state) >= 0)
            return amberColor
        if (["failed", "error", "corrupt"].indexOf(state) >= 0)
            return redColor
        return mutedColor
    }

    function stateIcon(state) {
        if (["ready", "installed", "available", "healthy", "compatible", "active"]
                .indexOf(state) >= 0)
            return "dialog-ok-apply"
        if (["attention", "degraded", "missing", "blocked", "stale", "incompatible", "unavailable"]
                .indexOf(state) >= 0)
            return "dialog-warning"
        if (["failed", "error", "corrupt"].indexOf(state) >= 0)
            return "dialog-error"
        return "dialog-information"
    }

    function visualIcon(key) {
        const icons = {
            "dashboard": "view-dashboard",
            "key": "document-encrypt",
            "emulator": "applications-games",
            "gamepad": "input-gaming",
            "handheld": "computer-laptop",
            "dock": "video-display",
            "save": "document-save",
            "sparkles": "applications-graphics",
            "image": "image-x-generic",
            "storage": "drive-harddisk",
            "tune": "configure"
        }
        return icons[key] || key || "dialog-information"
    }

    function cardMetric(card) {
        if (card.metric !== undefined && card.metric !== null)
            return String(card.metric)
        if (card.count !== undefined && card.count !== null)
            return String(card.count)
        if (card.installed !== undefined && card.installed !== null)
            return String(card.installed)
        if (card.required !== undefined && card.required !== null)
            return String(card.required)
        return "—"
    }

    function readinessPercent() {
        const value = Number(readiness.percent || 0)
        return isNaN(value) ? 0 : Math.max(0, Math.min(100, Math.round(value)))
    }

    function scopeId() {
        return scopes.length > 0 && scopeIndex < scopes.length ? scopes[scopeIndex].id : "global"
    }

    function isGlobalOverview() {
        return scopeId() === "global" && selectedArea.id === "overview"
    }

    function isEmulatorOverview() {
        return scopeId() === "emulator" && selectedArea.id === "overview"
    }

    function isGameLibrary() {
        return scopeId() === "game" && selectedArea.id === "overview"
    }

    function selectScope(index) {
        scopeIndex = normalizedIndex(index, scopes)
        if (scopeId() === "game" || scopeId() === "emulator")
            areaIndex = areaIndexById("overview")
        if (scopeId() === "game")
            gameDetailsOpen = true
    }

    function filteredGames() {
        const query = gameSearchText.trim().toLocaleLowerCase()
        const rows = games.filter(function(game) {
            if (query === "")
                return true
            return String(game.name || "").toLocaleLowerCase().indexOf(query) >= 0
                || String(game.titleId || "").toLocaleLowerCase().indexOf(query) >= 0
        })
        rows.sort(function(left, right) {
            let leftValue
            let rightValue
            if (gameSortKey === "size") {
                leftValue = Number(left.size || 0)
                rightValue = Number(right.size || 0)
            } else {
                leftValue = String(left[gameSortKey] || "").toLocaleLowerCase()
                rightValue = String(right[gameSortKey] || "").toLocaleLowerCase()
            }
            let comparison = 0
            if (leftValue < rightValue)
                comparison = -1
            else if (leftValue > rightValue)
                comparison = 1
            if (comparison === 0)
                comparison = String(left.name || "").localeCompare(String(right.name || ""))
            return gameSortAscending ? comparison : -comparison
        })
        return rows
    }

    function setGameSort(key) {
        if (gameSortKey === key)
            gameSortAscending = !gameSortAscending
        else {
            gameSortKey = key
            gameSortAscending = true
        }
    }

    function selectGame(game) {
        if (!game)
            return
        const index = games.findIndex(function(candidate) {
            return candidate.id === game.id && candidate.path === game.path
        })
        if (index >= 0)
            gameIndex = index
        selectedGameId = String(game.id || "")
        gameDetailsOpen = true
    }

    function formatBytes(value) {
        const bytes = Number(value || 0)
        if (!isFinite(bytes) || bytes <= 0)
            return qsTr("Tamanho não publicado")
        const gib = bytes / (1024 * 1024 * 1024)
        if (gib >= 1)
            return qsTr("%1 GB").arg(gib.toFixed(gib >= 10 ? 1 : 2))
        const mib = bytes / (1024 * 1024)
        return qsTr("%1 MB").arg(mib.toFixed(mib >= 10 ? 0 : 1))
    }

    function compatibilityState(game, emulatorId) {
        const compatibility = game && game.compatibility ? game.compatibility : {}
        const value = compatibility[emulatorId]
        return value && value.state ? String(value.state) : String(value || "unknown")
    }

    function compatibilityLabel(state) {
        const labels = {
            "perfect": qsTr("Perfeito"), "compatible": qsTr("Perfeito"),
            "playable": qsTr("Jogável"), "broken": qsTr("Quebrado"),
            "failed": qsTr("Quebrado"), "unknown": qsTr("Não avaliado")
        }
        return labels[state] || qsTr("Não avaliado")
    }

    function compatibilityColor(state) {
        if (state === "perfect" || state === "compatible")
            return greenColor
        if (state === "playable")
            return amberColor
        if (state === "broken" || state === "failed")
            return redColor
        return mutedColor
    }

    function gameFeatures(game) {
        return [
            {"icon": "document-save", "label": game.saveState || qsTr("Save —")},
            {"icon": "extension", "label": game.modsCount !== undefined
                ? qsTr("Mods %1").arg(game.modsCount) : qsTr("Mods —")},
            {"icon": "package-x-generic", "label": game.dlcCount !== undefined
                ? qsTr("DLC %1").arg(game.dlcCount) : qsTr("DLC —")},
            {"icon": "system-software-update", "label": game.updateVersion
                ? qsTr("Update %1").arg(game.updateVersion) : qsTr("Update —")},
            {"icon": "applications-graphics", "label": game.shaderCount !== undefined
                ? qsTr("Shaders %1").arg(game.shaderCount) : qsTr("Shaders —")}
        ]
    }

    function gameEmulatorIndex(game) {
        if (!game)
            return -1
        const emulatorId = pendingEmulatorGameId === game.id
            ? pendingEmulatorId : game.emulatorId
        if (!emulatorId)
            return -1
        return emulators.findIndex(function(emulator) { return emulator.id === emulatorId })
    }

    function gamePlayAction(game) {
        if (game && pendingEmulatorGameId === game.id) {
            return {
                "id": "game.play.pending-emulator",
                "label": qsTr("Confirmar emulador"),
                "enabled": false,
                "reason": qsTr("Aplique ou cancele a troca de emulador antes de jogar.")
            }
        }
        if (game && game.playAction)
            return game.playAction
        return {
            "id": "game.play.unavailable", "label": qsTr("Jogar"), "enabled": false,
            "reason": qsTr("O serviço ainda não publicou um plano de lançamento para este jogo.")
        }
    }

    function steamSelectedCount() {
        return games.filter(function(game) { return game.steamSelected === true }).length
    }

    function steamPublishedCount() {
        return games.filter(function(game) { return game.steamPublished === true }).length
    }

    function coverCount() {
        return games.filter(function(game) {
            return Boolean(game.coverUrl || game.bannerAsset)
        }).length
    }

    function openGameArea(areaId) {
        areaIndex = areaIndexById(areaId)
    }

    function areaDataById(id) {
        const allData = selectedPlatform.areaData || {}
        return allData[id] || {}
    }

    function areaCard(areaId, cardId) {
        const data = areaDataById(areaId)
        const publishedCards = data.cards || []
        for (let index = 0; index < publishedCards.length; index += 1) {
            if (publishedCards[index].id === cardId)
                return publishedCards[index]
        }
        return null
    }

    function installedEmulatorCount() {
        return emulators.filter(function(emulator) {
            return emulator.installState === "installed"
                || emulator.state === "installed" || emulator.state === "ready"
        }).length
    }

    function contextTitle() {
        if (scopeId() === "emulator")
            return selectedEmulator.name
        if (scopeId() === "game")
            return selectedGame.name
        if (scopeId() === "handheld")
            return qsTr("Modo portátil")
        if (scopeId() === "dock")
            return qsTr("Modo dock")
        return selectedPlatform.name
    }

    function scopedRuntimeProfile() {
        if (scopeId() !== "handheld" && scopeId() !== "dock")
            return null
        return runtimeProfiles[scopeId()] || null
    }

    function inheritedValue(field, suffix) {
        const profile = scopedRuntimeProfile()
        const value = profile && profile[field] ? profile[field].value : null
        return value === null || value === undefined
            ? qsTr("herdado (%1)").arg(suffix) : String(value)
    }

    function areaTitle(id) {
        if (id === "overview" && scopeId() === "global")
            return qsTr("Painel da plataforma")
        if (id === "overview" && scopeId() === "emulator")
            return qsTr("Gerenciar emulador")
        const titles = {
            "overview": qsTr("Prontidão da plataforma"),
            "keysFirmware": qsTr("Keys, firmware e compatibilidade"),
            "updatesDlc": qsTr("Updates e conteúdo adicional"),
            "modsCheats": qsTr("Mods e cheats por jogo"),
            "graphicsPerformance": qsTr("Gráficos, fluidez e perfis"),
            "controls": qsTr("Controles e mudança de modo"),
            "saves": qsTr("Saves e migração"),
            "shaderCache": qsTr("Shader cache e anti-stutter"),
            "media": qsTr("Capas, nomes e metadados"),
            "storage": qsTr("Armazenamento compartilhado"),
            "advanced": qsTr("Ferramentas avançadas")
        }
        return titles[id] || selectedArea.label || qsTr("Emulação")
    }

    function areaDescription(id) {
        if (id === "overview" && scopeId() === "global")
            return qsTr("Diagnóstico dos requisitos globais para abrir jogos com segurança.")
        if (id === "overview" && scopeId() === "emulator")
            return qsTr("Instale, abra, atualize ou remova o emulador selecionado.")
        const descriptions = {
            "overview": qsTr("Veja o que já está pronto e a ordem segura para começar a jogar."),
            "keysFirmware": qsTr("Importe arquivos próprios e antecipe incompatibilidades antes de abrir um jogo."),
            "updatesDlc": qsTr("Acompanhe a versão ativa de cada jogo e escolha updates ou DLC sem perder o original."),
            "modsCheats": qsTr("Importe, ative e remova conteúdo local vinculado ao Title ID e ao emulador escolhido."),
            "graphicsPerformance": qsTr("Aplique perfis conhecidos bons, alternância dock/portátil e geração de quadros quando suportada."),
            "controls": qsTr("Configure até quatro jogadores e adapte o layout automaticamente ao modo de uso."),
            "saves": qsTr("Proteja, restaure e migre progresso entre emuladores com verificação."),
            "shaderCache": qsTr("Reduza engasgos e invalide caches incompatíveis sem apagar o backup válido."),
            "media": qsTr("Gerencie capas, nomes e correspondência por Title ID ou DAT importado pelo usuário."),
            "storage": qsTr("Compartilhe conteúdo compatível e deduplique arquivos entre emuladores."),
            "advanced": qsTr("Converta formatos, inspecione ferramentas e revise operações antes de aplicar.")
        }
        return descriptions[id] || ""
    }

    function defaultCards(id) {
        if (id === "keysFirmware") {
            return [
                {"title": qsTr("Keys de produção"), "icon": "document-encrypt", "state": "unknown", "status": qsTr("Não verificadas"), "detail": qsTr("Importação local, validação de formato e vínculo por versão."), "metric": "—"},
                {"title": qsTr("Firmware instalado"), "icon": "media-flash", "state": "unknown", "status": qsTr("Não verificado"), "detail": qsTr("Versão, origem local e integridade sem expor conteúdo sensível."), "metric": "—"},
                {"title": qsTr("Compatibilidade do jogo"), "icon": "dialog-ok-apply", "state": "unknown", "status": qsTr("Selecione um jogo"), "detail": qsTr("Cruza Title ID com as versões mínimas de keys e firmware."), "metric": qsTr("Pré-execução")}
            ]
        }
        if (id === "updatesDlc") {
            return [
                {"title": qsTr("Update ativo"), "icon": "system-software-update", "state": "unknown", "status": qsTr("Nenhum jogo selecionado"), "detail": qsTr("Instale, alterne e reverta patches fornecidos pelo usuário."), "metric": "—"},
                {"title": qsTr("Conteúdo adicional"), "icon": "package-x-generic", "state": "unknown", "status": qsTr("Nenhum DLC catalogado"), "detail": qsTr("Ativação por título com inventário e origem auditável."), "metric": "0"},
                {"title": qsTr("Versão efetiva"), "icon": "view-refresh", "state": "unknown", "status": qsTr("Aguardando leitura"), "detail": qsTr("Compara jogo base, update escolhido e conteúdo habilitado."), "metric": "—"}
            ]
        }
        if (id === "modsCheats") {
            return [
                {"title": qsTr("Mods locais"), "icon": "extension", "state": "unknown", "status": qsTr("Nenhum mod inventariado"), "detail": qsTr("Pastas e ZIPs são validados e instalados no emulador deste jogo."), "metric": "0"},
                {"title": qsTr("Cheats Atmosphere"), "icon": "applications-development", "state": "unknown", "status": qsTr("Nenhum cheat inventariado"), "detail": qsTr("O nome do arquivo deve ser o Build ID para impedir associação ao jogo errado."), "metric": "0"}
            ]
        }
        if (id === "graphicsPerformance") {
            return [
                {"title": qsTr("Perfil conhecido bom"), "icon": "favorite", "state": "unknown", "status": qsTr("Sem recomendação local"), "detail": qsTr("Ajustes por Title ID, versionados e reversíveis."), "metric": qsTr("Por jogo")},
                {"title": qsTr("Dock ↔ portátil"), "icon": "video-display", "state": "unknown", "status": qsTr("Automação não verificada"), "detail": qsTr("Resolução, escala e modo interno acompanham a conexão física."), "metric": qsTr("Automático")},
                {"title": qsTr("LSFG-VK"), "icon": "speedometer", "state": "unknown", "status": qsTr("Capacidade não verificada"), "detail": qsTr("30→60 FPS somente em hardware e jogo compatíveis, com opt-out."), "metric": "30→60"}
            ]
        }
        if (id === "controls") {
            return [
                {"title": qsTr("Jogadores detectados"), "icon": "input-gaming", "state": "unknown", "status": qsTr("Aguardando controles"), "detail": qsTr("Mapeamento automático e override por jogo para até quatro jogadores."), "metric": "0 / 4"},
                {"title": qsTr("Modo do console"), "icon": "computer-laptop", "state": "unknown", "status": qsTr("Não observado"), "detail": qsTr("Alterna handheld/dock sem substituir preferências explícitas."), "metric": qsTr("Auto")},
                {"title": qsTr("Perfil por emulador"), "icon": "preferences-desktop-peripherals", "state": "unknown", "status": qsTr("Nenhum perfil ativo"), "detail": qsTr("Mostra especialidades e limites do emulador escolhido."), "metric": "—"}
            ]
        }
        if (id === "saves") {
            return [
                {"title": qsTr("Backup mais recente"), "icon": "document-save", "state": "unknown", "status": qsTr("Nenhum backup verificado"), "detail": qsTr("Snapshot por conteúdo antes de qualquer migração."), "metric": "—"},
                {"title": qsTr("Migração entre emuladores"), "icon": "folder-sync", "state": "unknown", "status": qsTr("Origem e destino pendentes"), "detail": qsTr("Converte layout quando necessário e valida o resultado antes da troca."), "metric": qsTr("Reversível")},
                {"title": qsTr("Integridade"), "icon": "security-high", "state": "unknown", "status": qsTr("Não verificada"), "detail": qsTr("O save original permanece disponível até a confirmação."), "metric": "—"}
            ]
        }
        if (id === "shaderCache") {
            return [
                {"title": qsTr("Cache do jogo"), "icon": "applications-graphics", "state": "unknown", "status": qsTr("Nenhum jogo selecionado"), "detail": qsTr("Tamanho, driver e versão do emulador associados ao cache."), "metric": "—"},
                {"title": qsTr("Backup e restauração"), "icon": "edit-undo", "state": "unknown", "status": qsTr("Sem ponto de restauração"), "detail": qsTr("Mantém uma cópia válida antes de limpar ou migrar."), "metric": qsTr("Seguro")},
                {"title": qsTr("Compatibilidade do cache"), "icon": "dialog-warning", "state": "unknown", "status": qsTr("Aguardando driver"), "detail": qsTr("Alerta quando mudança de driver ou emulador exige invalidação."), "metric": "—"}
            ]
        }
        if (id === "media") {
            return [
                {"title": qsTr("Identificação"), "icon": "edit-find", "state": "unknown", "status": qsTr("Nenhum título analisado"), "detail": qsTr("Title ID, hash e DAT local ajudam a evitar correspondência errada."), "metric": "—"},
                {"title": qsTr("Capas e metadados"), "icon": "image-x-generic", "state": "unknown", "status": qsTr("Biblioteca sem mídia"), "detail": qsTr("Preview antes de substituir imagem, título ou descrição."), "metric": "0"},
                {"title": qsTr("Provedores"), "icon": "network-server", "state": "unknown", "status": qsTr("Chaves de API"), "detail": qsTr("Configure provedores de scraping como SteamGridDB para buscar mídia automaticamente."), "metric": qsTr("Configurar"), "actions": [{"id": "open-credential-dialog", "label": qsTr("Abrir configuração"), "enabled": true}]},
                {"title": qsTr("Renomeação"), "icon": "edit-rename", "state": "unknown", "status": qsTr("Nenhuma mudança planejada"), "detail": qsTr("Detecta colisões e preserva o caminho original para rollback."), "metric": qsTr("Com preview")}
            ]
        }
        if (id === "storage") {
            return [
                {"title": qsTr("Conteúdo compartilhado"), "icon": "folder-publicshare", "state": "unknown", "status": qsTr("Não indexado"), "detail": qsTr("Keys, firmware, DLC, mods e caches permanecem vinculados à origem."), "metric": "—"},
                {"title": qsTr("Deduplicação"), "icon": "edit-copy", "state": "unknown", "status": qsTr("Nenhum ganho calculado"), "detail": qsTr("Compartilha apenas formatos comprovadamente compatíveis."), "metric": "0 B"},
                {"title": qsTr("Isolamento"), "icon": "security-medium", "state": "unknown", "status": qsTr("Aguardando verificação"), "detail": qsTr("Dados incompatíveis continuam separados por emulador."), "metric": qsTr("Por capacidade")}
            ]
        }
        if (id === "advanced") {
            return [
                {"title": qsTr("Conversão NSZ"), "icon": "document-export", "state": "unknown", "status": qsTr("Ferramenta não verificada"), "detail": qsTr("Conversão local com manifest de ferramenta, espaço pré-checado e rollback."), "metric": "NSZ"},
                {"title": qsTr("DAT local"), "icon": "view-list-details", "state": "unknown", "status": qsTr("Nenhum DAT importado"), "detail": qsTr("Banco fornecido pelo usuário; nenhum conteúdo é redistribuído."), "metric": "0"},
                {"title": qsTr("Operações recentes"), "icon": "view-history", "state": "unknown", "status": qsTr("Nenhuma operação"), "detail": qsTr("Planos, confirmações, verificações e rollbacks auditáveis."), "metric": "0"}
            ]
        }
        return [
            {"title": qsTr("Keys e firmware"), "icon": "document-encrypt", "state": "unknown", "status": qsTr("Aguardando verificação"), "detail": qsTr("Compatibilidade é conferida antes do lançamento."), "metric": "—", "targetArea": "keysFirmware"},
            {"title": qsTr("Emuladores"), "icon": "applications-games", "state": emulators.length > 0 ? "ready" : "missing", "status": emulators.length > 0 ? qsTr("%1 detectado(s)").arg(emulators.length) : qsTr("Nenhum verificado"), "detail": qsTr("Eden, Citron e Ryubing podem expor capacidades diferentes."), "metric": String(emulators.length)},
            {"title": qsTr("Biblioteca"), "icon": "folder-games", "state": games.length > 0 ? "ready" : "empty", "status": games.length > 0 ? qsTr("%1 jogo(s)").arg(games.length) : qsTr("Nenhum jogo detectado"), "detail": qsTr("Title ID orienta firmware, update, saves e perfil."), "metric": String(games.length)},
            {"title": qsTr("Modo atual"), "icon": "computer-laptop", "state": "unknown", "status": selectedPlatform.modeLabel || qsTr("Não observado"), "detail": qsTr("Perfis portátil e dock preservam overrides por jogo."), "metric": selectedPlatform.modeShortLabel || "—"}
        ]
    }

    function cards() {
        if (isGlobalOverview())
            return overviewCards()
        if (selectedArea.id === "modsCheats" && scopeId() === "game")
            return gameExtraCards()
        if (areaData.cards && areaData.cards.length > 0)
            return areaData.cards
        return defaultCards(selectedArea.id)
    }

    function gameExtraCards() {
        const result = []
        const published = areaData.cards || []
        for (let i = 0; i < published.length; ++i)
            result.push(published[i])
        const mods = selectedGame.mods || []
        for (let m = 0; m < mods.length; ++m) {
            const mod = mods[m]
            result.push({
                "id": "installed-mod-" + mod.id,
                "title": mod.name,
                "icon": "extension",
                "state": mod.state === "active" ? "ready" : "attention",
                "statusLabel": mod.state === "active" ? qsTr("Ativo") : qsTr("Inativo"),
                "detail": qsTr("%1 • versão %2 • %3 • %4")
                    .arg(mod.emulatorId || qsTr("emulador não definido"))
                    .arg(mod.version || qsTr("não informada"))
                    .arg(mod.priority === null || mod.priority === undefined
                        ? qsTr("prioridade não suportada") : qsTr("prioridade %1").arg(mod.priority))
                    .arg(mod.compatibility && mod.compatibility.reason
                        ? mod.compatibility.reason : qsTr("compatibilidade não publicada")),
                "metric": qsTr("Mod"),
                "actions": [mod.stateAction, mod.removeAction]
            })
        }
        const cheats = selectedGame.cheats || []
        for (let c = 0; c < cheats.length; ++c) {
            const cheat = cheats[c]
            result.push({
                "id": "installed-cheat-" + cheat.id,
                "title": cheat.name,
                "icon": "applications-development",
                "state": cheat.enabled ? "ready" : "attention",
                "statusLabel": cheat.enabled ? qsTr("Ativo") : qsTr("Inativo"),
                "detail": qsTr("Build ID %1 • %2 código(s) • %3")
                    .arg(cheat.buildId || qsTr("não identificado")).arg(cheat.codeCount || 0)
                    .arg(cheat.compatibility && cheat.compatibility.reason
                        ? cheat.compatibility.reason : qsTr("compatibilidade não publicada")),
                "metric": qsTr("Cheat"),
                "actions": [cheat.stateAction, cheat.removeAction]
            })
        }
        return result
    }

    function overviewCards() {
        const publishedKeys = areaCard("keysFirmware", "keys") || ({
            "state": "unknown", "statusLabel": qsTr("Não verificadas"),
            "detail": qsTr("Importe suas keys para validar a plataforma.")
        })
        const publishedFirmware = areaCard("keysFirmware", "firmware") || ({
            "state": "unknown", "statusLabel": qsTr("Não verificado"),
            "detail": qsTr("Importe seu firmware para validar a plataforma.")
        })
        const publishedLibrary = areaCard("overview", "library")
            || areaCard("overview", "games") || ({
                "state": games.length > 0 ? "ready" : "attention",
                "statusLabel": qsTr("%1 jogo(s)").arg(games.length),
                "detail": qsTr("Nenhum diretório monitorado.")
            })
        const overviewData = areaDataById("overview")
        const scanAction = overviewData.primaryAction || ({
            "id": "library.scan", "label": qsTr("Varrer"), "enabled": false,
            "reason": qsTr("A varredura ainda não foi publicada pelo serviço.")
        })
        const installed = installedEmulatorCount()
        const emulatorName = selectedEmulator.id ? selectedEmulator.name
            : qsTr("Nenhum selecionado")
        return [
            {
                "id": "health-keys", "title": qsTr("Keys"),
                "icon": "document-encrypt", "state": publishedKeys.state,
                "statusLabel": publishedKeys.statusLabel || publishedKeys.status,
                "detail": publishedKeys.detail,
                "actions": publishedKeys.action ? [publishedKeys.action] : [{
                    "label": qsTr("Gerenciar Keys"), "targetArea": "keysFirmware",
                    "enabled": true
                }]
            },
            {
                "id": "health-firmware", "title": qsTr("Firmware"),
                "icon": "media-flash", "state": publishedFirmware.state,
                "statusLabel": publishedFirmware.statusLabel || publishedFirmware.status,
                "detail": publishedFirmware.detail,
                "actions": publishedFirmware.action ? [publishedFirmware.action] : [{
                    "label": qsTr("Gerenciar firmware"), "targetArea": "keysFirmware",
                    "enabled": true
                }]
            },
            {
                "id": "health-library", "title": qsTr("Biblioteca e ROMs"),
                "icon": "folder-games", "state": publishedLibrary.state,
                "statusLabel": publishedLibrary.statusLabel || publishedLibrary.status,
                "detail": publishedLibrary.detail,
                "metric": String(games.length),
                "actions": [
                    publishedLibrary.action || ({
                        "label": qsTr("Adicionar pasta"), "targetArea": "media",
                        "enabled": true
                    }),
                    scanAction,
                    {"label": qsTr("Revisar nomes"), "targetArea": "media", "enabled": true}
                ]
            },
            {
                "id": "health-emulator", "title": qsTr("Emulador principal"),
                "icon": "applications-games",
                "state": installed > 0 ? "attention" : "missing",
                "statusLabel": qsTr("Padrão não definido"),
                "detail": qsTr("%1 instalado(s). Em foco: %2. O serviço ainda não publica a preferência usada pelo Play.")
                    .arg(installed).arg(emulatorName),
                "metric": String(installed),
                "actions": [{
                    "label": qsTr("Escolher e gerenciar"), "targetScope": "emulator",
                    "enabled": emulators.length > 0,
                    "reason": emulators.length > 0 ? "" : qsTr("Nenhum emulador foi publicado.")
                }]
            }
        ]
    }

    function cardActions(card) {
        if (card.actions && card.actions.length > 0)
            return card.actions
        if (card.action)
            return [card.action]
        if (card.targetArea)
            return [{"label": qsTr("Abrir área"), "targetArea": card.targetArea, "enabled": true}]
        return []
    }

    function dispatchCardAction(action) {
        if (!action)
            return
        if (action.targetScope) {
            const target = scopes.findIndex(function(scope) { return scope.id === action.targetScope })
            if (target >= 0) {
                scopeIndex = target
                areaIndex = areaIndexById("overview")
            }
            return
        }
        if (action.targetArea) {
            areaIndex = areaIndexById(action.targetArea)
            return
        }
        dispatchAction(action)
    }

    function primaryAction() {
        if (isEmulatorOverview() && selectedEmulator.action)
            return selectedEmulator.action
        if (areaData.primaryAction)
            return areaData.primaryAction
        return {
            "id": "unavailable",
            "label": qsTr("Aguardando backend"),
            "enabled": false,
            "reason": qsTr("A ação será liberada quando a bridge confirmar a capacidade e publicar um plano seguro."),
            "requiresConfirmation": true
        }
    }

    function areaIndexById(id) {
        const index = areas.findIndex(function(area) { return area.id === id })
        return index >= 0 ? index : 0
    }

    function dispatchAction(action) {
        if (!action || action.enabled !== true) {
            page.actionRequested(action)
            return
        }
        pendingAction = action
        if (["content.update.import", "content.dlc.import",
             "content.save.import", "content.shader.import", "mod.import", "cheat.import"].indexOf(action.id) >= 0
                && !(selectedGame.titleId || "")) {
            page.actionRequested({
                "id": action.id,
                "label": action.label,
                "enabled": false,
                "reason": qsTr("Este arquivo foi reconhecido como jogo, mas o Title ID ainda não foi identificado. Renomeie o arquivo ou uma pasta-pai incluindo o Title ID de 16 dígitos e faça uma nova varredura."),
                "requiresConfirmation": true
            })
            pendingAction = null
            return
        }
        if (action.id === "library.root.add") {
            sourceFolderDialog.open()
        } else if (action.id === "keys.import" || action.id === "firmware.import"
                || action.id === "mod.import") {
            sourceChoiceDialog.open()
        } else if (["content.update.import", "content.dlc.import",
                    "content.save.import", "content.shader.import", "nsz.convert",
                    "cheat.import"].indexOf(action.id) >= 0) {
            sourceFileDialog.open()
        } else if (String(action.id).startsWith("game.media.import:")) {
            mediaFileDialog.open()
        } else {
            page.actionRequested(action)
        }
    }

    function submitSelectedSource(version) {
        if (!pendingAction || pendingPath === "")
            return
        const request = {
            "id": pendingAction.id,
            "label": pendingAction.label,
            "enabled": true,
            "reason": null,
            "requiresConfirmation": true,
            "path": pendingPath,
            "titleId": selectedGame.titleId || "",
            "emulatorId": selectedGame.emulatorId || "",
            "gameId": selectedGame.id || ""
        }
        if (version !== undefined && version !== null && String(version).trim() !== "")
            request.version = String(version).trim()
        page.actionRequested(request)
        pendingAction = null
        pendingPath = ""
    }

    function localPath(url) {
        const value = String(url || "")
        if (!value.startsWith("file://"))
            return ""
        return decodeURIComponent(value.replace(/^file:\/\/(?:localhost)?/, ""))
    }

    Dialog {
        id: sourceChoiceDialog
        title: qsTr("Escolher origem local")
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.NoButton
        contentItem: ColumnLayout {
            spacing: 12
            Label {
                text: qsTr("Selecione um arquivo real, um ZIP ou uma pasta. O conteúdo será validado antes da importação.")
                color: page.textColor
                wrapMode: Text.WordWrap
                Layout.preferredWidth: 480
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Arquivo ou ZIP")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onClicked: {
                        sourceChoiceDialog.close()
                        sourceFileDialog.open()
                    }
                }
                Button {
                    text: qsTr("Pasta")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onClicked: {
                        sourceChoiceDialog.close()
                        sourceFolderDialog.open()
                    }
                }
            }
            Button {
                text: qsTr("Cancelar")
                Layout.fillWidth: true
                Layout.minimumHeight: 48
                onClicked: sourceChoiceDialog.close()
            }
        }
    }

    FileDialog {
        id: sourceFileDialog
        title: qsTr("Selecionar conteúdo local")
        fileMode: FileDialog.OpenFile
        nameFilters: pendingAction && pendingAction.id === "keys.import"
            ? [qsTr("Keys e arquivos compactados (*.keys *.zip)"), qsTr("Todos os arquivos (*)")]
            : pendingAction && pendingAction.id === "firmware.import"
                ? [qsTr("Firmware e arquivos compactados (*.nca *.zip)"), qsTr("Todos os arquivos (*)")]
                : pendingAction && pendingAction.id === "mod.import"
                    ? [qsTr("Pacotes de mod (*.zip)"), qsTr("Todos os arquivos (*)")]
                    : pendingAction && pendingAction.id === "cheat.import"
                        ? [qsTr("Cheats Atmosphere (*.txt)"), qsTr("Todos os arquivos (*)")]
                : [qsTr("Conteúdo Switch (*.nsp *.xci *.nsz *.zip)"), qsTr("Todos os arquivos (*)")]
        onAccepted: {
            pendingPath = page.localPath(selectedFile)
            if (pendingAction && (pendingAction.id === "firmware.import"
                    || pendingAction.id === "content.update.import"))
                versionDialog.open()
            else
                submitSelectedSource("")
        }
    }

    FolderDialog {
        id: sourceFolderDialog
        title: qsTr("Selecionar pasta local")
        onAccepted: {
            pendingPath = page.localPath(selectedFolder)
            if (pendingAction && pendingAction.id === "firmware.import")
                versionDialog.open()
            else
                submitSelectedSource("")
        }
    }

    FileDialog {
        id: mediaFileDialog
        title: qsTr("Selecionar imagem para capa")
        fileMode: FileDialog.OpenFile
        nameFilters: [
            qsTr("Imagens (*.jpg *.jpeg *.png *.webp)"),
            qsTr("Todos os arquivos (*)"),
        ]
        onAccepted: {
            const request = {
                "id": pendingAction ? pendingAction.id : "",
                "label": qsTr("Importar mídia personalizada"),
                "enabled": true,
                "requiresConfirmation": true,
                "path": page.localPath(selectedFile),
                "gameId": page.selectedGame.id,
            }
            page.actionRequested(request)
            pendingAction = null
        }
    }

    Dialog {
        id: versionDialog
        title: pendingAction && pendingAction.id === "firmware.import"
            ? qsTr("Versão do firmware") : qsTr("Versão do update")
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.NoButton
        contentItem: ColumnLayout {
            spacing: 12
            Label {
                text: pendingAction && pendingAction.id === "firmware.import"
                    ? qsTr("Informe a versão exibida pela origem do seu firmware, por exemplo 18.1.0.")
                    : qsTr("Informe a versão do update para que ela apareça no inventário.")
                color: page.textColor
                wrapMode: Text.WordWrap
                Layout.preferredWidth: 440
            }
            TextField {
                id: versionField
                placeholderText: qsTr("Ex.: 18.1.0")
                color: page.textColor
                Layout.fillWidth: true
                Accessible.name: qsTr("Versão do conteúdo")
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Cancelar")
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onClicked: versionDialog.close()
                }
                Button {
                    text: qsTr("Continuar")
                    enabled: versionField.text.trim().length > 0
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onClicked: {
                        versionDialog.close()
                        submitSelectedSource(versionField.text)
                        versionField.text = ""
                    }
                }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: page.compactLayout ? 104 : 142
            color: page.backgroundColor

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: page.compactLayout ? 14 : 26
                anchors.rightMargin: page.compactLayout ? 14 : 24
                anchors.topMargin: page.compactLayout ? 10 : 18
                anchors.bottomMargin: page.compactLayout ? 10 : 14
                spacing: page.compactLayout ? 12 : 18

                Rectangle {
                    Layout.preferredWidth: page.compactLayout ? 60 : 84
                    Layout.preferredHeight: page.compactLayout ? 60 : 84
                    radius: page.compactLayout ? 13 : 18
                    color: page.raisedColor
                    border.color: page.selectedPlatform.state === "ready"
                        ? page.greenColor : page.cyanColor
                    border.width: 2

                    SwitchPlatformMark {
                        visible: page.selectedPlatform.iconKey === "switch"
                            || page.selectedPlatform.id === "switch"
                        anchors.centerIn: parent
                        width: page.compactLayout ? 44 : 62
                        height: page.compactLayout ? 44 : 62
                        cutoutColor: page.raisedColor
                    }

                    ModernIcon {
                        visible: page.selectedPlatform.iconKey !== "switch"
                            && page.selectedPlatform.id !== "switch"
                        anchors.centerIn: parent
                        width: page.compactLayout ? 34 : 44
                        height: page.compactLayout ? 34 : 44
                        iconName: page.selectedPlatform.iconKey || "applications-games"
                        iconColor: page.cyanColor
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3

                    Label {
                        text: qsTr("Emulação")
                        color: page.mutedColor
                        font.pixelSize: page.compactLayout ? 10 : 12
                        font.bold: true
                        font.letterSpacing: 1.2
                    }
                    Label {
                        text: page.selectedPlatform.name || qsTr("Plataforma")
                        color: page.textColor
                        font.pixelSize: page.compactLayout ? 23 : 29
                        font.bold: true
                    }
                    Label {
                        visible: !page.compactLayout
                        text: qsTr("Uma central para preparar, jogar e preservar sua biblioteca com segurança.")
                        color: page.mutedColor
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Label {
                        visible: !page.compactLayout
                        text: page.emulation && page.emulation.contextLabel
                            ? page.emulation.contextLabel : qsTr("Dados locais • sem downloads automáticos de conteúdo")
                        color: page.mutedColor
                        font.pixelSize: 11
                    }
                }

                ColumnLayout {
                    spacing: 5
                    Label {
                        text: qsTr("Plataforma")
                        color: page.mutedColor
                        font.pixelSize: 11
                    }
                    SteamComboBox {
                        id: platformPicker
                        model: page.platforms
                        textRole: "name"
                        currentIndex: page.platformIndex
                        enabled: page.platforms.length > 1
                        palette.button: page.raisedColor
                        palette.buttonText: page.textColor
                        palette.base: page.raisedColor
                        palette.text: page.textColor
                        palette.highlight: page.cyanDarkColor
                        palette.highlightedText: page.textColor
                        Layout.preferredWidth: page.compactLayout ? 180 : 220
                        Layout.minimumHeight: page.compactLayout ? 42 : 48
                        Accessible.name: qsTr("Selecionar plataforma de emulação")
                        onActivated: {
                            page.platformIndex = currentIndex
                            page.resetContext()
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: page.compactLayout ? 112 : 150
                    Layout.preferredHeight: page.compactLayout ? 62 : 72
                    radius: 10
                    color: page.readinessPercent() >= 80 ? "#0c2a21" : "#24180b"
                    border.color: page.readinessPercent() >= 80 ? page.greenColor : page.amberColor

                    Column {
                        anchors.centerIn: parent
                        spacing: 2
                        Label {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: page.readinessPercent() + "%"
                            color: page.readinessPercent() >= 80 ? page.greenColor : page.amberColor
                            font.pixelSize: page.compactLayout ? 20 : 24
                            font.bold: true
                        }
                        Label {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: qsTr("prontidão")
                            color: page.mutedColor
                            font.pixelSize: 11
                        }
                    }
                }
            }
        }

        Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: page.compactLayout ? 58 : 68
            color: page.surfaceColor

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: page.compactLayout ? 12 : 24
                anchors.rightMargin: page.compactLayout ? 12 : 24
                spacing: page.compactLayout ? 6 : 10

                Label {
                    text: qsTr("Escopo")
                    color: page.mutedColor
                    font.bold: true
                    Layout.rightMargin: page.compactLayout ? 0 : 4
                }

                Repeater {
                    model: page.scopes
                    delegate: Button {
                        required property int index
                        required property var modelData
                        text: modelData.label
                        icon.name: modelData.icon || "applications-games"
                        icon.color: checked ? page.cyanColor : page.mutedColor
                        checkable: true
                        checked: page.scopeIndex === index
                        enabled: modelData.enabled !== false
                        Layout.fillWidth: page.compactLayout
                        Layout.preferredWidth: page.compactLayout ? -1
                            : Math.max(112, implicitWidth + 12)
                        Layout.minimumHeight: page.compactLayout ? 42 : 48
                        Accessible.name: qsTr("Aplicar no escopo %1").arg(text)
                        Accessible.description: modelData.reason || ""
                        onClicked: page.selectScope(index)
                        background: Rectangle {
                            color: parent.checked ? page.cyanDarkColor : page.backgroundColor
                            border.color: parent.checked || parent.activeFocus
                                ? page.cyanColor : page.borderColor
                            border.width: parent.checked || parent.activeFocus ? 2 : 1
                            radius: 7
                        }
                        contentItem: RowLayout {
                            spacing: page.compactLayout ? 4 : 8
                            ModernIcon {
                                iconName: page.visualIcon(modelData.icon || modelData.iconKey)
                                iconColor: parent.parent.checked ? page.cyanColor : page.mutedColor
                                Layout.preferredWidth: page.compactLayout ? 17 : 19
                                Layout.preferredHeight: page.compactLayout ? 17 : 19
                            }
                            Label {
                                text: modelData.label
                                color: page.textColor
                                font.bold: parent.parent.checked
                                horizontalAlignment: Text.AlignHCenter
                                Layout.fillWidth: true
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                SteamComboBox {
                    visible: page.scopeId() === "emulator" && page.width >= 1250
                    model: page.emulators
                    textRole: "name"
                    currentIndex: page.emulatorIndex
                    enabled: page.emulators.length > 0
                    palette.button: page.raisedColor
                    palette.buttonText: page.textColor
                    palette.base: page.raisedColor
                    palette.text: page.textColor
                    Layout.preferredWidth: 220
                    Layout.minimumHeight: 48
                    Accessible.name: qsTr("Selecionar emulador")
                    onActivated: {
                        page.emulatorIndex = currentIndex
                        const emulator = page.emulators[currentIndex]
                        if (emulator && emulator.id !== page.selectedPlatform.defaultEmulatorId)
                            page.actionRequested({"id": "game.emulator.default", "label": qsTr("Definir como padrão da plataforma"), "enabled": true, "emulatorId": emulator.id})
                    }
                }

            }
        }

        Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }

        RowLayout {
            visible: page.compactLayout && !page.isGameLibrary()
            Layout.fillWidth: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.topMargin: 7
            Layout.bottomMargin: 7
            spacing: 8
            Label {
                text: qsTr("Área")
                color: page.mutedColor
                font.bold: true
            }
            SteamComboBox {
                model: page.areas
                textRole: "label"
                currentIndex: page.areaIndex
                Layout.fillWidth: true
                Layout.minimumHeight: page.minimumTouchTarget
                Accessible.name: qsTr("Selecionar área de emulação")
                onActivated: page.areaIndex = currentIndex
            }
            Label {
                text: page.contextTitle()
                color: page.cyanColor
                font.bold: true
                elide: Text.ElideRight
                Layout.maximumWidth: 220
            }
        }

        Rectangle {
            visible: page.compactLayout && !page.isGameLibrary()
            color: page.borderColor
            Layout.fillWidth: true
            Layout.preferredHeight: 1
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                visible: page.showAreaSidebar
                Layout.preferredWidth: page.width < 1180 ? 184 : 216
                Layout.fillHeight: true
                color: page.sidebarColor || page.surfaceColor
                border.color: page.borderColor

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    Label {
                        text: qsTr("ÁREAS")
                        color: page.mutedColor
                        font.pixelSize: 10
                        font.bold: true
                        font.letterSpacing: 1.0
                        Layout.leftMargin: 8
                        Layout.topMargin: 5
                    }

                    ListView {
                        id: areaList
                        model: page.areas
                        clip: true
                        spacing: 4
                        currentIndex: page.areaIndex
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        delegate: Button {
                            required property int index
                            required property var modelData
                            width: ListView.view.width
                            height: 48
                            text: modelData.label
                            icon.name: page.visualIcon(modelData.icon || modelData.iconKey)
                            icon.color: checked ? page.cyanColor : page.mutedColor
                            display: AbstractButton.TextBesideIcon
                            checkable: true
                            checked: page.areaIndex === index
                            leftPadding: 12
                            rightPadding: 8
                            spacing: 10
                            Accessible.name: qsTr("Abrir área %1").arg(text)
                            onClicked: page.areaIndex = index
                            background: Rectangle {
                                color: parent.checked ? "#122b3d" : "transparent"
                                border.color: parent.checked || parent.activeFocus
                                    ? page.cyanColor : "transparent"
                                border.width: parent.checked || parent.activeFocus ? 2 : 0
                                radius: 7
                            }
                            contentItem: RowLayout {
                                spacing: 10
                                ModernIcon {
                                    iconName: page.visualIcon(modelData.icon || modelData.iconKey)
                                    iconColor: parent.parent.checked ? page.cyanColor : page.mutedColor
                                    Layout.preferredWidth: 20
                                    Layout.preferredHeight: 20
                                }
                                Label {
                                    text: modelData.label
                                    color: parent.parent.checked ? page.textColor : page.mutedColor
                                    font.bold: parent.parent.checked
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                        }
                    }
                }
            }

            ScrollView {
                id: contentScroll
                visible: !(page.compactLayout && page.isGameLibrary()
                    && page.gameDetailsOpen)
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                background: Rectangle { color: page.backgroundColor }

                ColumnLayout {
                    width: Math.min(contentScroll.availableWidth, page.contentMaxWidth)
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 16

                    Rectangle {
                        visible: page.compactLayout && !page.isGameLibrary()
                        Layout.fillWidth: true
                        Layout.leftMargin: 12
                        Layout.rightMargin: 12
                        Layout.topMargin: 8
                        implicitHeight: compactActionContent.implicitHeight + 20
                        color: page.surfaceColor
                        border.color: page.borderColor
                        radius: 8

                        RowLayout {
                            id: compactActionContent
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 10
                            Label {
                                text: page.primaryAction().reason || page.areaDescription(page.selectedArea.id)
                                color: page.primaryAction().enabled === false
                                    ? page.mutedColor : page.cyanColor
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Button {
                                id: compactPrimaryAction
                                text: page.primaryAction().label
                                enabled: page.primaryAction().enabled !== false
                                Layout.preferredWidth: Math.min(250, contentScroll.width * 0.34)
                                Layout.minimumHeight: page.minimumTouchTarget
                                Accessible.name: text
                                Accessible.description: page.primaryAction().reason || ""
                                onClicked: page.dispatchAction(page.primaryAction())
                                background: Rectangle {
                                    color: parent.enabled ? page.cyanDarkColor : page.raisedColor
                                    border.color: parent.activeFocus ? page.textColor : page.cyanColor
                                    border.width: parent.activeFocus ? 2 : 1
                                    radius: 7
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: page.isGameLibrary()
                        Layout.fillWidth: true
                        Layout.leftMargin: page.compactLayout ? 12 : 18
                        Layout.rightMargin: page.compactLayout ? 12 : 18
                        Layout.topMargin: page.compactLayout ? 10 : 16
                        spacing: 10

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Label {
                                    text: qsTr("Biblioteca por jogo")
                                    color: page.textColor
                                    font.pixelSize: 24
                                    font.bold: true
                                }
                                Label {
                                    text: qsTr("%1 de %2 jogo(s) • %3 capa(s) reais • selecione uma linha para abrir os ajustes")
                                        .arg(page.filteredGames().length).arg(page.games.length)
                                        .arg(page.coverCount())
                                    color: page.mutedColor
                                    font.pixelSize: 12
                                }
                            }
                            TextField {
                                id: gameSearchField
                                placeholderText: qsTr("Buscar por nome ou Title ID")
                                text: page.gameSearchText
                                color: page.textColor
                                placeholderTextColor: page.mutedColor
                                selectByMouse: true
                                Layout.preferredWidth: Math.min(360, contentScroll.width * 0.38)
                                Layout.minimumHeight: page.minimumTouchTarget
                                Accessible.name: qsTr("Buscar jogos")
                                onTextChanged: page.gameSearchText = text
                                background: Rectangle {
                                    color: page.surfaceColor
                                    border.color: gameSearchField.activeFocus
                                        ? page.cyanColor : page.borderColor
                                    border.width: gameSearchField.activeFocus ? 2 : 1
                                    radius: 7
                                }
                            }
                            Button {
                                text: qsTr("Sincronizar Steam (%1)").arg(page.steamSelectedCount())
                                icon.name: "steam"
                                enabled: page.steamSelectedCount() > 0
                                    || page.steamPublishedCount() > 0
                                palette.button: enabled ? page.cyanDarkColor : page.raisedColor
                                palette.buttonText: enabled ? page.textColor : page.mutedColor
                                Layout.minimumHeight: page.minimumTouchTarget
                                Accessible.description: qsTr("A Steam deve estar fechada; somente jogos marcados serão sincronizados.")
                                onClicked: page.dispatchAction({
                                    "id": "steam.shortcuts.sync",
                                    "label": text,
                                    "enabled": true,
                                    "requiresConfirmation": true
                                })
                            }
                            Button {
                                text: qsTr("Varrer")
                                icon.name: "view-refresh"
                                palette.button: page.raisedColor
                                palette.buttonText: page.textColor
                                Layout.minimumHeight: page.minimumTouchTarget
                                Accessible.name: qsTr("Varrer biblioteca novamente")
                                onClicked: page.dispatchAction({
                                    "id": "library.scan", "label": text, "enabled": true
                                })
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Label {
                                text: qsTr("Ordenar por")
                                color: page.mutedColor
                                font.bold: true
                                Layout.rightMargin: 4
                            }
                            Repeater {
                                model: [
                                    {"key": "name", "label": qsTr("Nome")},
                                    {"key": "titleId", "label": qsTr("Title ID")},
                                    {"key": "size", "label": qsTr("Tamanho")},
                                    {"key": "format", "label": qsTr("Formato")},
                                    {"key": "state", "label": qsTr("Estado")}
                                ]
                                delegate: Button {
                                    required property var modelData
                                    text: modelData.label + (page.gameSortKey === modelData.key
                                        ? (page.gameSortAscending ? "  ↑" : "  ↓") : "")
                                    checkable: true
                                    checked: page.gameSortKey === modelData.key
                                    palette.button: checked ? page.cyanDarkColor : page.raisedColor
                                    palette.buttonText: page.textColor
                                    Layout.minimumHeight: page.minimumTouchTarget
                                    Accessible.name: qsTr("Ordenar por %1").arg(modelData.label)
                                    onClicked: page.setGameSort(modelData.key)
                                }
                            }
                            Item { Layout.fillWidth: true }
                            Label {
                                text: qsTr("Metadados ausentes ficam marcados para nova varredura")
                                color: page.mutedColor
                                font.pixelSize: 11
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 34
                            color: page.surfaceColor
                            border.color: page.borderColor
                            radius: 6
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 10
                                Label { text: qsTr("CAPA"); color: page.mutedColor; font.pixelSize: 10; font.bold: true; Layout.preferredWidth: 86 }
                                Label { text: qsTr("JOGO • COMPATIBILIDADE • COMPLEMENTOS"); color: page.mutedColor; font.pixelSize: 10; font.bold: true; Layout.fillWidth: true }
                                Label { visible: contentScroll.width >= 760; text: qsTr("REQUISITOS"); color: page.mutedColor; font.pixelSize: 10; font.bold: true; horizontalAlignment: Text.AlignLeft; Layout.preferredWidth: 118 }
                                Label { visible: contentScroll.width >= 760; text: qsTr("EMULADOR"); color: page.mutedColor; font.pixelSize: 10; font.bold: true; Layout.preferredWidth: 126 }
                                Label { text: qsTr("AÇÃO"); color: page.mutedColor; font.pixelSize: 10; font.bold: true; Layout.preferredWidth: 112 }
                            }
                        }

                        Rectangle {
                            visible: page.filteredGames().length === 0
                            Layout.fillWidth: true
                            Layout.minimumHeight: 120
                            color: page.surfaceColor
                            border.color: page.borderColor
                            radius: 8
                            Column {
                                anchors.centerIn: parent
                                spacing: 6
                                ModernIcon {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: 28
                                    height: 28
                                    iconName: "edit-find"
                                    iconColor: page.mutedColor
                                }
                                Label {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: page.games.length === 0
                                        ? qsTr("Nenhum jogo base foi encontrado")
                                        : qsTr("Nenhum jogo corresponde à busca")
                                    color: page.textColor
                                    font.bold: true
                                }
                                Label {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: page.games.length === 0
                                        ? qsTr("Adicione uma pasta ou faça uma nova varredura.")
                                        : qsTr("Tente outro nome ou Title ID.")
                                    color: page.mutedColor
                                }
                            }
                        }

                        Repeater {
                            model: page.filteredGames()
                            delegate: Rectangle {
                                id: gameRow
                                required property var modelData
                                readonly property bool selected: page.selectedGame.id === modelData.id
                                    && page.selectedGame.path === modelData.path
                                Layout.fillWidth: true
                                Layout.preferredHeight: 150
                                color: selected ? "#10283a" : page.surfaceColor
                                border.color: selected ? page.cyanColor : page.borderColor
                                border.width: selected ? 2 : 1
                                radius: 8

                                TapHandler {
                                    acceptedButtons: Qt.LeftButton
                                    onTapped: page.selectGame(gameRow.modelData)
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 10

                                    Rectangle {
                                        Layout.preferredWidth: 86
                                        Layout.preferredHeight: 66
                                        color: page.raisedColor
                                        border.color: page.borderColor
                                        radius: 6
                                        clip: true
                                        Image {
                                            id: gameBanner
                                            anchors.fill: parent
                                            source: gameRow.modelData.coverUrl || gameRow.modelData.bannerAsset || ""
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            visible: String(source) !== "" && status === Image.Ready
                                        }
                                        SwitchPlatformMark {
                                            anchors.centerIn: parent
                                            width: 42
                                            height: 42
                                            visible: !gameBanner.visible
                                            cutoutColor: page.raisedColor
                                        }
                                        Label {
                                            anchors.right: parent.right
                                            anchors.bottom: parent.bottom
                                            rightPadding: 4
                                            bottomPadding: 2
                                            text: String(gameRow.modelData.format || "—").toUpperCase()
                                            color: page.textColor
                                            font.pixelSize: 9
                                            font.bold: true
                                            background: Rectangle { color: "#aa071019"; radius: 3 }
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 260
                                        spacing: 4
                                        Label {
                                            text: gameRow.modelData.name || qsTr("Jogo sem nome")
                                            color: page.textColor
                                            font.pixelSize: 15
                                            font.bold: true
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                        Label {
                                            text: qsTr("Title ID: %1%2")
                                                .arg(gameRow.modelData.titleId || qsTr("não identificado"))
                                                .arg(gameRow.modelData.version
                                                    ? qsTr(" • versão %1").arg(gameRow.modelData.version) : "")
                                            color: gameRow.modelData.identityVerified === false
                                                ? page.amberColor : page.mutedColor
                                            font.pixelSize: 11
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 5
                                            Repeater {
                                                model: page.emulators
                                                delegate: Rectangle {
                                                    required property var modelData
                                                    readonly property string compatibility: page.compatibilityState(
                                                        gameRow.modelData, modelData.id)
                                                    Layout.preferredWidth: compatibilityText.implicitWidth + 14
                                                    Layout.preferredHeight: 22
                                                    color: "transparent"
                                                    border.color: page.compatibilityColor(compatibility)
                                                    radius: 10
                                                    Label {
                                                        id: compatibilityText
                                                        anchors.centerIn: parent
                                                        text: "● " + modelData.name
                                                        color: page.compatibilityColor(parent.compatibility)
                                                        font.pixelSize: 9
                                                        font.bold: true
                                                    }
                                                    ToolTip.visible: compatibilityHover.hovered
                                                    ToolTip.text: modelData.name + ": "
                                                        + page.compatibilityLabel(parent.compatibility)
                                                    HoverHandler { id: compatibilityHover }
                                                }
                                            }
                                            Item { Layout.fillWidth: true }
                                        }
                                        Flow {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: childrenRect.height
                                            spacing: 5
                                            Repeater {
                                                model: page.gameFeatures(gameRow.modelData)
                                                delegate: Rectangle {
                                                    required property var modelData
                                                    width: featureRow.implicitWidth + 12
                                                    height: 22
                                                    color: page.backgroundColor
                                                    border.color: page.borderColor
                                                    radius: 5
                                                    Row {
                                                        id: featureRow
                                                        anchors.centerIn: parent
                                                        spacing: 4
                                                        ModernIcon { width: 13; height: 13; iconName: modelData.icon; iconColor: page.mutedColor }
                                                        Label { text: modelData.label; color: page.mutedColor; font.pixelSize: 9 }
                                                    }
                                                }
                                            }
                                        }
                                        CheckBox {
                                            text: gameRow.modelData.steamPublished
                                                ? qsTr("Publicado na Steam") : qsTr("Incluir na Steam")
                                            checked: gameRow.modelData.steamSelected === true
                                            palette.windowText: checked ? page.cyanColor : page.mutedColor
                                            Accessible.description: qsTr("Marca este jogo para a próxima sincronização da biblioteca Steam.")
                                            onClicked: {
                                                page.selectGame(gameRow.modelData)
                                                page.dispatchAction({
                                                    "id": "game.steam.set",
                                                    "label": checked ? qsTr("Marcar para Steam") : qsTr("Desmarcar da Steam"),
                                                    "enabled": true,
                                                    "requiresConfirmation": true,
                                                    "gameId": gameRow.modelData.id,
                                                    "selected": checked
                                                })
                                            }
                                        }
                                    }

                                    ColumnLayout {
                                        visible: contentScroll.width >= 760
                                        Layout.preferredWidth: 118
                                        spacing: 4
                                        Label { text: page.formatBytes(gameRow.modelData.size); color: page.textColor; font.bold: true }
                                        Label { text: String(gameRow.modelData.format || "—").toUpperCase(); color: page.mutedColor; font.pixelSize: 11 }
                                        Label {
                                            text: gameRow.modelData.requiresFirmware
                                                && gameRow.modelData.requiresFirmware.required
                                                ? qsTr("FW ≥ %1").arg(gameRow.modelData.requiresFirmware.required)
                                                : qsTr("FW em análise")
                                            color: gameRow.modelData.requiresFirmware
                                                && gameRow.modelData.requiresFirmware.required
                                                ? page.mutedColor : page.amberColor
                                            font.pixelSize: 10
                                        }
                                        Label {
                                            text: gameRow.modelData.region || qsTr("Região em análise")
                                            color: gameRow.modelData.region
                                                ? page.mutedColor : page.amberColor
                                            font.pixelSize: 10
                                        }
                                    }

                                    SteamComboBox {
                                        visible: contentScroll.width >= 760
                                        model: page.emulators
                                        textRole: "name"
                                        currentIndex: page.gameEmulatorIndex(gameRow.modelData)
                                        displayText: currentIndex >= 0 ? currentText : qsTr("Não definido")
                                        enabled: page.emulators.length > 0
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        palette.base: page.raisedColor
                                        palette.text: page.textColor
                                        Layout.preferredWidth: 126
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        Accessible.name: qsTr("Emulador padrão de %1").arg(gameRow.modelData.name)
                                        Accessible.description: qsTr("Define qual emulador será usado pelo botão Jogar e pelo atalho da Steam.")
                                        onActivated: {
                                            page.selectGame(gameRow.modelData)
                                            page.pendingEmulatorGameId = gameRow.modelData.id
                                            page.pendingEmulatorId = page.emulators[currentIndex].id
                                            page.dispatchAction({
                                                "id": "game.emulator.set",
                                                "label": qsTr("Definir emulador do jogo"),
                                                "enabled": true,
                                                "requiresConfirmation": true,
                                                "gameId": gameRow.modelData.id,
                                                "emulatorId": page.emulators[currentIndex].id
                                            })
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.preferredWidth: 112
                                        spacing: 5
                                        Button {
                                            readonly property var playAction: page.gamePlayAction(gameRow.modelData)
                                            text: playAction.label
                                            icon.name: "media-playback-start"
                                            enabled: playAction.enabled === true
                                            palette.button: enabled ? page.cyanDarkColor : page.raisedColor
                                            palette.buttonText: enabled ? page.textColor : page.mutedColor
                                            Layout.fillWidth: true
                                            Layout.minimumHeight: page.minimumTouchTarget
                                            Accessible.description: playAction.reason || ""
                                            onClicked: {
                                                page.selectGame(gameRow.modelData)
                                                page.dispatchAction(playAction)
                                            }
                                        }
                                        Button {
                                            text: qsTr("Ajustes")
                                            icon.name: "configure"
                                            palette.button: page.raisedColor
                                            palette.buttonText: page.textColor
                                            Layout.fillWidth: true
                                            Layout.minimumHeight: page.minimumTouchTarget
                                            onClicked: page.selectGame(gameRow.modelData)
                                        }
                                    }
                                }
                            }
                        }

                        Item { Layout.preferredHeight: 8 }
                    }

                    ColumnLayout {
                        visible: !page.isGameLibrary()
                        Layout.fillWidth: true
                        Layout.leftMargin: page.responsiveGutter
                        Layout.rightMargin: page.responsiveGutter
                        Layout.topMargin: page.compactLayout ? 12 : 20
                        spacing: 5

                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: page.areaTitle(page.selectedArea.id)
                                color: page.textColor
                                font.pixelSize: page.compactLayout ? 21 : 24
                                font.bold: true
                                Layout.fillWidth: true
                            }
                            Label {
                                text: page.contextTitle()
                                visible: !page.compactLayout && (page.width >= 1250
                                    || (page.scopeId() !== "emulator" && page.scopeId() !== "game"))
                                color: page.cyanColor
                                font.bold: true
                                leftPadding: 10
                                rightPadding: 10
                                topPadding: 6
                                bottomPadding: 6
                                background: Rectangle {
                                    color: page.cyanDarkColor
                                    radius: 12
                                    border.color: page.cyanColor
                                }
                            }
                            SteamComboBox {
                                visible: page.width < 1250 && page.scopeId() === "emulator"
                                model: page.emulators
                                textRole: "name"
                                currentIndex: page.emulatorIndex
                                enabled: page.emulators.length > 0
                                palette.button: page.raisedColor
                                palette.buttonText: page.textColor
                                palette.base: page.raisedColor
                                palette.text: page.textColor
                                Layout.preferredWidth: 210
                                Layout.minimumHeight: 48
                                Accessible.name: qsTr("Selecionar emulador")
                                onActivated: {
                                    page.emulatorIndex = currentIndex
                                    const emulator = page.emulators[currentIndex]
                                    if (emulator && emulator.id !== page.selectedPlatform.defaultEmulatorId)
                                        page.actionRequested({"id": "game.emulator.default", "label": qsTr("Definir como padrão da plataforma"), "enabled": true, "emulatorId": emulator.id})
                                }
                            }
                            SteamComboBox {
                                visible: page.width < 1250 && page.scopeId() === "game"
                                model: page.games
                                textRole: "name"
                                currentIndex: page.gameIndex
                                enabled: page.games.length > 0
                                palette.button: page.raisedColor
                                palette.buttonText: page.textColor
                                palette.base: page.raisedColor
                                palette.text: page.textColor
                                Layout.preferredWidth: 230
                                Layout.minimumHeight: 48
                                Accessible.name: qsTr("Selecionar jogo")
                                onActivated: page.gameIndex = currentIndex
                            }
                        }
                        Label {
                            text: page.areaDescription(page.selectedArea.id)
                            color: page.mutedColor
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    Rectangle {
                        visible: !page.isGameLibrary() && page.scopedRuntimeProfile() !== null
                        Layout.fillWidth: true
                        Layout.leftMargin: page.responsiveGutter
                        Layout.rightMargin: page.responsiveGutter
                        implicitHeight: runtimeProfileContent.implicitHeight + 24
                        color: page.surfaceColor
                        border.color: page.runtimeProfiles.activeScope === page.scopeId()
                            ? page.cyanColor : page.borderColor
                        radius: 10

                        ColumnLayout {
                            id: runtimeProfileContent
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    text: page.scopeId() === "dock"
                                        ? qsTr("Perfil Dock") : qsTr("Perfil Portátil")
                                    color: page.textColor
                                    font.bold: true
                                    font.pixelSize: 16
                                    Layout.fillWidth: true
                                }
                                Label {
                                    text: page.runtimeProfiles.activeScope === page.scopeId()
                                        ? qsTr("Observado agora") : qsTr("Inativo")
                                    color: page.runtimeProfiles.activeScope === page.scopeId()
                                        ? page.cyanColor : page.mutedColor
                                    font.bold: true
                                }
                            }
                            Flow {
                                Layout.fillWidth: true
                                spacing: 12
                                Label {
                                    text: qsTr("Resolução %1×%2")
                                        .arg(page.scopedRuntimeProfile().resolution.width)
                                        .arg(page.scopedRuntimeProfile().resolution.height)
                                    color: page.textColor
                                }
                                Label {
                                    text: qsTr("Escala %1×").arg(
                                        Number(page.scopedRuntimeProfile().renderScale).toFixed(2))
                                    color: page.textColor
                                }
                                Label {
                                    text: qsTr("TDP %1").arg(page.inheritedValue("tdp", qsTr("perfil Steam/jogo")))
                                    color: page.mutedColor
                                }
                                Label {
                                    text: qsTr("FPS %1").arg(page.inheritedValue("fps", qsTr("perfil Steam/jogo")))
                                    color: page.mutedColor
                                }
                                Label {
                                    text: qsTr("Controles %1/%2")
                                        .arg(page.scopedRuntimeProfile().controllers.activePlayers)
                                        .arg(page.scopedRuntimeProfile().controllers.maximumPlayers)
                                    color: page.mutedColor
                                }
                                Label { text: qsTr("Áudio herdado do sistema"); color: page.mutedColor }
                            }
                            Label {
                                visible: page.runtimeProfiles.autoTransition
                                    && page.runtimeProfiles.autoTransition.supported !== true
                                text: page.runtimeProfiles.autoTransition
                                    ? page.runtimeProfiles.autoTransition.reason : ""
                                color: page.amberColor
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }

                    Rectangle {
                        visible: !page.isGameLibrary()
                        Layout.fillWidth: true
                        Layout.leftMargin: page.responsiveGutter
                        Layout.rightMargin: page.responsiveGutter
                        Layout.preferredHeight: page.compactLayout ? 56 : 64
                        Layout.minimumHeight: Layout.preferredHeight
                        color: page.readinessPercent() >= 80 ? "#0c2a21" : "#24180b"
                        border.color: page.readinessPercent() >= 80
                            ? page.greenColor : page.amberColor
                        radius: 10

                        RowLayout {
                            id: readinessRow
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.margins: 10
                            spacing: 10

                            ModernIcon {
                                iconName: page.stateIcon(page.selectedPlatform.state)
                                iconColor: page.readinessPercent() >= 80
                                    ? page.greenColor : page.amberColor
                                Layout.preferredWidth: 24
                                Layout.preferredHeight: 24
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Label {
                                    text: page.readiness.title || qsTr("Verificando plataforma")
                                    color: page.readinessPercent() >= 80
                                        ? page.greenColor : page.amberColor
                                    font.bold: true
                                    font.pixelSize: 14
                                }
                                Label {
                                    text: page.readiness.detail || ""
                                    color: page.mutedColor
                                    elide: Text.ElideRight
                                    maximumLineCount: 1
                                    Layout.fillWidth: true
                                }
                            }
                            ProgressBar {
                                from: 0
                                to: 100
                                value: page.readinessPercent()
                                Layout.preferredWidth: contentScroll.width < 680 ? 90 : 130
                                Accessible.name: qsTr("Prontidão da plataforma")
                                Accessible.description: qsTr("%1 por cento").arg(page.readinessPercent())
                            }
                        }
                    }

                    GridLayout {
                        visible: !page.isEmulatorOverview() && !page.isGameLibrary()
                        Layout.fillWidth: true
                        Layout.leftMargin: page.responsiveGutter
                        Layout.rightMargin: page.responsiveGutter
                        columns: page.compactLayout ? 1 : contentScroll.width >= 760 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 12

                        Repeater {
                            model: page.cards()
                            delegate: Rectangle {
                                required property int index
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.minimumWidth: 250
                                Layout.preferredHeight: page.isGlobalOverview()
                                    ? (page.compactLayout ? 144 : 184)
                                    : cardColumn.implicitHeight + (page.compactLayout ? 20 : 28)
                                Layout.minimumHeight: Layout.preferredHeight
                                color: page.surfaceColor
                                border.color: page.stateColor(modelData.state)
                                border.width: 1
                                radius: 10

                                ColumnLayout {
                                    id: cardColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: page.compactLayout ? 10 : 14
                                    spacing: page.compactLayout ? 6 : 8

                                    RowLayout {
                                        Layout.fillWidth: true
                                        ModernIcon {
                                            iconName: page.visualIcon(
                                                modelData.icon || modelData.iconKey
                                                    || page.stateIcon(modelData.state)
                                            )
                                            iconColor: page.stateColor(modelData.state)
                                            Layout.preferredWidth: 24
                                            Layout.preferredHeight: 24
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 1
                                            Label {
                                                text: modelData.title
                                                color: page.textColor
                                                font.bold: true
                                                font.pixelSize: 15
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                            Label {
                                                text: modelData.status || modelData.statusLabel
                                                    || qsTr("Estado desconhecido")
                                                color: page.stateColor(modelData.state)
                                                font.pixelSize: 12
                                            }
                                        }
                                        Label {
                                            text: page.cardMetric(modelData)
                                            color: page.textColor
                                            font.pixelSize: 18
                                            font.bold: true
                                        }
                                    }
                                    Label {
                                        text: modelData.detail || ""
                                        color: page.mutedColor
                                        font.pixelSize: 12
                                        wrapMode: Text.WordWrap
                                        maximumLineCount: page.isGlobalOverview() ? 2 : 4
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }

                                    Item { Layout.fillHeight: true }

                                    RowLayout {
                                        visible: page.cardActions(modelData).length > 0
                                        Layout.fillWidth: true
                                        spacing: 6

                                        Repeater {
                                            model: page.cardActions(modelData)
                                            delegate: Button {
                                                required property var modelData
                                                text: modelData.label || qsTr("Abrir área")
                                                icon.name: "go-next"
                                                enabled: modelData.enabled !== false
                                                palette.button: page.raisedColor
                                                palette.buttonText: page.textColor
                                                Layout.fillWidth: true
                                                Layout.minimumWidth: 0
                                                Layout.maximumWidth: 190
                                                Layout.minimumHeight: page.minimumTouchTarget
                                                Accessible.name: text
                                                Accessible.description: modelData.reason || ""
                                                onClicked: page.dispatchCardAction(modelData)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: page.isEmulatorOverview()
                        Layout.fillWidth: true
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        spacing: 8

                        Label {
                            text: qsTr("Emuladores desta plataforma")
                            color: page.textColor
                            font.pixelSize: 18
                            font.bold: true
                        }

                        Rectangle {
                            visible: page.emulators.length === 0
                            Layout.fillWidth: true
                            Layout.minimumHeight: 82
                            color: page.surfaceColor
                            border.color: page.borderColor
                            radius: 9
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 14
                                ModernIcon {
                                    iconName: "applications-games"
                                    iconColor: page.mutedColor
                                    Layout.preferredWidth: 24
                                    Layout.preferredHeight: 24
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Label { text: qsTr("Nenhum emulador Switch foi verificado"); color: page.textColor; font.bold: true }
                                    Label {
                                        text: qsTr("A central exibirá Eden, Citron e Ryubing somente quando o backend confirmar disponibilidade e capacidades.")
                                        color: page.mutedColor
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                        }

                        Repeater {
                            id: emulatorMaintenanceRepeater
                            objectName: "emulatorMaintenanceRepeater"
                            model: page.emulators
                            delegate: Rectangle {
                                id: emulatorRow
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: emulatorRowContent.implicitHeight + 24
                                Layout.minimumHeight: implicitHeight
                                color: page.surfaceColor
                                border.color: modelData.isDefault ? page.cyanColor : page.borderColor
                                radius: 9

                                ColumnLayout {
                                    id: emulatorRowContent
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 8

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 10
                                        Item {
                                            Layout.preferredWidth: 24
                                            Layout.preferredHeight: 24
                                            Image {
                                                id: emulatorLogo
                                                anchors.fill: parent
                                                source: emulatorRow.modelData.iconAsset || ""
                                                fillMode: Image.PreserveAspectFit
                                                asynchronous: true
                                                smooth: true
                                                Accessible.ignored: true
                                            }
                                            ModernIcon {
                                                anchors.fill: parent
                                                visible: !emulatorRow.modelData.iconAsset
                                                    || emulatorLogo.status === Image.Error
                                                iconName: emulatorRow.modelData.iconKey
                                                    || "applications-games"
                                                iconColor: page.stateColor(emulatorRow.modelData.state)
                                            }
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 1
                                            RowLayout {
                                                Layout.fillWidth: true
                                                Label {
                                                    text: emulatorRow.modelData.name
                                                    color: page.textColor
                                                    font.bold: true
                                                }
                                                Label {
                                                    visible: emulatorRow.modelData.isDefault === true
                                                    text: qsTr("PADRÃO")
                                                    color: page.cyanColor
                                                    font.bold: true
                                                    font.pixelSize: 11
                                                }
                                                Label {
                                                    visible: emulatorRow.modelData.running === true
                                                    text: qsTr("EM EXECUÇÃO")
                                                    color: page.greenColor
                                                    font.bold: true
                                                    font.pixelSize: 11
                                                }
                                                Item { Layout.fillWidth: true }
                                            }
                                            Label {
                                                text: emulatorRow.modelData.specialty
                                                    || emulatorRow.modelData.description
                                                    || qsTr("Capacidades ainda não publicadas")
                                                color: page.mutedColor
                                                font.pixelSize: 12
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                        }
                                        Label {
                                            text: emulatorRow.modelData.statusLabel
                                                || qsTr("Desconhecido")
                                            color: page.stateColor(emulatorRow.modelData.state)
                                            font.bold: true
                                        }
                                    }

                                    Flow {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        Label {
                                            text: qsTr("Versão %1 → %2")
                                                .arg(emulatorRow.modelData.version || "—")
                                                .arg(emulatorRow.modelData.targetVersion || "—")
                                            color: emulatorRow.modelData.health
                                                && emulatorRow.modelData.health.versionCurrent
                                                ? page.greenColor : page.mutedColor
                                            height: 24
                                        }
                                        Label {
                                            text: emulatorRow.modelData.health
                                                && emulatorRow.modelData.health.keysReady
                                                ? qsTr("Keys verificadas") : qsTr("Keys pendentes")
                                            color: emulatorRow.modelData.health
                                                && emulatorRow.modelData.health.keysReady
                                                ? page.greenColor : page.amberColor
                                            height: 24
                                        }
                                        Label {
                                            text: qsTr("%1 diretório(s) de jogos")
                                                .arg(emulatorRow.modelData.libraryRootCount || 0)
                                            color: page.mutedColor
                                            height: 24
                                        }
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Label {
                                            text: emulatorRow.modelData.health
                                                ? emulatorRow.modelData.health.reason : ""
                                            color: page.mutedColor
                                            wrapMode: Text.WordWrap
                                            Layout.fillWidth: true
                                        }
                                        Button {
                                            id: emulatorActionsButton
                                            text: qsTr("Ações (%1)").arg(
                                                emulatorRow.modelData.actions
                                                    ? emulatorRow.modelData.actions.length : 0)
                                            icon.name: "application-menu"
                                            enabled: emulatorRow.modelData.actions
                                                && emulatorRow.modelData.actions.length > 0
                                            palette.button: page.raisedColor
                                            palette.buttonText: page.textColor
                                            Layout.minimumWidth: 136
                                            Layout.minimumHeight: page.minimumTouchTarget
                                            Accessible.name: qsTr("Ações de %1")
                                                .arg(emulatorRow.modelData.name)
                                            Accessible.description: qsTr("Abrir menu de manutenção do emulador")
                                            onClicked: emulatorActionsMenu.popup()
                                        }
                                    }

                                    Menu {
                                        id: emulatorActionsMenu
                                        modal: true
                                        focus: true
                                        closePolicy: Popup.CloseOnEscape
                                            | Popup.CloseOnPressOutside

                                        Instantiator {
                                            model: emulatorRow.modelData.actions
                                                && emulatorRow.modelData.actions.length > 0
                                                ? emulatorRow.modelData.actions
                                                : []
                                            delegate: MenuItem {
                                                required property var modelData
                                                text: modelData && modelData.label
                                                    ? modelData.label : qsTr("Detalhes")
                                                enabled: Boolean(modelData)
                                                    && modelData.enabled !== false
                                                height: page.minimumTouchTarget
                                                Accessible.name: qsTr("%1: %2").arg(text)
                                                    .arg(emulatorRow.modelData.name)
                                                Accessible.description: modelData
                                                    ? modelData.reason || "" : ""
                                                onTriggered: page.dispatchAction(modelData)
                                            }
                                            onObjectAdded: function(index, object) {
                                                emulatorActionsMenu.insertItem(index, object)
                                            }
                                            onObjectRemoved: function(index, object) {
                                                emulatorActionsMenu.removeItem(object)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Item { Layout.fillWidth: true; Layout.preferredHeight: 18 }
                }
            }

            Rectangle {
                id: contextPanel
                visible: page.showContextPanel || (page.compactLayout
                    && page.isGameLibrary() && page.gameDetailsOpen)
                Layout.fillWidth: page.compactLayout && page.isGameLibrary()
                Layout.preferredWidth: page.compactLayout && page.isGameLibrary()
                    ? page.width
                    : page.isGameLibrary() ? (page.width < 1200 ? 340 : 360) : 286
                Layout.fillHeight: true
                color: page.surfaceColor
                border.color: page.borderColor

                ColumnLayout {
                    visible: !page.isGameLibrary()
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 12

                    Label {
                        text: qsTr("Contexto atual")
                        color: page.mutedColor
                        font.pixelSize: 11
                        font.bold: true
                        font.letterSpacing: 1
                    }
                    Label {
                        text: page.contextTitle()
                        color: page.textColor
                        font.pixelSize: 20
                        font.bold: true
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        ModernIcon {
                            iconName: page.stateIcon(page.selectedPlatform.state)
                            iconColor: page.stateColor(page.selectedPlatform.state)
                            Layout.preferredWidth: 22
                            Layout.preferredHeight: 22
                        }
                        Label {
                            text: page.selectedPlatform.statusLabel
                                || page.readiness.title || qsTr("Estado desconhecido")
                            color: page.stateColor(page.selectedPlatform.state)
                            font.bold: true
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }

                    Label { text: qsTr("O que esta área protege"); color: page.textColor; font.bold: true }
                    Label {
                        text: page.areaDescription(page.selectedArea.id)
                        color: page.mutedColor
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Rectangle {
                        visible: page.readiness.blockers && page.readiness.blockers.length > 0
                        Layout.fillWidth: true
                        Layout.minimumHeight: blockersColumn.implicitHeight + 24
                        color: "#24180b"
                        border.color: page.amberColor
                        radius: 8
                        ColumnLayout {
                            id: blockersColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 12
                            spacing: 5
                            Label { text: qsTr("Antes de continuar"); color: page.amberColor; font.bold: true }
                            Repeater {
                                model: page.readiness.blockers || []
                                delegate: Label {
                                    required property string modelData
                                    text: "• " + modelData
                                    color: page.mutedColor
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                        }
                    }

                    Label {
                        text: qsTr("Nenhum arquivo será alterado sem plano e confirmação explícita.")
                        color: page.mutedColor
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Item { Layout.fillHeight: true }

                    Label {
                        visible: !page.primaryAction().enabled
                        text: page.primaryAction().reason || ""
                        color: page.amberColor
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Button {
                        text: page.primaryAction().label || qsTr("Revisar ação")
                        icon.name: page.primaryAction().requiresConfirmation
                            ? "security-medium" : "go-next"
                        enabled: page.primaryAction().enabled === true
                        palette.button: page.raisedColor
                        palette.buttonText: page.textColor
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
                        Accessible.name: text
                        Accessible.description: page.primaryAction().reason || ""
                        onClicked: page.dispatchAction(page.primaryAction())
                    }
                    Button {
                        visible: page.selectedPlatform.state === "degraded"
                            || page.selectedPlatform.state === "failed"
                        text: qsTr("Abrir diagnóstico")
                        icon.name: "tools-report-bug"
                        palette.button: page.raisedColor
                        palette.buttonText: page.textColor
                        Layout.fillWidth: true
                        Layout.minimumHeight: 48
                        Accessible.name: text
                        onClicked: page.systemRequested()
                    }
                }

                ScrollView {
                    id: gamePanelScroll
                    visible: page.isGameLibrary()
                    anchors.fill: parent
                    clip: true
                    contentWidth: availableWidth
                    leftPadding: 16
                    rightPadding: 16
                    topPadding: 14
                    bottomPadding: 14

                    ColumnLayout {
                        width: gamePanelScroll.availableWidth
                        spacing: 12

                        RowLayout {
                            Layout.fillWidth: true
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Label {
                                    text: qsTr("AJUSTES DO JOGO")
                                    color: page.mutedColor
                                    font.pixelSize: 10
                                    font.bold: true
                                    font.letterSpacing: 1
                                }
                                Label {
                                    text: page.selectedGame.name
                                    color: page.textColor
                                    font.pixelSize: 18
                                    font.bold: true
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 3
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                            ToolButton {
                                icon.name: "window-close"
                                icon.color: page.textColor
                                Accessible.name: qsTr("Fechar ajustes do jogo")
                                onClicked: page.gameDetailsOpen = false
                            }
                        }

                        Label {
                            text: qsTr("Title ID: %1").arg(
                                page.selectedGame.titleId || qsTr("não identificado"))
                            color: page.mutedColor
                            font.pixelSize: 11
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }

                        Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            Label { text: qsTr("Emulador para este jogo"); color: page.textColor; font.bold: true }
                            SteamComboBox {
                                model: page.emulators
                                textRole: "name"
                                currentIndex: page.gameEmulatorIndex(page.selectedGame)
                                displayText: currentIndex >= 0 ? currentText : qsTr("Não definido")
                                enabled: page.emulators.length > 0
                                palette.button: page.raisedColor
                                palette.buttonText: page.textColor
                                palette.base: page.raisedColor
                                palette.text: page.textColor
                                Layout.fillWidth: true
                                Layout.minimumHeight: page.minimumTouchTarget
                                Accessible.description: qsTr("Preferência persistente usada pelo lançamento direto e pela Steam.")
                                onActivated: {
                                    page.pendingEmulatorGameId = page.selectedGame.id
                                    page.pendingEmulatorId = page.emulators[currentIndex].id
                                    page.dispatchAction({
                                        "id": "game.emulator.set",
                                        "label": qsTr("Definir emulador do jogo"),
                                        "enabled": true,
                                        "requiresConfirmation": true,
                                        "gameId": page.selectedGame.id,
                                        "emulatorId": page.emulators[currentIndex].id
                                    })
                                }
                            }
                            Label {
                                text: qsTr("Esta escolha controla o Play direto e o atalho publicado na Steam.")
                                color: page.mutedColor
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.minimumHeight: performancePanel.implicitHeight + 24
                            color: page.backgroundColor
                            border.color: page.borderColor
                            radius: 8
                            ColumnLayout {
                                id: performancePanel
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12
                                spacing: 7
                                RowLayout {
                                    ModernIcon { iconName: "speedometer"; iconColor: page.cyanColor; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
                                    Label { text: qsTr("Performance e upscaling"); color: page.textColor; font.bold: true; Layout.fillWidth: true }
                                }
                                Label {
                                    text: qsTr("LSFG-VK: %1").arg(page.selectedGame.lsfgMode || qsTr("não configurado"))
                                    color: page.mutedColor
                                }
                                Label {
                                    text: qsTr("Upscaler: %1").arg(page.selectedGame.upscaler || qsTr("não configurado"))
                                    color: page.mutedColor
                                }
                                Button {
                                    text: qsTr("Configurar gráficos e fluidez")
                                    icon.name: "go-next"
                                    palette.button: page.raisedColor
                                    palette.buttonText: page.textColor
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: page.minimumTouchTarget
                                    background: Rectangle {
                                        color: page.raisedColor
                                        border.color: parent.hovered || parent.activeFocus
                                            ? page.cyanColor : page.borderColor
                                        radius: 6
                                    }
                                    onClicked: page.openGameArea("graphicsPerformance")
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.minimumHeight: contentPanel.implicitHeight + 24
                            color: page.backgroundColor
                            border.color: page.borderColor
                            radius: 8
                            ColumnLayout {
                                id: contentPanel
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12
                                spacing: 7
                                RowLayout {
                                    ModernIcon { iconName: "package-x-generic"; iconColor: page.cyanColor; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
                                    Label { text: qsTr("Conteúdo e modding"); color: page.textColor; font.bold: true; Layout.fillWidth: true }
                                }
                                Label {
                                    text: qsTr("Updates: %1 • DLCs: %2 • Mods: %3")
                                        .arg(page.selectedGame.updateVersion || "—")
                                        .arg(page.selectedGame.dlcCount !== undefined
                                            ? page.selectedGame.dlcCount : "—")
                                        .arg(page.selectedGame.modsCount !== undefined
                                            ? page.selectedGame.modsCount : "—")
                                    color: page.mutedColor
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Button {
                                        text: qsTr("Updates e DLC")
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        background: Rectangle {
                                            color: page.raisedColor
                                            border.color: parent.hovered || parent.activeFocus
                                                ? page.cyanColor : page.borderColor
                                            radius: 6
                                        }
                                        onClicked: page.openGameArea("updatesDlc")
                                    }
                                    Button {
                                        text: qsTr("Mods e cheats")
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        background: Rectangle {
                                            color: page.raisedColor
                                            border.color: parent.hovered || parent.activeFocus
                                                ? page.cyanColor : page.borderColor
                                            radius: 6
                                        }
                                        enabled: page.selectedGame.id !== ""
                                        Accessible.description: qsTr("Gerenciar conteúdo local deste jogo.")
                                        onClicked: page.openGameArea("modsCheats")
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.minimumHeight: preservationPanel.implicitHeight + 24
                            color: page.backgroundColor
                            border.color: page.borderColor
                            radius: 8
                            ColumnLayout {
                                id: preservationPanel
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12
                                spacing: 7
                                RowLayout {
                                    ModernIcon { iconName: "document-save"; iconColor: page.cyanColor; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
                                    Label { text: qsTr("Saves e shader cache"); color: page.textColor; font.bold: true; Layout.fillWidth: true }
                                }
                                Label {
                                    text: qsTr("Save: %1 • Shaders: %2")
                                        .arg(page.selectedGame.saveState || "—")
                                        .arg(page.selectedGame.shaderCount !== undefined
                                            ? page.selectedGame.shaderCount : "—")
                                    color: page.mutedColor
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Button {
                                        text: qsTr("Backup e restaurar")
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        background: Rectangle {
                                            color: page.raisedColor
                                            border.color: parent.hovered || parent.activeFocus
                                                ? page.cyanColor : page.borderColor
                                            radius: 6
                                        }
                                        onClicked: page.openGameArea("saves")
                                    }
                                    Button {
                                        text: qsTr("Cache")
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        background: Rectangle {
                                            color: page.raisedColor
                                            border.color: parent.hovered || parent.activeFocus
                                                ? page.cyanColor : page.borderColor
                                            radius: 6
                                        }
                                        onClicked: page.openGameArea("shaderCache")
                                    }
                                }
                            }
                        }

                        Rectangle {
                            id: mediaPanel
                            visible: page.selectedGame.coverUrl !== undefined
                                && page.selectedGame.id !== ""
                            Layout.fillWidth: true
                            Layout.minimumHeight: mediaPanelBody.implicitHeight + 24
                            color: page.backgroundColor
                            border.color: page.borderColor
                            radius: 8
                            ColumnLayout {
                                id: mediaPanelBody
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12
                                spacing: 7
                                RowLayout {
                                    ModernIcon { iconName: "image-x-generic"; iconColor: page.cyanColor; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
                                    Label { text: qsTr("Mídia"); color: page.textColor; font.bold: true; Layout.fillWidth: true }
                                    Label {
                                        text: {
                                            var source = page.selectedGame.mediaSource || ""
                                            if (source === "custom") return qsTr("Customizada")
                                            if (source === "scraper") return qsTr("Scraping")
                                            if (source === "nca") return qsTr("NCA")
                                            if (source === "emulator-cache") return qsTr("Cache")
                                            return qsTr("Padrão")
                                        }
                                        color: page.mutedColor
                                        font.pixelSize: 10
                                        font.bold: true
                                        font.letterSpacing: 1
                                    }
                                }
                                Image {
                                    id: mediaPreview
                                    visible: page.selectedGame.coverUrl !== undefined
                                        && page.selectedGame.coverUrl !== ""
                                    source: page.selectedGame.coverUrl || ""
                                    sourceSize.width: 120
                                    sourceSize.height: 68
                                    fillMode: Image.PreserveAspectFit
                                    Layout.preferredHeight: 68
                                    Layout.preferredWidth: 120
                                    Layout.alignment: Qt.AlignHCenter
                                    Layout.maximumHeight: 68
                                    Accessible.name: qsTr("Preview de mídia")
                                }
                                Flow {
                                    visible: (page.selectedGame.mediaCandidates || []).length > 0
                                    Layout.fillWidth: true
                                    spacing: 4
                                    Repeater {
                                        model: page.selectedGame.mediaCandidates || []
                                        delegate: Rectangle {
                                            required property int index
                                            required property var modelData
                                            width: 56
                                            height: 56
                                            radius: 6
                                            color: index === (page.selectedGame.mediaCandidateIdx || -1)
                                                ? page.cyanDarkColor : page.surfaceColor
                                            border.color: index === (page.selectedGame.mediaCandidateIdx || -1)
                                                ? page.cyanColor : page.borderColor
                                            border.width: index === (page.selectedGame.mediaCandidateIdx || -1) ? 2 : 1
                                            Accessible.name: qsTr("Candidato %1: %2").arg(index + 1).arg(modelData.mediaKind || "")
                                            Image {
                                                anchors.centerIn: parent
                                                width: 48
                                                height: 48
                                                source: modelData.url || ""
                                                sourceSize.width: 48
                                                sourceSize.height: 48
                                                fillMode: Image.PreserveAspectFit
                                                visible: modelData.url && modelData.url.length > 0
                                            }
                                            Label {
                                                anchors.bottom: parent.bottom
                                                anchors.horizontalCenter: parent.horizontalCenter
                                                text: {
                                                    var kind = modelData.mediaKind || ""
                                                    if (kind === "boxart" || kind === "grid") return qsTr("Cx")
                                                    if (kind === "hero") return qsTr("Hr")
                                                    if (kind === "icon") return qsTr("Ic")
                                                    if (kind === "logo") return qsTr("Lg")
                                                    if (kind === "screenshot") return qsTr("Sc")
                                                    return kind.charAt(0).toUpperCase()
                                                }
                                                color: page.mutedColor
                                                font.pixelSize: 8
                                                font.bold: true
                                                visible: !(modelData.url && modelData.url.length > 0)
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    if (index !== (page.selectedGame.mediaCandidateIdx || -1)) {
                                                        page.dispatchAction({
                                                            "id": "game.media.select:" + page.selectedGame.id + ":" + index,
                                                            "label": qsTr("Selecionar candidato %1").arg(index + 1),
                                                            "enabled": true,
                                                            "requiresConfirmation": false,
                                                            "gameId": page.selectedGame.id,
                                                            "candidateIdx": index
                                                        })
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Button {
                                        text: qsTr("Importar")
                                        icon.name: "document-import"
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        background: Rectangle {
                                            color: page.raisedColor
                                            border.color: parent.hovered || parent.activeFocus
                                                ? page.cyanColor : page.borderColor
                                            radius: 6
                                        }
                                        Accessible.description: qsTr("Importar mídia personalizada do disco.")
                                        onClicked: page.dispatchAction({
                                            "id": "game.media.import:" + page.selectedGame.id,
                                            "label": qsTr("Importar mídia personalizada"),
                                            "enabled": true,
                                            "requiresConfirmation": true,
                                            "gameId": page.selectedGame.id
                                        })
                                    }
                                    Button {
                                        text: qsTr("Buscar")
                                        icon.name: "edit-find"
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        background: Rectangle {
                                            color: page.raisedColor
                                            border.color: parent.hovered || parent.activeFocus
                                                ? page.cyanColor : page.borderColor
                                            radius: 6
                                        }
                                        Accessible.description: qsTr("Buscar mídia na internet.")
                                        onClicked: page.dispatchAction({
                                            "id": "game.media.search:" + page.selectedGame.id,
                                            "label": qsTr("Buscar mídia na internet"),
                                            "enabled": true,
                                            "requiresConfirmation": false,
                                            "gameId": page.selectedGame.id
                                        })
                                    }
                                    Button {
                                        text: qsTr("Limpar")
                                        icon.name: "edit-clear"
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        background: Rectangle {
                                            color: page.raisedColor
                                            border.color: parent.hovered || parent.activeFocus
                                                ? page.cyanColor : page.borderColor
                                            radius: 6
                                        }
                                        Accessible.description: qsTr("Limpar mídia personalizada.")
                                        onClicked: page.dispatchAction({
                                            "id": "game.media.clear:" + page.selectedGame.id,
                                            "label": qsTr("Limpar mídia personalizada"),
                                            "enabled": true,
                                            "requiresConfirmation": true,
                                            "gameId": page.selectedGame.id
                                        })
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    Label {
                                        visible: page.selectedGame.mediaErrors !== undefined
                                            && Object.keys(page.selectedGame.mediaErrors).length > 0
                                        text: qsTr("Provedores com erro: %1")
                                            .arg(Object.keys(page.selectedGame.mediaErrors).join(", "))
                                        color: page.amberColor
                                        font.pixelSize: 10
                                        Layout.fillWidth: true
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    TextField {
                                        id: steamUserIdField
                                        visible: page.selectedGame.steamAppId !== undefined
                                            && page.selectedGame.steamAppId > 0
                                        placeholderText: qsTr("Steam ID (ex: 7656119...)")
                                        text: page.steamUserId
                                        color: page.textColor
                                        placeholderTextColor: page.mutedColor
                                        selectByMouse: true
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        onTextChanged: page.steamUserId = text
                                        background: Rectangle {
                                            color: page.surfaceColor
                                            border.color: steamUserIdField.activeFocus
                                                ? page.cyanColor : page.borderColor
                                            radius: 6
                                        }
                                        Accessible.name: qsTr("Steam user ID para publicação de mídia")
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    Button {
                                        id: publishSteamBtn
                                        text: page.selectedGame.steamViewState === "published"
                                            ? qsTr("Publicado") : qsTr("Publicar na Steam")
                                        icon.name: "steam"
                                        enabled: page.selectedGame.steamViewState !== "published"
                                            && page.selectedGame.steamAppId !== undefined
                                            && page.selectedGame.steamAppId > 0
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        background: Rectangle {
                                            color: publishSteamBtn.enabled
                                                ? page.raisedColor : page.surfaceColor
                                            border.color: parent.hovered || parent.activeFocus
                                                ? page.cyanColor : page.borderColor
                                            radius: 6
                                        }
                                        onClicked: page.dispatchAction({
                                            "id": "game.media.publish-steam:" + page.selectedGame.id,
                                            "label": qsTr("Publicar mídia na Steam"),
                                            "enabled": true,
                                            "requiresConfirmation": true,
                                            "gameId": page.selectedGame.id,
                                            "steamUserId": page.steamUserId || ""
                                        })
                                    }
                                    Button {
                                        id: unpublishSteamBtn
                                        text: qsTr("Remover da Steam")
                                        icon.name: "steam"
                                        enabled: page.selectedGame.steamViewState === "published"
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: page.minimumTouchTarget
                                        background: Rectangle {
                                            color: unpublishSteamBtn.enabled
                                                ? page.raisedColor : page.surfaceColor
                                            border.color: parent.hovered || parent.activeFocus
                                                ? page.cyanColor : page.borderColor
                                            radius: 6
                                        }
                                        onClicked: page.dispatchAction({
                                            "id": "game.media.unpublish-steam:" + page.selectedGame.id,
                                            "label": qsTr("Remover mídia da Steam"),
                                            "enabled": true,
                                            "requiresConfirmation": true,
                                            "gameId": page.selectedGame.id,
                                            "steamUserId": page.steamUserId || ""
                                        })
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.minimumHeight: toolsPanel.implicitHeight + 24
                            color: page.backgroundColor
                            border.color: page.borderColor
                            radius: 8
                            ColumnLayout {
                                id: toolsPanel
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12
                                spacing: 7
                                RowLayout {
                                    ModernIcon { iconName: "configure"; iconColor: page.cyanColor; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
                                    Label { text: qsTr("Disco e integridade"); color: page.textColor; font.bold: true; Layout.fillWidth: true }
                                }
                                Button {
                                    text: qsTr("Converter NSP → NSZ")
                                    icon.name: "document-export"
                                    palette.button: page.raisedColor
                                    palette.buttonText: page.textColor
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: page.minimumTouchTarget
                                    background: Rectangle {
                                        color: page.raisedColor
                                        border.color: parent.hovered || parent.activeFocus
                                            ? page.cyanColor : page.borderColor
                                        radius: 6
                                    }
                                    onClicked: page.openGameArea("advanced")
                                }
                                Button {
                                    text: qsTr("Revisar nome e metadados")
                                    icon.name: "edit-rename"
                                    palette.button: page.raisedColor
                                    palette.buttonText: page.textColor
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: page.minimumTouchTarget
                                    background: Rectangle {
                                        color: page.raisedColor
                                        border.color: parent.hovered || parent.activeFocus
                                            ? page.cyanColor : page.borderColor
                                        radius: 6
                                    }
                                    onClicked: page.openGameArea("media")
                                }
                                Button {
                                    text: qsTr("Excluir ROM…")
                                    icon.name: "edit-delete"
                                    enabled: Boolean(page.selectedGame.deleteAction)
                                    palette.button: page.raisedColor
                                    palette.buttonText: page.redColor
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: page.minimumTouchTarget
                                    Accessible.description: qsTr("A remoção exige confirmação e mantém backup transacional para rollback.")
                                    onClicked: page.dispatchAction(page.selectedGame.deleteAction)
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            color: "transparent"
                            border.color: page.borderColor
                            radius: 8
                            height: advancedHeader.height + advancedBody.height
                            property bool expanded: false
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 7
                                Item {
                                    id: advancedHeader
                                    width: parent.width
                                    height: page.minimumTouchTarget
                                    RowLayout {
                                        anchors.fill: parent
                                        spacing: 8
                                        ModernIcon {
                                            iconName: "preferences-system"
                                            iconColor: page.cyanColor
                                            Layout.preferredWidth: 20
                                            Layout.preferredHeight: 20
                                        }
                                        Label {
                                            text: qsTr("Avançado")
                                            color: page.textColor
                                            font.bold: true
                                            Layout.fillWidth: true
                                        }
                                        Label {
                                            text: parent.parent.parent.expanded ? "▲" : "▼"
                                            color: page.mutedColor
                                            font.pixelSize: 12
                                        }
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        activeFocusOnTab: true
                                        cursorShape: Qt.PointingHandCursor
                                        Accessible.role: Accessible.Button
                                        Accessible.name: parent.parent.parent.expanded
                                            ? qsTr("Recolher opções avançadas")
                                            : qsTr("Expandir opções avançadas")
                                        onClicked: parent.parent.parent.expanded = !parent.parent.parent.expanded
                                        Keys.onReturnPressed: parent.parent.parent.expanded = !parent.parent.parent.expanded
                                        Keys.onEnterPressed: parent.parent.parent.expanded = !parent.parent.parent.expanded
                                        Keys.onSpacePressed: parent.parent.parent.expanded = !parent.parent.parent.expanded
                                    }
                                }
                                ColumnLayout {
                                    id: advancedBody
                                    width: parent.width
                                    visible: parent.parent.expanded
                                    spacing: 7
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        CheckBox {
                                            id: steamAutoPubCheck
                                            checked: page.globalSettings.autoPublishSteam === true
                                            Accessible.name: qsTr("Publicar automaticamente na Steam")
                                            Layout.preferredWidth: 20
                                            onClicked: page.actionRequested({"id": "emulation.global.set-auto-publish-steam", "label": qsTr("Atualizar publicação automática"), "enabled": true, "value": checked})
                                        }
                                        Label {
                                            text: qsTr("Publicar automaticamente na Steam")
                                            color: page.textColor
                                            Layout.fillWidth: true
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                    Label {
                                        text: qsTr("Ao buscar mídia com sucesso, publica automaticamente o artwork na Steam.")
                                        color: page.mutedColor
                                        font.pixelSize: 10
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        CheckBox {
                                            id: preferNcaCheck
                                            checked: page.globalSettings.preferNativeNca !== false
                                            Accessible.name: qsTr("Preferir extração NCA nativa")
                                            Layout.preferredWidth: 20
                                            onClicked: page.actionRequested({"id": "emulation.global.set-prefer-native-nca", "label": qsTr("Atualizar preferência NCA"), "enabled": true, "value": checked})
                                        }
                                        Label {
                                            text: qsTr("Preferir extração NCA nativa como fallback de mídia")
                                            color: page.textColor
                                            Layout.fillWidth: true
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                    Label {
                                        text: qsTr("Usa o ícone extraído do arquivo NCA da ROM como fallback quando não há mídia externa.")
                                        color: page.mutedColor
                                        font.pixelSize: 10
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                        }

                        Label {
                            text: qsTr("Ações mutáveis continuam sujeitas a preview, confirmação e rollback.")
                            color: page.mutedColor
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }

    }
}
