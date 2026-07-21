// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: false
    property int failures: 0

    function check(condition, message) {
        if (condition)
            return
        failures += 1
        console.error("FAIL: " + message)
    }

    function runChecks() {
        performEmulationAction({
            "id": "future.mutation",
            "enabled": false,
            "reason": "Plano seguro ainda não implementado"
        })
        check(lastRequest === "Plano seguro ainda não implementado",
              "ação desabilitada deve explicar o motivo")
        check(lastRequestIsError, "ação desabilitada deve permanecer erro recuperável")

        performEmulationAction({"id": "unknown.action", "enabled": true})
        check(lastRequest.indexOf("não reconhecida") >= 0,
              "action id fora da allowlist deve ser recusado")

        performEmulationAction({"id": "emulation.refresh", "enabled": true})
        check(lastRequest.indexOf("Bridge local indisponível") >= 0,
              "refresh deve usar somente o GET /status existente")

        Qt.exit(failures === 0 ? 0 : 1)
    }

    Component.onCompleted: Qt.callLater(runChecks)
}
