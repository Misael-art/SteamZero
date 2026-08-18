// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Consumidor do plano de movimento já materializado. Aplica somente o
// snapshot do estado pedido; não avalia easing nem executa timeline.
import QtQuick

Item {
    id: motionPreview

    required property var motion
    property string stateName: "normal"

    readonly property var snapshot: {
        if (!motion || !motion.states)
            return ({"opacity": 1, "scale": 1, "translateX": 0, "translateY": 0})
        return motion.states[stateName] || motion.states.normal
    }
    readonly property real snapshotOpacity: snapshot && snapshot.opacity !== undefined ? snapshot.opacity : 1
    readonly property real snapshotScale: snapshot && snapshot.scale !== undefined ? snapshot.scale : 1
    readonly property real snapshotX: snapshot && snapshot.translateX !== undefined ? snapshot.translateX : 0
    readonly property real snapshotY: snapshot && snapshot.translateY !== undefined ? snapshot.translateY : 0
    readonly property int focusDuration: {
        if (!motion || !motion.transitions || !motion.transitions.focusIn)
            return 0
        return Number(motion.transitions.focusIn.duration)
    }

    // Transparência por estado de interação. A opacidade e a duração do fade
    // chegam resolvidas; este consumidor não sabe o que é "ocioso".
    readonly property var presence: motion && motion.presence ? motion.presence : ({})
    readonly property var chromePresence: presence.chrome
        ? presence.chrome : ({"opacity": 1, "fadeDuration": 0, "state": "unknown"})
    readonly property real chromeOpacity: Number(chromePresence.opacity)
    readonly property int chromeFadeDuration: Number(chromePresence.fadeDuration)
    readonly property string interactionState: String(chromePresence.state)

    Rectangle {
        id: card
        objectName: "motionCard"
        anchors.centerIn: parent
        width: Math.max(48, parent.width * 0.42)
        height: Math.max(28, parent.height * 0.55)
        radius: 8
        color: "#22d3ee"
        opacity: motionPreview.snapshotOpacity
        scale: motionPreview.snapshotScale
        transform: Translate {
            x: motionPreview.snapshotX
            y: motionPreview.snapshotY
        }
    }

    Rectangle {
        id: chromeLayer
        objectName: "chromeLayer"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 10
        color: "#f2f6fb"
        opacity: motionPreview.chromeOpacity

        Behavior on opacity {
            NumberAnimation { duration: motionPreview.chromeFadeDuration }
        }
    }
}
