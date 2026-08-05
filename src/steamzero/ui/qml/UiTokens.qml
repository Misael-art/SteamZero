// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick

QtObject {
    required property real viewportWidth
    required property real viewportHeight
    property bool handheld: false
    property bool television: false
    property bool highContrast: false
    property bool reducedMotion: false
    property real userScale: 1.0

    readonly property real visualScale: Math.max(1.0, Math.min(userScale, 1.5))

    readonly property bool compact: handheld || viewportWidth < 1080 || viewportHeight < 680
    readonly property bool wide: !compact && viewportWidth >= 2200
    readonly property string composition: compact ? "compact" : wide ? "wide" : "standard"

    readonly property int sidebarWidth: compact ? 72 : television ? 300 : 248
    readonly property int pageMargin: compact ? 16 : television ? 36 : 24
    readonly property int gap: compact ? 12 : television ? 24 : 16
    readonly property int targetSize: television ? 64 : 48
    readonly property int footerHeight: compact ? 46 : television ? 64 : 52
    readonly property int inspectorWidth: Math.round((wide ? 400 : 344)
        * Math.min(visualScale, 1.25))
    readonly property int maximumContentWidth: wide ? 1920 : 1760

    readonly property int pageTitleSize: Math.round((television ? 42 : compact ? 26 : 30) * visualScale)
    readonly property int sectionTitleSize: Math.round((television ? 28 : 20) * visualScale)
    readonly property int cardTitleSize: Math.round((television ? 23 : 18) * visualScale)
    readonly property int bodySize: Math.round((television ? 20 : 15) * visualScale)
    readonly property int labelSize: Math.round((television ? 18 : 13) * visualScale)
    readonly property int metadataSize: Math.round((television ? 15 : 12) * visualScale)

    readonly property color background: highContrast ? "#03080c" : "#e7eceb"
    readonly property color sidebar: highContrast ? "#050b11" : "#d8dfdf"
    readonly property color surface: highContrast ? "#0a141d" : "#f4f7f5"
    readonly property color raised: highContrast ? "#122638" : "#ffffff"
    readonly property color border: highContrast ? "#68839b" : "#aebdbe"
    readonly property color text: highContrast ? "#ffffff" : "#16212a"
    readonly property color muted: highContrast ? "#c6d0db" : "#53616b"
    readonly property color cyan: highContrast ? "#55d8ff" : "#006f99"
    readonly property color cyanDark: highContrast ? "#0b6387" : "#005471"
    readonly property color amber: highContrast ? "#ffc14d" : "#9a5a00"
    readonly property color green: highContrast ? "#7be47f" : "#167a45"
    readonly property color red: highContrast ? "#ff8e94" : "#ae2634"
}
