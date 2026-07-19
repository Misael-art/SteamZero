// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: panel

    required property var desktopStatus
    required property var sessionManager
    required property var hostPreparation
    required property color backgroundColor
    required property color surfaceColor
    required property color raisedColor
    required property color borderColor
    required property color textColor
    required property color mutedColor
    required property color cyanColor
    required property color cyanDarkColor
    required property color greenColor
    required property color amberColor
    required property color redColor

    signal profilePlanRequested(string profile)
    signal profileApplyRequested(string planId, string confirmToken)
    signal safeResetRequested()
    signal conflictRequested()
    signal recoveryRequested()
    signal keyboardRequested()
    signal systemRequested()

    property int profileIndex: 0
    property var reviewedPlan: null

    readonly property var context: desktopStatus && desktopStatus.context
        ? desktopStatus.context : ({"capabilities": [], "conflicts": [], "displays": []})
    readonly property var capabilities: context.capabilities || []
    readonly property var conflicts: context.conflicts || []
    readonly property string truthState: desktopStatus.truthState || "unapplied"
    readonly property bool healthy: truthState === "ready" || truthState === "applied"
    readonly property bool keyboardAvailable: capabilities.indexOf("steam-keyboard") >= 0
        || capabilities.indexOf("plasma-keyboard") >= 0
        || capabilities.indexOf("kwin-virtual-keyboard") >= 0
    readonly property var directBoot: sessionManager && sessionManager.directBoot
        ? sessionManager.directBoot : ({"state": "available", "configured": false})
    readonly property bool touchMode: desktopStatus.current && desktopStatus.current.profile
        ? desktopStatus.current.profile.touchMode : false

    function profileLabel(value) {
        if (value === "handheld-desktop")
            return qsTr("Portátil")
        if (value === "docked-desktop")
            return qsTr("Dock")
        if (value === "safe")
            return qsTr("Seguro")
        return qsTr("Não definido")
    }

    function stateLabel() {
        if (desktopStatus.recoveryRequired)
            return qsTr("Recuperação necessária")
        if (conflicts.length > 0)
            return qsTr("Controle concorrente detectado")
        if (healthy)
            return qsTr("Modo Desktop pronto")
        if (truthState === "stale")
            return qsTr("Contexto alterado; revise o perfil")
        if (truthState === "degraded")
            return qsTr("Estado observado divergente")
        return qsTr("Perfil ainda não aplicado")
    }

    function stateColor() {
        if (desktopStatus.recoveryRequired)
            return redColor
        return healthy ? greenColor : amberColor
    }

    function showPlan(plan) {
        reviewedPlan = plan
        reviewDialog.open()
    }

    spacing: 14

    Rectangle {
        Layout.fillWidth: true
        Layout.leftMargin: 20
        Layout.rightMargin: 20
        Layout.minimumHeight: 92
        color: panel.healthy ? "#0c2a21" : "#24180b"
        border.color: panel.stateColor()
        border.width: 1
        radius: 8

        RowLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 14
            ToolButton {
                enabled: false
                icon.name: panel.desktopStatus.recoveryRequired
                    ? "dialog-error" : panel.healthy ? "dialog-ok-apply" : "dialog-warning"
                icon.color: panel.stateColor()
                icon.width: 30
                icon.height: 30
                background: Item {}
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Label {
                    text: panel.stateLabel()
                    color: panel.stateColor()
                    font.pixelSize: 19
                    font.bold: true
                }
                Label {
                    text: panel.desktopStatus.statusReasons
                        && panel.desktopStatus.statusReasons.length > 0
                        ? panel.desktopStatus.statusReasons.join(" · ")
                        : qsTr("Touch, escala, janelas, painel e entrada são reconciliados com rollback G-STATE.")
                    color: panel.mutedColor
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
            Button {
                visible: panel.conflicts.length > 0
                text: qsTr("Resolver conflito")
                icon.name: "dialog-warning"
                Layout.minimumHeight: 48
                Accessible.name: qsTr("Resolver conflito de controle do Modo Desktop")
                onClicked: panel.conflictRequested()
            }
            Button {
                visible: Boolean(panel.desktopStatus.recoveryRequired)
                text: qsTr("Restaurar agora")
                icon.name: "edit-undo"
                Layout.minimumHeight: 48
                Accessible.name: text
                onClicked: panel.recoveryRequested()
            }
        }
    }

    GridLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.leftMargin: 20
        Layout.rightMargin: 20
        columns: panel.width >= 1120 ? 2 : 1
        columnSpacing: 12
        rowSpacing: 12

        Rectangle {
            Layout.fillWidth: true
            Layout.minimumHeight: 255
            color: panel.surfaceColor
            border.color: panel.borderColor
            radius: 8
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                RowLayout {
                    ToolButton { enabled: false; icon.name: "preferences-desktop"; icon.color: panel.cyanColor; background: Item {} }
                    Label { text: qsTr("Experiência do Modo Desktop"); color: panel.textColor; font.pixelSize: 18; font.bold: true; Layout.fillWidth: true }
                    Label { text: qsTr("SteamZero"); color: panel.greenColor; font.bold: true }
                }
                Label {
                    text: qsTr("Escolha como o Plasma deve se comportar no Deck ou no dock.")
                    color: panel.mutedColor
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Repeater {
                        model: [qsTr("Automático"), qsTr("Portátil"), qsTr("Dock"), qsTr("Seguro")]
                        delegate: Button {
                            required property int index
                            required property string modelData
                            text: modelData
                            checkable: true
                            checked: panel.profileIndex === index
                            Layout.fillWidth: true
                            Layout.minimumHeight: 48
                            Accessible.name: qsTr("Perfil Desktop %1").arg(text)
                            onClicked: panel.profileIndex = index
                            background: Rectangle {
                                color: parent.checked ? panel.cyanDarkColor : panel.raisedColor
                                border.color: parent.checked || parent.activeFocus
                                    ? panel.cyanColor : panel.borderColor
                                border.width: parent.checked || parent.activeFocus ? 2 : 1
                                radius: 5
                            }
                        }
                    }
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 5
                    Label { text: qsTr("Recomendado"); color: panel.mutedColor }
                    Label { text: panel.profileLabel(panel.desktopStatus.recommendedProfile); color: panel.cyanColor; font.bold: true }
                    Label { text: qsTr("Desejado"); color: panel.mutedColor }
                    Label { text: panel.profileLabel(panel.desktopStatus.desiredProfile); color: panel.textColor }
                    Label { text: qsTr("Aplicado"); color: panel.mutedColor }
                    Label { text: panel.profileLabel(panel.desktopStatus.appliedProfile); color: panel.textColor }
                    Label { text: qsTr("Observado"); color: panel.mutedColor }
                    Label { text: panel.profileLabel(panel.desktopStatus.observedProfile); color: panel.healthy ? panel.greenColor : panel.amberColor }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.minimumHeight: 255
            color: panel.surfaceColor
            border.color: panel.borderColor
            radius: 8
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                RowLayout {
                    ToolButton { enabled: false; icon.name: "input-touchpad"; icon.color: panel.cyanColor; background: Item {} }
                    Label { text: qsTr("Entrada, touch e teclado"); color: panel.textColor; font.pixelSize: 18; font.bold: true; Layout.fillWidth: true }
                    Label {
                        text: panel.conflicts.length === 0 ? qsTr("Owner exclusivo") : qsTr("Bloqueado")
                        color: panel.conflicts.length === 0 ? panel.greenColor : panel.amberColor
                        font.bold: true
                    }
                }
                Label {
                    text: panel.context.deviceKind && panel.context.deviceKind.indexOf("deck-") === 0
                        ? qsTr("Steam Deck oficial detectado; touch e controles físicos podem usar o perfil dedicado.")
                        : qsTr("PC compatível detectado; somente capacidades observadas serão habilitadas.")
                    color: panel.mutedColor
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Rectangle { color: panel.borderColor; Layout.fillWidth: true; Layout.preferredHeight: 1 }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: qsTr("Teclado virtual"); color: panel.textColor; Layout.fillWidth: true }
                    Label { text: panel.keyboardAvailable ? qsTr("Disponível") : qsTr("Ausente"); color: panel.keyboardAvailable ? panel.greenColor : panel.amberColor }
                    Button {
                        text: qsTr("Abrir teclado")
                        enabled: panel.keyboardAvailable
                        Layout.minimumHeight: 48
                        Accessible.name: text
                        onClicked: panel.keyboardRequested()
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: qsTr("Teclado externo"); color: panel.mutedColor; Layout.fillWidth: true }
                    Label { text: panel.context.externalKeyboard ? qsTr("Conectado") : qsTr("Não detectado"); color: panel.textColor }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: qsTr("Mouse externo"); color: panel.mutedColor; Layout.fillWidth: true }
                    Label { text: panel.context.externalMouse ? qsTr("Conectado") : qsTr("Não detectado"); color: panel.textColor }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.minimumHeight: 235
            color: panel.surfaceColor
            border.color: panel.borderColor
            radius: 8
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                RowLayout {
                    ToolButton { enabled: false; icon.name: "video-display"; icon.color: panel.cyanColor; background: Item {} }
                    Label { text: qsTr("Tela, dock e hotplug"); color: panel.textColor; font.pixelSize: 18; font.bold: true; Layout.fillWidth: true }
                    Label { text: qsTr("KDE / KScreen"); color: panel.cyanColor; font.bold: true }
                }
                Repeater {
                    model: panel.context.displays || []
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.minimumHeight: 40
                        ToolButton { enabled: false; icon.name: modelData.internal ? "computer-laptop" : "video-display"; icon.color: panel.greenColor; background: Item {} }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Label { text: modelData.internal ? qsTr("Tela interna") : modelData.name; color: panel.textColor; font.bold: true }
                            Label { text: "%1×%2 · %3 Hz".arg(modelData.width || "—").arg(modelData.height || "—").arg(modelData.refreshHz || "—"); color: panel.mutedColor; font.pixelSize: 11 }
                        }
                        Label { text: qsTr("Escala %1").arg(modelData.scale || "—"); color: panel.cyanColor }
                    }
                }
                Label {
                    visible: !panel.context.displays || panel.context.displays.length === 0
                    text: qsTr("KScreen não retornou uma topologia observável.")
                    color: panel.amberColor
                }
                Item { Layout.fillHeight: true }
                Label {
                    text: panel.context.physicalDock
                        ? qsTr("Dock físico conectado · perfil externo recomendado")
                        : qsTr("Sem dock físico · retorno ao painel interno monitorado")
                    color: panel.context.physicalDock ? panel.cyanColor : panel.mutedColor
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.minimumHeight: 235
            color: panel.surfaceColor
            border.color: panel.borderColor
            radius: 8
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                RowLayout {
                    ToolButton { enabled: false; icon.name: "system-switch-user"; icon.color: panel.cyanColor; background: Item {} }
                    Label { text: qsTr("Sessão e resiliência"); color: panel.textColor; font.pixelSize: 18; font.bold: true; Layout.fillWidth: true }
                    Label { text: "G-STATE"; color: panel.greenColor; font.bold: true }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: qsTr("Game Mode independente"); color: panel.textColor; Layout.fillWidth: true }
                    Label { text: panel.sessionManager.state === "ready" ? qsTr("Pronto") : qsTr("Incompleto"); color: panel.sessionManager.state === "ready" ? panel.greenColor : panel.amberColor }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: qsTr("Boot direto pelo GRUB"); color: panel.textColor; Layout.fillWidth: true }
                    Label { text: panel.directBoot.configured ? qsTr("Ativo") : qsTr("Disponível"); color: panel.directBoot.configured ? panel.greenColor : panel.amberColor }
                }
                Label {
                    text: panel.directBoot.reason || ""
                    color: panel.mutedColor
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: qsTr("Laboratório KVM/libvirt"); color: panel.mutedColor; Layout.fillWidth: true }
                    Label {
                        text: panel.hostPreparation.state === "ready"
                            ? qsTr("Pronto") : qsTr("Preparação necessária")
                        color: panel.hostPreparation.state === "ready"
                            ? panel.greenColor : panel.amberColor
                        font.bold: true
                    }
                }
                Label {
                    text: panel.hostPreparation.hardwareLab
                        ? panel.hostPreparation.hardwareLab.reason : ""
                    color: panel.mutedColor
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Item { Layout.fillHeight: true }
                Button {
                    text: qsTr("Abrir Sistema")
                    icon.name: "configure"
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: qsTr("Abrir ferramentas do Sistema e diagnóstico")
                    onClicked: panel.systemRequested()
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.leftMargin: 20
        Layout.rightMargin: 20
        Layout.bottomMargin: 20
        spacing: 12
        Button {
            text: qsTr("Restaurar perfil seguro")
            icon.name: "edit-undo"
            Layout.fillWidth: true
            Layout.minimumHeight: 54
            Accessible.name: text
            onClicked: panel.safeResetRequested()
        }
        Button {
            text: qsTr("Revisar e aplicar no Desktop")
            icon.name: "dialog-ok-apply"
            enabled: panel.conflicts.length === 0 && !panel.desktopStatus.recoveryRequired
            Layout.fillWidth: true
            Layout.minimumHeight: 54
            Accessible.name: text
            onClicked: panel.profilePlanRequested(
                ["auto", "handheld", "dock", "safe"][panel.profileIndex]
            )
            background: Rectangle {
                color: parent.enabled ? "#069bd7" : panel.raisedColor
                border.color: parent.activeFocus ? panel.textColor : panel.cyanColor
                border.width: parent.activeFocus ? 2 : 1
                radius: 7
            }
        }
    }

    Dialog {
        id: reviewDialog
        title: qsTr("Revisar perfil do Modo Desktop")
        modal: true
        width: Math.min(panel.width - 48, 720)
        x: (panel.width - width) / 2
        y: Math.max(16, (panel.height - height) / 2)
        standardButtons: Dialog.NoButton
        background: Rectangle { color: panel.raisedColor; radius: 10; border.color: panel.cyanColor }
        contentItem: ColumnLayout {
            spacing: 14
            Label { text: panel.reviewedPlan ? qsTr("Perfil: %1").arg(panel.profileLabel(panel.reviewedPlan.target.id)) : ""; color: panel.textColor; font.pixelSize: 18; font.bold: true }
            Label { text: qsTr("As mudanças usam snapshot, verificação e rollback G-STATE."); color: panel.greenColor; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            TextArea {
                text: panel.reviewedPlan ? panel.reviewedPlan.changes.join("\n") : ""
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.WrapAnywhere
                inputMethodHints: Qt.ImhNone
                onActiveFocusChanged: { if (activeFocus && panel.touchMode) Qt.inputMethod.show() }
                color: panel.textColor
                Layout.fillWidth: true
                Layout.minimumHeight: 140
                background: Rectangle { color: panel.backgroundColor; radius: 6; border.color: panel.borderColor }
            }
            Label {
                visible: panel.reviewedPlan && panel.reviewedPlan.blockers.length > 0
                text: panel.reviewedPlan ? qsTr("Bloqueado: %1").arg(panel.reviewedPlan.blockers.join("; ")) : ""
                color: panel.amberColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Button { text: qsTr("Cancelar"); Layout.fillWidth: true; Layout.minimumHeight: 48; onClicked: reviewDialog.close() }
                Button {
                    text: qsTr("Aplicar com rollback")
                    enabled: panel.reviewedPlan && panel.reviewedPlan.blockers.length === 0
                    Layout.fillWidth: true
                    Layout.minimumHeight: 48
                    Accessible.name: text
                    onClicked: {
                        panel.profileApplyRequested(
                            panel.reviewedPlan.planId, panel.reviewedPlan.confirmToken
                        )
                        reviewDialog.close()
                    }
                }
            }
        }
    }
}
