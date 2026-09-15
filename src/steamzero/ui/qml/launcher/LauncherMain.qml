// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Cena raiz do AURA Launcher. Busca o modelo já resolvido na ponte local e
// entrega ao shell; o pedido de lançamento volta pelo mesmo canal.
//
// Enquanto o modelo não chega, a tela diz que está carregando. Mostrar uma home
// vazia nesse intervalo faria o usuário concluir que não tem jogos.

import QtQuick
import QtQuick.Controls
import QtQuick.Window

Window {
    id: root
    visible: true
    visibility: Window.FullScreen
    title: "SteamZero"
    color: "#071019"

    property string api: ""
    property string token: ""
    property var model: null
    property string failure: ""
    property var cinemaScene: null
    property int cinemaRequest: 0
    // A ponte é local; três segundos distinguem indisponibilidade de uma
    // operação normal sem deixar a cena presa se o processo for suspenso.
    readonly property int requestTimeoutMs: 3000
    property string perfReportUrl: ""
    property bool perfReported: false
    property bool perfWarm: false
    property real perfStartedAt: Date.now()
    property real perfFirstFrameAt: 0
    property var perfSamples: []

    function reportPerformance() {
        if (root.perfReportUrl === "" || root.perfReported)
            return
        root.perfReported = true
        const request = new XMLHttpRequest()
        request.open("POST", root.perfReportUrl)
        request.setRequestHeader("Content-Type", "application/json")
        request.send(JSON.stringify({
            "samples": root.perfSamples,
            "startupMs": root.perfFirstFrameAt > 0
                ? root.perfFirstFrameAt - root.perfStartedAt : null,
            "surface": root.width + "x" + root.height
        }))
    }

    FrameAnimation {
        id: perfFrames
        running: root.perfReportUrl !== "" && !root.perfReported
        onTriggered: {
            if (root.perfFirstFrameAt === 0)
                root.perfFirstFrameAt = Date.now()
            if (root.perfWarm)
                root.perfSamples.push(frameTime * 1000.0)
        }
    }

    Timer {
        id: perfWarmup
        interval: 2000
        running: root.perfReportUrl !== ""
        repeat: false
        onTriggered: root.perfWarm = true
    }

    Timer {
        id: perfReport
        interval: 8000
        running: root.perfReportUrl !== ""
        repeat: false
        onTriggered: root.reportPerformance()
    }

    function refreshCinema() {
        const shell = root._activeLauncherShell()
        if (!shell || root.api === "" || root.token === "")
            return
        const focusId = shell.homeFocus
        const requestId = ++root.cinemaRequest
        root._request("GET", "/cinema?focus=" + encodeURIComponent(focusId)
                      + "&width=" + root.width + "&height=" + root.height,
                      null, function(status, text) {
            if (requestId !== root.cinemaRequest || shell.homeFocus !== focusId)
                return
            if (status !== 200) {
                root.cinemaScene = null
                return
            }
            try {
                const scene = JSON.parse(text)
                root.cinemaScene = scene.focusId === focusId
                    && scene.layouts && scene.layouts.covers ? scene : null
            } catch (error) {
                root.cinemaScene = null
            }
        })
    }
    onWidthChanged: cinemaRefresh.restart()
    onHeightChanged: cinemaRefresh.restart()
    Timer {
        id: cinemaRefresh
        interval: 16
        onTriggered: root.refreshCinema()
    }
    property var accessibility: ({"highContrast": false, "visualScale": 1.0, "reducedMotion": false})

    // Busca full-text: ativa no foco do campo, mostra os resultados da ponte.
    property bool searching: false
    property string searchQuery: ""
    property var searchResults: []

    function _activeLauncherShell() {
        return launcherLoader && launcherLoader.item ? launcherLoader.item : null
    }

    property bool sessionPollPending: false
    property int launchGeneration: 0
    // requestId do POST atual: é ele que autoriza o shell a aceitar uma falha
    // sem sessionId — resposta de tentativa antiga não altera pedido novo.
    property string launchRequestId: ""

    // O overlay é uma superfície de leitura/ação sobre a sessão canônica. O
    // QML não decide capabilities nem executa o emulador: apenas pede o
    // read model e envia a tripla autenticada ao bridge.
    property bool sessionOverlayOpen: false
    property bool sessionOverlayPending: false
    property int sessionOverlayGeneration: 0
    property string sessionOverlayGameId: ""
    property var sessionOverlayModel: null
    property string sessionOverlayError: ""

    function _overlayErrorText(status, text) {
        if (status === 0)
            return qsTr("AURA-OSD-BRIDGE-OFFLINE-001\nA ponte local não respondeu. Tente novamente.")
        try {
            const payload = JSON.parse(text)
            const error = payload && payload.error
            if (error && typeof error === "object" && error.code) {
                return [error.code, error.detail || error.message || error.what,
                        error.impact, error.nextAction || error.action]
                    .filter(function(value) { return typeof value === "string" && value.length > 0 })
                    .join("\n")
            }
        } catch (error) {}
        return qsTr("AURA-OSD-BRIDGE-ERROR-002\nA sessão não pôde ser consultada (%1).").arg(status)
    }

    function refreshSessionOverlay() {
        if (!root.sessionOverlayOpen || root.sessionOverlayPending
                || root.sessionOverlayGameId === "")
            return false
        const generation = ++root.sessionOverlayGeneration
        root.sessionOverlayPending = true
        root._request("GET", "/session?gameId="
                      + encodeURIComponent(root.sessionOverlayGameId) + "&overlay=1",
                      null, function(status, text) {
            if (generation !== root.sessionOverlayGeneration)
                return
            root.sessionOverlayPending = false
            if (status !== 200) {
                root.sessionOverlayError = root._overlayErrorText(status, text)
                root.sessionOverlayModel = null
                return
            }
            try {
                const payload = JSON.parse(text)
                root.sessionOverlayModel = payload && payload.overlay
                    ? payload.overlay : null
                root.sessionOverlayError = root.sessionOverlayModel === null
                    ? qsTr("AURA-OSD-RESPONSE-003\nA ponte não publicou o modelo do overlay.") : ""
                sessionOverlay.setModel(root.sessionOverlayModel)
            } catch (error) {
                root.sessionOverlayModel = null
                root.sessionOverlayError = qsTr("AURA-OSD-RESPONSE-004\nA resposta do overlay está ilegível.")
            }
        })
        return true
    }

    function openSessionOverlay(gameId) {
        const shell = root._activeLauncherShell()
        const requested = String(gameId || (shell ? shell.sessionGameId : ""))
        root.sessionOverlayGameId = requested
        root.sessionOverlayError = requested === ""
            ? qsTr("AURA-OSD-SESSION-001\nNenhuma sessão ativa foi identificada.") : ""
        root.sessionOverlayModel = null
        root.sessionOverlayOpen = true
        sessionOverlay.forceActiveFocus()
        if (requested !== "")
            root.refreshSessionOverlay()
        return requested !== ""
    }

    function closeSessionOverlay() {
        ++root.sessionOverlayGeneration
        root.sessionOverlayPending = false
        root.sessionOverlayOpen = false
        root.sessionOverlayError = ""
        root.sessionOverlayModel = null
        const shell = root._activeLauncherShell()
        if (shell)
            shell.forceActiveFocus()
    }

    function toggleSessionOverlay() {
        if (root.sessionOverlayOpen) {
            root.closeSessionOverlay()
            return true
        }
        const shell = root._activeLauncherShell()
        if (!shell || root.model === null || shell.sessionGameId === ""
                || (shell.launchState !== "launching"
                    && shell.launchState !== "emulator-visible"))
            return false
        return root.openSessionOverlay(shell.sessionGameId)
    }

    function dispatchSessionOverlayAction(actionId, slot, discId) {
        if (root.sessionOverlayPending || !root.sessionOverlayModel)
            return false
        const model = root.sessionOverlayModel
        if (!model.sessionId || !model.gameId)
            return false
        root.sessionOverlayPending = true
        root.sessionOverlayError = ""
        const request = {
            "gameId": String(model.gameId),
            "sessionId": String(model.sessionId),
            "actionId": String(actionId)
        }
        if (slot !== undefined && Number(slot) >= 0)
            request.slot = Number(slot)
        if (discId !== undefined && String(discId) !== "")
            request.discId = String(discId)
        root._request("POST", "/session/action", request, function(status, text) {
            root.sessionOverlayPending = false
            if (status !== 200) {
                root.sessionOverlayError = root._overlayErrorText(status, text)
                return
            }
            sessionOverlay.closeSaveGallery()
            sessionOverlay.closePeripheralSurface()
            root.refreshSessionOverlay()
        })
        return true
    }

    Timer {
        interval: 1000
        repeat: true
        running: root.sessionOverlayOpen && !root.sessionOverlayPending
        onTriggered: root.refreshSessionOverlay()
    }

    Shortcut {
        sequence: "F1"
        enabled: root.model !== null && !root.searching
        onActivated: root.toggleSessionOverlay()
    }

    Shortcut {
        sequence: "Menu"
        enabled: root.model !== null && !root.searching
        onActivated: root.toggleSessionOverlay()
    }

    function pollSession() {
        const shell = root._activeLauncherShell()
        if (!shell || root.sessionPollPending || !shell.sessionGameId)
            return
        const generation = root.launchGeneration
        root.sessionPollPending = true
        root._request("GET", "/session?gameId=" + encodeURIComponent(shell.sessionGameId),
                      null, function(status, text) {
            root.sessionPollPending = false
            if (generation !== root.launchGeneration || status !== 200)
                return
            try {
                shell.observeSession(JSON.parse(text))
            } catch (error) {}
        })
    }

    Timer {
        interval: 400
        repeat: true
        running: {
            const shell = root._activeLauncherShell()
            return shell !== null && (shell.launchState === "launching"
                                      || shell.launchState === "emulator-visible")
        }
        onTriggered: root.pollSession()
    }

    // Alt+Tab can activate the Launcher while the game is still running.
    // Only a terminal record from the lifecycle owner triggers the return.
    onActiveChanged: {
        if (active)
            root.pollSession()
        if (active && root.sessionOverlayOpen)
            root.refreshSessionOverlay()
    }

    function _argument(name) {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length - 1; ++i)
            if (args[i] === name)
                return args[i + 1]
        return ""
    }

    // Qt's XMLHttpRequest.timeout is not reliable while a loopback peer has
    // accepted the connection but is suspended. Keep the deadline in the
    // scene graph as well: a frozen bridge must return control to the user.
    Component {
        id: requestWatchdogComponent
        Timer { repeat: false }
    }

    function _request(method, path, body, onDone) {
        if (root.api === "" || root.token === "") {
            // Sem canal não há requisição válida; chamar `open` com URL vazia
            // travaria o XMLHttpRequest. O estado já foi marcado como offline
            // em `_start`; aqui apenas sinalizamos para o callback.
            onDone(0, "")
            return
        }
        const request = new XMLHttpRequest()
        const watchdog = requestWatchdogComponent.createObject(root, {
            "interval": root.requestTimeoutMs
        })
        let completed = false
        function finish(status, text) {
            if (completed)
                return
            completed = true
            if (watchdog !== null) {
                watchdog.stop()
                watchdog.destroy()
            }
            onDone(status, text)
        }
        if (watchdog !== null) {
            watchdog.triggered.connect(function() { finish(0, "") })
            watchdog.start()
        }
        request.open(method, root.api + path)
        request.timeout = root.requestTimeoutMs
        request.setRequestHeader("X-SteamZero-Token", root.token)
        if (body !== null)
            request.setRequestHeader("Content-Type", "application/json")
        request.onreadystatechange = function() {
            if (request.readyState === XMLHttpRequest.DONE)
                finish(request.status, request.responseText)
        }
        request.onerror = function() { finish(0, "") }
        request.ontimeout = function() { finish(0, "") }
        request.send(body === null ? undefined : JSON.stringify(body))
    }

    function _search() {
        const q = root.searchQuery.trim()
        if (q === "") {
            root.searchResults = []
            return
        }
        root._request("GET", "/search?q=" + encodeURIComponent(q), null, function(status, text) {
            if (status !== 200)
                return
            try {
                const payload = JSON.parse(text)
                root.searchResults = payload.games || []
            } catch (error) {
                root.searchResults = []
            }
        })
    }

    function _launchSearch(gameId, focusId) {
        const shell = root._activeLauncherShell()
        if (!shell || !root.model || !root.model.sections)
            return false
        // Search is another entry to the same launch state machine. Save a
        // real focus node, not a synthetic search id absent from the home map.
        for (let s = 0; s < root.model.sections.length; ++s) {
            const section = root.model.sections[s]
            const nodeId = section.id + ":" + gameId
            if (!root.model.focusMap.nodes[nodeId])
                continue
            shell.homeFocus = nodeId
            if (!shell.openGame(gameId))
                return false
            root.searching = false
            return shell.launchFocused()
        }
        return false
    }

    function launchErrorText(status, text) {
        if (status === 0)
            return qsTr("LAUNCHER-BRIDGE-OFFLINE-001\nA ponte local do SteamZero não respondeu. O jogo não foi iniciado.\nVolte e tente novamente; se persistir, abra a central para verificar o serviço.")
        try {
            const payload = JSON.parse(text)
            const error = payload.error
            if (error && typeof error === "object" && error.code) {
                const explanation = error.detail || error.what
                    || error.probableCause || error.cause
                const recovery = error.manualAction || error.action || error.nextAction
                return [error.code, explanation, error.impact, recovery]
                    .filter(function(value) { return typeof value === "string" && value.length > 0 })
                    .join("\n")
            }
        } catch (error) {}
        return qsTr("LAUNCHER-LAUNCH-FAILED-001\nO início do jogo não foi confirmado (%1). Verifique a conexão local e tente novamente.").arg(status)
    }

    function _resolveGamePage(gameId) {
        if (!root.model || !root.model.sections)
            return null
        for (let s = 0; s < root.model.sections.length; ++s) {
            const section = root.model.sections[s]
            if (!section || !section.items)
                continue
            for (let i = 0; i < section.items.length; ++i) {
                const item = section.items[i]
                if (String(item.id) !== String(gameId))
                    continue
                return {
                    "gameId": String(item.id),
                    "title": String(item.title || item.id),
                    "platform": String(section.title || section.id),
                    "coverUrl": String(item.coverUrl || ""),
                    "description": String(item.description || ""),
                    "releaseDate": String(item.releaseDate || ""),
                    "developer": String(item.developer || ""),
                    "publisher": String(item.publisher || ""),
                    "ageRating": String(item.ageRating || ""),
                    "genres": Array.isArray(item.genres) ? item.genres.slice(0, 16) : [],
                    "players": item.players !== undefined ? Number(item.players) : undefined,
                    "rating": item.rating !== undefined ? Number(item.rating) : undefined,
                    "playtime": item.playtime !== undefined ? Number(item.playtime) : undefined,
                    "fanartUrl": String(item.fanartUrl || ""),
                    "logoUrl": String(item.logoUrl || ""),
                    "iconUrl": String(item.iconUrl || ""),
                    "screenshotUrl": String(item.screenshotUrl || ""),
                    "screenshotUrls": Array.isArray(item.screenshotUrls)
                        ? item.screenshotUrls.slice(0, 8) : [],
                    "requirements": Array.isArray(item.requirements)
                        ? item.requirements.slice(0, 16) : [],
                    "controls": Array.isArray(item.controls)
                        ? item.controls.slice(0, 16) : [],
                    "metadata": item,
                    "lastPlayed": null,
                    "initialFocus": "action:play",
                    "actions": [
                        {"id": "play", "focusId": "action:play", "label": qsTr("Jogar"),
                         "enabled": true, "reason": ""}
                    ]
                }
            }
        }
        return null
    }

    // Estados acionáveis do fluxo: loading, error, offline, ready.
    property string loadState: "loading"

    function _start() {
        if (root.api === "" || root.token === "") {
            // Sem canal não há como buscar a biblioteca nem lançar nada; dizer
            // isso é melhor do que abrir uma home permanentemente vazia.
            root.failure = "canal local ausente"
            root.loadState = "offline"
            return
        }
        root.loadState = "loading"
        root.failure = ""
        _request("GET", "/model", null, function(status, text) {
            if (status !== 200) {
                root.failure = "modelo indisponível (" + status + ")"
                root.loadState = "error"
                return
            }
            try {
                root.model = JSON.parse(text)
                if (root.model && root.model.accessibility)
                    root.accessibility = root.model.accessibility
                root.loadState = "ready"
            } catch (error) {
                root.failure = "modelo ilegível"
                root.loadState = "error"
            }
        })
    }

    function _retry() {
        root.model = null
        root._start()
    }

    Component.onCompleted: {
        root.api = _argument("--steamzero-api")
        root.token = _argument("--steamzero-token")
        root.perfReportUrl = _argument("--steamzero-perf-url")
        root._start()
    }

    Text {
        anchors.centerIn: parent
        visible: root.model === null
        color: root.loadState === "offline" || root.loadState === "error" ? "#ff8a90" : "#8b93a8"
        font.pixelSize: 16
        text: root.loadState === "loading"
            ? qsTr("Carregando biblioteca…")
            : (root.loadState === "offline"
                ? qsTr("Canal local ausente — o daemon do SteamZero não está acessível.")
                : root.failure)
    }

    Rectangle {
        anchors.centerIn: parent
        visible: root.loadState === "offline" || root.loadState === "error"
        objectName: "launcherRetry"
        width: 200
        height: 44
        radius: 8
        color: "#0b1622"
        border.width: 1
        border.color: "#243044"
        Accessible.name: qsTr("Tentar novamente")
        Accessible.role: Accessible.Button
        Accessible.description: qsTr("Recarregar a biblioteca do SteamZero")
        // Estado acionável: o usuário não fica preso numa tela de erro sem
        // saída — pode pedir de novo (retry) e voltar ao fluxo.
        Text {
            anchors.centerIn: parent
            text: qsTr("Tentar novamente")
            color: "#f2f6fb"
            font.pixelSize: 14
        }
        TapHandler { onTapped: root._retry() }
        Keys.onReturnPressed: root._retry()
        Keys.onEnterPressed: root._retry()
        Keys.onSpacePressed: root._retry()
        focus: root.loadState === "offline" || root.loadState === "error"
        activeFocusOnTab: true
    }

    // Painel de busca full-text. Aparece quando a busca está ativa; usa a
    // rota /search da ponte (que não duplica o acervo) e mostra resultados em
    // grade. Não interfere na navegação por foco da home (outra superfície).
    Rectangle {
        id: searchPanel
        anchors.fill: parent
        // The shell Loader is declared later; search must remain above it.
        z: 20
        visible: root.searching
        color: "#0b1020ee"
        focus: root.searching

        Column {
            anchors.fill: parent
            anchors.margins: 40
            spacing: 16

            Text {
                text: qsTr("Buscar na biblioteca")
                color: "#cbd5e1"
                font.pixelSize: 24
            }

            TextField {
                id: searchField
                objectName: "launcherSearchField"
                width: parent.width
                height: 48
                placeholderText: qsTr("Digite o nome do jogo…")
                color: "#f2f6fb"
                placeholderTextColor: "#8b93a8"
                text: root.searchQuery
                onTextChanged: {
                    root.searchQuery = text
                    root._search()
                }
                Keys.onEscapePressed: { root.searching = false; root.searchQuery = ""; root.searchResults = [] }
                Keys.onReturnPressed: {
                    if (root.searchResults.length > 0)
                        root._launchSearch(root.searchResults[0].id, "search:" + root.searchResults[0].id)
                }
            }

            Text {
                visible: root.searchQuery.trim() !== "" && root.searchResults.length === 0
                text: qsTr("Nenhum jogo encontrado para \"%1\"").arg(root.searchQuery)
                color: "#8b93a8"
                font.pixelSize: 14
            }

            Grid {
                width: parent.width
                columns: Math.max(3, Math.floor(searchPanel.width / 260))
                spacing: 12
                Repeater {
                    model: root.searchResults
                    delegate: Rectangle {
                        required property var modelData
                        objectName: "launcherSearchItem"
                        width: Math.min((searchPanel.width - 40) / Math.max(3, Math.floor(searchPanel.width / 260)) - 12, 280)
                        height: 132
                        radius: 10
                        color: "#0b1622"
                        clip: true
                        MouseArea {
                            anchors.fill: parent
                            onClicked: root._launchSearch(modelData.id, "search:" + modelData.id)
                        }
                        Image {
                            anchors.fill: parent
                            visible: !!modelData.coverUrl
                            source: modelData.coverUrl || ""
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            sourceSize.width: width * 2
                            sourceSize.height: height * 2
                        }
                        Text {
                            anchors.fill: parent
                            anchors.bottomMargin: 6
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            verticalAlignment: Text.AlignBottom
                            text: modelData.title
                            color: "#f2f6fb"
                            font.pixelSize: 13
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }
    }

    Loader {
        id: launcherLoader
        anchors.fill: parent
        active: root.model !== null
        // Um `Loader` só repassa foco ao item carregado se ele próprio o tiver.
        // Sem isto o shell nascia sem foco de teclado e nenhuma tecla chegava
        // aos handlers — só um clique de mouse destravava. No Game Mode do Deck
        // não existe mouse, então o Launcher abria inoperável.
        // A condição espelha os outros dois pretendentes a foco desta cena (o
        // botão de retry e o painel de busca) para que nenhum roube o do outro.
        focus: root.model !== null && !root.searching
               && root.loadState !== "offline" && root.loadState !== "error"
        sourceComponent: Component {
            LauncherShell {
                id: launcherShell
                focusMap: root.model.focusMap
                sections: root.model.sections
                catalogSummary: root.model.catalogSummary || ({})
                cinemaScene: root.cinemaScene
                onHomeFocusChanged: cinemaRefresh.restart()
                Component.onCompleted: cinemaRefresh.restart()
                accessibility: root.accessibility
                resolveGamePage: function(gameId) { return root._resolveGamePage(gameId) }
                returnContext: root.model.returnContext || null
                onLaunchRequested: function(gameId, focusId) {
                    ++root.launchGeneration
                    root._request("POST", "/launch",
                                  {"gameId": gameId, "focusId": focusId},
                                  function(status, text) {
                                      if (status === 200) {
                                          try {
                                              const payload = JSON.parse(text)
                                              root.launchRequestId = payload
                                                  && payload.requestId
                                                  ? String(payload.requestId) : ""
                                          } catch (error) {
                                              root.launchRequestId = ""
                                          }
                                          launcherShell.expectedRequestId = root.launchRequestId
                                          root.pollSession()
                                      } else if (status === 204) {
                                          // Ponte sem contrato de recibo (release
                                          // anterior): a sessão canônica segue sendo
                                          // a única fonte de confirmação.
                                          root.pollSession()
                                      } else {
                                          launcherShell.failLaunch(
                                              root.launchErrorText(status, text))
                                      }
                                  })
                }
                onSearchRequested: function() {
                    root.searching = true
                    searchField.forceActiveFocus()
                }
                onActionRequested: function(actionId) {
                    if (actionId === "library.add" || actionId === "library.retry")
                        root._retry()
                }
            }
        }
    }

    LauncherSessionOverlay {
        id: sessionOverlay
        anchors.fill: parent
        overlayOpen: root.sessionOverlayOpen
        overlayModel: root.sessionOverlayModel
        gameTitle: {
            const shell = root._activeLauncherShell()
            return shell && shell.gamePage ? String(shell.gamePage.title || "") : ""
        }
        accessibility: root.accessibility
        requestPending: root.sessionOverlayPending
        bridgeError: root.sessionOverlayError
        onActionRequested: function(actionId) {
            root.dispatchSessionOverlayAction(actionId)
        }
        onSaveStateRequested: function(actionId, slot) {
            root.dispatchSessionOverlayAction(actionId, slot)
        }
        onDiscRequested: function(discId) {
            root.dispatchSessionOverlayAction("disc", undefined, discId)
        }
        onCloseRequested: root.closeSessionOverlay()
    }
}
