// SPDX-License-Identifier: GPL-3.0-or-later
//
// Prova de BOOTSTRAP DE FOCO do Launcher: ao abrir, sem mouse, a primeira tecla
// já precisa navegar.
//
// Os harnesses irmãos (`check_launcher_gestures.qml` e os demais) instanciam
// `LauncherHome`/`LauncherShell` direto e chamam `forceActiveFocus()` antes de
// pressionar. Isso prova que a tecla ativa o cartão FOCADO — mas entrega o foco
// de mão beijada, que é justamente o que a produção nunca faz. A cena real é
// `LauncherMain`, e lá o shell nasce dentro de um `Loader`.
//
// Medido no host em 2026-09-04, release 2.0.0rc1-a44f52964b3e, com `ydotoold`
// ativo e foco de janela conferido por `kdotool` antes e depois de cada
// injeção: setas, Tab e Return moveram ZERO pixel; um clique de mouse e então a
// mesma seta moveram o anel de foco em 30.201 pixels. O anel ciano era desenhado
// desde o início, então a tela parecia focada sem estar.
//
// Causa: `Loader` não repassa foco ao item carregado a menos que o próprio
// `Loader` tenha `focus: true`. No Deck em Game Mode não existe mouse, então o
// Launcher nascia inoperável.
//
// Por isso aqui NÃO se chama `forceActiveFocus()` em lugar nenhum. A cena é
// montada como em produção e a primeira tecla é a primeira interação.
import QtQuick
import QtTest
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    readonly property var sections: [
        {"id": "library", "title": "Biblioteca", "items": [
            {"id": "celeste", "title": "Celeste", "coverUrl": ""},
            {"id": "hollow", "title": "Hollow Knight", "coverUrl": "",
             "description": "Descrição canônica. ".repeat(300)}
        ]}
    ]

    readonly property var focusMap: ({
        "initial": "library:celeste",
        "rows": ["library:celeste", "library:hollow"],
        "diagnostics": [],
        "nodes": {
            "library:celeste": {"id": "library:celeste", "section": "library", "column": 0,
                                "up": null, "down": null, "left": null,
                                "right": "library:hollow", "action": null},
            "library:hollow": {"id": "library:hollow", "section": "library", "column": 1,
                               "up": null, "down": null, "left": "library:celeste",
                               "right": null, "action": null}
        }
    })

    readonly property var model: ({
        "focusMap": harness.focusMap,
        "sections": harness.sections,
        "catalogSummary": {},
        "returnContext": null
    })

    Component {
        id: sceneComponent
        LauncherMain {}
    }

    Component {
        id: cinemaComponent
        LauncherCinema {}
    }

    TestCase {
        name: "LauncherFocusBootstrap"
        when: windowShown

        function test_cinema_text_does_not_overlap_cover_data() {
            return [
                {tag: "deck", w: 1280, h: 800, textScale: 1},
                {tag: "deck-large-text", w: 1280, h: 800, textScale: 2},
                {tag: "full-hd", w: 1920, h: 1080, textScale: 1.5},
                {tag: "ultrawide", w: 3440, h: 1440, textScale: 2}
            ]
        }

        function test_cinema_text_does_not_overlap_cover(data) {
            const coverHeight = Math.min(data.h * 0.72, 640)
            const cinema = createTemporaryObject(cinemaComponent, harness, {
                width: data.w, height: data.h,
                currentFocus: "library:game",
                accessibility: {visualScale: data.textScale},
                scene: {
                    focusId: "library:game", selected: 0, collection: "Biblioteca",
                    viewport: {width: data.w, height: data.h},
                    items: [{title: "<b>Um título longo</b>", players: 2, genres: ["Aventura"]}],
                    layouts: {covers: {entries: [{
                        x: (data.w - coverHeight * 2/3) / 2,
                        y: (data.h - coverHeight) / 2,
                        width: coverHeight * 2/3, height: coverHeight,
                        scale: 1, opacity: 1, z: 10, highlighted: true, source: ""
                    }]}}
                }
            })
            verify(cinema !== null)
            const cover = findChild(cinema, "cinemaSelectedCover")
            const title = findChild(cinema, "cinemaSelectedTitle")
            const footer = findChild(cinema, "cinemaFooter")
            verify(cover !== null && title !== null && footer !== null)
            wait(0)
            const top = cover.mapToItem(cinema, 0, 0)
            const bottom = cover.mapToItem(cinema, cover.width, cover.height)
            verify(bottom.y > top.y, "a capa deve manter área visível")
            verify(bottom.y <= title.y - 1, "a capa não pode encobrir o título")
            verify(title.y + title.height <= footer.y, "título separado do rodapé")
            verify(footer.y >= 0 && footer.y + footer.height <= cinema.height)
            compare(title.textFormat, Text.PlainText)
            compare(title.text, "<b>Um título longo</b>")
        }

        function test_search_launch_uses_shell_error_and_real_return_context() {
            const scene = createTemporaryObject(sceneComponent, harness)
            scene.model = harness.model
            scene.loadState = "ready"
            scene.searching = true
            verify(scene._launchSearch("hollow", "search:hollow"))
            const shell = scene._activeLauncherShell()
            compare(shell.exitFocus, "library:hollow")
            compare(scene.searching, false)
            // No API in this fixture: the shared launch callback must surface
            // failure, instead of silently swallowing the search request.
            compare(shell.launchState, "failed")
            verify(shell.launchError.indexOf("LAUNCHER-LAUNCH-FAILED-001") >= 0)
            shell.recoverLaunch()
            shell.back()
            compare(shell.homeFocus, "library:hollow")
            compare(scene._launchSearch("absent", "search:absent"), false)
        }

        function test_cinema_keeps_keyboard_navigation_and_activation() {
            const scene = createTemporaryObject(sceneComponent, harness)
            scene.model = harness.model
            scene.loadState = "ready"
            scene.cinemaScene = {
                "focusId": "library:celeste", "selected": 0,
                "collection": "Biblioteca", "items": [{"title": "Celeste"}],
                "layouts": {"covers": {"entries": [{
                    "x": 420, "y": 160, "width": 240, "height": 360,
                    "scale": 1, "opacity": 1, "z": 1, "highlighted": true,
                    "source": ""
                }]}}
            }
            scene.requestActivate()
            tryVerify(function() { return scene.active }, 5000)
            const shell = scene._activeLauncherShell()
            tryVerify(function() { return scene.activeFocusItem !== null }, 2000)
            compare(scene.activeFocusItem.objectName, "launcherCinema")
            const cinema = scene.activeFocusItem
            compare(findChild(scene.contentItem, "launcherItem"), null,
                    "a grade antiga deve ser descarregada, não apenas escondida")
            compare(cinema.selectionReady, true)
            keyClick(Qt.Key_Right)
            tryCompare(shell, "homeFocus", "library:hollow")
            compare(cinema.selectionReady, false)
            compare(cinema.activateSelection(), false,
                    "a capa anterior não pode abrir o novo jogo por toque")
            keyClick(Qt.Key_Return)
            tryCompare(shell, "screen", "game")
            compare(shell.gamePage.title, "Hollow Knight")
            const description = findChild(scene.contentItem, "gameDescription")
            verify(description !== null)
            compare(description.text, harness.sections[0].items[1].description)
            compare(description.textFormat, Text.PlainText)
            const scroll = findChild(scene.contentItem, "gameDescriptionScroll")
            tryVerify(function() { return scroll.contentHeight > scroll.height })
            keyClick(Qt.Key_Down)
            tryVerify(function() { return scroll.contentY > 0 }, 2000,
                      "descrição longa precisa rolar por teclado sem perder Jogar")
            keyClick(Qt.Key_Escape)
            tryCompare(shell, "screen", "home")
            compare(shell.homeFocus, "library:hollow")
        }

        function test_search_is_above_home_and_escape_restores_navigation() {
            const scene = createTemporaryObject(sceneComponent, harness)
            scene.model = harness.model
            scene.loadState = "ready"
            scene.requestActivate()
            tryVerify(function() { return scene.active }, 5000)
            const shell = scene._activeLauncherShell()
            tryVerify(function() { return scene.activeFocusItem !== null }, 2000)
            keyClick(Qt.Key_F)
            tryCompare(scene, "searching", true)
            const field = findChild(scene.contentItem, "launcherSearchField")
            verify(field !== null)
            tryCompare(field, "activeFocus", true)
            const panel = field.parent.parent
            verify(panel.z > shell.parent.z,
                   "a busca precisa ser composta acima do Loader fullscreen")
            keyClick(Qt.Key_Escape)
            tryCompare(scene, "searching", false)
            keyClick(Qt.Key_Right)
            tryCompare(shell, "homeFocus", "library:hollow")
        }

        function test_first_key_navigates_without_any_pointer_interaction() {
            // Cena real, montada como em produção: sem `api`/`token` o modelo
            // entra por atribuição, que é o mesmo caminho do retorno da ponte.
            const scene = createTemporaryObject(sceneComponent, harness)
            verify(scene !== null, "a cena raiz do Launcher precisa instanciar")

            scene.model = harness.model
            scene.loadState = "ready"

            // Ativar a JANELA é o compositor dando foco ao aplicativo, que é o
            // que acontece em produção. Não é entregar foco a um controle —
            // nenhum `forceActiveFocus()` aparece neste arquivo.
            scene.requestActivate()
            tryVerify(function() { return scene.active }, 5000,
                      "a janela precisa ficar ativa para receber teclado")

            const shell = scene._activeLauncherShell()
            verify(shell !== null, "o shell precisa ter carregado dentro do Loader")
            compare(shell.homeFocus, "library:celeste",
                    "o foco lógico inicial precisa vir do focusMap")

            // Esperar a cena assentar antes de pressionar. Isto não entrega
            // foco a ninguém: só evita medir a janela no meio da ativação e
            // atribuir ao produto uma tecla que se perdeu no harness.
            tryVerify(function() { return scene.activeFocusItem !== null }, 2000,
                      "a cena precisa ter algum item focado antes da tecla")

            // Nenhum clique: é a primeira interação do usuário, exatamente como
            // no Deck sem mouse.
            keyClick(Qt.Key_Right)

            tryVerify(function() { return shell.homeFocus === "library:hollow" }, 2000,
                      "a primeira tecla depois de abrir não moveu o foco: o "
                      + "Launcher nasceu sem foco de teclado e só um clique de "
                      + "mouse o destravaria — no Game Mode não existe mouse")
        }

        function test_the_active_focus_lands_inside_the_loaded_shell() {
            // Complemento estrutural: o teste acima também falharia se a tecla
            // se perdesse por outro motivo. Este afirma a condição exata.
            //
            // Note que NÃO se afirma `shell.activeFocus`: assim que o foco
            // desce até o cartão, o shell deixa de ser o item focado e passa a
            // ser apenas ancestral dele. Afirmar o shell reprovaria a cena
            // correta. O que importa é o foco ter aterrissado dentro dele.
            const scene = createTemporaryObject(sceneComponent, harness)
            scene.model = harness.model
            scene.loadState = "ready"
            scene.requestActivate()

            tryVerify(function() { return scene.active }, 5000,
                      "a janela precisa ficar ativa")

            const shell = scene._activeLauncherShell()
            verify(shell !== null, "o shell precisa ter carregado")

            function descendsFrom(item, ancestor) {
                for (let node = item; node !== null; node = node.parent)
                    if (node === ancestor)
                        return true
                return false
            }

            tryVerify(function() {
                return scene.activeFocusItem !== null
                    && descendsFrom(scene.activeFocusItem, shell)
            }, 2000,
                      "nenhum item dentro do shell recebeu foco ativo sem que "
                      + "ninguém o entregasse: um Loader sem `focus: true` não "
                      + "repassa foco ao item que carrega, e o Launcher nasce "
                      + "surdo ao teclado")
        }
    }
}
