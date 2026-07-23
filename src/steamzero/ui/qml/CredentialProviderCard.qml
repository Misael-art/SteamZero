// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    required property var provider
    property color surfaceColor: "#202735"
    property color raisedColor: "#293244"
    property color borderColor: "#475569"
    property color textColor: "#f8fafc"
    property color mutedColor: "#94a3b8"
    property color cyanColor: "#22d3ee"
    property color greenColor: "#4ade80"
    property color amberColor: "#fbbf24"
    property color redColor: "#fb7185"
    property bool busy: false
    property string credentialState: ""
    property string message: ""
    property bool messageIsError: false
    property int fieldRevision: 0
    readonly property bool hasCredentialFields: fieldModel.count > 0
    readonly property bool configured: credentialState === "stored"
                                               || credentialState === "validated"
                                               || credentialState === "rejected"
    readonly property bool requiredComplete: {
        fieldRevision
        for (let index = 0; index < fieldModel.count; ++index) {
            const row = fieldModel.get(index)
            if (row.fieldRequired && row.fieldValue.trim().length === 0)
                return false
        }
        return fieldModel.count > 0
    }
    readonly property var saveControl: saveButton
    readonly property var testControl: testButton
    readonly property var revokeControl: revokeButton
    readonly property var createAccountControl: createAccountButton
    readonly property var credentialLinkControl: credentialLinkButton
    readonly property var documentationControl: documentationButton
    readonly property var termsControl: termsButton
    readonly property var fieldRepeaterControl: fieldRepeater

    signal saveRequested(string providerId, var credentials)
    signal testRequested(string providerId)
    signal revokeRequested(string providerId)
    signal linkRequested(string providerId, string linkKey)
    signal keyboardRequested(string fieldId)

    Layout.fillWidth: true
    implicitHeight: providerContent.implicitHeight + 24
    color: surfaceColor
    radius: 8
    border.color: borderColor

    function rebuildFields() {
        fieldModel.clear()
        const fields = provider && provider.credentialFields
            ? provider.credentialFields : []
        for (let index = 0; index < fields.length; ++index) {
            const field = fields[index]
            fieldModel.append({
                "fieldId": field.id,
                "fieldLabel": field.label || field.id,
                "fieldPlaceholder": field.placeholder || "",
                "fieldHelp": field.help || "",
                "fieldSecret": Boolean(field.secret),
                "fieldRequired": Boolean(field.required),
                "fieldValue": ""
            })
        }
        credentialState = provider && provider.credentialState
            ? provider.credentialState
            : (provider && provider.configured ? "stored" : "notConfigured")
        fieldRevision += 1
    }

    function setFieldValue(index, value) {
        if (index < 0 || index >= fieldModel.count)
            return
        fieldModel.setProperty(index, "fieldValue", String(value))
        fieldRevision += 1
    }

    function credentialsPayload() {
        const credentials = {}
        for (let index = 0; index < fieldModel.count; ++index) {
            const row = fieldModel.get(index)
            const value = row.fieldValue.trim()
            if (value.length > 0)
                credentials[row.fieldId] = value
        }
        return credentials
    }

    function clearFields() {
        for (let index = 0; index < fieldModel.count; ++index) {
            fieldModel.setProperty(index, "fieldValue", "")
            const row = fieldRepeater.itemAt(index)
            if (row && row.inputControl)
                row.inputControl.text = ""
        }
        fieldRevision += 1
    }

    function applyProviderStatus(status) {
        if (!status)
            return
        credentialState = status.credentialState
            || (status.configured ? "stored" : "notConfigured")
    }

    function saveSucceeded(response) {
        applyProviderStatus(response ? response.providerStatus : null)
        if (credentialState === "notConfigured")
            credentialState = "stored"
        messageIsError = false
        message = qsTr("Credencial salva e verificada no cofre.")
        busy = false
        clearFields()
    }

    function saveFailed(errorMessage) {
        messageIsError = true
        message = qsTr("Não foi possível salvar: %1").arg(errorMessage)
        busy = false
    }

    function testSucceeded(response) {
        applyProviderStatus(response ? response.providerStatus : null)
        credentialState = response && response.state
            ? response.state : credentialState
        messageIsError = !(response && response.valid)
        message = response && response.valid
            ? qsTr("Conexão validada.")
            : qsTr("Credencial rejeitada: %1").arg(
                  response && response.error ? response.error : qsTr("falha de validação"))
        busy = false
    }

    function actionFailed(errorMessage) {
        messageIsError = true
        message = String(errorMessage)
        busy = false
    }

    function revokeSucceeded(response) {
        applyProviderStatus(response ? response.providerStatus : null)
        credentialState = "notConfigured"
        messageIsError = false
        message = qsTr("Credencial revogada do cofre.")
        busy = false
        clearFields()
    }

    function stateLabel() {
        const labels = {
            "notConfigured": qsTr("Não configurado"),
            "stored": qsTr("Salvo no cofre"),
            "validated": qsTr("Validado"),
            "rejected": qsTr("Rejeitado"),
            "vaultUnavailable": qsTr("Cofre indisponível"),
            "local": qsTr("Integração local — nenhuma credencial necessária"),
            "unavailable": qsTr("Indisponível")
        }
        return labels[credentialState] || labels.notConfigured
    }

    function stateColor() {
        if (credentialState === "validated" || credentialState === "local")
            return greenColor
        if (credentialState === "rejected" || credentialState === "vaultUnavailable")
            return redColor
        if (credentialState === "stored")
            return cyanColor
        return amberColor
    }

    onProviderChanged: rebuildFields()
    Component.onCompleted: rebuildFields()

    ListModel {
        id: fieldModel
    }

    ColumnLayout {
        id: providerContent
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        Label {
            text: root.provider ? root.provider.name : ""
            color: root.textColor
            font.bold: true
            font.pixelSize: 14
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Label {
            text: root.stateLabel()
            color: root.stateColor()
            font.pixelSize: 12
            font.bold: true
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Label {
            text: root.provider ? root.provider.description : ""
            color: root.mutedColor
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Label {
            visible: Boolean(root.provider && root.provider.unavailableReason)
            text: visible ? root.provider.unavailableReason : ""
            color: root.amberColor
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Repeater {
            id: fieldRepeater
            model: fieldModel
            delegate: ColumnLayout {
                id: fieldRow
                required property int index
                required property string fieldId
                required property string fieldLabel
                required property string fieldPlaceholder
                required property string fieldHelp
                required property bool fieldSecret
                required property bool fieldRequired
                required property string fieldValue
                readonly property var inputControl: credentialField
                readonly property var keyboardControl: keyboardButton

                Layout.fillWidth: true
                spacing: 3

                Label {
                    text: fieldLabel + (fieldRequired ? qsTr(" *") : qsTr(" (opcional)"))
                    color: root.textColor
                    font.pixelSize: 11
                    Layout.fillWidth: true
                }
                TextField {
                    id: credentialField
                    text: fieldValue
                    placeholderText: fieldPlaceholder
                    color: root.textColor
                    placeholderTextColor: root.mutedColor
                    selectByMouse: true
                    echoMode: fieldSecret ? TextInput.Password : TextInput.Normal
                    activeFocusOnTab: true
                    enabled: !root.busy
                    Accessible.name: fieldLabel
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    onTextChanged: {
                        if (text !== fieldValue)
                            root.setFieldValue(index, text)
                    }
                    background: Rectangle {
                        color: root.surfaceColor
                        border.color: parent.activeFocus ? root.cyanColor : root.borderColor
                        radius: 6
                    }
                }
                Button {
                    id: keyboardButton
                    text: qsTr("Abrir teclado virtual")
                    enabled: !root.busy
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Abrir teclado virtual para %1").arg(fieldLabel)
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    palette.button: root.raisedColor
                    palette.buttonText: root.textColor
                    onClicked: {
                        credentialField.forceActiveFocus(Qt.TabFocusReason)
                        root.keyboardRequested(fieldId)
                    }
                }
                Label {
                    visible: fieldHelp.length > 0
                    text: fieldHelp
                    color: root.mutedColor
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }

        Button {
            id: saveButton
            visible: root.provider && root.provider.enabled && root.hasCredentialFields
            text: root.busy ? qsTr("Aguarde…") : qsTr("Salvar")
            enabled: visible && root.requiredComplete && !root.busy
            activeFocusOnTab: true
            Accessible.name: text
            Layout.fillWidth: true
            Layout.minimumHeight: 48
            palette.button: root.raisedColor
            palette.buttonText: root.textColor
            onClicked: {
                root.busy = true
                root.message = ""
                root.saveRequested(root.provider.id, root.credentialsPayload())
            }
        }
        Button {
            id: testButton
            visible: Boolean(root.provider && root.provider.enabled && root.configured
                             && (root.provider.credentialTestSupported
                                 || root.provider.canTestCredential))
            text: qsTr("Testar conexão")
            enabled: visible && !root.busy
            activeFocusOnTab: true
            Accessible.name: text
            Layout.fillWidth: true
            Layout.minimumHeight: 48
            palette.button: root.raisedColor
            palette.buttonText: root.textColor
            onClicked: {
                root.busy = true
                root.message = ""
                root.testRequested(root.provider.id)
            }
        }
        Button {
            id: revokeButton
            visible: Boolean(root.provider && root.provider.enabled && root.configured
                             && (root.provider.credentialRevokeSupported
                                 || root.provider.canRevokeCredential))
            text: qsTr("Revogar")
            enabled: visible && !root.busy
            activeFocusOnTab: true
            Accessible.name: text
            Layout.fillWidth: true
            Layout.minimumHeight: 48
            palette.button: root.raisedColor
            palette.buttonText: root.textColor
            onClicked: {
                root.busy = true
                root.message = ""
                root.revokeRequested(root.provider.id)
            }
        }
        Button {
            id: createAccountButton
            visible: Boolean(root.provider && root.provider.links
                             && root.provider.links.createAccount)
            text: qsTr("Criar conta")
            enabled: visible && !root.busy
            activeFocusOnTab: true
            Accessible.name: text
            Layout.fillWidth: true
            Layout.minimumHeight: 48
            palette.button: root.raisedColor
            palette.buttonText: root.textColor
            onClicked: root.linkRequested(root.provider.id, "createAccount")
        }
        Button {
            id: credentialLinkButton
            visible: Boolean(root.provider && root.provider.links
                             && root.provider.links.credentials)
            text: qsTr("Obter credencial")
            enabled: visible && !root.busy
            activeFocusOnTab: true
            Accessible.name: text
            Layout.fillWidth: true
            Layout.minimumHeight: 48
            palette.button: root.raisedColor
            palette.buttonText: root.textColor
            onClicked: root.linkRequested(root.provider.id, "credentials")
        }
        Button {
            id: documentationButton
            visible: Boolean(root.provider && root.provider.links
                             && root.provider.links.documentation)
            text: qsTr("Documentação")
            enabled: visible && !root.busy
            activeFocusOnTab: true
            Accessible.name: text
            Layout.fillWidth: true
            Layout.minimumHeight: 48
            palette.button: root.raisedColor
            palette.buttonText: root.textColor
            onClicked: root.linkRequested(root.provider.id, "documentation")
        }
        Button {
            id: termsButton
            visible: Boolean(root.provider && root.provider.links
                             && root.provider.links.terms)
            text: qsTr("Termos")
            enabled: visible && !root.busy
            activeFocusOnTab: true
            Accessible.name: text
            Layout.fillWidth: true
            Layout.minimumHeight: 48
            palette.button: root.raisedColor
            palette.buttonText: root.textColor
            onClicked: root.linkRequested(root.provider.id, "terms")
        }
        Label {
            visible: root.message.length > 0
            text: root.message
            color: root.messageIsError ? root.redColor : root.cyanColor
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Accessible.name: text
            Layout.fillWidth: true
        }
    }
}
