// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Escape e Tab REAIS, pela rota de entrada do usuário.
//
// A passagem anterior chamou `dialog.close()` de "Escape". Não é: `close()` é
// uma chamada programática que ignora `closePolicy` inteiro. Um diálogo com
// `Popup.NoAutoClose` fecha por `close()` e NÃO deve fechar por Escape — e o
// harness antigo teria dado o mesmo verde nos dois casos.
//
// Aqui os eventos passam por `keyClick`, do QtTest, que entrega a tecla ao item
// com foco pelo mesmo caminho de um teclado de verdade.
//
// Uso: qmltestrunner -input tests/qml/check_dialog_keys.qml

import QtQuick
import QtTest
import "../../src/steamzero/ui/qml"

Main {
    id: shell
    visible: true
    width: 1600
    height: 1000

    // Plano sintético: só o que a UI lê para desenhar. Nenhum segredo.
    function samplePlan(action) {
        return {
            "planId": "plan-auditoria",
            "confirmToken": "token-auditoria",
            "action": action,
            "summary": "Plano de auditoria offscreen.",
            "steps": [],
            "rollback": {"available": true, "detail": "Rollback declarado."}
        }
    }

    function focusablesIn(item, out, depth) {
        if (!item || depth > 30)
            return out
        if (item.enabled === true && item.visible === true
                && item.activeFocusOnTab === true)
            out.push(item)
        const kids = item.children
        if (kids) {
            for (let i = 0; i < kids.length; i++)
                focusablesIn(kids[i], out, depth + 1)
        }
        return out
    }

    function isInside(root, item) {
        let node = item
        while (node) {
            if (node === root)
                return true
            node = node.parent
        }
        return false
    }

    TestCase {
        id: suite
        name: "DialogKeyJourneys"
        when: windowShown

        function invoker() {
            return shell.navigationMenuControl
        }

        function openWith(dialog, plan) {
            if (plan)
                shell.emulationPlan = plan
            invoker().forceActiveFocus(Qt.TabFocusReason)
            dialog.open()
            tryVerify(function() { return dialog.visible === true }, 2000,
                      "evento dialog-aberto não ocorreu")
        }

        // ---- Escape real -------------------------------------------------

        function test_01_escape_closes_a_dialog_that_allows_it() {
            const dialog = shell.emulationPlanDialogControl
            openWith(dialog, shell.samplePlan("emulator.install"))

            keyClick(Qt.Key_Escape)

            tryVerify(function() { return dialog.visible === false }, 2000,
                      "Escape real não fechou um diálogo com closePolicy permissiva")
            verify(shell.emulationPlan === null,
                   "o plano sobreviveu ao cancelamento por Escape real")
        }

        function test_02_escape_does_not_close_recovery() {
            // recoveryDialog declara Popup.NoAutoClose: recovery é decisão que
            // o usuário precisa tomar, não algo que se dispensa por engano.
            // Este é o teste que `close()` jamais poderia fazer.
            const dialog = shell.recoveryDialogControl
            openWith(dialog, null)

            keyClick(Qt.Key_Escape)
            wait(200)

            verify(dialog.visible === true,
                   "Escape fechou o modal de recovery, que declara NoAutoClose")
            dialog.close()
        }

        function test_03_escape_returns_focus_to_the_invoker() {
            const dialog = shell.componentPlanDialogControl
            const origin = invoker()
            shell.componentPlan = shell.samplePlan("component.install")
            origin.forceActiveFocus(Qt.TabFocusReason)
            dialog.open()
            tryVerify(function() { return dialog.visible === true }, 2000)

            keyClick(Qt.Key_Escape)

            tryVerify(function() { return dialog.visible === false }, 2000)
            tryVerify(function() { return shell.activeFocusItem === origin }, 2000,
                      "evento foco-restaurado não ocorreu após Escape real")
            verify(shell.componentPlan === null, "plano sujo após Escape real")
        }

        // ---- focus trap ---------------------------------------------------

        function test_04_tab_cycle_stays_inside_the_modal() {
            const dialog = shell.emulationPlanDialogControl
            openWith(dialog, shell.samplePlan("emulator.install"))

            const inside = shell.focusablesIn(dialog.contentItem, [], 0)
            verify(inside.length > 1,
                   "o modal precisa de mais de um focável para o ciclo significar algo")

            // Uma volta completa mais uma: se o foco escapar para trás do modal
            // em qualquer passo, o produto perdeu o trap.
            for (let i = 0; i < inside.length + 1; i++) {
                keyClick(Qt.Key_Tab)
                verify(shell.isInside(dialog.contentItem, shell.activeFocusItem),
                       "Tab levou o foco para fora do modal no passo " + i
                       + " (foco em " + shell.activeFocusItem + ")")
            }

            for (let j = 0; j < inside.length + 1; j++) {
                keyClick(Qt.Key_Backtab)
                verify(shell.isInside(dialog.contentItem, shell.activeFocusItem),
                       "Shift+Tab levou o foco para fora do modal no passo " + j)
            }

            keyClick(Qt.Key_Escape)
            tryVerify(function() { return dialog.visible === false }, 2000)
        }

        function test_05_focus_enters_the_modal_on_open() {
            const dialog = shell.conflictDialogControl
            shell.conflictPlan = shell.samplePlan("desktop.conflict")
            invoker().forceActiveFocus(Qt.TabFocusReason)
            dialog.open()
            tryVerify(function() { return dialog.visible === true }, 2000)
            tryVerify(function() {
                return shell.isInside(dialog.contentItem, shell.activeFocusItem)
            }, 2000, "o foco não entrou no modal ao abrir")
            keyClick(Qt.Key_Escape)
            tryVerify(function() { return dialog.visible === false }, 2000)
        }
    }
}
