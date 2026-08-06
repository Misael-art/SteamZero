// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Anel visual de foco. Deliberadamente burro, como SceneText.qml e
// SceneImage.qml: ATRIBUI os valores do modelo e não decide nada.
//
// O que o shell manda (caixa expandida pela margem, cor, espessura da borda)
// já foi decidido pelo tema — `focus_ring_geometry` e o token
// `color.focusRing`. Se o anel apareceu no lugar errado, o defeito está ANTES
// deste componente: na geometria ou no adapter. Não conserte aqui.
//
// Geometria vinda pronta no modelo: o QML não sabe o que é "célula focada",
// não re-deriva a caixa da capa e não tem regra de inset própria.
import QtQuick

Rectangle {
    id: focusRing

    required property var model

    objectName: model.id
    x: model.x
    y: model.y
    width: model.width
    height: model.height
    visible: model.visible

    // Borda do anel: cor e espessura vêm do modelo. Fundo transparente de
    // propósito — o anel contorna, não cobre.
    color: "transparent"
    border.color: model.color
    border.width: model.borderWidth
}