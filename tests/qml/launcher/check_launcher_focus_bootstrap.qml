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
            {"id": "hollow", "title": "Hollow Knight", "coverUrl": ""}
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

    TestCase {
        name: "LauncherFocusBootstrap"
        when: windowShown

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
