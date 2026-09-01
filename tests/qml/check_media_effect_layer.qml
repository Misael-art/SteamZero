// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 360
    height: 240
    property int failures: 0
    readonly property string captureOutput: {
        const prefix = "--capture-output="
        for (let i = 0; i < Qt.application.arguments.length; ++i) {
            if (Qt.application.arguments[i].startsWith(prefix))
                return Qt.application.arguments[i].slice(prefix.length)
        }
        return ""
    }

    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#071019"
    }

    MediaEffectLayer {
        id: media
        anchors.centerIn: parent
        width: 240
        height: 160
        source: Qt.resolvedUrl("../fixtures/scene-media/cover-01.png")
        decodeSize: Qt.size(240, 160)
        fillMode: Image.PreserveAspectCrop
        effects: [
            {"type": "reflection", "parameters": {"opacity": 0.35, "scale": 0.30}},
            {"type": "gradientMask", "parameters": {"start": 0.82, "end": 0.04}},
            {"type": "vignette", "parameters": {"color": "#071019", "strength": 0.28}}
        ]
    }

    // A mídia é decodificada fora da thread de render; o harness espera pelo
    // resultado em vez de apostar num intervalo único. O orçamento mantém uma
    // source que nunca carrega reprovando, em vez de pendurar a suíte.
    property int loadTicks: 0
    readonly property int loadTickBudget: 30

    Timer {
        interval: 60
        running: true
        repeat: true
        onTriggered: {
            if (media.sourceStatus === Image.Loading && loadTicks < loadTickBudget) {
                loadTicks += 1
                return
            }
            running = false
            check(media.sourceStatus === Image.Ready,
                  "mídia de teste deve carregar antes de compor os efeitos")
            check(media.reflectionActive, "reflexo resolvido deve chegar ao renderer")
            check(media.gradientMaskActive, "máscara gradiente resolvida deve chegar ao renderer")
            check(media.vignetteActive, "vinheta resolvida deve chegar ao renderer")
            check(media.decodeSize.width === 240 && media.decodeSize.height === 160,
                  "o teto de decode declarado deve chegar à mídia")
            // Textura e máscara existem para o renderer avançado. Quando ele
            // não está carregado elas não podem custar nada por capa — e a
            // máscara, em particular, não pode ficar visível sobre a mídia.
            check(media.mediaTextureBound === media.advancedEffectsLoaded,
                  "a textura intermediária deve acompanhar o renderer avançado (texture "
                  + media.mediaTextureBound + ", loaded " + media.advancedEffectsLoaded + ")")
            check(media.maskRenderable === media.advancedEffectsLoaded,
                  "a máscara só deve ser renderizável quando há quem a consuma e a oculte (mask "
                  + media.maskRenderable + ", loaded " + media.advancedEffectsLoaded + ")")
            check(media.advancedEffectsLoaded === media.advancedEffectsAvailable,
                  "a capacidade publicada deve resultar no renderer avançado carregado")
            if (captureOutput !== "" && failures === 0) {
                contentItem.grabToImage(function(result) {
                    result.saveToFile(captureOutput)
                    Qt.exit(0)
                })
            } else {
                Qt.exit(failures === 0 ? 0 : 1)
            }
        }
    }
}
