// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Node builtin da engine para invert e hue rotate.
//
// Nem todo runtime QML traz o módulo de efeitos de cor: a imagem canônica do
// gate visual, por exemplo, só instala qt6-declarative e qt6-base. Em vez de
// declarar a capability no domínio e sumir aqui, este node instancia o efeito
// sob demanda e publica `available`. Quem consome decide o fallback, e o
// diagnóstico chega ao usuário em vez de virar pixel silenciosamente igual.
//
// O tema não fornece shader, expressão nem parâmetro livre: só nomeia `invert`
// ou `hueRotate` e uma fração de rotação já validada pelo domínio.

import QtQuick

Item {
    id: transform

    // Imagem-fonte já carregada; o node nunca decodifica de novo.
    required property Item source
    // "invert" | "hueRotate" | "" (nenhum)
    property string mode: ""
    // Fração 0..1 de rotação de matiz, usada apenas por hueRotate.
    property real hue: 0.0

    readonly property bool requested: mode === "invert" || mode === "hueRotate"
    readonly property bool available: _effect !== null
    // Pedido que o runtime não consegue atender: o consumidor publica fallback.
    readonly property bool unsupported: requested && !available

    property Item _effect: null
    property var _component: null

    function _build() {
        if (_effect !== null) {
            _effect.destroy()
            _effect = null
        }
        if (!requested)
            return
        // O corpo é fixo e escrito aqui: nada do pacote entra nesta string.
        const body = mode === "invert"
            ? 'import QtQuick; import Qt5Compat.GraphicalEffects; Item {\n'
              + '  id: node\n'
              + '  property Item src: null\n'
              + '  property real amount: 0\n'
              + '  anchors.fill: parent\n'
              + '  LevelAdjust {\n'
              + '    id: inverted\n'
              + '    anchors.fill: parent\n'
              + '    source: node.src\n'
              + '    minimumOutput: "#ffffffff"\n'
              + '    maximumOutput: "#ff000000"\n'
              + '    visible: false\n'
              + '  }\n'
              // O invert de níveis também levanta o alpha das regiões vazias.
              // Remascarar com a própria fonte devolve a transparência e
              // preserva os furos internos da forma.
              + '  OpacityMask { anchors.fill: parent; source: inverted; maskSource: node.src }\n'
              + '}'
            : 'import QtQuick; import Qt5Compat.GraphicalEffects; Item {\n'
              + '  id: node\n'
              + '  property Item src: null\n'
              + '  property real amount: 0\n'
              + '  anchors.fill: parent\n'
              + '  HueSaturation { anchors.fill: parent; source: node.src; hue: node.amount }\n'
              + '}'
        try {
            _component = Qt.createQmlObject(body, transform, "AssetColorTransform." + mode)
            _component.src = source
            if (mode === "hueRotate")
                _component.amount = hue
            _effect = _component
        } catch (error) {
            // Módulo ausente no runtime. Sem exceção vazando e sem efeito falso.
            _effect = null
        }
    }

    onModeChanged: _build()
    onHueChanged: {
        if (_effect !== null && mode === "hueRotate")
            _effect.amount = hue
    }
    onSourceChanged: _build()
    Component.onCompleted: _build()
}
