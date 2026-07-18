// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtTest
import ".."

TestCase {
    id: testCase
    name: "ResponsiveDesktopUi"

    Component {
        id: windowComponent
        Main { visible: false }
    }

    function componentRow(state) {
        return {
            "id": "demo", "name": "Demo", "description": "Componente de teste",
            "iconName": "input-gaming", "systems": ["Demo"], "state": state,
            "statusLabel": state === "installed" ? "Instalado" : "Não instalado",
            "versionLabel": "—", "detail": "Estado sintético para teste de UI.",
            "blockedReason": "", "action": {"kind": "detail", "label": "Detalhes", "enabled": true}
        }
    }

    function status(deviceKind, components, display) {
        return {
            "effectiveProfile": deviceKind.indexOf("deck-") === 0 ? "handheld-desktop" : "docked-desktop",
            "recommendedProfile": deviceKind.indexOf("deck-") === 0 ? "handheld-desktop" : "docked-desktop",
            "manualOverride": null,
            "current": {},
            "recoveryRequired": false,
            "independentRuntime": true,
            "context": {
                "deviceKind": deviceKind, "sessionType": "wayland", "displays": [display],
                "physicalDock": false, "externalKeyboard": true, "externalMouse": true,
                "capabilities": [], "conflicts": []
            },
            "dashboard": {
                "components": components, "steam": [],
                "sync": {"state": "idle", "pending": 0, "conflicted": 0, "done": 0},
                "doctor": {"state": "healthy", "checks": []}
            }
        }
    }

    function test_compositionProfiles() {
        const window = createTemporaryObject(windowComponent, null)
        verify(window !== null)

        window.width = 1280
        window.height = 800
        window.desktopStatus = status("deck-lcd", [], {
            "name": "eDP-1", "connected": true, "internal": true,
            "width": 800, "height": 1280, "scale": 1.35
        })
        compare(window.compositionProfile, "compact")
        compare(window.sidebarLogicalWidth, 72)
        compare(window.minimumInteractiveTarget, 48)
        compare(window.displaySummary(), "1280×800 · escala 135%")

        window.desktopStatus = status("desktop", [], {
            "name": "DP-1", "connected": true, "internal": false,
            "width": 1920, "height": 1080, "scale": 1.0
        })
        window.width = 1920
        window.height = 1080
        compare(window.compositionProfile, "standard")
        compare(window.sidebarLogicalWidth, 248)

        window.width = 2560
        compare(window.compositionProfile, "wide")

        const tvStatus = status("desktop", [], {
            "name": "TV-1", "connected": true, "internal": false,
            "width": 3840, "height": 2160, "scale": 2.0
        })
        tvStatus.context.externalKeyboard = false
        tvStatus.context.externalMouse = false
        window.desktopStatus = tvStatus
        window.width = 1920
        compare(window.sidebarLogicalWidth, 300)
        compare(window.minimumInteractiveTarget, 64)
        window.destroy()
    }

    function test_emptyFilterClearsSelection() {
        const window = createTemporaryObject(windowComponent, null)
        verify(window !== null)
        window.desktopStatus = status("deck-lcd", [componentRow("missing")], {
            "name": "eDP-1", "connected": true, "internal": true,
            "width": 800, "height": 1280, "scale": 1.35
        })
        window.emulatorFilter = 0
        window.ensureSelections()
        verify(window.selectedEmulator !== null)

        window.emulatorFilter = 2
        window.ensureSelections()
        compare(window.filteredEmulatorItems.length, 0)
        compare(window.selectedEmulator, null)
        window.destroy()
    }

    function test_loadingOverlayIsDelayedAndIndeterminate() {
        const window = createTemporaryObject(windowComponent, null)
        verify(window !== null)
        window.pendingRequests = 1
        compare(window.loadingOverlayVisible, false)
        wait(320)
        compare(window.loadingOverlayVisible, true)
        window.pendingRequests = 0
        compare(window.loadingOverlayVisible, false)
        window.destroy()
    }

    function test_accessibilityPreferencesRemainPresentational() {
        const window = createTemporaryObject(windowComponent, null)
        verify(window !== null)
        const normalBorder = String(window.borderColor)
        window.highContrastPreference = true
        verify(String(window.borderColor) !== normalBorder)
        window.reducedMotionPreference = true
        compare(window.motionReduced, true)
        window.destroy()
    }
}
