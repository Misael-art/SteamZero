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
    // Teto de decodificação da mídia, em pixels de dispositivo. Uma capa de
    // 600x900 desenhada numa célula de 190x274 custa o mesmo decode e a mesma
    // textura de GPU que uma capa em tela cheia; quem sabe o tamanho real é a
    // superfície que instancia este renderer, não o renderer.
    //
    // É `required` de propósito. Um padrão como `Qt.size(0, 0)` — o valor que a
    // Image entende como "tamanho natural do arquivo" — deixaria uma superfície
    // nova voltar ao decode integral só por esquecimento, e em silêncio: nada
    // falha, a mídia aparece igual, e o custo só se manifesta como rolagem
    // travada num aparelho que o autor da superfície talvez não tenha. Exigir a
    // declaração transforma esse esquecimento em erro de carregamento do QML.
    required property size decodeSize
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
    // Superfície de diagnóstico das camadas que só existem para alimentar o
    // renderer avançado. Sem ela não há como provar, de fora, que a textura e a
    // máscara acompanham o consumidor em vez de custar por capa sem uso.
    readonly property bool mediaTextureBound: mediaTexture.sourceItem !== null
    readonly property bool maskRenderable: gradientMask.visible

    Image {
        id: mediaSource
        anchors.fill: parent
        source: root.source
        fillMode: root.fillMode
        // Teto, não tamanho alvo: uma arte menor que o teto continua sendo
        // decodificada no tamanho natural (medido — arte 320x180 com teto de
        // 4096 mantém implicitWidth 320). Por isso declarar um teto generoso
        // numa tela 4K não infla o consumo de uma capa pequena. Em SVG o teto
        // vira mesmo o tamanho de rasterização, que é o comportamento desejado.
        sourceSize: root.decodeSize
        // Decodificar fora da thread de render é o que impede que uma capa
        // grande apareça como engasgo na rolagem. O custo é um quadro sem a
        // imagem; o placeholder abaixo já cobre esse intervalo.
        asynchronous: true
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
    //
    // `sourceItem` só é ligado quando o renderer avançado existe para consumir
    // a textura. Sem esse gate, cada capa da biblioteca alocava um FBO do
    // tamanho do delegate e o redesenhava mesmo quando nada além da Image
    // aparecia na tela — uma cópia por capa, por quadro, sem consumidor.
    ShaderEffectSource {
        id: mediaTexture
        anchors.fill: parent
        sourceItem: root.advancedEffectsLoaded ? mediaSource : null
        hideSource: root.advancedEffectsLoaded
    }

    // Esta é uma fonte de máscara produzida pelo renderer, nunca pelo tema.
    // O tema só pode fornecer os dois níveis normalizados da Effect Stack.
    Item {
        id: gradientMask
        anchors.fill: parent
        // O ShaderEffectSource do renderer avançado oculta esta source da cena,
        // mas ela deve permanecer renderizável para que a máscara tenha alpha
        // válido. Sem esse renderer não há quem a oculte nem quem a consuma: o
        // gradiente branco ficaria por cima da mídia e ainda custaria um nó de
        // cena por capa. Por isso a existência da máscara acompanha a do
        // consumidor.
        visible: root.advancedEffectsLoaded
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

    // A vinheta são quatro retângulos com gradiente. Multiplicados pelas capas
    // visíveis de uma grade, é um custo que só se justifica quando a pilha
    // resolvida pediu vinheta; por isso ela é carregada, e não apenas ocultada.
    Loader {
        anchors.fill: parent
        active: root.vignetteActive
        sourceComponent: VignetteLayer {
            tint: root.vignetteEffect ? root.vignetteEffect.color : "#000000"
            strength: root.vignetteEffect ? root.vignetteEffect.strength : 0
        }
    }
}
