// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Nível de detalhe das capas: converte o tamanho em que uma capa será
// desenhada no teto de decodificação que a Image deve usar.
//
// A regra mora em um lugar só de propósito. Uma capa de 600x900 decodificada
// para uma célula de 190x274 custa o decode inteiro, a memória inteira e a
// textura inteira de GPU; multiplicado pelas capas visíveis de uma grade, é a
// diferença entre rolar liso e engasgar. Se cada superfície escolhesse o
// próprio teto, a home e a biblioteca acabariam com nitidez diferente para a
// mesma arte, e o diagnóstico apontaria para a superfície errada.
//
// Este componente não resolve asset, não escolhe fillMode e não conhece o read
// model: ele só aritmética de tamanho.
import QtQuick

QtObject {
    id: lod

    // Quem instancia liga isto a `Screen.devicePixelRatio`. O padrão 1 mantém o
    // componente utilizável em harness sem tela associada.
    property real devicePixelRatio: 1

    // Degrau da escada de LOD, em pixels de dispositivo. Sem o degrau, cada
    // pixel de redimensionamento da janela — e cada troca de foco no carrossel,
    // que muda a largura do delegate — invalidaria a textura e forçaria um novo
    // decode. Com ele, capa focada e periférica caem no mesmo degrau e
    // reaproveitam o mesmo decode.
    readonly property int step: 64

    function decodeStep(logicalPixels) {
        const devicePixels = Math.max(0, logicalPixels) * Math.max(1, devicePixelRatio)
        return Math.max(step, Math.ceil(devicePixels / step) * step)
    }

    // `Qt.size(0, 0)` é o valor que a Image entende como "tamanho natural do
    // arquivo"; aqui nunca devolvemos isso, porque uma superfície que pediu LOD
    // já declarou que conhece o tamanho de desenho.
    function decodeSize(logicalWidth, logicalHeight) {
        return Qt.size(decodeStep(logicalWidth), decodeStep(logicalHeight))
    }
}
