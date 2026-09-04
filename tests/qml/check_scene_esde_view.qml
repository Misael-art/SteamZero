// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// O renderizador do IR de cena. Os dois casos que importam aqui nasceram de
// defeitos medidos: cor com alfa lida ao contrário e elemento sem geometria
// desenhado no tamanho natural cobrindo a tela inteira.
import QtQuick
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    width: 1000
    height: 800

    SceneEsdeView {
        id: view
        anchors.fill: parent
        viewData: ({
            "id": "system",
            "elements": [
                {"id": "com-geometria", "kind": "image", "name": "fundo",
                 "layout": {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.25},
                 "source": "qrc:/inexistente.png"},
                {"id": "sem-geometria", "kind": "image", "name": "solto",
                 "source": "qrc:/inexistente.png"},
                {"id": "texto", "kind": "text", "name": "titulo",
                 "layout": {"x": 0.1, "y": 0.6, "width": 0.3, "height": 0.05},
                 "text": "Olá"},
                {"id": "vinculo", "kind": "text", "name": "bind",
                 "layout": {"x": 0.1, "y": 0.7, "width": 0.3, "height": 0.05},
                 "binding": {"field": "title"}},
                {"id": "carrossel", "kind": "carousel", "name": "car",
                 "layout": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0,
                            "itemWidth": 0.1, "itemHeight": 0.15, "maxItemCount": 4}},
                {"id": "menu-only", "kind": "helpSystem", "name": "help-menu",
                 "layout": {"x": 0.5, "y": 0.98, "width": 0.3, "height": 0.04,
                            "scope": "menu"}},
                {"id": "medalhas", "kind": "badges", "name": "bg",
                 "layout": {"x": 0.5, "y": 0.5, "width": 0.2, "height": 0.1}},
                {"id": "escondido", "kind": "image", "name": "oculto",
                 "layout": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                 "appearance": {"visible": false},
                 "source": "qrc:/inexistente.png"}
            ]
        })
    }

    TestCase {
        name: "SceneEsdeView"
        when: windowShown

        function test_an_element_without_geometry_is_not_drawn() {
            // Desenhá-lo no tamanho natural em (0,0) inventaria layout e, na
            // medição real, cobria a cena inteira com uma arte esticada.
            const reasons = view.notDrawn.filter(function(e) { return e.id === "sem-geometria" })
            compare(reasons.length, 1)
            compare(reasons[0].reason, "sem geometria declarada")
        }

        function test_a_kind_without_a_renderer_says_so_instead_of_vanishing() {
            // `carousel` passou a desenhar; `badges` ainda não. O caso precisa
            // continuar coberto, senão o caminho de degradação fica sem prova.
            const badges = view.notDrawn.filter(function(e) { return e.id === "medalhas" })
            compare(badges.length, 1)
            verify(badges[0].reason.indexOf("tipo ainda nao desenhado") === 0)
        }

        function test_a_data_driven_kind_draws_its_structure() {
            // O conteúdo do carrossel vem do runtime, mas a MOLDURA e os
            // compartimentos são do tema, e o tema pediu que aparecessem.
            const carousel = view.notDrawn.filter(function(e) { return e.id === "carrossel" })
            compare(carousel.length, 0)
        }

        function test_a_menu_scoped_element_stays_out_of_the_base_view() {
            // `scope: menu` descreve o elemento COM UM MENU ABERTO. Desenhá-lo
            // na base empilhava um segundo helpsystem sobre o do tema, com
            // outra posição e outra cor, disputando o rodapé.
            const scoped = view.notDrawn.filter(function(e) { return e.id === "menu-only" })
            compare(scoped.length, 1)
            verify(scoped[0].reason.indexOf("escopo \'menu\'") === 0)
        }

        function test_an_element_the_theme_hides_is_not_counted_as_drawn() {
            // `visible: false` é escolha do tema. Contá-lo inflaria a fidelidade
            // com um elemento que o próprio tema manda esconder.
            const hidden = view.notDrawn.filter(function(e) { return e.id === "escondido" })
            compare(hidden.length, 1)
            compare(hidden[0].reason, "o tema declara invisivel")
        }

        function test_text_and_binding_both_count_as_drawable() {
            // 2 textos + o carrossel. `badges` e o oculto ficam de fora.
            compare(view.drawnCount, 4)
        }

        function test_a_binding_shows_the_field_instead_of_inventing_a_title() {
            // A superfície não tem dado de jogo. Escrever um título plausível
            // faria a prévia mentir sobre o que o tema mostra.
            const bound = view.notDrawn.filter(function(e) { return e.id === "vinculo" })
            compare(bound.length, 0)
        }

        function test_esde_colour_is_reordered_for_qml() {
            // ES-DE escreve RRGGBBAA; QML lê AARRGGBB. Sem reordenar, o alfa
            // vira vermelho e só um branco opaco sobreviveria por acaso.
            compare(view.esdeColor("ff000080", "#000000"), "#80ff0000")
            compare(view.esdeColor("ff0000", "#000000"), "#ff0000")
            compare(view.esdeColor("", "#123456"), "#123456")
            compare(view.esdeColor(undefined, "#123456"), "#123456")
        }

        function test_geometry_is_normalised_against_the_surface() {
            compare(view.width, 1000)
            compare(view.numberOr({"x": 0.5}, "x", 0), 0.5)
            compare(view.numberOr({}, "x", 0.25), 0.25)
            compare(view.numberOr(null, "x", 0.75), 0.75)
        }
    }
}
