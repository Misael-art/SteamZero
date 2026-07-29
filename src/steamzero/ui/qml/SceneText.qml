// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Renderizador de texto de cena. Deliberadamente burro.
//
// Este componente ATRIBUI valores. Ele não resolve token, não consulta o read
// model, não escolhe fonte de fallback e não corrige valor que chegou errado.
//
// A razão é concreta: se o QML tivesse suas próprias regras de fallback, elas um
// dia divergiriam das do resolver — e o mesmo tema renderizaria diferente
// conforme o backend, enquanto o diagnóstico apontaria para a regra errada.
// Manter a decisão de um lado só é o que garante que dois renderizadores
// desenhem a mesma coisa.
//
// Se um valor chegou errado aqui, o defeito está ANTES: no resolver ou no
// adapter. Não conserte no QML.

import QtQuick

Text {
    id: sceneText

    // O modelo vem pronto do adapter. Nenhum campo é interpretado.
    required property var model

    objectName: model.id
    text: model.text

    x: model.x
    y: model.y

    // `width`/`height` ausentes no modelo significam dimensão implícita — o
    // `Text` se dimensiona pelo conteúdo. Atribuir 0 seria diferente: caixa
    // explicitamente sem tamanho. Por isso a distinção é `undefined` vs valor,
    // e não um número mágico.
    width: model.width !== undefined ? model.width : implicitWidth
    height: model.height !== undefined ? model.height : implicitHeight

    visible: model.visible
    opacity: model.opacity
    color: model.color

    font.family: model.fontFamily
    font.pixelSize: model.fontPixelSize
    font.weight: model.fontWeight
    font.italic: model.fontItalic

    horizontalAlignment: Text[model.horizontalAlignment]
    verticalAlignment: Text[model.verticalAlignment]
}
