// SPDX-License-Identifier: GPL-3.0-or-later
//
// Contrato de saída do AURA Launcher: a ação é visível, acessível e pede
// confirmação sem tocar no daemon ou na sessão do emulador.
import QtQuick
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    Component {
        id: launcherComponent
        // A cena real é uma Window; mantê-la visível aqui permite que o
        // qmltestrunner complete o ciclo de vida do objeto e não fique preso
        // esperando o encerramento de uma janela invisível.
        LauncherMain { visible: true }
    }

    property int failures: 0

    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    function findByObjectName(node, name) {
        if (node === null || node === undefined)
            return null
        if (node.objectName === name)
            return node
        var children = node.children || []
        for (var i = 0; i < children.length; ++i) {
            var found = findByObjectName(children[i], name)
            if (found !== null)
                return found
        }
        return null
    }

    Timer {
        interval: 100
        running: true
        repeat: false
        onTriggered: {
            var launcher = launcherComponent.createObject(harness)
            check(launcher !== null, "a cena principal precisa ser criada")
            if (launcher === null) {
                Qt.exit(1)
                return
            }
            check(launcher.exitPromptOpen === false,
                  "a confirmação começa fechada")
            check(typeof launcher._requestExit === "function",
                  "a cena expõe a solicitação de saída")
            check(typeof launcher._cancelExit === "function",
                  "a cena expõe o cancelamento da saída")

            launcher._requestExit()
            check(launcher.exitPromptOpen === true,
                  "solicitar saída abre a confirmação")
            var cancel = findByObjectName(launcher.contentItem, "launcherExitCancel")
            var confirm = findByObjectName(launcher.contentItem, "launcherExitConfirm")
            check(cancel !== null, "a confirmação expõe Cancelar")
            check(confirm !== null, "a confirmação expõe Confirmar saída")
            if (cancel !== null) {
                check(cancel.Accessible.role === Accessible.Button,
                      "Cancelar anuncia papel de botão")
            }
            if (confirm !== null) {
                check(confirm.Accessible.role === Accessible.Button,
                      "Confirmar anuncia papel de botão")
                check(confirm.Accessible.name === "Confirmar saída",
                      "Confirmar anuncia nome estável")
            }

            launcher._cancelExit()
            check(launcher.exitPromptOpen === false,
                  "cancelar fecha a confirmação sem sair")
            launcher.destroy()
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
