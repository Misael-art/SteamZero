// SPDX-License-Identifier: GPL-3.0-or-later
//
// Prova o foco, fallback e dispatch semântico da galeria; nenhum emulador é
// controlado pelo QML.
import QtQuick
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    property int failures: 0
    property int checks: 0
    property var requested: []
    property bool closed: false

    function check(condition, message) {
        checks += 1
        if (!condition) {
            failures += 1
            console.error("FAIL #" + checks + ": " + message)
        }
    }

    readonly property var readyModel: ({
        "schemaVersion": 1,
        "state": "ready",
        "available": true,
        "saveAvailable": true,
        "loadAvailable": true,
        "reason": "",
        "entries": [
            {"slot": 1, "timestamp": "2026-09-13T20:00:00Z",
             "playtimeSeconds": 600, "thumbnailUrl": "asset://save/1.png",
             "thumbnailFallback": false, "compatibility": "native",
             "available": true, "backupAvailable": true, "reason": ""},
            {"slot": 2, "timestamp": "2026-09-13T20:10:00Z",
             "playtimeSeconds": 900, "thumbnailUrl": "",
             "thumbnailFallback": true, "compatibility": "unknown",
             "available": true, "backupAvailable": false, "reason": ""}
        ]
    })

    LauncherSaveStateGallery {
        id: gallery
        anchors.fill: parent
        onSlotRequested: function(actionId, slot) {
            harness.requested.push({"actionId": actionId, "slot": slot})
        }
        onCloseRequested: harness.closed = true
    }

    Timer {
        interval: 100
        running: true
        repeat: false
        onTriggered: {
            gallery.setModel(harness.readyModel)
            gallery.openGallery("loadState")
            harness.check(gallery.visible, "a galeria disponível precisa abrir")
            harness.check(gallery.entries.length === 2, "a galeria precisa renderizar os slots")
            harness.check(gallery.selectedEntry.slot === 1, "o primeiro slot precisa receber foco")
            harness.check(gallery.activateFocused(), "slot compatível precisa aceitar seleção")
            harness.check(harness.requested.length === 1
                          && harness.requested[0].actionId === "loadState"
                          && harness.requested[0].slot === 1,
                          "a seleção precisa publicar actionId e slot")
            harness.check(gallery.move("right"), "a navegação horizontal precisa mover o foco")
            harness.check(gallery.selectedEntry.slot === 2, "o segundo slot precisa receber foco")
            gallery.mode = "saveState"
            harness.check(gallery.activateFocused(), "save-state deve aceitar um slot vazio")
            harness.check(harness.requested[1].actionId === "saveState"
                          && harness.requested[1].slot === 2,
                          "salvar deve preservar o slot selecionado")
            gallery.setModel({"state": "unavailable", "available": false,
                              "saveAvailable": false, "loadAvailable": false,
                              "reason": "O adapter não oferece save-state.", "entries": []})
            harness.check(gallery.entries.length === 0, "fallback sem mídia não pode inventar slots")
            harness.check(gallery.closeGallery(), "fechar a galeria deve ser acionável")
            harness.check(harness.closed, "fechar deve avisar o overlay")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
