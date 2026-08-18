// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 320
    height: 200
    property int failures: 0
    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    SceneContainerPreview {
        id: containers
        anchors.fill: parent
        containers: ({
            "criticalErrorZ": 90,
            "containers": {
                "previewPanel": {
                    "id": "previewPanel", "kind": "panel",
                    "x": 198, "y": 0, "width": 122, "height": 200,
                    "padding": 16, "radius": 12, "elevation": 2, "z": 10,
                    "scrim": 0, "scrimZ": 0, "blocksInput": false, "dismissible": true
                },
                "previewModal": {
                    "id": "previewModal", "kind": "modal",
                    "x": 50, "y": 40, "width": 220, "height": 120,
                    "padding": 12, "radius": 16, "elevation": 3, "z": 41,
                    "scrim": 0.6, "scrimZ": 40, "blocksInput": true, "dismissible": true
                }
            },
            "diagnostics": []
        })
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            const panel = containers.containerAt("previewPanel")
            const modal = containers.containerAt("previewModal")
            harness.check(panel !== null && modal !== null, "contêineres não chegaram ao QML")
            harness.check(containers.scrimOpacity === 0.6,
                          "scrim do modal precisa vir materializado")
            harness.check(containers.modalBlocksInput === true,
                          "bloqueio de entrada não pode ser decidido no QML")
            harness.check(containers.criticalStaysOnTop === true,
                          "modal não pode cobrir a faixa do erro crítico")
            harness.check(panel.z < modal.scrimZ,
                          "empilhamento precisa vir resolvido do domínio")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
