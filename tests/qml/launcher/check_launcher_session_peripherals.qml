// SPDX-License-Identifier: GPL-3.0-or-later
//
// Prova a navegação horizontal e o fallback da superfície de periféricos.
import QtQuick
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    property int failures: 0
    property var requested: []

    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    readonly property var readyModel: ({
        "schemaVersion": 1,
        "state": "ready",
        "available": true,
        "discs": [
            {"id": "disc-0", "label": "Disco 1", "index": 0,
             "inserted": true, "available": true, "compatible": true},
            {"id": "disc-1", "label": "Disco 2", "index": 1,
             "inserted": false, "available": true, "compatible": true}
        ],
        "activeDisc": 0,
        "bezels": [],
        "fade": {"phase": "return", "progress": 0.4, "durationMs": 180,
                 "reducedMotion": false}
    })

    LauncherSessionPeripherals {
        id: surface
        anchors.fill: parent
        onDiscRequested: function(discId) { harness.requested.push(discId) }
    }

    Timer {
        interval: 100
        running: true
        repeat: false
        onTriggered: {
            surface.setModel(harness.readyModel)
            surface.openSurface()
            harness.check(surface.visible, "a superfície precisa abrir")
            harness.check(surface.discs.length === 2, "os discos declarados precisam aparecer")
            harness.check(surface.selectedDisc.id === "disc-0", "o disco ativo recebe foco inicial")
            harness.check(surface.move("right"), "o carousel precisa aceitar navegação")
            harness.check(surface.selectedDisc.id === "disc-1", "a navegação chega ao disco vizinho")
            harness.check(surface.activateFocused(), "o disco compatível precisa aceitar seleção")
            harness.check(harness.requested[0] === "disc-1", "a seleção publica o id semântico")
            surface.setModel({"state": "unavailable", "available": false,
                              "discs": [], "bezels": [],
                              "reason": "O adapter não oferece troca de disco."})
            harness.check(surface.discs.length === 0, "fallback não pode inventar discos")
            harness.check(surface.closeSurface(), "a superfície precisa fechar")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
