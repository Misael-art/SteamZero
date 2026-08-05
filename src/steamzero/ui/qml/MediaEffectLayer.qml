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

    readonly property var reflectionEffect: effect("reflection")
    readonly property var gradientMaskEffect: effect("gradientMask")
    readonly property var vignetteEffect: effect("vignette")
    readonly property bool reflectionActive: reflectionEffect !== null
    readonly property bool gradientMaskActive: gradientMaskEffect !== null
    readonly property bool vignetteActive: vignetteEffect !== null
    readonly property int sourceStatus: mediaSource.status

    Image {
        id: mediaSource
        anchors.fill: parent
        source: root.source
        fillMode: root.fillMode
        visible: true
    }

    // Mantém uma única decodificação da mídia e esconde a imagem crua. As
    // camadas confiáveis abaixo reutilizam esta textura, em vez de abrir outra
    // source ou aceitar bytes/código do tema.
    ShaderEffectSource {
        id: mediaTexture
        anchors.fill: parent
        sourceItem: mediaSource
        hideSource: true
    }

    // Esta é uma fonte de máscara produzida pelo renderer, nunca pelo tema.
    // O tema só pode fornecer os dois níveis normalizados da Effect Stack.
    Item {
        id: gradientMask
        anchors.fill: parent
        // ShaderEffectSource abaixo oculta esta source da cena, mas ela deve
        // permanecer renderizável para que a máscara tenha alpha válido.
        visible: true
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop {
                    position: 0
                    color: Qt.rgba(1, 1, 1, gradientMaskEffect
                        ? gradientMaskEffect.start : 1)
                }
                GradientStop {
                    position: 1
                    color: Qt.rgba(1, 1, 1, gradientMaskEffect
                        ? gradientMaskEffect.end : 0)
                }
            }
        }
    }

    MultiEffect {
        id: renderedMedia
        anchors.fill: parent
        source: mediaTexture

        readonly property var blurEffect: root.effect("blur")
        readonly property var saturationEffect: root.effect("saturation")
        readonly property var brightnessEffect: root.effect("brightness")
        readonly property var contrastEffect: root.effect("contrast")
        readonly property var colorizeEffect: root.effect("colorize")
        readonly property var shadowEffect: root.effect("shadow")
        readonly property var glowEffect: root.effect("glow")
        readonly property var opacityEffect: root.effect("opacity")
        readonly property var gradientMaskEffect: root.effect("gradientMask")
        readonly property var vignetteEffect: root.effect("vignette")

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
        maskEnabled: gradientMaskEffect !== null
        // ShaderEffectSource é a superfície segura do Qt que captura a máscara
        // declarativa local; o manifesto jamais fornece shader ou source.
        maskSource: ShaderEffectSource {
            sourceItem: gradientMask
            hideSource: true
        }

        // O glow usa a mesma primitiva de sombra do Qt: é uma aproximação
        // declarada e segura, não um shader fornecido pelo tema.
        shadowOpacity: glowEffect ? glowEffect.strength
            : shadowEffect ? shadowEffect.opacity : 0.0
    }

    ReflectionLayer {
        anchors.fill: parent
        sourceItem: mediaTexture
        reflectionOpacity: reflectionEffect ? reflectionEffect.opacity : 0
        reflectionScale: reflectionEffect ? reflectionEffect.scale : 0
        maskStart: gradientMaskEffect ? gradientMaskEffect.start : 0.72
        maskEnd: gradientMaskEffect ? gradientMaskEffect.end : 0
    }

    VignetteLayer {
        anchors.fill: parent
        tint: vignetteEffect ? vignetteEffect.color : "#000000"
        strength: vignetteEffect ? vignetteEffect.strength : 0
    }
}
