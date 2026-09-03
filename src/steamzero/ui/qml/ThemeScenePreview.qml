// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Prévia da cena compilada de um tema instalado.
//
// Os seletores não são refinamento estético: a proporção carrega a GEOMETRIA e
// o esquema de cor carrega as variáveis de fundo. Medido no xmb-menu, compilar
// sem escolhê-los deixava 2 de 27 elementos posicionados — a cena existia e não
// desenhava. Esconder essas dimensões faria o usuário ver uma tela vazia sem
// nenhuma pista do porquê.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: preview

    property var requestAction: function(_id, _payload, _cb, _ecb) {}
    property string themeId: ""
    property color surfaceColor: "#0d1924"
    property color borderColor: "#2a3a49"
    property color textColor: "#f2f6fb"
    property color mutedColor: "#9eabba"

    property var rendered: null
    property var selections: ({})
    property string errorText: ""
    property bool loading: false
    property string viewId: "gamelist"
    property string systemId: "snes"

    readonly property var views: rendered && rendered.scene ? rendered.scene.views : []
    readonly property var currentView: {
        for (let i = 0; i < views.length; ++i) {
            if (views[i].id === preview.viewId)
                return views[i]
        }
        return views.length ? views[0] : null
    }

    // Um seletor vazio parece controle quebrado. O rótulo diz qual dimensão é,
    // e a ausência de escolha ganha nome em vez de virar espaço em branco.
    function labelFor(label, value) {
        return label + ": " + (value ? value : qsTr("padrão do tema"))
    }

    function optionsFor(dimension) {
        // "" é a ausência de escolha, e precisa ser oferecida: um tema pode não
        // declarar a dimensão, e forçar uma escolha inventaria seleção.
        const declared = selections && selections[dimension] ? selections[dimension] : []
        return [""].concat(declared)
    }

    function render() {
        if (!themeId)
            return
        preview.loading = true
        preview.errorText = ""
        preview.requestAction("theme.scene.render", {
            "themeId": preview.themeId,
            "systemId": preview.systemId,
            "aspectRatio": aspectBox.currentValue || "",
            "colorScheme": colorBox.currentValue || "",
            "fontSize": fontBox.currentValue || "",
            "variant": variantBox.currentValue || ""
        }, function(result) {
            preview.loading = false
            preview.rendered = result
            if (result && result.selections)
                preview.selections = result.selections
        }, function(error) {
            preview.loading = false
            // A prévia anterior permanece: sumir com ela esconderia o que já
            // havia funcionado e faria o erro parecer estado vazio.
            preview.errorText = error && error.detail ? String(error.detail) : qsTr("falhou")
        })
    }

    Component.onCompleted: preview.render()

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            SteamComboBox {
                id: aspectBox
                objectName: "aspectRatioBox"
                Layout.minimumHeight: 48
                Layout.minimumWidth: 130
                model: preview.optionsFor("aspectRatio")
                displayText: preview.labelFor(qsTr("Proporção"), currentValue)
                Accessible.name: qsTr("Proporção de tela")
                onActivated: preview.render()
            }
            SteamComboBox {
                id: colorBox
                objectName: "colorSchemeBox"
                Layout.minimumHeight: 48
                Layout.minimumWidth: 150
                model: preview.optionsFor("colorScheme")
                displayText: preview.labelFor(qsTr("Cor"), currentValue)
                Accessible.name: qsTr("Esquema de cor")
                onActivated: preview.render()
            }
            SteamComboBox {
                id: fontBox
                objectName: "fontSizeBox"
                Layout.minimumHeight: 48
                Layout.minimumWidth: 120
                model: preview.optionsFor("fontSize")
                displayText: preview.labelFor(qsTr("Fonte"), currentValue)
                Accessible.name: qsTr("Tamanho de fonte")
                onActivated: preview.render()
            }
            SteamComboBox {
                id: variantBox
                objectName: "variantBox"
                Layout.minimumHeight: 48
                Layout.minimumWidth: 180
                model: preview.optionsFor("variant")
                displayText: preview.labelFor(qsTr("Variante"), currentValue)
                Accessible.name: qsTr("Variante")
                onActivated: preview.render()
            }
            Item { Layout.fillWidth: true }
            SteamComboBox {
                id: viewBox
                objectName: "viewBox"
                Layout.minimumHeight: 48
                Layout.minimumWidth: 130
                model: ["system", "gamelist", "menu"]
                currentIndex: 1
                Accessible.name: qsTr("View do tema")
                onActivated: preview.viewId = currentValue
            }
        }

        Label {
            objectName: "previewError"
            visible: preview.errorText !== ""
            text: preview.errorText
            color: "#ff6b73"
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#000000"
            border.color: preview.borderColor
            border.width: 1
            clip: true

            SceneEsdeView {
                id: sceneView
                objectName: "sceneView"
                anchors.fill: parent
                anchors.margins: 1
                visible: preview.currentView !== null
                viewData: preview.currentView ? preview.currentView : ({"id": "", "elements": []})
            }

            Label {
                anchors.centerIn: parent
                visible: preview.loading
                text: qsTr("compilando…")
                color: preview.mutedColor
            }
        }

        // A distinção entre COMPILADO e DESENHADO fica na tela porque confundir
        // as duas foi o que produziu um relatório de 95% de fidelidade para uma
        // cena que não desenhava nada.
        Label {
            objectName: "fidelityLine"
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: preview.mutedColor
            text: {
                if (!preview.rendered)
                    return ""
                const total = preview.currentView ? preview.currentView.elements.length : 0
                return qsTr("%1 de %2 elementos desenhados nesta view · %3 assets resolvidos")
                    .arg(sceneView.drawnCount).arg(total)
                    .arg(preview.rendered.assets ? preview.rendered.assets.resolved : 0)
            }
        }

        Label {
            objectName: "notDrawnLine"
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: preview.mutedColor
            visible: sceneView.notDrawn.length > 0
            text: {
                const counts = {}
                for (let i = 0; i < sceneView.notDrawn.length; ++i) {
                    const reason = sceneView.notDrawn[i].reason
                    counts[reason] = (counts[reason] || 0) + 1
                }
                const parts = []
                for (const reason in counts)
                    parts.push(counts[reason] + "× " + reason)
                return qsTr("Não desenhados: ") + parts.join(" · ")
            }
        }
    }
}
