// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Cena raiz do AURA Launcher. Busca o modelo já resolvido na ponte local e
// entrega ao shell; o pedido de lançamento volta pelo mesmo canal.
//
// Enquanto o modelo não chega, a tela diz que está carregando. Mostrar uma home
// vazia nesse intervalo faria o usuário concluir que não tem jogos.

import QtQuick
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
    property var accessibility: ({"highContrast": false, "visualScale": 1.0, "reducedMotion": false})

    // Busca full-text: ativa no foco do campo, mostra os resultados da ponte.
    property bool searching: false
    property string searchQuery: ""
    property var searchResults: []

    function _argument(name) {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length - 1; ++i)
            if (args[i] === name)
                return args[i + 1]
        return ""
    }

    function _request(method, path, body, onDone) {
        const request = new XMLHttpRequest()
        request.open(method, root.api + path)
        request.setRequestHeader("X-SteamZero-Token", root.token)
        if (body !== null)
            request.setRequestHeader("Content-Type", "application/json")
        request.onreadystatechange = function() {
            if (request.readyState === XMLHttpRequest.DONE)
                onDone(request.status, request.responseText)
        }
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
        root._request("POST", "/launch", {"gameId": gameId, "focusId": focusId}, function() {})
    }

    Component.onCompleted: {
        root.api = _argument("--steamzero-api")
        root.token = _argument("--steamzero-token")
        if (root.api === "" || root.token === "") {
            // Sem canal não há como buscar a biblioteca nem lançar nada; dizer
            // isso é melhor do que abrir uma home permanentemente vazia.
            root.failure = "canal local ausente"
            return
        }
        _request("GET", "/model", null, function(status, text) {
            if (status !== 200) {
                root.failure = "modelo indisponível (" + status + ")"
                return
            }
            try {
                root.model = JSON.parse(text)
                if (root.model && root.model.accessibility)
                    root.accessibility = root.model.accessibility
            } catch (error) {
                root.failure = "modelo ilegível"
            }
        })
    }

    Text {
        anchors.centerIn: parent
        visible: root.model === null
        color: root.failure === "" ? "#8b93a8" : "#ff8a90"
        font.pixelSize: 16
        text: root.failure === "" ? qsTr("Carregando biblioteca…") : root.failure
    }

    // Painel de busca full-text. Aparece quando a busca está ativa; usa a
    // rota /search da ponte (que não duplica o acervo) e mostra resultados em
    // grade. Não interfere na navegação por foco da home (outra superfície).
    Rectangle {
        id: searchPanel
        anchors.fill: parent
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
        anchors.fill: parent
        active: root.model !== null
        sourceComponent: Component {
            LauncherShell {
                focusMap: root.model.focusMap
                sections: root.model.sections
                accessibility: root.accessibility
                onLaunchRequested: function(gameId, focusId) {
                    root._request("POST", "/launch",
                                  {"gameId": gameId, "focusId": focusId},
                                  function(status, text) {})
                }
                onSearchRequested: function() {
                    root.searching = true
                    searchField.forceActiveFocus()
                }
            }
        }
    }
}
