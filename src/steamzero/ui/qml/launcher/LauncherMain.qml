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

    Loader {
        anchors.fill: parent
        active: root.model !== null
        sourceComponent: Component {
            LauncherShell {
                focusMap: root.model.focusMap
                sections: root.model.sections
                onLaunchRequested: function(gameId, focusId) {
                    root._request("POST", "/launch",
                                  {"gameId": gameId, "focusId": focusId},
                                  function(status, text) {})
                }
            }
        }
    }
}
