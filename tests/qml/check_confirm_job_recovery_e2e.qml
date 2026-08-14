// SPDX-License-Identifier: GPL-3.0-or-later
//
// Jornada de mutação pela UI real: plano vindo da bridge, confirmação por
// clique, bloqueio da duplicidade, central de tarefas e recovery. A URL e o
// token são efêmeros, escritos pelo teste Python em build/ (ignorado).

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
        x: 0
        y: 0
        width: 1600
        height: 1000
    }

    TestCase {
        id: suite
        name: "ConfirmJobRecoveryE2E"
        when: windowShown

        function config() {
            const request = new XMLHttpRequest()
            request.open("GET", Qt.resolvedUrl("../../build/ui-confirm-job-e2e.json"), false)
            request.send()
            verify(request.status === 0 || request.status === 200,
                   "a configuração efêmera da bridge não foi lida")
            return JSON.parse(request.responseText)
        }

        function allChildren(item, result) {
            if (!item)
                return result
            const children = item.childItems !== undefined ? item.childItems : item.children
            if (!children)
                return result
            for (let index = 0; index < children.length; index++) {
                const child = children[index]
                result.push(child)
                allChildren(child, result)
            }
            return result
        }

        function buttonWithText(root, label) {
            const children = allChildren(root.contentItem || root, [])
            for (let index = 0; index < children.length; index++) {
                const candidate = children[index]
                if (candidate.text === label && candidate.enabled && effectivelyVisible(candidate))
                    return candidate
            }
            return null
        }

        function itemWithObjectName(root, name) {
            const children = allChildren(root.contentItem || root, [])
            for (let index = 0; index < children.length; index++) {
                const candidate = children[index]
                if (candidate.objectName === name && candidate.enabled
                        && effectivelyVisible(candidate))
                    return candidate
            }
            return null
        }

        function effectivelyVisible(item) {
            let current = item
            while (current) {
                if (current.visible === false)
                    return false
                current = current.parent
            }
            return true
        }

        function bootstrap() {
            const bridge = config()
            shell.apiUrl = bridge.apiUrl
            shell.apiToken = bridge.apiToken
            shell.refreshStatus("")
            tryVerify(function() {
                return shell.uiContracts.byId !== undefined
                    && shell.uiContracts.byId["component.plan"] !== undefined
            }, 3000, "o catálogo não chegou pela bridge real")
        }

        function openComponentPlan() {
            let opened = false
            shell.requestAction("component.plan", {
                "componentId": "dolphin",
                "action": "install"
            }, function(response) {
                shell.componentPlan = response.plan
                shell.componentPlanDialogControl.open()
                opened = true
            })
            tryVerify(function() { return opened && shell.componentPlanDialogControl.visible }, 3000,
                      "o plano real não abriu o diálogo de confirmação")
        }

        function test_01_confirm_click_is_idempotent_until_the_bridge_replies() {
            bootstrap()
            openComponentPlan()
            const apply = itemWithObjectName(shell.componentPlanDialogControl,
                                             "component-plan-apply")
            verify(apply !== null, "o CTA real de confirmação não foi encontrado")

            mouseClick(apply, apply.width / 2, apply.height / 2, Qt.LeftButton)
            verify(apply.enabled === false,
                   "o CTA permaneceu acionável enquanto a confirmação está pendente")
            mouseClick(apply, apply.width / 2, apply.height / 2, Qt.LeftButton)

            tryVerify(function() { return !shell.componentPlanDialogControl.visible }, 3000,
                      "a confirmação válida não fechou o diálogo")
            tryVerify(function() {
                return shell.lastRequest === "Componente verificado e pronto"
            }, 3000, "o retorno positivo foi exibido antes de atualizar o estado")
        }

        function test_02_task_cancel_and_retry_use_the_real_drawer_controls() {
            shell.responsiveTaskDrawer.open()
            tryVerify(function() { return shell.taskItems.length === 2 }, 3000,
                      "a central não carregou os jobs da bridge")
            let cancel = itemWithObjectName(shell.responsiveTaskDrawer,
                                            "task-cancel-running-job")
            verify(cancel !== null, "o CTA de cancelamento não foi encontrado")
            verify(cancel.width > 0 && cancel.height > 0,
                   "o CTA de cancelamento não recebeu geometria clicável")
            // Drawer mora em Popup separado neste executor offscreen. O clique
            // físico foi provado no CTA de confirmação acima; aqui acionamos o
            // sinal do controle real para validar a ligação QML -> bridge.
            cancel.clicked()
            verify(cancel.enabled === false,
                   "o CTA de cancelamento não ficou bloqueado durante a requisição")
            cancel.clicked()
            tryVerify(function() {
                return shell.taskItems.length > 0 && shell.taskItems[0].state === "cancelled"
            }, 3000, "o cancelamento não atualizou a central de tarefas")

            const retry = itemWithObjectName(shell.responsiveTaskDrawer,
                                             "task-retry-failed-job")
            verify(retry !== null, "o CTA de repetição não foi encontrado")
            retry.clicked()
            verify(retry.enabled === false,
                   "o CTA de repetição não ficou bloqueado durante a requisição")
            retry.clicked()
            tryVerify(function() {
                return shell.taskItems.length > 1 && shell.taskItems[1].state === "succeeded"
            }, 3000, "a repetição não atualizou a central de tarefas")
            shell.responsiveTaskDrawer.close()
        }

        function test_03_recovery_waits_for_the_real_response_before_it_closes() {
            const dialog = shell.recoveryDialogControl
            dialog.open()
            tryVerify(function() { return dialog.visible }, 2000)
            const recover = itemWithObjectName(dialog, "desktop-recovery-apply")
            verify(recover !== null, "o CTA de recovery não foi encontrado")
            mouseClick(recover, recover.width / 2, recover.height / 2, Qt.LeftButton)
            verify(recover.enabled === false,
                   "o recovery permaneceu acionável enquanto a resposta está pendente")
            tryVerify(function() { return !dialog.visible }, 3000,
                      "o recovery aceito não fechou o diálogo")
            tryVerify(function() {
                return shell.lastRequest === "Recuperação concluída com segurança"
            }, 3000, "o recovery não confirmou o estado atualizado")
        }
    }
}
