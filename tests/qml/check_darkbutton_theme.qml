// SPDX-License-Identifier: GPL-3.0-or-later
// P0-1/P0-2 da auditoria: DarkButton legível no tema claro.
// O harness prova que o label segue a paleta do pai (nada de texto claro
// hardcodado sobre fundo claro) e salva a cena; o runner Python conta os
// pixels escuros do botão para provar que o texto renderiza sobre o fundo.
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 640
    height: 300
    color: "#e7eceb"

    property int failures: 0
    property int pendingExitCode: 0
    property bool captured: false
    readonly property string captureOutput: {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; ++i) {
            if (args[i].startsWith("--capture-output="))
                return args[i].slice("--capture-output=".length)
        }
        return ""
    }

    function check(cond, message) {
        if (cond)
            console.log("ok: " + message)
        else {
            failures += 1
            console.log("FAIL: " + message)
        }
    }

    // Sair de dentro do callback de grabToImage derruba o processo por sinal
    // (causa do qmlReturncode=-11 na auditoria); o pedido atravessa o loop.
    function requestExit(code) {
        pendingExitCode = code
        exitTimer.restart()
    }

    Timer {
        id: exitTimer
        interval: 0
        repeat: false
        onTriggered: Qt.exit(harness.pendingExitCode)
    }

    // Mesma composição da sidebar do Main.qml: fundo claro, texto da paleta.
    DarkButton {
        id: sidebarButton
        x: 220
        y: 100
        width: 200
        height: 48
        text: "Quick Reset"
        palette.buttonText: "#16212a"
        background: Rectangle {
            color: "#f4f7f5"
            radius: 6
            border.color: "#aebdbe"
            border.width: 1
        }
    }

    DarkButton {
        id: primaryButton
        primary: true
        x: 220
        y: 170
        width: 200
        height: 48
        text: "Instalar"
        palette.buttonText: "#16212a"
        background: Rectangle {
            color: "#006f99"
            radius: 6
        }
    }

    function assertLabelFollowsPalette() {
        check(Qt.colorEqual(sidebarButton.labelColor, "#16212a"),
              "label do botão comum segue palette.buttonText do pai")
        check(!Qt.colorEqual(sidebarButton.labelColor, "#f2f6fb"),
              "nenhum texto claro hardcodado sobre fundo claro")
        check(Qt.colorEqual(primaryButton.labelColor, "#0b1a22"),
              "label do botão primary é escuro sobre o preenchimento ciano")
    }

    function captureScene() {
        var grabbed = harness.contentItem.grabToImage(function(result) {
            if (result === null) {
                check(false, "grabToImage devolveu nulo")
                requestExit(failures === 0 ? 0 : 1)
                return
            }
            if (!result.saveToFile(captureOutput)) {
                check(false, "saveToFile falhou em " + captureOutput)
                requestExit(1)
                return
            }
            console.log("HARNESS-CAPTURED " + captureOutput)
            requestExit(failures === 0 ? 0 : 1)
        })
        if (!grabbed) {
            check(false, "grabToImage recusou o pedido")
            requestExit(1)
        }
    }

    function runVerification() {
        if (captured)
            return
        captured = true
        assertLabelFollowsPalette()
        captureScene()
    }

    Timer {
        id: settleTimer
        interval: 300
        repeat: false
        onTriggered: runVerification()
    }

    Connections {
        target: harness
        function onAfterRendering() {
            if (!captured)
                Qt.callLater(runVerification)
        }
    }

    Component.onCompleted: settleTimer.restart()
}
