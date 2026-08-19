// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Renderizador de badge semântico. Deliberadamente burro, como SceneText.
//
// O caractere do glifo, o par de cores da variante, o texto já truncado e a
// decisão de visibilidade chegam prontos do resolver. Este componente não
// conhece "favorito", "aviso" ou "atualizando": ele só desenha o que recebeu.
//
// Se um badge apareceu vazio, com a cor errada ou com um glifo indevido, o
// defeito está no resolver — não conserte aqui.

import QtQuick

Rectangle {
    id: sceneBadge

    // O modelo vem pronto do adapter. Nenhum campo é interpretado.
    required property var model

    objectName: model.id

    x: model.x
    y: model.y
    z: model.z !== undefined ? model.z : 0
    scale: model.scale !== undefined ? model.scale : 1

    width: model.width !== undefined ? model.width : row.implicitWidth + 12
    height: model.height !== undefined ? model.height : row.implicitHeight + 6

    visible: model.visible
    opacity: model.opacity
    color: model.background
    radius: height / 2

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 4

        Text {
            id: glyph
            objectName: "badgeGlyph"
            visible: text.length > 0
            text: model.glyphChar
            color: model.foreground
            font.pixelSize: 12
        }

        Text {
            id: label
            objectName: "badgeLabel"
            visible: text.length > 0
            text: model.text
            color: model.foreground
            font.pixelSize: 12
        }
    }
}
