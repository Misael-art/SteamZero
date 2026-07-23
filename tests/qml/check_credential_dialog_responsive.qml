// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 949
    height: 593

    property int failures: 0
    property int checks: 0
    property int firstFailure: 0
    property int viewportIndex: 0
    property int phase: 0
    readonly property var viewports: [
        {"width": 949, "height": 593},
        {"width": 1280, "height": 800}
    ]
    readonly property var providersFixture: [
        {
            "id": "screenscraper",
            "name": "ScreenScraper",
            "description": "Credenciais de integração e conta pessoal opcional.",
            "enabled": true,
            "configured": false,
            "credentialState": "notConfigured",
            "credentialTestSupported": true,
            "credentialRevokeSupported": true,
            "credentialFields": [
                {"id": "devid", "label": "Developer ID", "secret": false,
                 "required": true, "help": "Integração"},
                {"id": "devpassword", "label": "Developer password", "secret": true,
                 "required": true, "help": "Integração"},
                {"id": "ssid", "label": "Usuário", "secret": false,
                 "required": false, "help": "Conta pessoal"},
                {"id": "sspassword", "label": "Senha", "secret": true,
                 "required": false, "help": "Conta pessoal"}
            ],
            "links": {}
        },
        {
            "id": "steam-local",
            "name": "Integração local com Steam",
            "description": "Nenhuma credencial necessária.",
            "enabled": true,
            "configured": true,
            "credentialState": "local",
            "credentialFields": [],
            "links": {}
        }
    ]

    desktopStatus: ({
        "truthState": "ready",
        "desiredProfile": "handheld-desktop",
        "appliedProfile": "handheld-desktop",
        "observedProfile": "handheld-desktop",
        "recommendedProfile": "handheld-desktop",
        "statusReasons": [],
        "recoveryRequired": false,
        "context": {"deviceKind": "deck-lcd", "displays": [], "conflicts": []},
        "dashboard": {"accessibility": {"reducedMotion": true}, "components": [],
                      "steam": [], "doctor": {"checks": []}}
    })

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    function beginViewport() {
        const viewport = viewports[viewportIndex]
        width = viewport.width
        height = viewport.height
        navigationMenuControl.forceActiveFocus(Qt.TabFocusReason)
        credentialDialogControl.providers = providersFixture
        credentialDialogControl.open()
        phase = 1
    }

    function verifyDialog() {
        const dialog = credentialDialogControl
        const scroll = credentialScrollControl
        const card = credentialProviderRepeaterControl.itemAt(0)
        check(dialog.visible, "diálogo de credenciais deve abrir")
        check(dialog.width <= width - 48 && dialog.height <= height - 32,
              "diálogo deve caber no viewport " + width + "x" + height)
        check(scroll && scroll.contentItem,
              "credenciais devem usar ScrollView real")
        check(scroll.contentItem.contentHeight > scroll.height,
              "quatro campos devem exigir rolagem vertical real")
        check(scroll.contentItem.contentWidth <= scroll.availableWidth + 1,
              "diálogo não pode produzir overflow horizontal")
        check(card && card.fieldRepeaterControl.count === 4,
              "campos do provider devem permanecer isolados")
        if (card) {
            const first = card.fieldRepeaterControl.itemAt(0)
            check(first.inputControl.height >= 48,
                  "TextField deve manter alvo mínimo 48×48")
            check(first.keyboardControl.height >= 48,
                  "teclado virtual deve ter alvo mínimo 48×48")
            first.inputControl.forceActiveFocus(Qt.TabFocusReason)
            dialog.moveFocus(true)
            check(window.activeFocusItem !== first.inputControl,
                  "D-pad para baixo deve avançar o foco")
        }
        credentialCloseControl.forceActiveFocus(Qt.TabFocusReason)
        ensureFocusedItemVisible(credentialCloseControl)
        const closeBottom = credentialCloseControl.mapToItem(
            scroll.contentItem, 0, credentialCloseControl.height).y
        check(closeBottom <= scroll.contentItem.contentY + scroll.height + 1,
              "último controle deve ficar visível acima da borda inferior")
        dialog.closeFromBack()
        phase = 2
    }

    function finishViewport() {
        check(activeFocusItem === navigationMenuControl,
              "fechar com B/Escape deve devolver foco ao invocador")
        requestAction("missing.fixture.contract", {}, function() {}, function(message) {})
        check(taskItems.length > 0 && taskItems[0].type === "ui.action"
              && taskItems[0].state === "failed",
              "falha de ação deve aparecer também na Central de tarefas")
        viewportIndex += 1
        if (viewportIndex >= viewports.length) {
            console.log("credential-dialog checks=" + checks
                        + " failures=" + failures)
            Qt.exit(failures === 0 ? 0 : firstFailure)
            return
        }
        beginViewport()
    }

    Timer {
        interval: 60
        running: true
        repeat: true
        onTriggered: {
            if (phase === 0)
                beginViewport()
            else if (phase === 1)
                verifyDialog()
            else
                finishViewport()
        }
    }
}
