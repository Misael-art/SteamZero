// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// VS-02 — prova que o Qt ACEITA o que o adapter emite.
//
// Os testes em Python provam o mapeamento; nenhum deles prova que
// `Text["AlignHCenter"]` resolve, que `font.weight: 600` é aceito, ou que
// `#80112233` não vira "Invalid property assignment" — o mesmo erro que já
// derrubou `rgba(212,84,84,0.08)` neste repositório.
//
// A entrada aqui é o payload literal de `QmlTextRenderModel.to_dict()`. Se o
// adapter mudar a forma, este harness quebra, que é o ponto: contrato entre dois
// lados só vale enquanto os dois lados são exercitados juntos.
import QtQuick
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 1920
    height: 1080

    property int failures: 0
    property int checks: 0

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        failures += 1
        console.error("FAIL: " + message)
    }

    // Payloads exatamente como `to_dict()` os emite.
    readonly property var packagedModel: ({
        "id": "gameTitle",
        "text": "Chrono Trigger",
        "x": 960.0,
        "y": 120.0,
        "width": 1536.0,
        "height": 64.0,
        "visible": true,
        "opacity": 1.0,
        "color": "#f2f6fb",
        "fontFamily": "Gilroy",
        "fontPixelSize": 48.0,
        "fontWeight": 600,
        "fontItalic": false,
        "horizontalAlignment": "AlignHCenter",
        "verticalAlignment": "AlignVCenter",
        "fontSource": "asset://font/Gilroy"
    })

    // Sem `width`/`height`: dimensão implícita. É o caso que um `0.0` apagaria.
    readonly property var implicitModel: ({
        "id": "subtitle",
        "text": "Square, 1995",
        "x": 0.0,
        "y": 0.0,
        "visible": true,
        "opacity": 0.5,
        "color": "#80112233",
        "fontFamily": "sans-serif",
        "fontPixelSize": 24.0,
        "fontWeight": 400,
        "fontItalic": true,
        "horizontalAlignment": "AlignRight",
        "verticalAlignment": "AlignBottom"
    })

    SceneText {
        id: packaged
        model: harness.packagedModel
    }

    SceneText {
        id: implicitSized
        model: harness.implicitModel
    }

    Component.onCompleted: {
        check(packaged.text === "Chrono Trigger", "texto não chegou")
        check(packaged.x === 960.0 && packaged.y === 120.0, "posição não aplicada")
        check(packaged.width === 1536.0, "largura explícita não aplicada: " + packaged.width)
        check(packaged.height === 64.0, "altura explícita não aplicada")
        check(packaged.visible === true, "visibilidade não aplicada")
        check(packaged.opacity === 1.0, "opacidade não aplicada")
        check(packaged.font.pixelSize === 48.0, "tamanho de fonte não aplicado")
        check(packaged.font.weight === 600, "peso não aplicado: " + packaged.font.weight)
        check(packaged.font.italic === false, "itálico não deveria estar ligado")

        // O ponto crítico: o nome vindo do adapter precisa resolver no enum do
        // Qt. Se `Text[nome]` devolvesse `undefined`, a atribuição falharia em
        // silêncio e o alinhamento cairia no default sem ninguém perceber.
        check(packaged.horizontalAlignment === Text.AlignHCenter,
              "alinhamento horizontal não resolveu: " + packaged.horizontalAlignment)
        check(packaged.verticalAlignment === Text.AlignVCenter,
              "alinhamento vertical não resolveu")

        // Cor precisa ser ACEITA, não só atribuída. `rgba()` já falhou aqui.
        check(packaged.color.toString().toLowerCase().indexOf("f2f6fb") !== -1,
              "cor não aplicada: " + packaged.color)

        check(implicitSized.horizontalAlignment === Text.AlignRight,
              "AlignRight não resolveu")
        check(implicitSized.verticalAlignment === Text.AlignBottom,
              "AlignBottom não resolveu")
        check(implicitSized.font.italic === true, "itálico não aplicado")
        check(implicitSized.opacity === 0.5, "opacidade fracionária não aplicada")

        // Dimensão implícita: sem `width` no payload, o Text se dimensiona pelo
        // conteúdo. Zero significaria elemento invisível — outra coisa.
        check(implicitSized.width === implicitSized.implicitWidth,
              "largura implícita não veio do conteúdo: " + implicitSized.width)
        check(implicitSized.width > 0,
              "largura implícita zerada — o texto não seria visível")
        check(implicitSized.height === implicitSized.implicitHeight,
              "altura implícita não veio do conteúdo")

        // Cor com alfa: `#AARRGGBB` precisa ser aceito pelo QML.
        check(implicitSized.color.a > 0.4 && implicitSized.color.a < 0.6,
              "alfa de #80112233 não foi interpretado: " + implicitSized.color.a)

        if (failures > 0) {
            console.error("check_scene_text: " + failures + " de " + checks + " falharam")
            Qt.exit(1)
        } else {
            console.info("check_scene_text: " + checks + " verificações OK")
            Qt.exit(0)
        }
    }
}
