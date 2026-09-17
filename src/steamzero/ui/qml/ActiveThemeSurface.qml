// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Camada visual do tema ativo. O backend entrega somente assetUris validadas;
// sem background a central continua legível com a paleta de tokens.
import QtQuick

Item {
    id: surface

    property var assetUris: ({})
    property color fallbackColor: "#e7eceb"
    property bool highContrast: false

    anchors.fill: parent
    z: -100
    visible: true

    Rectangle {
        anchors.fill: parent
        color: surface.fallbackColor
    }

    Image {
        id: backgroundImage
        anchors.fill: parent
        visible: !surface.highContrast && source.toString().length > 0
        source: surface.assetUris && surface.assetUris.background
            ? String(surface.assetUris.background) : ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        smooth: true
        opacity: 0.58
    }

    // Vignette preserva legibilidade da central sem editar o asset original.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#b8000000" }
            GradientStop { position: 0.48; color: "#22000000" }
            GradientStop { position: 1.0; color: "#d9000000" }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.color: surface.highContrast ? "#ffffff" : "transparent"
        border.width: surface.highContrast ? 2 : 0
    }
}
