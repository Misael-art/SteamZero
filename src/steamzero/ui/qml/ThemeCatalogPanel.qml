// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Catálogo de temas ES-DE curados: listar, instalar, remover e recuperar
// espaço. Consome exclusivamente as rotas `theme.catalog.*` e `theme.store.gc`
// já publicadas no contrato — nenhuma decisão de política mora aqui.
//
// Três escolhas de apresentação que existem por causa do comportamento do
// backend, e não por gosto:
//
// 1. Os temas EXCLUÍDOS aparecem, com o motivo. Um catálogo que só mostra o que
//    entrou faz a ausência parecer esquecimento; dizer "este tema existe e ficou
//    de fora porque não declara licença" é informação.
// 2. "Instalado" e "atualizado" são estados distintos, porque o backend os
//    distingue: a versão instalada pode não ser a do catálogo.
// 3. Instalar não ativa. O botão diz "Instalar", não "Aplicar", e o painel não
//    promete uma troca de aparência que a rota não faz.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
// DarkButton respeita a paleta do pai; Button puro traz o estilo claro do Qt
// e destoa do painel escuro, como a primeira captura mostrou.

Rectangle {
    id: panel

    property color backgroundColor: "#071019"
    property color surfaceColor: "#0d1924"
    property color raisedColor: "#122131"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"
    property color cyanColor: "#13bdf2"
    property color cyanDarkColor: "#0a5f85"
    property color greenColor: "#59d35d"
    property color amberColor: "#ff9f1a"
    property color redColor: "#ff6b73"

    property var requestAction: function(_id, _payload, _cb, _ecb) {}
    property bool compactLayout: false

    signal notified(string message, bool isError)

    // -- estado -------------------------------------------------------------
    property var entries: []
    property var excluded: []
    property var storeUsage: ({"blobs": 0, "bytes": 0})
    property bool loading: false
    property string busyThemeId: ""
    property string errorText: ""
    // Guarda o operationId da última instalação para permitir desfazer sem
    // pedir que a pessoa anote um identificador de 26 caracteres.
    property var lastOperation: ({})
    property var gcPreview: null

    color: panel.backgroundColor
    implicitHeight: 560

    // Os botões herdam daqui em vez de cada um declarar cor.
    palette.buttonText: panel.textColor
    palette.button: panel.raisedColor

    function humanBytes(value) {
        const bytes = Number(value || 0)
        if (bytes < 1024)
            return bytes + " B"
        if (bytes < 1024 * 1024)
            return (bytes / 1024).toFixed(1) + " KB"
        return (bytes / 1024 / 1024).toFixed(1) + " MB"
    }

    function refresh() {
        panel.loading = true
        panel.errorText = ""
        panel.requestAction("theme.catalog.list", {}, function(response) {
            panel.loading = false
            panel.entries = (response && response.entries) || []
            panel.excluded = (response && response.excluded) || []
            panel.storeUsage = (response && response.storeUsage) || {"blobs": 0, "bytes": 0}
        }, function(error) {
            panel.loading = false
            // A falha fica NA TELA, não só num toast que some: sem catálogo a
            // lista vazia seria indistinguível de "nenhum tema disponível".
            panel.errorText = String((error && (error.detail || error.message)) || error || "")
        })
    }

    function installTheme(themeId, overwrite) {
        panel.busyThemeId = themeId
        panel.requestAction("theme.catalog.install",
                            {"themeId": themeId, "overwrite": overwrite === true},
                            function(response) {
            panel.busyThemeId = ""
            if (response && response.operationId) {
                const updated = {}
                for (const key in panel.lastOperation)
                    updated[key] = panel.lastOperation[key]
                updated[themeId] = String(response.operationId)
                panel.lastOperation = updated
            }
            panel.notified(qsTr("Tema instalado. Ainda não aplicado."), false)
            panel.refresh()
        }, function(error) {
            panel.busyThemeId = ""
            panel.notified(String((error && (error.detail || error.message)) || error || ""), true)
        })
    }

    function uninstallTheme(themeId) {
        panel.busyThemeId = themeId
        panel.requestAction("theme.catalog.uninstall", {"themeId": themeId}, function() {
            panel.busyThemeId = ""
            // Dizer que os assets ficaram é o que evita a pergunta seguinte:
            // "removi o tema, por que o espaço não voltou?"
            panel.notified(qsTr("Tema removido. Os assets foram preservados."), false)
            panel.refresh()
        }, function(error) {
            panel.busyThemeId = ""
            panel.notified(String((error && (error.detail || error.message)) || error || ""), true)
        })
    }

    function rollbackTheme(themeId) {
        const operationId = panel.lastOperation[themeId] || ""
        if (!operationId) {
            panel.notified(qsTr("Nada a desfazer nesta sessão."), true)
            return
        }
        panel.busyThemeId = themeId
        panel.requestAction("theme.catalog.rollback",
                            {"themeId": themeId, "operationId": operationId},
                            function(response) {
            panel.busyThemeId = ""
            panel.notified(response && response.restoredPrevious
                           ? qsTr("Versão anterior restaurada.")
                           : qsTr("Instalação desfeita."), false)
            panel.refresh()
        }, function(error) {
            panel.busyThemeId = ""
            panel.notified(String((error && (error.detail || error.message)) || error || ""), true)
        })
    }

    function previewGarbage() {
        panel.requestAction("theme.store.gc", {}, function(response) {
            panel.gcPreview = response || null
        }, function(error) {
            panel.notified(String((error && (error.detail || error.message)) || error || ""), true)
        })
    }

    function applyGarbage() {
        panel.requestAction("theme.store.gc", {"apply": true}, function(response) {
            panel.gcPreview = null
            panel.notified(qsTr("Espaço recuperado: %1")
                           .arg(panel.humanBytes(response && response.reclaimedBytes)), false)
            panel.refresh()
        }, function(error) {
            panel.notified(String((error && (error.detail || error.message)) || error || ""), true)
        })
    }

    Component.onCompleted: panel.refresh()

    // -- corpo --------------------------------------------------------------
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: panel.compactLayout ? 12 : 20
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Label {
                text: qsTr("Temas")
                color: panel.textColor
                font.pixelSize: panel.compactLayout ? 20 : 24
                font.bold: true
                Layout.fillWidth: true
                Accessible.role: Accessible.Heading
            }
            Label {
                objectName: "storeUsageLabel"
                text: qsTr("%1 em %2 arquivos")
                    .arg(panel.humanBytes(panel.storeUsage.bytes))
                    .arg(panel.storeUsage.blobs || 0)
                color: panel.mutedColor
                font.pixelSize: 13
            }
            DarkButton {
                objectName: "refreshButton"
                text: qsTr("Atualizar")
                enabled: !panel.loading
                Layout.minimumHeight: 48
                Accessible.name: text
                onClicked: panel.refresh()
            }
        }

        Label {
            objectName: "errorLabel"
            visible: panel.errorText !== ""
            text: qsTr("Não foi possível ler o catálogo: %1").arg(panel.errorText)
            color: panel.redColor
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        BusyIndicator {
            running: panel.loading
            visible: panel.loading
            Layout.alignment: Qt.AlignHCenter
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ColumnLayout {
                width: parent.width
                spacing: 10

                Repeater {
                    objectName: "entryRepeater"
                    model: panel.entries

                    Rectangle {
                        required property var modelData
                        required property int index

                        objectName: "themeCard_" + modelData.id
                        Layout.fillWidth: true
                        implicitHeight: cardLayout.implicitHeight + 24
                        color: panel.surfaceColor
                        border.color: panel.borderColor
                        border.width: 1
                        radius: 8

                        ColumnLayout {
                            id: cardLayout
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 6

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Label {
                                    text: modelData.name || modelData.id
                                    color: panel.textColor
                                    font.pixelSize: 16
                                    font.bold: true
                                    Layout.fillWidth: true
                                }
                                // Instalado e atualizado sao estados diferentes,
                                // porque a versao instalada pode nao ser a do
                                // catalogo. Um selo so esconderia essa diferenca.
                                Rectangle {
                                    objectName: "stateBadge_" + modelData.id
                                    visible: modelData.installed === true
                                    color: modelData.upToDate ? panel.greenColor : panel.amberColor
                                    radius: 4
                                    implicitWidth: badgeText.implicitWidth + 12
                                    implicitHeight: badgeText.implicitHeight + 6
                                    Label {
                                        id: badgeText
                                        anchors.centerIn: parent
                                        text: modelData.upToDate
                                            ? qsTr("Instalado")
                                            : qsTr("Atualização disponível")
                                        color: "#05121b"
                                        font.pixelSize: 11
                                        font.bold: true
                                    }
                                }
                            }

                            Label {
                                text: qsTr("Licença %1 · %2")
                                    .arg(modelData.license || qsTr("não declarada"))
                                    .arg((modelData.credits || []).join(", "))
                                color: panel.mutedColor
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                DarkButton {
                                    objectName: "installButton_" + modelData.id
                                    text: modelData.installed
                                        ? qsTr("Reinstalar")
                                        : qsTr("Instalar")
                                    enabled: panel.busyThemeId === ""
                                    Layout.minimumHeight: 48
                                    Accessible.name: text + " " + (modelData.name || modelData.id)
                                    onClicked: panel.installTheme(modelData.id,
                                                                  modelData.installed === true)
                                }
                                DarkButton {
                                    objectName: "rollbackButton_" + modelData.id
                                    visible: panel.lastOperation[modelData.id] !== undefined
                                    text: qsTr("Desfazer")
                                    enabled: panel.busyThemeId === ""
                                    Layout.minimumHeight: 48
                                    Accessible.name: text
                                    onClicked: panel.rollbackTheme(modelData.id)
                                }
                                Item { Layout.fillWidth: true }
                                DarkButton {
                                    objectName: "uninstallButton_" + modelData.id
                                    visible: modelData.installed === true
                                    text: qsTr("Remover")
                                    enabled: panel.busyThemeId === ""
                                    Layout.minimumHeight: 48
                                    Accessible.name: text + " " + (modelData.name || modelData.id)
                                    // Destrutiva: confirma antes, como o contrato exige.
                                    onClicked: uninstallDialog.ask(modelData.id,
                                                                   modelData.name || modelData.id)
                                }
                            }
                        }
                    }
                }

                // -- espaço ---------------------------------------------------
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: gcLayout.implicitHeight + 24
                    color: panel.raisedColor
                    border.color: panel.borderColor
                    border.width: 1
                    radius: 8

                    ColumnLayout {
                        id: gcLayout
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 6

                        Label {
                            text: qsTr("Espaço em disco")
                            color: panel.textColor
                            font.pixelSize: 14
                            font.bold: true
                        }
                        Label {
                            // Explica por que remover um tema não devolveu o
                            // espaço — que é a pergunta natural depois de remover.
                            text: qsTr("Remover um tema preserva os arquivos, porque outro tema "
                                       + "pode usá-los. A recuperação é uma ação à parte.")
                            color: panel.mutedColor
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Label {
                            objectName: "gcPreviewLabel"
                            visible: panel.gcPreview !== null
                            text: panel.gcPreview
                                ? qsTr("%1 arquivo(s) sem dono, %2 a recuperar")
                                    .arg(panel.gcPreview.orphans || 0)
                                    .arg(panel.humanBytes(panel.gcPreview.reclaimedBytes))
                                : ""
                            color: panel.amberColor
                            font.pixelSize: 13
                            Layout.fillWidth: true
                        }
                        RowLayout {
                            spacing: 8
                            DarkButton {
                                objectName: "gcPreviewButton"
                                text: qsTr("Verificar")
                                Layout.minimumHeight: 48
                                Accessible.name: text
                                onClicked: panel.previewGarbage()
                            }
                            DarkButton {
                                objectName: "gcApplyButton"
                                // Só aparece quando há o que recuperar: um botão
                                // que não faz nada ensina a ignorá-lo.
                                visible: panel.gcPreview !== null
                                    && (panel.gcPreview.orphans || 0) > 0
                                text: qsTr("Recuperar espaço")
                                Layout.minimumHeight: 48
                                Accessible.name: text
                                onClicked: gcDialog.open()
                            }
                        }
                    }
                }

                // -- excluídos ------------------------------------------------
                Rectangle {
                    objectName: "excludedSection"
                    visible: panel.excluded.length > 0
                    Layout.fillWidth: true
                    implicitHeight: excludedLayout.implicitHeight + 24
                    color: panel.surfaceColor
                    border.color: panel.borderColor
                    border.width: 1
                    radius: 8

                    ColumnLayout {
                        id: excludedLayout
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 4

                        Label {
                            text: qsTr("Não disponíveis (%1)").arg(panel.excluded.length)
                            color: panel.textColor
                            font.pixelSize: 14
                            font.bold: true
                        }
                        Repeater {
                            objectName: "excludedRepeater"
                            model: panel.excluded
                            Label {
                                required property var modelData
                                text: "· " + (modelData.repo || "") + " — " + (modelData.reason || "")
                                color: panel.mutedColor
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }
        }
    }

    // -- confirmações -------------------------------------------------------
    Dialog {
        id: uninstallDialog
        objectName: "uninstallDialog"
        anchors.centerIn: parent
        modal: true
        title: qsTr("Remover tema")
        standardButtons: Dialog.Cancel | Dialog.Ok

        property string themeId: ""
        property string themeName: ""

        function ask(identifier, name) {
            uninstallDialog.themeId = identifier
            uninstallDialog.themeName = name
            uninstallDialog.open()
        }

        Label {
            text: qsTr("Remover \"%1\"? Os arquivos compartilhados são preservados.")
                .arg(uninstallDialog.themeName)
            color: panel.textColor
            wrapMode: Text.WordWrap
        }
        onAccepted: panel.uninstallTheme(uninstallDialog.themeId)
    }

    Dialog {
        id: gcDialog
        objectName: "gcDialog"
        anchors.centerIn: parent
        modal: true
        title: qsTr("Recuperar espaço")
        standardButtons: Dialog.Cancel | Dialog.Ok

        Label {
            text: qsTr("Apagar em definitivo os arquivos que nenhum tema instalado usa?")
            color: panel.textColor
            wrapMode: Text.WordWrap
        }
        onAccepted: panel.applyGarbage()
    }
}
