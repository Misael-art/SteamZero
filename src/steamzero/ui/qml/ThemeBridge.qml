// SPDX-License-Identifier: GPL-3.0-or-later
// Bridge entre resolved theme JSON e propriedades QML consumíveis.
import QtQuick

QtObject {
    // Tema ativo
    readonly property string themeId: resolved
        ? resolved.themeId : "org.steamzero.default"
    readonly property string themeVersion: resolved
        ? resolved.themeVersion : "1.0.0"
    readonly property bool highContrast: resolved
        ? resolved.highContrast : false
    readonly property bool reducedMotion: resolved
        ? resolved.reducedMotion : false

    // Tokens do tema resolvido
    readonly property var tokens: resolved
        ? resolved.resolved : _FALLBACK_TOKENS

    // Expõe se há um tema carregado (não só fallback)
    readonly property bool active: resolved !== null

    // Cores
    readonly property color background: _get("color", "background", "#071019")
    readonly property color sidebar: _get("color", "sidebar", "#09131d")
    readonly property color surface: _get("color", "surface", "#0d1924")
    readonly property color surfaceRaised: _get("color", "surfaceRaised", "#122131")
    readonly property color surfaceSelected: _get("color", "surfaceSelected", "#1a2b3c")
    readonly property color border: _get("color", "border", "#2a3a49")
    readonly property color text: _get("color", "text", "#f2f6fb")
    readonly property color textMuted: _get("color", "textMuted", "#9eabba")
    readonly property color textDisabled: _get("color", "textDisabled", "#667481")
    readonly property color accent: _get("color", "accent", "#13bdf2")
    readonly property color accentStrong: _get("color", "accentStrong", "#0a5f85")
    readonly property color success: _get("color", "success", "#59d35d")
    readonly property color warning: _get("color", "warning", "#ff9f1a")
    readonly property color danger: _get("color", "danger", "#ff6b73")
    readonly property color focus: _get("color", "focus", "#13bdf2")

    // Geometria
    readonly property int radiusSmall: _get("geometry", "radiusSmall", 6)
    readonly property int radiusMedium: _get("geometry", "radiusMedium", 10)
    readonly property int radiusLarge: _get("geometry", "radiusLarge", 16)
    readonly property int spacingSmall: _get("geometry", "spacingSmall", 8)
    readonly property int spacingMedium: _get("geometry", "spacingMedium", 16)
    readonly property int spacingLarge: _get("geometry", "spacingLarge", 24)

    // Tipografia
    readonly property real typographyScale: _get("typography", "scale", 1.0)

    // Movimento
    readonly property int motionDuration: reducedMotion ? 0
        : _get("motion", "durationNormal", 180)
    readonly property int motionDurationFast: reducedMotion ? 0
        : _get("motion", "durationFast", 120)
    readonly property int motionDurationLong: reducedMotion ? 0
        : _get("motion", "durationLong", 300)

    // Fonte
    readonly property string fontFamily: _getStr("typography", "family", "")

    // --- Internals ---------------------------------------------------------

    property var _source: null   // define pelo binding em Main.qml

    readonly property var resolved: _source && _source.resolved
        ? _source.resolved : null

    function _get(group, key, fallback) {
        var t = tokens
        if (!t || !t[group]) return fallback
        var v = t[group][key]
        return v !== undefined && v !== null ? v : fallback
    }

    function _getStr(group, key, fallback) {
        var t = tokens
        if (!t || !t[group]) return fallback
        var v = t[group][key]
        return typeof v === "string" && v.length > 0 ? v : fallback
    }

    readonly property var _FALLBACK_TOKENS: ({
        "color": {
            "background": "#071019",
            "sidebar": "#09131d",
            "surface": "#0d1924",
            "surfaceRaised": "#122131",
            "surfaceSelected": "#1a2b3c",
            "border": "#2a3a49",
            "text": "#f2f6fb",
            "textMuted": "#9eabba",
            "textDisabled": "#667481",
            "accent": "#13bdf2",
            "accentStrong": "#0a5f85",
            "success": "#59d35d",
            "warning": "#ff9f1a",
            "danger": "#ff6b73",
            "focus": "#13bdf2"
        },
        "geometry": {
            "radiusSmall": 6,
            "radiusMedium": 10,
            "radiusLarge": 16,
            "spacingSmall": 8,
            "spacingMedium": 16,
            "spacingLarge": 24
        },
        "typography": {
            "scale": 1.0,
            "family": ""
        },
        "motion": {
            "durationFast": 120,
            "durationNormal": 180,
            "durationLong": 300
        }
    })
}
