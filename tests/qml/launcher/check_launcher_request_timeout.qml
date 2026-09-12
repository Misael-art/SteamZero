// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Um peer loopback pode aceitar TCP e depois congelar. XMLHttpRequest.timeout
// não resolve isso em todas as versões de Qt; este harness prova o watchdog
// independente da cena antes de a ponte física ser suspensa no host.
import QtQuick
import QtTest
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    Component { id: sceneComponent; LauncherMain {} }

    TestCase {
        name: "LauncherRequestTimeout"
        when: windowShown

        function test_suspended_loopback_peer_returns_actionable_timeout() {
            const scene = createTemporaryObject(sceneComponent, harness)
            verify(scene !== null)
            scene.api = "http://127.0.0.1:18169"
            scene.token = "qml-timeout-test"
            let completed = false
            let status = -1
            scene._request("GET", "/hold", null, function(resultStatus, text) {
                status = resultStatus
                completed = true
            })
            tryVerify(function() { return completed }, scene.requestTimeoutMs + 1500,
                      "ponte suspensa não pode deixar a cena em preparação")
            compare(status, 0)
        }
    }
}
