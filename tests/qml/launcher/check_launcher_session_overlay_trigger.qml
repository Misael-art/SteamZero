// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// A superfície de OSD já tinha contrato e componentes, mas não tinha uma
// entrada de teclado na cena raiz. Este harness prova o caminho de produção:
// sessão canônica ativa -> tecla de menu -> OSD aberto -> mesma tecla fecha.
import QtQuick
import QtTest
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    readonly property var focusMap: ({
        "initial": "library:game",
        "rows": ["library:game"],
        "diagnostics": [],
        "nodes": {
            "library:game": {"id": "library:game", "section": "library",
                             "column": 0, "up": null, "down": null,
                             "left": null, "right": null, "action": null}
        }
    })
    readonly property var model: ({
        "focusMap": harness.focusMap,
        "sections": [{"id": "library", "title": "Biblioteca",
                      "items": [{"id": "game", "title": "AURA Test"}]}],
        "catalogSummary": {},
        "returnContext": null
    })

    Component { id: sceneComponent; LauncherMain {} }

    TestCase {
        name: "LauncherSessionOverlayTrigger"
        when: windowShown

        function createActiveSessionScene() {
            const scene = createTemporaryObject(sceneComponent, harness)
            verify(scene !== null)
            scene.model = harness.model
            scene.loadState = "ready"
            scene.requestActivate()
            tryVerify(function() { return scene.active }, 5000)
            const shell = scene._activeLauncherShell()
            verify(shell !== null)
            shell.sessionGameId = "game"
            shell.launchState = "emulator-visible"
            return scene
        }

        function test_menu_key_opens_and_closes_osd_for_active_session() {
            const scene = createActiveSessionScene()
            keyClick(Qt.Key_F1)
            tryCompare(scene, "sessionOverlayOpen", true)
            verify(scene.sessionOverlayError.indexOf("AURA-OSD-") === 0,
                   "sem bridge no harness, o erro precisa continuar diagnosticável")
            keyClick(Qt.Key_F1)
            tryCompare(scene, "sessionOverlayOpen", false)
            keyClick(Qt.Key_Menu)
            tryCompare(scene, "sessionOverlayOpen", true)
            keyClick(Qt.Key_Menu)
            tryCompare(scene, "sessionOverlayOpen", false)
        }

        function test_menu_key_is_ignored_without_canonical_session() {
            const scene = createActiveSessionScene()
            const shell = scene._activeLauncherShell()
            shell.sessionGameId = ""
            compare(scene.sessionOverlayOpen, false)
            compare(scene.toggleSessionOverlay(), false)
            keyClick(Qt.Key_F1)
            compare(shell.sessionGameId, "")
            compare(scene.sessionOverlayOpen, false)
        }
    }
}
