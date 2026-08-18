// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Renderizador de imagem de cena. Deliberadamente burro.
//
// Este componente ATRIBUI valores. Ele não resolve asset, não consulta o read
// model, não escolhe fill mode e não corrige valor que chegou errado.
//
// A razão é a mesma de SceneText.qml: se o QML tivesse suas próprias regras de
// fallback, elas um dia divergiriam das do resolver — e o mesmo tema
// renderizaria diferente conforme o backend, enquanto o diagnóstico apontaria
// para a regra errada. Manter a decisão de um lado só é o que garante que dois
// renderizadores desenhem a mesma coisa.
//
// `model.source` é o caminho de asset do pacote (assets/...), nunca um caminho
// do host. Quem entrega o arquivo real é o shell, na fronteira do QML; este
// componente recebe o resultado disso via `source`.
//
// Se um valor chegou errado aqui, o defeito está ANTES: no resolver ou no
// adapter. Não conserte no QML.

import QtQuick

Image {
    id: sceneImage

    // O modelo vem pronto do adapter. Nenhum campo é interpretado.
    required property var model

    objectName: model.id
    source: model.source

    x: model.x
    y: model.y
    z: model.z !== undefined ? model.z : 0
    scale: model.scale !== undefined ? model.scale : 1

    // `width`/`height` ausentes no modelo significam dimensão implícita — a
    // imagem no tamanho natural do arquivo. Atribuir 0 seria diferente: caixa
    // explicitamente sem tamanho. Por isso a distinção é `undefined` vs valor,
    // e não um número mágico.
    width: model.width !== undefined ? model.width : implicitWidth
    height: model.height !== undefined ? model.height : implicitHeight

    visible: model.visible
    opacity: model.opacity

    fillMode: Image[model.fillMode]
}
