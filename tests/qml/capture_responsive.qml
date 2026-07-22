// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    color: "#071019"
    property int captureIndex: 0
    readonly property var captures: [
        {"width": 1208, "height": 696, "page": "emulation",
         "path": "/tmp/steamzero-responsive-1280x800-emulation.png"},
        {"width": 1208, "height": 696, "page": "steam",
         "path": "/tmp/steamzero-responsive-1280x800-steam.png"},
        {"width": 1656, "height": 954, "page": "emulation",
         "path": "/tmp/steamzero-responsive-1920x1080-emulation.png"},
        {"width": 2296, "height": 954, "page": "emulation",
         "path": "/tmp/steamzero-responsive-2560x1080-emulation.png"},
        {"width": 2296, "height": 954, "page": "steam",
         "path": "/tmp/steamzero-responsive-2560x1080-steam.png"}
    ]

    function prepareCapture() {
        if (captureIndex >= captures.length) {
            Qt.exit(0)
            return
        }
        const capture = captures[captureIndex]
        width = capture.width
        height = capture.height
        pageLoader.sourceComponent = capture.page === "emulation"
            ? emulationComponent : steamComponent
        renderTimer.restart()
    }

    Loader {
        id: pageLoader
        anchors.fill: parent
    }

    Timer {
        id: renderTimer
        interval: 500
        repeat: false
        onTriggered: pageLoader.item.grabToImage(function(result) {
            const capture = harness.captures[harness.captureIndex]
            if (!result.saveToFile(capture.path)) {
                Qt.exit(1)
                return
            }
            harness.captureIndex += 1
            harness.prepareCapture()
        })
    }

    Component {
        id: emulationComponent
        Emulation {
            emulation: ({
                "contextLabel": "Deck LCD • Modo Desktop",
                "platforms": [{
                    "id": "switch", "name": "Nintendo Switch", "iconKey": "switch",
                    "state": "ready", "statusLabel": "Pronto",
                    "readiness": {"percent": 100, "title": "Pronto",
                        "detail": "Ambiente pronto para uso.", "blockers": []},
                    "emulators": [
                        {"id": "eden", "name": "Eden", "state": "ready",
                         "statusLabel": "Instalado"},
                        {"id": "citron", "name": "Citron", "state": "ready",
                         "statusLabel": "Instalado"}
                    ],
                    "games": []
                }]
            })
            backgroundColor: "#071019"
            sidebarColor: "#09131d"
            surfaceColor: "#0d1924"
            raisedColor: "#122131"
            borderColor: "#2a3a49"
            textColor: "#f2f6fb"
            mutedColor: "#9eabba"
            cyanColor: "#13bdf2"
            cyanDarkColor: "#0a5f85"
            greenColor: "#59d35d"
            amberColor: "#ff9f1a"
            redColor: "#ff6b73"
        }
    }

    Component {
        id: steamComponent
        SteamGameplay {
            gameplay: ({
                "games": [{"id": "3311720", "name": "Gimmick! 2 Demo",
                    "coverUrl": ""}],
                "environment": [
                    {"id": "steam", "name": "Steam", "detail": "Contexto de jogo",
                     "owner": "Steam", "state": "ready", "statusLabel": "pronto"},
                    {"id": "gamescope", "name": "Gamescope",
                     "detail": "Composição e FPS", "owner": "SteamZero",
                     "state": "ready", "statusLabel": "pronto"},
                    {"id": "gamemode", "name": "Feral GameMode",
                     "detail": "Prioridade de CPU", "owner": "Steam",
                     "state": "ready", "statusLabel": "pronto"},
                    {"id": "mangohud", "name": "MangoHud", "detail": "Métricas",
                     "owner": "SteamZero", "state": "ready", "statusLabel": "pronto"}
                ],
                "readiness": {"percent": 100, "title": "Pronto para configurar",
                    "detail": "Hardware compatível • Perfil seguro disponível"},
                "hardware": {"deviceLabel": "Deck LCD", "tdpMin": 3, "tdpMax": 15,
                    "gpuMin": 200, "gpuMax": 1600, "refreshHz": 60,
                    "memoryGb": 16, "withinSafeLimits": true},
                "context": {"device": "Deck LCD", "battery": 84,
                    "mode": "Modo Desktop"},
                "currentProfile": {"gameId": "3311720", "scope": "game",
                    "profile": "balanced", "fps": 40, "gpuMode": "auto",
                    "gamescope": true, "gameMode": true, "mangoHud": "basic",
                    "upscaling": "native", "frameGeneration": "off"},
                "launcher": {"state": "ready", "statusLabel": "Perfil recomendado",
                    "launchOption": "steamzero-launch --appid 3311720 -- %command%",
                    "configuration": {"state": "managed", "statusLabel": "Configurado",
                        "managed": true}},
                "impact": {"battery": "4 h 15 min", "resolution": "800×1280",
                    "fluidity": "40 FPS estáveis"}
            })
            desktopStatus: ({})
            backgroundColor: "#071019"
            surfaceColor: "#0d1924"
            raisedColor: "#122131"
            borderColor: "#2a3a49"
            textColor: "#f2f6fb"
            mutedColor: "#9eabba"
            cyanColor: "#13bdf2"
            cyanDarkColor: "#0a5f85"
            greenColor: "#59d35d"
            amberColor: "#ff9f1a"
            redColor: "#ff6b73"
        }
    }

    Component.onCompleted: prepareCapture()
}
