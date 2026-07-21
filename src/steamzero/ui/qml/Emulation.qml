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
    property bool gameDetailsOpen: true

    readonly property var defaultAreas: [
        {"id": "overview", "label": qsTr("Visão geral"), "icon": "view-dashboard"},
        {"id": "keysFirmware", "label": qsTr("Keys e firmware"), "icon": "document-encrypt"},
        {"id": "updatesDlc", "label": qsTr("Updates e DLC"), "icon": "download"},
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
    }

    onSelectedPlatformChanged: Qt.callLater(syncPublishedSelection)
    Component.onCompleted: syncPublishedSelection()

    function moveVerticalFocus(forward) {
        const hostWindow = page.Window.window
        const active = hostWindow ? hostWindow.activeFocusItem : null
        const next = active ? active.nextItemInFocusChain(forward) : null
        if (next)
            next.forceActiveFocus(Qt.TabFocusReason)
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
        if (!game || !game.emulatorId)
            return -1
        return emulators.findIndex(function(emulator) { return emulator.id === game.emulatorId })
    }

    function gamePlayAction(game) {
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

    function areaTitle(id) {
        if (id === "overview" && scopeId() === "global")
            return qsTr("Painel da plataforma")
        if (id === "overview" && scopeId() === "emulator")
            return qsTr("Gerenciar emulador")
        const titles = {
            "overview": qsTr("Prontidão da plataforma"),
            "keysFirmware": qsTr("Keys, firmware e compatibilidade"),
            "updatesDlc": qsTr("Updates e conteúdo adicional"),
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
        if (areaData.cards && areaData.cards.length > 0)
            return areaData.cards
        return defaultCards(selectedArea.id)
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
             "content.save.import", "content.shader.import"].indexOf(action.id) >= 0
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
        } else if (action.id === "keys.import" || action.id === "firmware.import") {
            sourceChoiceDialog.open()
        } else if (["content.update.import", "content.dlc.import",
                    "content.save.import", "content.shader.import", "nsz.convert"].indexOf(action.id) >= 0) {
            sourceFileDialog.open()
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
            "emulatorId": selectedEmulator.id || ""
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
            Layout.preferredHeight: 142
            color: page.backgroundColor

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 26
                anchors.rightMargin: 24
                anchors.topMargin: 18
                anchors.bottomMargin: 14
                spacing: 18

                Rectangle {
                    Layout.preferredWidth: 84
                    Layout.preferredHeight: 84
                    radius: 18
                    color: page.raisedColor
                    border.color: page.selectedPlatform.state === "ready"
                        ? page.greenColor : page.cyanColor
                    border.width: 2

                    SwitchPlatformMark {
                        visible: page.selectedPlatform.iconKey === "switch"
                            || page.selectedPlatform.id === "switch"
                        anchors.centerIn: parent
                        width: 62
                        height: 62
                        cutoutColor: page.raisedColor
                    }

                    ModernIcon {
                        visible: page.selectedPlatform.iconKey !== "switch"
                            && page.selectedPlatform.id !== "switch"
                        anchors.centerIn: parent
                        width: 44
                        height: 44
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
                        font.pixelSize: 12
                        font.bold: true
                        font.letterSpacing: 1.2
                    }
                    Label {
                        text: page.selectedPlatform.name || qsTr("Plataforma")
                        color: page.textColor
                        font.pixelSize: 29
                        font.bold: true
                    }
                    Label {
                        text: qsTr("Uma central para preparar, jogar e preservar sua biblioteca com segurança.")
                        color: page.mutedColor
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Label {
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
                    ComboBox {
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
                        Layout.preferredWidth: 220
                        Layout.minimumHeight: 48
                        Accessible.name: qsTr("Selecionar plataforma de emulação")
                        onActivated: {
                            page.platformIndex = currentIndex
                            page.resetContext()
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 150
                    Layout.preferredHeight: 72
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
                            font.pixelSize: 24
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
            Layout.preferredHeight: 68
            color: page.surfaceColor

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 24
                anchors.rightMargin: 24
                spacing: 10

                Label {
                    text: qsTr("Escopo")
                    color: page.mutedColor
                    font.bold: true
                    Layout.rightMargin: 4
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
                        Layout.preferredWidth: Math.max(112, implicitWidth + 12)
                        Layout.minimumHeight: 48
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
                            spacing: 8
                            ModernIcon {
                                iconName: page.visualIcon(modelData.icon || modelData.iconKey)
                                iconColor: parent.parent.checked ? page.cyanColor : page.mutedColor
                                Layout.preferredWidth: 19
                                Layout.preferredHeight: 19
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

                ComboBox {
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
                    onActivated: page.emulatorIndex = currentIndex
                }

            }
        }

        Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                visible: !page.isGameLibrary()
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
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                background: Rectangle { color: page.backgroundColor }

                ColumnLayout {
                    width: contentScroll.availableWidth
                    spacing: 16

                    ColumnLayout {
                        visible: page.isGameLibrary()
                        Layout.fillWidth: true
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        Layout.topMargin: 16
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
                                    text: qsTr("%1 de %2 jogo(s) • selecione uma linha para abrir os ajustes")
                                        .arg(page.filteredGames().length).arg(page.games.length)
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
                                Layout.minimumHeight: 44
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
                                Layout.minimumHeight: 44
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
                                Layout.minimumHeight: 44
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
                                    Layout.minimumHeight: 38
                                    Accessible.name: qsTr("Ordenar por %1").arg(modelData.label)
                                    onClicked: page.setGameSort(modelData.key)
                                }
                            }
                            Item { Layout.fillWidth: true }
                            Label {
                                text: qsTr("Dados ausentes aparecem como —")
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
                                Label { visible: contentScroll.width >= 760; text: qsTr("REQUISITOS"); color: page.mutedColor; font.pixelSize: 10; font.bold: true; Layout.preferredWidth: 118 }
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
                                            source: gameRow.modelData.bannerAsset || ""
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
                                                    Layout.preferredWidth: compatibilityText.implicitWidth + 16
                                                    Layout.preferredHeight: 22
                                                    color: "transparent"
                                                    border.color: page.compatibilityColor(compatibility)
                                                    radius: 10
                                                    Label {
                                                        id: compatibilityText
                                                        anchors.centerIn: parent
                                                        text: modelData.name + " • "
                                                            + page.compatibilityLabel(parent.compatibility)
                                                        color: page.compatibilityColor(parent.compatibility)
                                                        font.pixelSize: 9
                                                        font.bold: true
                                                    }
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
                                                : qsTr("FW mínimo —")
                                            color: page.mutedColor
                                            font.pixelSize: 10
                                        }
                                        Label {
                                            text: gameRow.modelData.region || qsTr("Região —")
                                            color: page.mutedColor
                                            font.pixelSize: 10
                                        }
                                    }

                                    ComboBox {
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
                                        Layout.minimumHeight: 40
                                        Accessible.name: qsTr("Emulador padrão de %1").arg(gameRow.modelData.name)
                                        Accessible.description: qsTr("Define qual emulador será usado pelo botão Jogar e pelo atalho da Steam.")
                                        onActivated: {
                                            page.selectGame(gameRow.modelData)
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
                                            Layout.minimumHeight: 40
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
                                            Layout.minimumHeight: 40
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
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        Layout.topMargin: 20
                        spacing: 5

                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: page.areaTitle(page.selectedArea.id)
                                color: page.textColor
                                font.pixelSize: 24
                                font.bold: true
                                Layout.fillWidth: true
                            }
                            Label {
                                text: page.contextTitle()
                                visible: page.width >= 1250
                                    || (page.scopeId() !== "emulator" && page.scopeId() !== "game")
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
                            ComboBox {
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
                                onActivated: page.emulatorIndex = currentIndex
                            }
                            ComboBox {
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
                        visible: !page.isGameLibrary()
                        Layout.fillWidth: true
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        Layout.preferredHeight: 64
                        Layout.minimumHeight: 64
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
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        columns: contentScroll.width >= 760 ? 2 : 1
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
                                    ? 184 : cardColumn.implicitHeight + 28
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
                                    anchors.margins: 14
                                    spacing: 8

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
                                                Layout.minimumHeight: 40
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
                            text: qsTr("Manutenção do emulador selecionado")
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
                            model: page.emulators.length > 0 ? [page.selectedEmulator] : []
                            delegate: Rectangle {
                                id: emulatorRow
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.minimumHeight: 72
                                color: page.surfaceColor
                                border.color: page.borderColor
                                radius: 9
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
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
                                        Label { text: modelData.name; color: page.textColor; font.bold: true }
                                        Label {
                                            text: modelData.specialty || modelData.description || qsTr("Capacidades ainda não publicadas")
                                            color: page.mutedColor
                                            font.pixelSize: 12
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                    }
                                    Label {
                                        text: modelData.statusLabel || qsTr("Desconhecido")
                                        color: page.stateColor(modelData.state)
                                        font.bold: true
                                    }
                                    RowLayout {
                                        spacing: 6
                                        Repeater {
                                            model: modelData.actions && modelData.actions.length > 0
                                                ? modelData.actions : [modelData.action]
                                            delegate: Button {
                                                required property var modelData
                                                text: modelData && modelData.label
                                                    ? modelData.label : qsTr("Detalhes")
                                                enabled: Boolean(modelData)
                                                    && modelData.enabled !== false
                                                palette.button: page.raisedColor
                                                palette.buttonText: page.textColor
                                                Layout.minimumHeight: 48
                                                Accessible.name: qsTr("%1: %2").arg(text)
                                                    .arg(emulatorRow.modelData.name)
                                                onClicked: page.dispatchAction(modelData)
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
                visible: page.isGameLibrary()
                    ? page.gameDetailsOpen && page.width >= 900 : page.width >= 1120
                Layout.preferredWidth: page.isGameLibrary()
                    ? (page.width < 1200 ? 340 : 360) : 286
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
                            ComboBox {
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
                                Layout.minimumHeight: 42
                                Accessible.description: qsTr("Preferência persistente usada pelo lançamento direto e pela Steam.")
                                onActivated: page.dispatchAction({
                                    "id": "game.emulator.set",
                                    "label": qsTr("Definir emulador do jogo"),
                                    "enabled": true,
                                    "requiresConfirmation": true,
                                    "gameId": page.selectedGame.id,
                                    "emulatorId": page.emulators[currentIndex].id
                                })
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
                                    Layout.minimumHeight: 42
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
                                        Layout.minimumHeight: 42
                                        onClicked: page.openGameArea("updatesDlc")
                                    }
                                    Button {
                                        text: qsTr("Mods")
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: 42
                                        enabled: false
                                        Accessible.description: qsTr("Gerenciador de mods ainda não publicado.")
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
                                        Layout.minimumHeight: 42
                                        onClicked: page.openGameArea("saves")
                                    }
                                    Button {
                                        text: qsTr("Cache")
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.fillWidth: true
                                        Layout.minimumHeight: 42
                                        onClicked: page.openGameArea("shaderCache")
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
                                    Layout.minimumHeight: 42
                                    onClicked: page.openGameArea("advanced")
                                }
                                Button {
                                    text: qsTr("Revisar nome e metadados")
                                    icon.name: "edit-rename"
                                    palette.button: page.raisedColor
                                    palette.buttonText: page.textColor
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 42
                                    onClicked: page.openGameArea("media")
                                }
                                Button {
                                    text: qsTr("Excluir ROM…")
                                    icon.name: "edit-delete"
                                    enabled: Boolean(page.selectedGame.deleteAction)
                                    palette.button: page.raisedColor
                                    palette.buttonText: page.redColor
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 42
                                    Accessible.description: qsTr("A remoção exige confirmação e mantém backup transacional para rollback.")
                                    onClicked: page.dispatchAction(page.selectedGame.deleteAction)
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
