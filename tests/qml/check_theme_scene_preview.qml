// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// A prévia da cena, pela rota real do usuário. O que se prova aqui é que a
// SELEÇÃO chega à rota: ela decide a geometria, e uma prévia que ignorasse os
// seletores mostraria sempre a mesma cena com controles que não fazem nada.
import QtQuick
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    width: 1000
    height: 700

    property var calls: []

    ThemeScenePreview {
        id: preview
        anchors.fill: parent
        themeId: "org.test.tema"
        requestAction: function(actionId, payload, callback, _errorCallback) {
            calls.push({"actionId": actionId, "payload": payload})
            callback({
                "themeId": "org.test.tema",
                "assets": {"resolved": 3, "missing": [], "awaitingSystem": []},
                "selections": {
                    "aspectRatio": ["16:10", "4:3"],
                    "colorScheme": ["blue", "green"],
                    "fontSize": ["medium"],
                    "variant": ["cover"]
                },
                "scene": {"views": [
                    {"id": "gamelist", "elements": [
                        {"id": "a", "kind": "text", "name": "t",
                         "layout": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.05},
                         "text": "Olá"},
                        {"id": "b", "kind": "carousel", "name": "c",
                         "layout": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}}
                    ]}
                ]}
            })
        }
    }

    TestCase {
        name: "ThemeScenePreview"
        when: windowShown

        function test_the_preview_asks_for_the_scene_on_its_own() {
            verify(calls.length > 0, "a prévia não chamou nenhuma rota")
            compare(calls[0].actionId, "theme.scene.render")
            compare(calls[0].payload.themeId, "org.test.tema")
        }

        function test_every_selection_dimension_reaches_the_route() {
            // A proporção carrega a geometria. Se ela não sair no payload, o
            // seletor é decorativo e a cena volta sem posição nenhuma.
            const payload = calls[0].payload
            for (const key of ["aspectRatio", "colorScheme", "fontSize", "variant", "systemId"])
                verify(payload[key] !== undefined, "seleção ausente no payload: " + key)
        }

        function test_the_options_offered_come_from_the_theme() {
            // Mais a ausência de escolha, que precisa ser oferecível.
            compare(preview.optionsFor("aspectRatio"), ["", "16:10", "4:3"])
            compare(preview.optionsFor("naoDeclarada"), [""])
        }

        function test_an_unchosen_dimension_is_named_instead_of_blank() {
            // Seletor em branco parece controle quebrado.
            compare(preview.labelFor("Proporção", ""), "Proporção: padrão do tema")
            compare(preview.labelFor("Proporção", "16:10"), "Proporção: 16:10")
        }

        function test_choosing_a_dimension_asks_the_route_again() {
            const before = calls.length
            const box = findChild(preview, "aspectRatioBox")
            verify(box !== null, "seletor de proporção não encontrado")
            box.currentIndex = 1
            box.activated(1)
            verify(calls.length > before, "mudar a proporção não recompilou a cena")
        }
    }
}
