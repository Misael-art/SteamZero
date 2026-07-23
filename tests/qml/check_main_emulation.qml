// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: false
    property int failures: 0
    property int checks: 0
    property int firstFailure: 0

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    function runChecks() {
        width = 1920
        height = 1080
        check(!compactLayout, "1920x1080 deve usar o shell desktop")
        width = 2560
        height = 1080
        check(ultrawideLayout, "2560x1080 deve ativar o perfil ultrawide")
        check(contentMaxWidth === 1400, "conteúdo ultrawide deve ser contido")
        width = 1280
        height = 800
        visible = true
        shellTimer.start()
    }

    Timer {
        id: shellTimer
        interval: 80
        onTriggered: window.runCompactChecks()
    }

    function runCompactChecks() {
        check(compactLayout, "1280x800 deve ativar o shell compacto")
        check(responsiveHeader.visible, "shell compacto deve publicar cabeçalho contextual")
        const emulationNavigation = responsiveDrawerNavigation.itemAt(1)
        const steamNavigation = responsiveDrawerNavigation.itemAt(2)
        check(emulationNavigation !== null && steamNavigation !== null,
              "drawer compacto deve manter os destinos principais")
        check(emulationNavigation.KeyNavigation.down === steamNavigation,
              "D-pad para baixo deve avançar de Emulação para Steam")
        check(emulationNavigation.Accessible.name === "Emulação",
              "item do drawer deve preservar seu nome acessível")
        desktopStatus = {
            "context": {"capabilities": [], "conflicts": [], "displays": []},
            "dashboard": {
                "accessibility": {"reducedMotion": true},
                "components": [], "steam": [], "sync": {},
                "doctor": {"checks": []},
                "uiContracts": {"schemaVersion": 1, "states": [], "actions": [], "byId": {}}
            }
        }
        check(reducedMotion && motionDuration === 0,
              "preferência reduzida do host deve remover animação do drawer")
        navigationMenuControl.forceActiveFocus(Qt.TabFocusReason)
        responsiveDrawer.open()
        drawerOpenTimer.start()
    }

    Timer {
        id: drawerOpenTimer
        interval: 80
        onTriggered: {
            window.check(window.activeFocusItem
                === window.responsiveDrawerNavigation.itemAt(window.sectionIndex),
                "drawer deve prender foco no destino atual")
            window.responsiveDrawer.close()
            drawerCloseTimer.start()
        }
    }

    Timer {
        id: drawerCloseTimer
        interval: 80
        onTriggered: window.finishChecks()
    }

    function finishChecks() {
        check(activeFocusItem === navigationMenuControl,
              "fechar drawer deve devolver foco ao botão de origem")
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
        check(lastRequest.indexOf("não publicou o contrato") >= 0,
              "keys.repair deve exigir um contrato publicado pelo backend")

        performEmulationAction({"id": "emulation.refresh", "enabled": true})
        check(lastRequest.indexOf("Bridge local indisponível") >= 0,
              "refresh deve usar somente o GET /status existente")

        Qt.exit(failures === 0 ? 0 : firstFailure)
    }

    Component.onCompleted: Qt.callLater(runChecks)
}
