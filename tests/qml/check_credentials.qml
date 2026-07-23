// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 949
    height: 593

    property int failures: 0
    property int checks: 0
    property string savedProvider: ""
    property var savedCredentials: ({})
    property var savedFieldRow: null
    property var openedLinks: []
    property string screenProvider: ""
    property var screenCredentials: ({})
    property string keyboardField: ""

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        failures += 1
        console.error("FAIL: " + message)
    }

    function verifyCompletion() {
        check(savedFieldRow.inputControl.text === "",
              "segredo só deve ser limpo após sucesso")
        check(localCard.fieldRepeaterControl.count === 0,
              "integração local não pode criar TextField")
        check(!localCard.saveControl.visible
              && !localCard.testControl.visible
              && !localCard.revokeControl.visible
              && !localCard.createAccountControl.visible
              && !localCard.credentialLinkControl.visible,
                  "integração local não pode expor ações de credencial")
        check(!localCard.documentationControl.visible
              && !localCard.termsControl.visible,
              "integração local não pode herdar links de outro delegate")
        check(localCard.message === "",
              "mensagem do provider remoto não pode vazar para o card local")
        console.log("credentials checks=" + checks + " failures=" + failures)
        Qt.exit(failures === 0 ? 0 : 1)
    }

    CredentialProviderCard {
        id: remoteCard
        width: 460
        provider: ({
            "id": "steamgriddb",
            "name": "SteamGridDB",
            "description": "Arte remota",
            "enabled": true,
            "configured": false,
            "credentialState": "notConfigured",
            "credentialTestSupported": true,
            "credentialRevokeSupported": true,
            "credentialFields": [{
                "id": "api_key",
                "label": "API key",
                "placeholder": "Cole a chave",
                "help": "Somente no cofre.",
                "secret": true,
                "required": true
            }],
            "links": {
                "createAccount": "https://www.steamgriddb.com/profile/preferences/api",
                "credentials": "https://www.steamgriddb.com/profile/preferences/api",
                "documentation": "https://www.steamgriddb.com/api/v2",
                "terms": "https://www.steamgriddb.com/terms"
            }
        })
        onSaveRequested: function(providerId, credentials) {
            harness.savedProvider = providerId
            harness.savedCredentials = credentials
        }
        onLinkRequested: function(providerId, linkKey) {
            harness.openedLinks = harness.openedLinks.concat([
                providerId + ":" + linkKey
            ])
        }
        onKeyboardRequested: function(fieldId) {
            harness.keyboardField = fieldId
        }
    }

    CredentialProviderCard {
        id: localCard
        x: 480
        width: 460
        provider: ({
            "id": "steam-local",
            "name": "Integração local com Steam",
            "description": "Sem credenciais.",
            "enabled": true,
            "configured": true,
            "credentialState": "local",
            "credentialTestSupported": false,
            "credentialRevokeSupported": false,
            "credentialFields": [],
            "links": {}
        })
    }

    CredentialProviderCard {
        id: screenCard
        y: 700
        width: 460
        provider: ({
            "id": "screenscraper",
            "name": "ScreenScraper",
            "description": "Credenciais de aplicação e conta pessoal opcional.",
            "enabled": true,
            "configured": false,
            "credentialState": "notConfigured",
            "credentialTestSupported": true,
            "credentialRevokeSupported": true,
            "credentialFields": [
                {"id": "devid", "label": "Developer ID", "placeholder": "",
                 "help": "Integração", "secret": false, "required": true},
                {"id": "devpassword", "label": "Developer password", "placeholder": "",
                 "help": "Integração", "secret": true, "required": true},
                {"id": "ssid", "label": "Usuário", "placeholder": "",
                 "help": "Conta pessoal", "secret": false, "required": false},
                {"id": "sspassword", "label": "Senha", "placeholder": "",
                 "help": "Conta pessoal", "secret": true, "required": false}
            ],
            "links": {}
        })
        onSaveRequested: function(providerId, credentials) {
            harness.screenProvider = providerId
            harness.screenCredentials = credentials
        }
    }

    Timer {
        interval: 50
        running: true
        repeat: false
        onTriggered: {
            check(screenCard.fieldRepeaterControl.count === 4,
                  "ScreenScraper deve renderizar quatro campos isolados")
            check(!screenCard.saveControl.enabled,
                  "ScreenScraper deve exigir os dois campos de aplicação")
            const screenDevId = screenCard.fieldRepeaterControl.itemAt(0)
            const screenDevPassword = screenCard.fieldRepeaterControl.itemAt(1)
            const screenUser = screenCard.fieldRepeaterControl.itemAt(2)
            const screenPassword = screenCard.fieldRepeaterControl.itemAt(3)
            check(screenDevId.inputControl.echoMode === TextInput.Normal
                  && screenUser.inputControl.echoMode === TextInput.Normal,
                  "devid e ssid devem ser campos de texto")
            check(screenDevPassword.inputControl.echoMode === TextInput.Password
                  && screenPassword.inputControl.echoMode === TextInput.Password,
                  "devpassword e sspassword devem ocultar segredos")
            screenDevId.inputControl.text = "dev-id"
            check(!screenCard.saveControl.enabled,
                  "um obrigatório isolado não pode habilitar Salvar")
            screenDevPassword.inputControl.text = "dev-secret"
            check(screenCard.saveControl.enabled,
                  "os dois obrigatórios devem habilitar Salvar")
            screenCard.saveControl.clicked()
            check(screenProvider === "screenscraper"
                  && Object.keys(screenCredentials).length === 2
                  && screenCredentials.devid === "dev-id"
                  && screenCredentials.devpassword === "dev-secret",
                  "opcionais vazios não devem entrar no payload")
            check(remoteCard.fieldRepeaterControl.count === 1,
                  "provider remoto deve publicar seu único campo")
            check(!remoteCard.saveControl.enabled,
                  "Salvar deve iniciar bloqueado sem campo obrigatório")
            const fieldRow = remoteCard.fieldRepeaterControl.itemAt(0)
            savedFieldRow = fieldRow
            check(fieldRow !== null && fieldRow.inputControl !== null,
                  "TextField reativo deve ser instanciado")
            fieldRow.inputControl.forceActiveFocus(Qt.TabFocusReason)
            fieldRow.inputControl.text = "segredo-de-teste"
            check(remoteCard.saveControl.enabled,
                  "digitar o obrigatório deve habilitar Salvar")
            check(fieldRow.keyboardControl.height >= 48,
                  "botão do teclado virtual deve manter alvo 48×48")
            fieldRow.keyboardControl.clicked()
            check(keyboardField === "api_key",
                  "teclado virtual deve receber somente o campo do card")
            remoteCard.saveControl.clicked()
            check(savedProvider === "steamgriddb",
                  "payload deve manter somente o provider do card")
            check(Object.keys(savedCredentials).length === 1
                  && savedCredentials.api_key === "segredo-de-teste",
                  "payload deve conter somente o campo declarado")
            remoteCard.saveSucceeded({
                "providerStatus": {
                    "configured": true,
                    "credentialState": "stored"
                }
            })
            check(remoteCard.credentialState === "stored",
                  "sucesso verificado deve atualizar o badge")
            check(remoteCard.message.indexOf("salva") >= 0,
                  "mensagem de sucesso deve permanecer no card")
            remoteCard.createAccountControl.clicked()
            remoteCard.credentialLinkControl.clicked()
            remoteCard.documentationControl.clicked()
            remoteCard.termsControl.clicked()
            check(openedLinks.join(",") ===
                  "steamgriddb:createAccount,steamgriddb:credentials,"
                  + "steamgriddb:documentation,steamgriddb:terms",
                  "cada botão deve enviar somente seu provider e link lógico")
            Qt.callLater(harness.verifyCompletion)
        }
    }
}
