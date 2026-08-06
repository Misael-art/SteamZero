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
        fillMode: Image.PreserveAspectCrop
        effects: [
            {"type": "reflection", "parameters": {"opacity": 0.35, "scale": 0.30}},
            {"type": "gradientMask", "parameters": {"start": 0.82, "end": 0.04}},
            {"type": "vignette", "parameters": {"color": "#071019", "strength": 0.28}}
        ]
    }

    Timer {
        interval: 180
        running: true
        repeat: false
        onTriggered: {
            check(media.sourceStatus === Image.Ready,
                  "mídia de teste deve carregar antes de compor os efeitos")
            check(media.reflectionActive, "reflexo resolvido deve chegar ao renderer")
            check(media.gradientMaskActive, "máscara gradiente resolvida deve chegar ao renderer")
            check(media.vignetteActive, "vinheta resolvida deve chegar ao renderer")
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
