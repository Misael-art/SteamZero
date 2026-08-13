// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// G45: o perfil de controle deixa de ser invisível na tela.
//
// O perfil já era resolvido e gravado, e nenhum QML o desenhava — então o
// usuário não tinha como saber a diferença entre "escolhi um perfil", "o perfil
// foi traduzido" e "o perfil vale de fato no emulador". Este cartão existe para
// tornar essas três coisas distintas e ditas.
//
// A regra de honestidade está no `isApplied()`: SOMENTE `applied` pinta verde e
// diz que está valendo. `pending-write` tem tudo resolvido e mesmo assim não é
// "pronto" — o arquivo ainda não existe. Chamar isso de configurado seria a
// promessa vazia que a G45 registra.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    // O bloco `controlsProfile` do jogo. `autoconfig` pode ser nulo: sem perfil
    // ativo não há nada a resolver, e inventar um estado seria pior que a
    // ausência.
    required property var profile
    required property color surfaceColor
    required property color raisedColor
    required property color borderColor
    required property color textColor
    required property color mutedColor
    required property color greenColor
    required property color amberColor
    required property color redColor

    readonly property var autoconfig: profile && profile.autoconfig ? profile.autoconfig : null
    readonly property var active: profile && profile.active ? profile.active : null
    readonly property var resolvedBindings: autoconfig ? (autoconfig.resolvedBindings || []) : []
    readonly property var unresolvedBindings: autoconfig ? (autoconfig.unresolvedBindings || []) : []
    readonly property var withoutEquivalent: autoconfig
        ? (autoconfig.withoutRetropadEquivalent || [])
        : (active && active.withoutRetropadEquivalent ? active.withoutRetropadEquivalent : [])

    implicitHeight: column.implicitHeight + 32

    function autoconfigState() {
        return autoconfig ? String(autoconfig.state || "") : "not-configured"
    }

    // Verde exige prova. Qualquer outro estado é âmbar (ainda não vale) ou
    // vermelho (falhou), nunca "pronto".
    function isApplied() {
        return autoconfigState() === "applied"
    }

    function accentColor() {
        var current = autoconfigState()
        if (current === "applied")
            return greenColor
        if (current === "write-failed" || current === "conflict")
            return redColor
        if (current === "partial")
            return amberColor
        return mutedColor
    }

    // A frase que explica por que o perfil ainda não vale. Sem ela o usuário vê
    // um estado e nenhum caminho.
    function honestMessage() {
        var current = autoconfigState()
        if (current === "not-configured")
            return qsTr("Nenhum perfil selecionado. O emulador usará os padrões dele.")
        if (current === "awaiting-device")
            return qsTr("O perfil está traduzido, mas nenhum controle reconhecido foi encontrado. "
                + "Sem o controle, o índice de cada botão não pode ser lido — e não será adivinhado.")
        if (current === "awaiting-emulator")
            return qsTr("O perfil está resolvido, mas o RetroArch ainda não informou em qual pasta "
                + "lê perfis de controle. Gravar sem essa informação não garantiria efeito.")
        if (current === "pending-write")
            return qsTr("O perfil está resolvido e ainda não foi gravado. Ele passa a valer "
                + "quando o arquivo for aplicado.")
        if (current === "partial")
            return qsTr("Parte do perfil foi aplicada. As ações abaixo sem índice físico não "
                + "valem, porque o controle não as declara.")
        if (current === "write-failed")
            return qsTr("Não foi possível gravar o perfil. O emulador continua utilizável com os "
                + "padrões dele.")
        if (current === "conflict")
            return qsTr("Existe um arquivo de controle que não foi criado pelo SteamZero. Ele não "
                + "será sobrescrito.")
        return qsTr("O perfil está aplicado e valendo no emulador.")
    }

    Rectangle {
        anchors.fill: parent
        color: root.surfaceColor
        radius: 12
        border.width: 1
        border.color: root.borderColor

        ColumnLayout {
            id: column
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    objectName: "controlsProfileTitle"
                    text: qsTr("Perfil de controle")
                    color: root.textColor
                    font.pixelSize: 16
                    font.bold: true
                }

                Item { Layout.fillWidth: true }

                Rectangle {
                    objectName: "controlsProfileStateChip"
                    radius: 10
                    color: root.raisedColor
                    border.width: 1
                    border.color: root.accentColor()
                    implicitWidth: stateText.implicitWidth + 20
                    implicitHeight: stateText.implicitHeight + 10

                    Text {
                        id: stateText
                        objectName: "controlsProfileStateLabel"
                        anchors.centerIn: parent
                        // O rótulo vem do backend: a tela não reinventa o estado.
                        text: root.autoconfig
                            ? String(root.autoconfig.statusLabel || "")
                            : (root.profile ? String(root.profile.statusLabel || "") : "")
                        color: root.accentColor()
                        font.pixelSize: 12
                    }
                }
            }

            Text {
                objectName: "controlsProfileActive"
                Layout.fillWidth: true
                text: root.active
                    ? qsTr("Perfil ativo: %1 (revisão %2, %3)")
                        .arg(String(root.active.id || ""))
                        .arg(String(root.active.revision || ""))
                        .arg(String(root.active.orientation || ""))
                    : qsTr("Nenhum perfil ativo")
                color: root.textColor
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }

            Text {
                objectName: "controlsProfileDevice"
                Layout.fillWidth: true
                visible: root.autoconfig !== null
                text: root.autoconfig && root.autoconfig.device
                    ? qsTr("Controle reconhecido: %1").arg(String(root.autoconfig.device.name || ""))
                    : qsTr("Nenhum controle reconhecido")
                color: root.mutedColor
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            Text {
                objectName: "controlsProfileMessage"
                Layout.fillWidth: true
                text: root.honestMessage()
                color: root.mutedColor
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            Text {
                objectName: "controlsProfileBindingsTitle"
                visible: root.resolvedBindings.length > 0
                text: root.isApplied()
                    ? qsTr("Mapeamentos valendo (%1)").arg(root.resolvedBindings.length)
                    : qsTr("Mapeamentos que serão aplicados (%1)").arg(root.resolvedBindings.length)
                color: root.textColor
                font.pixelSize: 13
                font.bold: true
            }

            Repeater {
                model: root.resolvedBindings
                delegate: Text {
                    required property var modelData
                    objectName: "controlsProfileBinding"
                    Layout.fillWidth: true
                    // Mostra a chave e o valor REAIS que vão para o arquivo. O
                    // usuário consegue conferir contra o emulador.
                    text: "%1 → %2 = %3"
                        .arg(String(modelData.action || ""))
                        .arg(String(modelData.key || ""))
                        .arg(String(modelData.value || ""))
                    color: root.mutedColor
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }

            Text {
                objectName: "controlsProfileUnresolvedTitle"
                visible: root.unresolvedBindings.length > 0
                text: qsTr("Sem índice físico, não vão valer (%1)").arg(root.unresolvedBindings.length)
                color: root.amberColor
                font.pixelSize: 13
                font.bold: true
            }

            Repeater {
                model: root.unresolvedBindings
                delegate: Text {
                    required property var modelData
                    objectName: "controlsProfileUnresolved"
                    Layout.fillWidth: true
                    // O motivo vem por extenso do backend: "não resolvido" sem
                    // causa deixaria o usuário sem ação possível.
                    text: "%1 — %2"
                        .arg(String(modelData.action || ""))
                        .arg(String(modelData.reasonLabel || ""))
                    color: root.mutedColor
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }

            Text {
                objectName: "controlsProfileWithoutEquivalentTitle"
                visible: root.withoutEquivalent.length > 0
                text: qsTr("Sem equivalente no RetroPad (%1)").arg(root.withoutEquivalent.length)
                color: root.amberColor
                font.pixelSize: 13
                font.bold: true
            }

            Repeater {
                model: root.withoutEquivalent
                delegate: Text {
                    required property var modelData
                    objectName: "controlsProfileWithoutEquivalent"
                    Layout.fillWidth: true
                    text: String(modelData)
                    color: root.mutedColor
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }

            Text {
                objectName: "controlsProfileDetail"
                Layout.fillWidth: true
                visible: root.autoconfig !== null && String(root.autoconfig.detail || "") !== ""
                text: root.autoconfig ? String(root.autoconfig.detail || "") : ""
                color: root.redColor
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }
    }
}
