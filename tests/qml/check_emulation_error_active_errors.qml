// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: false
    width: 1280
    height: 800
    property int failures: 0
    property int checks: 0
    property int firstFailure: 0

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    function processResult() {
        if (window.activeErrors.length > 0) {
            var err = window.activeErrors[0]
            check(err.code === "E-TX-001",
                  "código deve ser E-TX-001, obtido: " + err.code)
            check(err.operationId === "op-transactional-789",
                  "operationId deve ser preservado, obtido: " + err.operationId)
        } else {
            check(false, "activeErrors vazio; requestAction não roteou o erro")
        }
        if (window.failures > 0) {
            Qt.exit(1)
        } else {
            Qt.exit(0)
        }
    }

    Component.onCompleted: {
        setupTimer.start()
    }

    Timer {
        id: setupTimer
        interval: 200
        onTriggered: {
            window.desktopStatus = {
                "context": {"capabilities": [], "conflicts": [], "displays": []},
                "dashboard": {
                    "uiContracts": {
                        "byId": {
                            "emulation.action.plan": {
                                "applicability": "applicable",
                                "enabled": true,
                                "endpoint": "/emulation/action/plan",
                                "method": "POST",
                                "reason": null
                            }
                        },
                        "actions": [],
                        "states": [],
                        "schemaVersion": 1
                    },
                    "components": [], "steam": [], "sync": {},
                    "doctor": {"checks": []},
                    "playtime": {"schemaVersion": 1, "totalPlayedSeconds": 0, "games": []},
                    "libraryHealth": {"schemaVersion": 1, "state": "unchecked",
                        "counts": {"verified": 0, "suspect": 0, "missing": 0,
                            "error": 0, "unavailable": 0, "unchecked": 0}}
                }
            }
            actionTimer.start()
        }
    }

    Timer {
        id: actionTimer
        interval: 120
        onTriggered: {
            window.requestAction("emulation.action.plan", {"actionId": "test"},
                function(response) {
                    window.check(false, "deveria receber erro, não sucesso")
                    window.processResult()
                },
                function(msg) {
                    window.resultMessage = msg
                    window.pendingPeriods = 0
                    resultTimer.start()
                }
            )
        }
    }

    property string resultMessage: ""
    property int pendingPeriods: 0

    Timer {
        id: resultTimer
        interval: 100
        repeat: true
        onTriggered: {
            if (window.activeErrors.length > 0 || window.pendingPeriods >= 30) {
                window.processResult()
            } else {
                window.pendingPeriods += 1
            }
        }
    }
}
