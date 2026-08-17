// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Renderer confiável para uma source de mídia e a pilha allowlisted resolvida
// em Python. O tema entrega apenas `effects`; não executa QML, JS ou shader.
import QtQuick

Item {
    id: root

    required property url source
    property int fillMode: Image.PreserveAspectCrop
    property var effects: []
    // QtQuick.Effects/MultiEffect existe somente a partir do Qt 6.5. O
    // launcher publica esta capacidade depois de conferir o runtime; sem ela,
    // a mídia continua visível e a vinheta declarativa permanece funcional.
    // Assim um efeito opcional nunca torna a biblioteca inteira indisponível.
    property bool advancedEffectsAvailable:
        Qt.application.arguments.indexOf("--steamzero-qtquick-effects") >= 0

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
    readonly property bool advancedEffectsLoaded:
        advancedRenderer.status === Loader.Ready

    Image {
        id: mediaSource
        anchors.fill: parent
        source: root.source
        fillMode: root.fillMode
        visible: true
        opacity: {
            if (root.advancedEffectsLoaded)
                return 1.0
            const configured = root.effect("opacity")
            return configured ? configured.amount : 1.0
        }
    }

    // Mantém uma única decodificação da mídia e esconde a imagem crua. As
    // camadas confiáveis abaixo reutilizam esta textura, em vez de abrir outra
    // source ou aceitar bytes/código do tema.
    ShaderEffectSource {
        id: mediaTexture
        anchors.fill: parent
        sourceItem: mediaSource
        hideSource: root.advancedEffectsLoaded
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
                    color: Qt.rgba(1, 1, 1, root.gradientMaskEffect
                        ? root.gradientMaskEffect.start : 1)
                }
                GradientStop {
                    position: 1
                    color: Qt.rgba(1, 1, 1, root.gradientMaskEffect
                        ? root.gradientMaskEffect.end : 0)
                }
            }
        }
    }

    // O arquivo avançado é carregado apenas quando a capacidade foi provada.
    // Em Qt 6.4 ele nem é compilado, evitando que um módulo opcional derrube
    // Main.qml e todas as jornadas que não dependem de efeitos.
    Loader {
        id: advancedRenderer
        anchors.fill: parent
        active: root.advancedEffectsAvailable
        source: active ? "MediaMultiEffectRenderer.qml" : ""
        onLoaded: {
            item.sourceItem = Qt.binding(function() { return mediaTexture })
            item.maskItem = Qt.binding(function() { return gradientMask })
            item.effects = Qt.binding(function() { return root.effects })
        }
    }

    VignetteLayer {
        anchors.fill: parent
        tint: root.vignetteEffect ? root.vignetteEffect.color : "#000000"
        strength: root.vignetteEffect ? root.vignetteEffect.strength : 0
    }
}
