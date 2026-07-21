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
        if (areaData.cards && areaData.cards.length > 0)
            return areaData.cards
        return defaultCards(selectedArea.id)
    }

    function primaryAction() {
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
                        onClicked: page.scopeIndex = index
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

                ComboBox {
                    visible: page.scopeId() === "game" && page.width >= 1250
                    model: page.games
                    textRole: "name"
                    currentIndex: page.gameIndex
                    enabled: page.games.length > 0
                    palette.button: page.raisedColor
                    palette.buttonText: page.textColor
                    palette.base: page.raisedColor
                    palette.text: page.textColor
                    Layout.preferredWidth: 250
                    Layout.minimumHeight: 48
                    Accessible.name: qsTr("Selecionar jogo")
                    onActivated: page.gameIndex = currentIndex
                }
            }
        }

        Rectangle { color: page.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
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
                        Layout.fillWidth: true
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        Layout.minimumHeight: readinessRow.implicitHeight + 28
                        color: page.readinessPercent() >= 80 ? "#0c2a21" : "#24180b"
                        border.color: page.readinessPercent() >= 80
                            ? page.greenColor : page.amberColor
                        radius: 10

                        RowLayout {
                            id: readinessRow
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.margins: 14
                            spacing: 12

                            ModernIcon {
                                iconName: page.stateIcon(page.selectedPlatform.state)
                                iconColor: page.readinessPercent() >= 80
                                    ? page.greenColor : page.amberColor
                                Layout.preferredWidth: 30
                                Layout.preferredHeight: 30
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Label {
                                    text: page.readiness.title || qsTr("Verificando plataforma")
                                    color: page.readinessPercent() >= 80
                                        ? page.greenColor : page.amberColor
                                    font.bold: true
                                    font.pixelSize: 16
                                }
                                Label {
                                    text: page.readiness.detail || ""
                                    color: page.mutedColor
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                            ProgressBar {
                                from: 0
                                to: 100
                                value: page.readinessPercent()
                                Layout.preferredWidth: contentScroll.width < 680 ? 120 : 190
                                Accessible.name: qsTr("Prontidão da plataforma")
                                Accessible.description: qsTr("%1 por cento").arg(page.readinessPercent())
                            }
                        }
                    }

                    GridLayout {
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
                                Layout.minimumHeight: cardColumn.implicitHeight + 28
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
                                        Layout.fillWidth: true
                                    }
                                    Button {
                                        visible: Boolean(modelData.targetArea)
                                            || Boolean(modelData.action)
                                        text: modelData.action && modelData.action.label
                                            ? modelData.action.label : qsTr("Abrir área")
                                        icon.name: "go-next"
                                        enabled: Boolean(modelData.targetArea)
                                            || Boolean(modelData.action && modelData.action.enabled)
                                        palette.button: page.raisedColor
                                        palette.buttonText: page.textColor
                                        Layout.minimumHeight: 48
                                        Accessible.name: text
                                        Accessible.description: modelData.action
                                            ? modelData.action.reason || "" : ""
                                        onClicked: {
                                            if (modelData.targetArea)
                                                page.areaIndex = page.areaIndexById(modelData.targetArea)
                                            else if (modelData.action)
                                                page.dispatchAction(modelData.action)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: page.selectedArea.id === "overview"
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
                            model: page.emulators
                            delegate: Rectangle {
                                id: emulatorRow
                                required property int index
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
                                                onClicked: {
                                                    page.emulatorIndex = emulatorRow.index
                                                    page.dispatchAction(modelData)
                                                }
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
                visible: page.width >= 1120
                Layout.preferredWidth: 286
                Layout.fillHeight: true
                color: page.surfaceColor
                border.color: page.borderColor

                ColumnLayout {
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
            }
        }
    }
}
