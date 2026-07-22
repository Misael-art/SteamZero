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
        width = 1280
        height = 800
        check(compactLayout, "1280x800 deve ativar o shell compacto")
        check(navigationWidth === 72, "sidebar compacta deve ocupar 72 px")
        width = 1920
        height = 1080
        check(!compactLayout, "1920x1080 deve usar o shell desktop")
        width = 2560
        height = 1080
        check(ultrawideLayout, "2560x1080 deve ativar o perfil ultrawide")
        check(contentMaxWidth === 1400, "conteúdo ultrawide deve ser contido")

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

        performEmulationAction({"id": "keys.repair", "enabled": true})
        check(lastRequest.indexOf("Bridge local indisponível") >= 0,
              "keys.repair deve ser encaminhada ao plano de emulação")

        performEmulationAction({"id": "emulation.refresh", "enabled": true})
        check(lastRequest.indexOf("Bridge local indisponível") >= 0,
              "refresh deve usar somente o GET /status existente")

        Qt.exit(failures === 0 ? 0 : 1)
    }

    Component.onCompleted: Qt.callLater(runChecks)
}
