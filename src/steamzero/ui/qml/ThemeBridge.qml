// SPDX-License-Identifier: GPL-3.0-or-later
// Bridge entre resolved theme JSON e propriedades QML consumíveis.
import QtQuick

QtObject {
    // Tema ativo
    readonly property string themeId: resolved
        ? resolved.themeId : "org.steamzero.default"
    readonly property string themeVersion: resolved
        ? resolved.themeVersion : "1.0.0"

    // Tokens do tema resolvido
    readonly property var tokens: resolved
        ? resolved.resolved : _FALLBACK_TOKENS

    // Expõe se há um tema carregado (não só fallback)
    readonly property bool active: resolved !== null

    // Fallback de acessibilidade quando não há tema ativo
    property var _fallbackAccessibility: null  // atualizado pelo binding em Main.qml

    // Alto contraste e movimento reduzido: prioriza tema, fallback para accessibility
    readonly property bool highContrast: resolved
        ? resolved.highContrast
        : _fallbackAccessibility && _fallbackAccessibility.highContrast === true
    readonly property bool reducedMotion: resolved
        ? resolved.reducedMotion
        : _fallbackAccessibility && _fallbackAccessibility.reducedMotion === true

    // Pilhas já negociadas pelo domínio. Componentes QML apenas as aplicam;
    // não escolhem capability, tier nem fallback.
    readonly property var effectStacks: resolved && resolved.effects
        ? resolved.effects : ({})
    readonly property var effectDiagnostics: resolved && resolved.effectDiagnostics
        ? resolved.effectDiagnostics : ([])
    // Receita decide fit/focal/source role; a URL continua vindo do read model.
    readonly property var mediaRecipes: resolved && resolved.mediaRecipes
        ? resolved.mediaRecipes : ({})
    // Variantes de asset já negociadas. O componente recebe somente nodes
    // builtin; fonte e receitas continuam dados, nunca código executável.
    readonly property var assetRecipes: resolved && resolved.assetRecipes
        ? resolved.assetRecipes : ({})
    readonly property var assetRecipeDiagnostics: resolved && resolved.assetRecipeDiagnostics
        ? resolved.assetRecipeDiagnostics : ([])
    // Contrato declarativo do tema e modelo final opcional fornecido pelo shell.
    // QML nunca consulta o catálogo nem resolve `item.*` por conta própria.
    readonly property var sceneLayouts: resolved && resolved.sceneLayouts
        ? resolved.sceneLayouts : ({})
    readonly property var sceneLayoutPreview: resolved && resolved.sceneLayoutPreview
        ? resolved.sceneLayoutPreview : ({})
    readonly property var dynamicPalette: resolved && resolved.dynamicPalette
        ? resolved.dynamicPalette : ({})
    readonly property var glassPreview: resolved && resolved.glassPreview
        ? resolved.glassPreview : ({})
    readonly property var sceneMotionPreview: resolved && resolved.sceneMotionPreview
        ? resolved.sceneMotionPreview : ({})
    readonly property var sceneSurfacePreview: resolved && resolved.sceneSurfacePreview
        ? resolved.sceneSurfacePreview : ({})

    // Cores — alto contraste sobrepõe quando ativo
    readonly property color background: highContrast ? "#000000" : _get("color", "background", "#e7eceb")
    readonly property color sidebar: highContrast ? "#000000" : _get("color", "sidebar", "#d8dfdf")
    readonly property color surface: highContrast ? "#000000" : _get("color", "surface", "#f4f7f5")
    readonly property color surfaceRaised: highContrast ? "#1a1a1a" : _get("color", "surfaceRaised", "#ffffff")
    readonly property color surfaceSelected: highContrast ? "#2a2a2a" : _get("color", "surfaceSelected", "#dce8e8")
    readonly property color border: highContrast ? "#ffffff" : _get("color", "border", "#aebdbe")
    readonly property color text: highContrast ? "#ffffff" : _get("color", "text", "#16212a")
    readonly property color textMuted: highContrast ? "#e8e8e8" : _get("color", "textMuted", "#53616b")
    readonly property color textDisabled: highContrast ? "#aaaaaa" : _get("color", "textDisabled", "#7a878b")
    readonly property color accent: highContrast ? "#00e5ff" : _get("color", "accent", "#006f99")
    readonly property color accentStrong: highContrast ? "#003d4d" : _get("color", "accentStrong", "#005471")
    readonly property color success: highContrast ? "#5eff62" : _get("color", "success", "#167a45")
    readonly property color warning: highContrast ? "#ffc400" : _get("color", "warning", "#9a5a00")
    readonly property color danger: highContrast ? "#ff8a90" : _get("color", "danger", "#ae2634")
    readonly property color focus: highContrast ? "#00e5ff" : _get("color", "focus", "#006f99")

    // Geometria
    readonly property int radiusSmall: _get("geometry", "radiusSmall", 6)
    readonly property int radiusMedium: _get("geometry", "radiusMedium", 10)
    readonly property int radiusLarge: _get("geometry", "radiusLarge", 16)
    readonly property int spacingSmall: _get("geometry", "spacingSmall", 8)
    readonly property int spacingMedium: _get("geometry", "spacingMedium", 16)
    readonly property int spacingLarge: _get("geometry", "spacingLarge", 24)
    readonly property int minimumTarget: _get("interaction", "minimumTarget", 48)
    readonly property real focusedScale: _get("stateVariants", "focusedScale", 1.05)
    readonly property real peripheralOpacity: _get("stateVariants", "peripheralOpacity", 0.58)
    readonly property string performanceTier: _getStr("performance", "defaultTier", "cinematic")

    // Tipografia
    readonly property real typographyScale: _get("typography", "scale", 1.0)
    readonly property var typographyRoles: ({
        "scale": typographyScale,
        "display": _get("typography", "display", 36),
        "heading": _get("typography", "heading", 24),
        "title": _get("typography", "title", 20),
        "body": _get("typography", "body", 16),
        "metadata": _get("typography", "metadata", 14),
        "badge": _get("typography", "badge", 12),
        "caption": _get("typography", "caption", 12),
        "controlHint": _get("typography", "controlHint", 14),
        "diagnostic": _get("typography", "diagnostic", 14)
    })

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

    property var _source: null   // atualizado pelo binding em Main.qml

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
            "background": "#e7eceb",
            "sidebar": "#d8dfdf",
            "surface": "#f4f7f5",
            "surfaceRaised": "#ffffff",
            "surfaceSelected": "#dce8e8",
            "border": "#aebdbe",
            "text": "#16212a",
            "textMuted": "#53616b",
            "textDisabled": "#7a878b",
            "accent": "#006f99",
            "accentStrong": "#005471",
            "success": "#167a45",
            "warning": "#9a5a00",
            "danger": "#ae2634",
            "focus": "#006f99"
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
        },
        "stateVariants": {
            "focusedScale": 1.05,
            "peripheralOpacity": 0.58,
            "selectedOpacity": 1.0
        },
        "interaction": {
            "focusVisible": true,
            "minimumTarget": 48
        },
        "accessibility": {
            "systemOverrides": true
        },
        "performance": {
            "defaultTier": "cinematic"
        }
    })
}
