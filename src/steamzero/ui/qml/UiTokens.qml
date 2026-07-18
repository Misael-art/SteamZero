// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick

QtObject {
    required property real viewportWidth
    required property real viewportHeight
    property bool handheld: false
    property bool television: false
    property bool highContrast: false
    property bool reducedMotion: false

    readonly property bool compact: handheld || viewportWidth < 1080 || viewportHeight < 680
    readonly property bool wide: !compact && viewportWidth >= 2200
    readonly property string composition: compact ? "compact" : wide ? "wide" : "standard"

    readonly property int sidebarWidth: compact ? 72 : television ? 300 : 248
    readonly property int pageMargin: compact ? 16 : television ? 36 : 24
    readonly property int gap: compact ? 12 : television ? 24 : 16
    readonly property int targetSize: television ? 64 : 48
    readonly property int footerHeight: compact ? 46 : television ? 64 : 52
    readonly property int inspectorWidth: wide ? 400 : 344
    readonly property int maximumContentWidth: wide ? 1920 : 1760

    readonly property int pageTitleSize: television ? 42 : compact ? 26 : 30
    readonly property int sectionTitleSize: television ? 28 : 20
    readonly property int cardTitleSize: television ? 23 : 18
    readonly property int bodySize: television ? 20 : 15
    readonly property int labelSize: television ? 18 : 13
    readonly property int metadataSize: television ? 15 : 12

    readonly property color background: highContrast ? "#03080c" : "#071019"
    readonly property color sidebar: highContrast ? "#050b11" : "#09131d"
    readonly property color surface: highContrast ? "#0a141d" : "#0d1924"
    readonly property color raised: highContrast ? "#122638" : "#122131"
    readonly property color border: highContrast ? "#68839b" : "#2a3a49"
    readonly property color text: "#f2f6fb"
    readonly property color muted: highContrast ? "#c6d0db" : "#9eabba"
    readonly property color cyan: highContrast ? "#55d8ff" : "#13bdf2"
    readonly property color cyanDark: highContrast ? "#0b6387" : "#0a5f85"
    readonly property color amber: highContrast ? "#ffc14d" : "#ff9f1a"
    readonly property color green: highContrast ? "#7be47f" : "#59d35d"
    readonly property color red: highContrast ? "#ff8e94" : "#ff6b73"
}
