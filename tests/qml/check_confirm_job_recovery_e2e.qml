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
        property var bridgeConfig: ({})
        property var releasedMutations: ({})

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
            bridgeConfig = config()
            shell.apiUrl = bridgeConfig.apiUrl
            shell.apiToken = bridgeConfig.apiToken
            shell.refreshStatus("")
            tryVerify(function() {
                return shell.uiContracts.byId !== undefined
                    && shell.uiContracts.byId["component.plan"] !== undefined
            }, 3000, "o catálogo não chegou pela bridge real")
        }

        function releaseMutation(name) {
            const request = new XMLHttpRequest()
            request.onreadystatechange = function() {
                if (request.readyState !== XMLHttpRequest.DONE)
                    return
                compare(request.status, 200,
                        "a barreira não observou a requisição pendente: " + name)
                const next = Object.assign({}, releasedMutations)
                next[name] = true
                releasedMutations = next
            }
            request.open("POST", bridgeConfig.syncUrl + "/release/" + name, true)
            request.send("{}")
            tryVerify(function() { return releasedMutations[name] === true }, 4000,
                      "a barreira não liberou a mutação: " + name)
        }

        function configureEmptyJobs() {
            const request = new XMLHttpRequest()
            request.onreadystatechange = function() {
                if (request.readyState !== XMLHttpRequest.DONE)
                    return
                compare(request.status, 200, "a fixture não aceitou o estado vazio")
                const next = Object.assign({}, releasedMutations)
                next["empty"] = true
                releasedMutations = next
            }
            request.open("POST", bridgeConfig.syncUrl + "/jobs/empty", true)
            request.send("{}")
            tryVerify(function() { return releasedMutations["empty"] === true }, 3000,
                      "a fixture não publicou o estado vazio")
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
            compare(shell.actionRequestKey("component.apply", {
                "planId": "component-e2e-plan",
                "confirmToken": "component-e2e-token"
            }), shell.actionRequestKey("component.apply", {
                "confirmToken": "component-e2e-token",
                "planId": "component-e2e-plan"
            }), "a chave de idempotência depende da ordem dos campos")
            compare(shell.actionRequestKey("component.apply", {
                "planId": "component-e2e-plan",
                "confirmToken": "component-e2e-token",
                "opcional": undefined
            }), shell.actionRequestKey("component.apply", {
                "planId": "component-e2e-plan",
                "confirmToken": "component-e2e-token"
            }), "a chave distingue um campo que o JSON transmitido omite")
            releaseMutation("apply")

            tryVerify(function() { return !shell.componentPlanDialogControl.visible }, 3000,
                      "a confirmação válida não fechou o diálogo")
            tryVerify(function() {
                return shell.lastRequest === "Tarefa iniciada; acompanhe o progresso em Tarefas"
            }, 3000, "a UI não distinguiu job iniciado de componente já verificado")
        }

        function test_02_task_cancel_and_retry_use_the_real_drawer_controls() {
            shell.responsiveTaskDrawer.open()
            tryVerify(function() { return shell.responsiveTaskDrawer.position >= 0.999 }, 2000,
                      "a animação do Drawer não chegou ao estado aberto")
            tryVerify(function() { return shell.taskLoading === true }, 2000,
                      "a central não publicou o estado de carregamento")
            verify(itemWithObjectName(shell.responsiveTaskDrawer,
                                      "task-loading-state") !== null,
                   "o estado de carregamento não está visível")
            releaseMutation("list")
            tryVerify(function() { return shell.taskItems.length === 2 }, 3000,
                      "a central não carregou os jobs da bridge")
            let cancel = itemWithObjectName(shell.responsiveTaskDrawer,
                                            "task-cancel-running-job")
            verify(cancel !== null, "o CTA de cancelamento não foi encontrado")
            verify(cancel.width > 0 && cancel.height > 0,
                   "o CTA de cancelamento não recebeu geometria clicável")
            mouseClick(cancel, cancel.width / 2, cancel.height / 2, Qt.LeftButton)
            verify(cancel.enabled === false,
                   "o CTA de cancelamento não ficou bloqueado durante a requisição")
            mouseClick(cancel, cancel.width / 2, cancel.height / 2, Qt.LeftButton)
            releaseMutation("cancel")
            tryVerify(function() {
                return shell.taskItems.length > 0 && shell.taskItems[0].state === "cancelled"
            }, 3000, "o cancelamento não atualizou a central de tarefas")

            const retry = itemWithObjectName(shell.responsiveTaskDrawer,
                                             "task-retry-failed-job")
            verify(retry !== null, "o CTA de repetição não foi encontrado")
            mouseClick(retry, retry.width / 2, retry.height / 2, Qt.LeftButton)
            verify(retry.enabled === false,
                   "o CTA de repetição não ficou bloqueado durante a requisição")
            mouseClick(retry, retry.width / 2, retry.height / 2, Qt.LeftButton)
            releaseMutation("retry")
            tryVerify(function() {
                return shell.taskItems.length > 1 && shell.taskItems[1].state === "succeeded"
            }, 3000, "a repetição não atualizou a central de tarefas")
            shell.responsiveTaskDrawer.close()
        }

        function test_03_task_empty_error_and_retry_are_distinct_states() {
            shell.responsiveTaskDrawer.open()
            tryVerify(function() { return shell.responsiveTaskDrawer.position >= 0.999 }, 2000)
            configureEmptyJobs()
            shell.refreshTasks()
            tryVerify(function() {
                return !shell.taskLoading && shell.taskLoadError === ""
                    && shell.taskItems.length === 0
            }, 3000, "a central não chegou ao estado vazio")
            verify(itemWithObjectName(shell.responsiveTaskDrawer,
                                      "task-empty-state") !== null,
                   "o estado vazio não está visível")

            shell.apiToken = "token-inválido"
            shell.refreshTasks()
            tryVerify(function() {
                return !shell.taskLoading && shell.taskLoadError.length > 0
            }, 3000, "a falha de carregamento não virou estado de erro")
            verify(itemWithObjectName(shell.responsiveTaskDrawer,
                                      "task-error-state") !== null,
                   "o estado de erro não está visível")

            shell.apiToken = bridgeConfig.apiToken
            const retryLoad = itemWithObjectName(shell.responsiveTaskDrawer,
                                                 "task-error-retry")
            verify(retryLoad !== null, "o erro não oferece nova tentativa")
            mouseClick(retryLoad, retryLoad.width / 2, retryLoad.height / 2,
                       Qt.LeftButton)
            tryVerify(function() {
                return !shell.taskLoading && shell.taskLoadError === ""
                    && shell.taskItems.length === 0
            }, 3000, "a nova tentativa não recuperou o estado vazio")
            shell.responsiveTaskDrawer.close()
        }

        function test_04_recovery_waits_for_the_real_response_before_it_closes() {
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

        function test_05_recovery_failure_keeps_the_dialog_and_allows_retry() {
            const dialog = shell.recoveryDialogControl
            shell.apiToken = "token-inválido"
            dialog.open()
            tryVerify(function() { return dialog.visible }, 2000)
            const recover = itemWithObjectName(dialog, "desktop-recovery-apply")
            verify(recover !== null, "o CTA de recovery não foi encontrado")
            mouseClick(recover, recover.width / 2, recover.height / 2, Qt.LeftButton)
            tryVerify(function() { return recover.enabled }, 3000,
                      "o recovery recusado não voltou a permitir tentativa")
            verify(dialog.visible, "uma falha de recovery fechou o diálogo de segurança")
            verify(shell.lastRequestIsError, "a falha de recovery não foi anunciada")
            shell.apiToken = bridgeConfig.apiToken
            dialog.close()
        }
    }
}
