// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Renderer confiável para uma source de mídia e a pilha allowlisted resolvida
// em Python. O tema entrega apenas `effects`; não executa QML, JS ou shader.
import QtQuick
import QtQuick.Effects

Item {
    id: root

    required property url source
    property int fillMode: Image.PreserveAspectCrop
    property var effects: []

    function effect(type) {
        for (let i = 0; i < effects.length; ++i) {
            if (effects[i].type === type)
                return effects[i].parameters
        }
        return null
    }

    Image {
        id: mediaSource
        anchors.fill: parent
        source: root.source
        fillMode: root.fillMode
        visible: false
    }

    MultiEffect {
        id: renderedMedia
        anchors.fill: parent
        source: mediaSource

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
        shadowColor: shadowEffect ? shadowEffect.color : "#00000000"
        opacity: opacityEffect ? opacityEffect.amount : 1.0

        // O glow usa a mesma primitiva de sombra do Qt: é uma aproximação
        // declarada e segura, não um shader fornecido pelo tema.
        shadowOpacity: glowEffect ? glowEffect.strength
            : shadowEffect ? shadowEffect.opacity : 0.0
    }
}
