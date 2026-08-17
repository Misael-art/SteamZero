// SPDX-License-Identifier: GPL-3.0-or-later
//
// Jornada de credenciais pela UI real: diálogo aberto pela rota da ação
// publicada, salvar/testar/revogar contra a bridge loopback controlada,
// falha de rede e rejeição lógica. Nenhuma credencial real: payload
// sintético e cofre em memória, com barreiras liberadas pelo teste Python.
// A URL e o token são efêmeros, escritos pelo teste em build/ (ignorado).

import QtQuick
import QtQuick.Controls
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
        name: "CredentialJourneyE2E"
        when: windowShown
        property var bridgeConfig: ({})
        property var releasedMutations: ({})

        function config() {
            const request = new XMLHttpRequest()
            request.open("GET", Qt.resolvedUrl("../../build/ui-credential-journey-e2e.json"), false)
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

        function effectivelyVisible(item) {
            let current = item
            while (current) {
                if (current.visible === false)
                    return false
                current = current.parent
            }
            return true
        }

        function countLabelsWithText(root, text) {
            const children = allChildren(root.contentItem || root, [])
            let count = 0
            for (let index = 0; index < children.length; index++) {
                const candidate = children[index]
                if (candidate.text === text && candidate.width > 0
                        && effectivelyVisible(candidate))
                    count += 1
            }
            return count
        }

        function countButtonsWithText(root, text) {
            const children = allChildren(root.contentItem || root, [])
            let count = 0
            for (let index = 0; index < children.length; index++) {
                const candidate = children[index]
                if (candidate instanceof Button && candidate.text === text
                        && candidate.width > 0 && candidate.height > 0
                        && effectivelyVisible(candidate))
                    count += 1
            }
            return count
        }

        function bootstrap() {
            bridgeConfig = config()
            shell.apiUrl = bridgeConfig.apiUrl
            shell.apiToken = bridgeConfig.apiToken
            shell.refreshStatus("")
            tryVerify(function() {
                return shell.uiContracts.byId !== undefined
                    && shell.uiContracts.byId["credential.status"] !== undefined
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

        function postMode(path) {
            const request = new XMLHttpRequest()
            request.onreadystatechange = function() {
                if (request.readyState !== XMLHttpRequest.DONE)
                    return
                compare(request.status, 200, "a fixture não aceitou o modo: " + path)
            }
            request.open("POST", bridgeConfig.syncUrl + path, true)
            request.send("{}")
        }

        function test_01_published_action_opens_dialog_and_filters_providers() {
            bootstrap()
            shell.performEmulationAction({
                "id": "open-credential-dialog",
                "label": "Abrir configuração",
                "enabled": true
            })
            const dialog = shell.credentialDialogControl
            tryVerify(function() { return dialog.visible }, 3000,
                      "a ação publicada não abriu o diálogo de credenciais")
            tryVerify(function() {
                return shell.credentialProviderRepeaterControl.itemAt(0) !== null
            }, 3000, "a bridge não publicou os providers no diálogo")

            const card = shell.credentialProviderRepeaterControl.itemAt(0)
            verify(card.provider.id === "steamgriddb",
                   "o primeiro card não é o provider habilitado")
            verify(card.credentialState === "notConfigured",
                   "o card não partiu de 'Não configurado'")
            verify(card.saveControl.visible && !card.saveControl.enabled,
                   "Salvar deve estar visível e bloqueado sem chave")
            verify(countLabelsWithText(dialog, "SteamGridDB") === 1,
                   "o provider habilitado não apareceu uma única vez")
            verify(countLabelsWithText(dialog, "Provedor desabilitado") === 0,
                   "provider desabilitado vazou para o diálogo")
            verify(countLabelsWithText(dialog, "Integração local com Steam") === 1,
                   "a integração local deve permanecer mesmo desabilitada")
            verify(countLabelsWithText(dialog, "Steam Web API") === 1
                   && countLabelsWithText(dialog, "Opcional — Steam Web API") === 1,
                   "a seção opcional não renderizou cabeçalho e card")
            verify(countButtonsWithText(dialog, "Salvar") === 1
                   && countButtonsWithText(dialog, "Abrir teclado virtual") === 1,
                   "somente o provider configurável expõe campo e Salvar")
            verify(countButtonsWithText(dialog, "Criar conta") === 1
                   && countButtonsWithText(dialog, "Documentação") === 1
                   && countButtonsWithText(dialog, "Termos") === 1,
                   "os links não devem vazar para os demais cards")
        }

        function test_02_save_pending_blocks_duplicate_and_success_clears_secret() {
            const card = shell.credentialProviderRepeaterControl.itemAt(0)
            const field = card.fieldRepeaterControl.itemAt(0).inputControl
            field.text = "segredo-de-teste"
            tryVerify(function() { return card.saveControl.enabled }, 2000,
                      "digitar a chave não habilitou Salvar")

            mouseClick(card.saveControl, card.saveControl.width / 2,
                       card.saveControl.height / 2, Qt.LeftButton)
            tryVerify(function() {
                return !card.saveControl.enabled && card.saveControl.text === "Aguarde…"
                    && !field.enabled
            }, 2000, "o card não bloqueou Salvar e o campo durante a requisição")
            mouseClick(card.saveControl, card.saveControl.width / 2,
                       card.saveControl.height / 2, Qt.LeftButton)
            releaseMutation("save")

            tryVerify(function() {
                return card.credentialState === "stored"
                    && card.message.indexOf("salva") >= 0
            }, 3000, "o salvamento confirmado não atualizou o card")
            verify(card.messageIsError === false,
                   "a confirmação de salvamento foi marcada como erro")
            tryVerify(function() { return field.text === "" }, 2000,
                      "o segredo não foi limpo após o sucesso")
            verify(countLabelsWithText(shell.credentialDialogControl,
                                       "Salvo no cofre") === 1,
                   "o badge de estado não exibiu 'Salvo no cofre'")
        }

        function test_03_test_validates_then_logical_rejection_keeps_the_card() {
            const card = shell.credentialProviderRepeaterControl.itemAt(0)
            tryVerify(function() { return card.testControl.visible }, 2000,
                      "o card configurado não expôs Testar conexão")
            mouseClick(card.testControl, card.testControl.width / 2,
                       card.testControl.height / 2, Qt.LeftButton)
            tryVerify(function() { return !card.testControl.enabled }, 2000,
                      "Testar não bloqueou durante a requisição")
            releaseMutation("test")
            tryVerify(function() {
                return card.credentialState === "validated"
                    && card.message.indexOf("validada") >= 0
            }, 3000, "a conexão válida não foi anunciada")
            verify(card.messageIsError === false,
                   "a validação positiva foi marcada como erro")

            postMode("/credential/reject-tests")
            mouseClick(card.testControl, card.testControl.width / 2,
                       card.testControl.height / 2, Qt.LeftButton)
            tryVerify(function() { return !card.testControl.enabled }, 2000,
                      "o segundo teste não bloqueou durante a requisição")
            releaseMutation("test")
            tryVerify(function() {
                return card.credentialState === "rejected"
                    && card.messageIsError
                    && card.message.indexOf("rejeitada") >= 0
            }, 3000, "a rejeição lógica não virou estado e erro no card")
            verify(countLabelsWithText(shell.credentialDialogControl,
                                       "Rejeitado") === 1,
                   "o badge de estado não exibiu 'Rejeitado'")
        }

        function test_04_network_failure_keeps_secret_and_offers_retry() {
            const card = shell.credentialProviderRepeaterControl.itemAt(0)
            const field = card.fieldRepeaterControl.itemAt(0).inputControl
            shell.apiToken = "token-invalido"
            field.text = "segredo-2"
            tryVerify(function() { return card.saveControl.enabled }, 2000,
                      "a chave digitada não habilitou Salvar")
            mouseClick(card.saveControl, card.saveControl.width / 2,
                       card.saveControl.height / 2, Qt.LeftButton)
            tryVerify(function() {
                return card.busy === false
                    && card.messageIsError
                    && card.message.indexOf("Não foi possível salvar") >= 0
            }, 3000, "a falha de rede não virou erro acionável no card")
            verify(card.credentialState === "rejected",
                   "a falha de rede mudou o estado da credencial")
            verify(field.text === "segredo-2",
                   "o segredo foi apagado após a falha, impedindo a nova tentativa")
            shell.apiToken = bridgeConfig.apiToken
        }

        function test_05_revoke_returns_to_not_configured_and_clears() {
            const card = shell.credentialProviderRepeaterControl.itemAt(0)
            const field = card.fieldRepeaterControl.itemAt(0).inputControl
            tryVerify(function() { return card.revokeControl.visible }, 2000,
                      "o card configurado não expôs Revogar")
            mouseClick(card.revokeControl, card.revokeControl.width / 2,
                       card.revokeControl.height / 2, Qt.LeftButton)
            tryVerify(function() { return !card.revokeControl.enabled }, 2000,
                      "Revogar não bloqueou durante a requisição")
            releaseMutation("delete")
            tryVerify(function() {
                return card.credentialState === "notConfigured"
                    && card.message.indexOf("revogada") >= 0
                    && card.messageIsError === false
            }, 3000, "a revogação não voltou o card para 'Não configurado'")
            tryVerify(function() { return field.text === "" }, 2000,
                      "o segredo não foi limpo após a revogação")
            verify(countLabelsWithText(shell.credentialDialogControl,
                                       "Não configurado") === 2,
                   "o badge de estado não voltou a 'Não configurado'")
            shell.credentialCloseControl.clicked()
            tryVerify(function() { return !shell.credentialDialogControl.visible }, 2000,
                      "Fechar não escondeu o diálogo")
        }
    }
}
