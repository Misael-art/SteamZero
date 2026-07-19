// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtTest
import ".."

TestCase {
    id: testCase
    name: "ResponsiveDesktopUi"

    Component {
        id: windowComponent
        Main { visible: false }
    }

    Component {
        id: tokensComponent
        UiTokens { viewportWidth: 1920; viewportHeight: 1080 }
    }

    Component {
        id: accessibilityMenuComponent
        AccessibilityMenu { width: 420 }
    }

    Component {
        id: navigatorHarnessComponent
        Item {
            property alias navigator: sectionNavigator
            property alias scrollArea: scrollArea
            width: 520
            height: 320

            Flickable {
                id: scrollArea
                width: 420
                height: 240
                contentWidth: width
                contentHeight: 960
                Item { id: firstAnchor; y: 0 }
                Item { id: secondAnchor; y: 380 }
                Item { id: thirdAnchor; y: 820 }
            }
            SectionNavigator {
                id: sectionNavigator
                flickable: scrollArea
                reducedMotion: true
                sections: [
                    {"label": "Primeira", "item": firstAnchor},
                    {"label": "Segunda", "item": secondAnchor},
                    {"label": "Terceira", "item": thirdAnchor}
                ]
            }
        }
    }

    Component {
        id: focusHarnessComponent
        Window {
            property alias originButton: originButton
            property alias sectionMenu: sectionMenu
            width: 640
            height: 480
            visible: true

            Button {
                id: originButton
                text: "Abrir seções"
                anchors.centerIn: parent
            }
            SectionMenu {
                id: sectionMenu
                width: 360
                x: (parent.width - width) / 2
                y: (parent.height - height) / 2
                sections: [
                    {"label": "Primeira"},
                    {"label": "Segunda"}
                ]
            }
        }
    }

    Component {
        id: feedbackComponent
        FeedbackNotice { width: 520 }
    }

    Component {
        id: footerComponent
        ResponsiveFooter { width: 720; compact: true }
    }

    Component {
        id: navigationIconComponent
        NavigationIcon { width: 28; height: 28 }
    }

    function channelToLinear(channel) {
        const normalized = channel / 255
        return normalized <= 0.04045 ? normalized / 12.92
            : Math.pow((normalized + 0.055) / 1.055, 2.4)
    }

    function luminance(hexColor) {
        const hex = String(hexColor).replace("#", "").slice(-6)
        const red = parseInt(hex.slice(0, 2), 16)
        const green = parseInt(hex.slice(2, 4), 16)
        const blue = parseInt(hex.slice(4, 6), 16)
        return 0.2126 * channelToLinear(red)
            + 0.7152 * channelToLinear(green)
            + 0.0722 * channelToLinear(blue)
    }

    function contrastRatio(first, second) {
        const firstLuminance = luminance(first)
        const secondLuminance = luminance(second)
        const lighter = Math.max(firstLuminance, secondLuminance)
        const darker = Math.min(firstLuminance, secondLuminance)
        return (lighter + 0.05) / (darker + 0.05)
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

    function test_compactNavigationUsesModernIconsInsteadOfInitials() {
        const window = createTemporaryObject(windowComponent, null)
        verify(window !== null)
        window.width = 1280
        window.height = 800
        window.desktopStatus = status("deck-lcd", [], {
            "name": "eDP-1", "connected": true, "internal": true,
            "width": 800, "height": 1280, "scale": 1.35
        })
        compare(window.compositionProfile, "compact")

        const expectedGlyphs = ["overview", "emulators", "steam", "profiles", "sync", "system"]
        for (let index = 0; index < expectedGlyphs.length; index++) {
            const navigationItem = window.mainNavigationItem(index)
            verify(navigationItem !== null)
            compare(navigationItem.navigationIconItem.glyph, expectedGlyphs[index])
            verify(navigationItem.navigationIconItem.visible)
        }
        window.destroy()
    }

    function test_navigationGlyphsCoverEveryPrimaryDestination() {
        const glyphs = ["overview", "emulators", "steam", "profiles", "sync", "system"]
        for (let index = 0; index < glyphs.length; index++) {
            const icon = createTemporaryObject(navigationIconComponent, null, {"glyph": glyphs[index]})
            verify(icon !== null)
            compare(icon.glyph, glyphs[index])
            verify(icon.implicitWidth >= 28)
            verify(icon.implicitHeight >= 28)
            icon.destroy()
        }
    }

    function test_unverifiedStatusDoesNotInventOperationalData() {
        const window = createTemporaryObject(windowComponent, null)
        verify(window !== null)
        window.desktopStatus = ({})
        compare(window.emulatorItems.length, 0)
        compare(window.steamItems.length, 0)
        compare(window.doctorState, "unverified")
        compare(window.environmentReady, false)
        window.destroy()
    }

    function test_portableControlsRespectMinimumMetrics() {
        const footer = createTemporaryObject(footerComponent, null)
        verify(footer !== null)
        verify(footer.compactTextSize >= 12)
        footer.destroy()

        const harness = createTemporaryObject(navigatorHarnessComponent, null)
        verify(harness !== null)
        verify(harness.navigator.minimumTarget >= 48)
        harness.destroy()
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

    function test_errorFeedbackExplainsImpactAndOffersAction() {
        const notice = createTemporaryObject(feedbackComponent, null, {
            "message": "A central local não respondeu",
            "error": true
        })
        verify(notice !== null)
        compare(notice.displayTitle, "Não foi possível concluir")
        verify(notice.impactText.indexOf("estado anterior foi preservado") >= 0)
        compare(notice.hasContextAction, true)

        notice.error = false
        compare(notice.displayTitle, "Ação concluída")
        compare(notice.impactText, "")
        compare(notice.hasContextAction, false)
        notice.destroy()
    }

    function test_accessibilityPreferencesRemainPresentational() {
        const window = createTemporaryObject(windowComponent, null)
        verify(window !== null)
        const normalBorder = String(window.borderColor)
        window.highContrastPreference = true
        verify(String(window.borderColor) !== normalBorder)
        window.reducedMotionPreference = true
        compare(window.motionReduced, true)
        window.interfaceScalePreference = 1.5
        compare(window.minimumInteractiveTarget, 72)
        window.destroy()
    }

    function test_accessibilityMenuOffersSupportedVisualScales() {
        const menu = createTemporaryObject(accessibilityMenuComponent, null)
        verify(menu !== null)
        menu.textScale = 1.0
        compare(menu.scaleIndex(), 0)
        menu.textScale = 1.25
        compare(menu.scaleIndex(), 1)
        menu.textScale = 1.5
        compare(menu.scaleIndex(), 2)
        menu.destroy()
    }

    function test_sectionNavigationUsesSemanticAnchors() {
        const harness = createTemporaryObject(navigatorHarnessComponent, null)
        verify(harness !== null)
        verify(harness.navigator.visible)

        harness.navigator.goTo(1)
        compare(harness.navigator.activeIndex, 1)
        compare(harness.scrollArea.contentY, 368)
        compare(harness.navigator.sectionLabel(1), "Segunda · 2 de 3")

        harness.navigator.nextSection()
        compare(harness.navigator.activeIndex, 2)
        compare(harness.scrollArea.contentY, 720)
        harness.navigator.previousSection()
        compare(harness.navigator.activeIndex, 1)
        harness.destroy()
    }

    function test_sectionHistorySupportsBackNavigation() {
        const window = createTemporaryObject(windowComponent, null)
        verify(window !== null)
        window.sectionIndex = 1
        window.sectionHistory = []
        window.navigateToSection(4)
        compare(window.sectionIndex, 4)
        compare(window.sectionHistory.length, 1)
        compare(window.sectionHistory[0], 1)
        window.navigateToSection(99)
        compare(window.sectionIndex, 4)
        compare(window.sectionHistory.length, 1)
        window.goBack()
        compare(window.sectionIndex, 1)
        compare(window.sectionHistory.length, 0)
        window.destroy()
    }

    function test_primaryFocusGraphSupportsDirectionalActivationAndBack() {
        const window = createTemporaryObject(windowComponent, null)
        verify(window !== null)
        window.visible = true
        window.requestActivate()
        tryCompare(window, "active", true)

        const overview = window.mainNavigationItem(0)
        const emulators = window.mainNavigationItem(1)
        verify(overview !== null)
        verify(emulators !== null)
        window.focusMainNavigation(0)
        tryCompare(overview, "activeFocus", true)

        keyClick(Qt.Key_Down)
        tryCompare(emulators, "activeFocus", true)
        keyClick(Qt.Key_Return)
        compare(window.sectionIndex, 1)

        window.navigateToSection(4)
        compare(window.sectionIndex, 4)
        keyClick(Qt.Key_Escape)
        compare(window.sectionIndex, 1)
        tryCompare(emulators, "activeFocus", true)
        window.destroy()
    }

    function test_sectionMenuReturnsFocusToOrigin() {
        const harness = createTemporaryObject(focusHarnessComponent, null)
        verify(harness !== null)
        harness.originButton.forceActiveFocus()
        tryCompare(harness.originButton, "activeFocus", true)

        harness.sectionMenu.returnFocusItem = harness.originButton
        harness.sectionMenu.open()
        tryCompare(harness.sectionMenu, "opened", true)
        verify(!harness.originButton.activeFocus)
        harness.sectionMenu.close()
        tryCompare(harness.originButton, "activeFocus", true)
        harness.destroy()
    }

    function test_textTokensMeetEssentialContrastThresholds() {
        const tokens = createTemporaryObject(tokensComponent, null)
        verify(tokens !== null)
        verify(contrastRatio(tokens.text, tokens.background) >= 7.0)
        verify(contrastRatio(tokens.muted, tokens.background) >= 4.5)
        verify(contrastRatio(tokens.cyan, tokens.background) >= 4.5)

        tokens.highContrast = true
        verify(contrastRatio(tokens.text, tokens.background) >= 7.0)
        verify(contrastRatio(tokens.muted, tokens.background) >= 7.0)
        verify(contrastRatio(tokens.cyan, tokens.background) >= 7.0)
        tokens.destroy()
    }
}
