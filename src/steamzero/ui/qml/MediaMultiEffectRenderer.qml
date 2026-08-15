// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Renderer avançado isolado: este arquivo só é carregado quando o launcher
// provou Qt >= 6.5, versão em que QtQuick.Effects/MultiEffect passou a existir.
import QtQuick
import QtQuick.Effects

Item {
    id: root

    property Item sourceItem: null
    property Item maskItem: null
    property var effects: []

    function effect(type) {
        for (let i = 0; i < effects.length; ++i) {
            if (effects[i].type === type)
                return effects[i].parameters
        }
        return null
    }

    readonly property var reflectionEffect: effect("reflection")
    readonly property var gradientMaskEffect: effect("gradientMask")

    MultiEffect {
        anchors.fill: parent
        source: root.sourceItem

        readonly property var blurEffect: root.effect("blur")
        readonly property var saturationEffect: root.effect("saturation")
        readonly property var brightnessEffect: root.effect("brightness")
        readonly property var contrastEffect: root.effect("contrast")
        readonly property var colorizeEffect: root.effect("colorize")
        readonly property var shadowEffect: root.effect("shadow")
        readonly property var glowEffect: root.effect("glow")
        readonly property var opacityEffect: root.effect("opacity")

        blurEnabled: blurEffect !== null
        blur: blurEffect ? blurEffect.radius / 64.0 : 0.0
        saturation: saturationEffect ? saturationEffect.amount : 0.0
        brightness: brightnessEffect ? brightnessEffect.amount : 0.0
        contrast: contrastEffect ? contrastEffect.amount : 0.0
        colorization: colorizeEffect ? colorizeEffect.strength : 0.0
        colorizationColor: colorizeEffect ? colorizeEffect.color : "#000000"
        shadowEnabled: shadowEffect !== null
        shadowBlur: shadowEffect ? shadowEffect.blur / 64.0 : 0.0
        shadowHorizontalOffset: shadowEffect ? shadowEffect.offsetX : 0.0
        shadowVerticalOffset: shadowEffect ? shadowEffect.offsetY : 0.0
        shadowColor: glowEffect ? glowEffect.color
            : shadowEffect ? shadowEffect.color : "#00000000"
        opacity: opacityEffect ? opacityEffect.amount : 1.0
        maskEnabled: root.gradientMaskEffect !== null
        maskSource: ShaderEffectSource {
            sourceItem: root.maskItem
            hideSource: true
        }

        // O glow usa a mesma primitiva de sombra do Qt: é uma aproximação
        // declarada e segura, não um shader fornecido pelo tema.
        shadowOpacity: glowEffect ? glowEffect.strength
            : shadowEffect ? shadowEffect.opacity : 0.0
    }

    ReflectionLayer {
        anchors.fill: parent
        sourceItem: root.sourceItem
        reflectionOpacity: root.reflectionEffect
            ? root.reflectionEffect.opacity : 0
        reflectionScale: root.reflectionEffect
            ? root.reflectionEffect.scale : 0
        maskStart: root.gradientMaskEffect
            ? root.gradientMaskEffect.start : 0.72
        maskEnd: root.gradientMaskEffect ? root.gradientMaskEffect.end : 0
    }
}
