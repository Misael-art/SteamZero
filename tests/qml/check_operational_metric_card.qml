// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 640
    height: 240
    property int failures: 0

    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    OperationalMetricCard {
        id: card
        anchors.centerIn: parent
        width: 400
        title: "Conflitos preservados"
        value: "2"
        iconName: "dialog-warning"
        state: "conflicted"
        surfaceColor: "#f4f7f5"
        raisedColor: "#ffffff"
        borderColor: "#aebdbe"
        textColor: "#16212a"
        mutedColor: "#53616b"
        cyanColor: "#006f99"
        greenColor: "#167a45"
        amberColor: "#9a5a00"
        redColor: "#ae2634"
    }

    Timer {
        interval: 80
        running: true
        onTriggered: {
            check(card.implicitHeight >= 96, "cartão operacional deve reservar leitura e toque")
            check(card.stateLabel() === "Conflito preservado",
                  "estado de conflito deve preservar a causa para a pessoa usuária")
            card.state = "done"
            check(card.stateLabel() === "Sem pendências",
                  "estado concluído deve usar texto factual")
            Qt.exit(failures === 0 ? 0 : 1)
        }
    }
}
