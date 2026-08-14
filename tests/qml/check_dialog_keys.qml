// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Escape e Tab REAIS, pela rota de entrada do usuário. A raiz Item é
// intencional: QuickTest hospeda casos em QQuickView; Main é uma Window.

import QtQuick
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 1600
    height: 1000

    Main {
        id: shell
        visible: true
        width: 1600
        height: 1000
    }

    TestCase {
        id: suite
        name: "DialogKeyJourneys"
        when: windowShown

        function emulatorPlan() {
            return {
                "planId": "emulator-plan-audit",
                "confirmToken": "emulator-token-audit",
                "action": "install",
                "summary": "Instalar o emulador de auditoria.",
                "preview": "Nenhum arquivo do usuário será alterado sem confirmação.",
                "steps": [{"id": "install", "label": "Instalar emulador"}],
                "rollback": {"available": true, "detail": "Rollback declarado."},
                "auditPreview": [],
                "quarantineId": ""
            }
        }

        function componentPlan() {
            return {
                "planId": "component-plan-audit",
                "confirmToken": "component-token-audit",
                "action": "install",
                "summary": "Instalar o componente de auditoria.",
                "preview": "O componente será verificado depois da aplicação.",
                "steps": [{"id": "install", "label": "Instalar componente"}],
                "rollback": {"available": true, "detail": "Rollback declarado."}
            }
        }

        function conflictPlan() {
            return {
                "planId": "conflict-plan-audit",
                "confirmToken": "conflict-token-audit",
                "action": {
                    "unit": "steamzero-audit-watcher.service",
                    "commands": [["systemctl", "--user", "stop",
                                  "steamzero-audit-watcher.service"]]
                },
                "summary": "Liberar o controle de auditoria.",
                "preview": "O watcher de auditoria será interrompido.",
                "steps": [{"id": "release", "label": "Liberar controle"}],
                "rollback": {"available": true, "detail": "Rollback declarado."}
            }
        }

        function invoker() {
            return shell.responsiveNavigation.itemAt(0)
        }

        function activateShell() {
            shell.requestActivate()
            tryVerify(function() { return shell.active === true }, 2000,
                      "a janela do produto não ficou ativa")
        }

        function visualChildren(item) {
            if (!item)
                return []
            if (item.childItems !== undefined)
                return item.childItems
            if (item.children !== undefined)
                return item.children
            return []
        }

        function addUnique(items, item) {
            if (item && items.indexOf(item) < 0)
                items.push(item)
        }

        function focusablesIn(item, out, depth) {
            if (!item || depth > 40)
                return out
            if (item.enabled === true && item.visible === true
                    && item.activeFocusOnTab === true)
                addUnique(out, item)
            const kids = visualChildren(item)
            for (let i = 0; i < kids.length; i++)
                focusablesIn(kids[i], out, depth + 1)
            return out
        }

        function modalFocusables(dialog) {
            const result = []
            // Popup/Overlay pode reparentar visualmente o conteúdo; o ponto de
            // entrada lógico continua sendo contentItem. Enumeramos a árvore
            // visual dela, não a cadeia de parent do foco ativo.
            focusablesIn(dialog.contentItem, result, 0)
            return result
        }

        function itemBelongsToModal(dialog, item) {
            if (!dialog || !item)
                return false
            const focusables = modalFocusables(dialog)
            for (let i = 0; i < focusables.length; i++) {
                const target = focusables[i]
                if (item === target)
                    return true
                // Um botão pode expor um subitem interno como activeFocusItem.
                const descendants = []
                focusablesIn(target, descendants, 0)
                if (descendants.indexOf(item) >= 0)
                    return true
            }
            return false
        }

        function waitForDialogFocus(dialog) {
            tryVerify(function() {
                return itemBelongsToModal(dialog, shell.activeFocusItem)
            }, 2000, "o foco não entrou no conteúdo visual do modal")
        }

        function openWith(dialog, plan, assignPlan) {
            activateShell()
            invoker().forceActiveFocus(Qt.TabFocusReason)
            tryVerify(function() { return shell.activeFocusItem === invoker() }, 2000,
                      "o originador não recebeu foco antes de abrir o modal")
            if (assignPlan)
                assignPlan(plan)
            dialog.open()
            tryVerify(function() { return dialog.visible === true }, 2000,
                      "evento dialog-aberto não ocorreu")
            waitForDialogFocus(dialog)
        }

        function assertFocusOracle(dialog) {
            const focusables = modalFocusables(dialog)
            verify(focusables.length > 1,
                   "o modal precisa enumerar mais de um focável")
            verify(itemBelongsToModal(dialog, shell.activeFocusItem),
                   "o foco inicial não foi reconhecido como interno")
            verify(!itemBelongsToModal(dialog, invoker()),
                   "o controle conhecido atrás do modal foi classificado como interno")
            for (let i = 0; i < focusables.length; i++) {
                focusables[i].forceActiveFocus(Qt.TabFocusReason)
                tryVerify(function() {
                    return shell.activeFocusItem === focusables[i]
                }, 2000, "o focável enumerado não recebeu foco")
                verify(itemBelongsToModal(dialog, shell.activeFocusItem),
                       "o focável enumerado foi classificado como externo: " + i)
            }
        }

        function test_01_escape_closes_a_dialog_that_allows_it() {
            const dialog = shell.emulationPlanDialogControl
            openWith(dialog, emulatorPlan(), function(plan) { shell.emulationPlan = plan })
            verify(shell.dialogInvoker === invoker(),
                   "o dialog não preservou o originador antes de receber Escape")

            keyClick(Qt.Key_Escape)

            tryVerify(function() { return dialog.visible === false }, 2000,
                      "Escape real não fechou um diálogo com closePolicy permissiva")
            verify(shell.emulationPlan === null,
                   "o plano sobreviveu ao cancelamento por Escape real")
            tryVerify(function() { return shell.activeFocusItem === invoker() }, 2000,
                      "Escape não devolveu foco ao originador")
        }

        function test_02_escape_does_not_close_recovery() {
            const dialog = shell.recoveryDialogControl
            openWith(dialog, null, null)

            keyClick(Qt.Key_Escape)

            tryVerify(function() { return dialog.visible === true }, 2000,
                      "Escape fechou o modal de recovery com NoAutoClose")
            waitForDialogFocus(dialog)
            // Recovery só pode ser dispensado pela ação correspondente; esta é
            // a limpeza controlada do teste, não prova de Escape.
            dialog.close()
            tryVerify(function() { return dialog.visible === false }, 2000)
        }

        function test_03_oracle_and_focus_trap_stay_inside_the_modal() {
            const dialog = shell.emulationPlanDialogControl
            openWith(dialog, emulatorPlan(), function(plan) { shell.emulationPlan = plan })
            assertFocusOracle(dialog)

            const focusables = modalFocusables(dialog)
            for (let i = 0; i < focusables.length + 1; i++) {
                keyClick(Qt.Key_Tab)
                tryVerify(function() {
                    return itemBelongsToModal(dialog, shell.activeFocusItem)
                }, 2000, "Tab levou o foco para fora do modal no passo " + i)
            }
            for (let j = 0; j < focusables.length + 1; j++) {
                keyClick(Qt.Key_Backtab)
                tryVerify(function() {
                    return itemBelongsToModal(dialog, shell.activeFocusItem)
                }, 2000, "Shift+Tab levou o foco para fora do modal no passo " + j)
            }

            keyClick(Qt.Key_Escape)
            tryVerify(function() { return dialog.visible === false }, 2000)
        }

        function test_04_visible_cancel_and_escape_have_the_same_final_state() {
            const dialog = shell.componentPlanDialogControl
            openWith(dialog, componentPlan(), function(plan) { shell.componentPlan = plan })
            const cancelButton = modalFocusables(dialog).find(function(item) {
                return item.text === "Cancelar"
            })
            verify(cancelButton !== undefined, "o botão visível de cancelar não foi enumerado")
            mouseClick(cancelButton, cancelButton.width / 2, cancelButton.height / 2,
                       Qt.LeftButton)
            tryVerify(function() { return dialog.visible === false }, 2000)
            verify(shell.componentPlan === null, "Cancelar visível deixou plano pendurado")
            tryVerify(function() { return shell.activeFocusItem === invoker() }, 2000)

            openWith(dialog, componentPlan(), function(plan) { shell.componentPlan = plan })
            keyClick(Qt.Key_Escape)
            tryVerify(function() { return dialog.visible === false }, 2000)
            verify(shell.componentPlan === null, "Escape deixou plano pendurado")
            tryVerify(function() { return shell.activeFocusItem === invoker() }, 2000)
        }

        function test_05_conflict_focus_enters_before_navigation() {
            const dialog = shell.conflictDialogControl
            openWith(dialog, conflictPlan(), function(plan) { shell.conflictPlan = plan })
            assertFocusOracle(dialog)
            keyClick(Qt.Key_Escape)
            tryVerify(function() { return dialog.visible === false }, 2000)
            verify(shell.conflictPlan === null, "Escape deixou plano de conflito pendurado")
        }
    }
}
