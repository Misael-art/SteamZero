// SPDX-License-Identifier: GPL-3.0-or-later
// Fixture visual/dev: os dados abaixo não são apresentados pelo produto.
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: optionNumber("--capture-width=", 1280)
    height: optionNumber("--capture-height=", 800)
    property int failures: 0
    property int phase: 0
    readonly property string captureOutput: {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; ++i) {
            if (args[i].startsWith("--capture-output="))
                return args[i].slice("--capture-output=".length)
        }
        return ""
    }
    property string requestedSystem: ""
    property string requestedCollection: ""
    property bool continueWasRequested: false
    property string requestedMaintenance: ""

    function optionNumber(prefix, fallback) {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; ++i) {
            if (args[i].startsWith(prefix)) {
                const parsed = Number(args[i].slice(prefix.length))
                if (Number.isFinite(parsed) && parsed > 0)
                    return Math.floor(parsed)
            }
        }
        return fallback
    }

    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    EditorialHome {
        id: home
        anchors.fill: parent
        steamGames: [
            {"id": "10", "name": "Fixture Steam", "coverUrl": "", "state": "installed"},
            {"id": "20", "name": "Fixture Steam Two", "coverUrl": "", "state": "installed"}
        ]
        emulation: ({
            "editorialPlatforms": [
                {"id": "switch", "name": "Fixture Switch", "state": "attention",
                    "statusLabel": "BIOS pendente", "games": [{"id": "rom-1", "name": "Fixture ROM"}]},
                {"id": "playstation", "name": "Fixture PlayStation", "state": "unverified",
                    "statusLabel": "Nenhum jogo inventariado", "games": []}
            ],
            "platforms": [{"id": "switch", "name": "Fixture Switch", "state": "attention",
                "statusLabel": "BIOS pendente", "games": [{"id": "rom-1", "name": "Fixture ROM"}]}]
        })
        playtime: ({"games": [{"gameId": "10", "title": "Fixture Steam", "source": "steam", "playedSeconds": 5400,
            "action": {"kind": "steam-continue", "label": "Continuar", "enabled": true}}]})
        collections: ({"favorites": ["steam:20"], "collections": [{
            "id": "fixture-collection", "name": "Coleção fixture", "members": ["steam:10", "steam:20"]
        }]})
        components: [{"id": "fixture-emulator", "state": "missing"}]
        sync: ({"pending": 1, "conflicted": 1})
        doctor: ({"state": "attention"})
        libraryHealth: ({"counts": {"suspect": 1, "missing": 0, "error": 0}})
        backgroundColor: "#e7eceb"
        surfaceColor: "#f4f7f5"
        raisedColor: "#ffffff"
        borderColor: "#aebdbe"
        textColor: "#16212a"
        mutedColor: "#53616b"
        cyanColor: "#006f99"
        cyanDarkColor: "#005471"
        greenColor: "#167a45"
        amberColor: "#a35d00"
        onLibraryRequested: function(systemId) { harness.requestedSystem = systemId }
        onCollectionRequested: function(collectionId) { harness.requestedCollection = collectionId }
        onContinueRequested: function(game) { harness.continueWasRequested = game.gameId === "10" }
        onMaintenanceRequested: function(area) { harness.requestedMaintenance = area }
    }

    Timer {
        interval: 100
        running: true
        repeat: true
        onTriggered: {
            if (phase === 0) {
                check(home.catalog.length === 3, "Home deve unificar Steam e emulação")
                check(home.recent.length === 1, "Recentes deve usar somente sessões publicadas")
                check(home.favorites.length === 1 && home.favorites[0].gameRef === "steam:20",
                      "favoritos devem usar gameRef publicado")
                check(home.collectionItems.length === 1
                      && home.primaryCollection.id === "fixture-collection",
                      "coleções devem vir do read model publicado")
                check(home.systems.length === 3 && home.systems[2].id === "playstation",
                      "Home deve publicar plataformas canônicas sem jogo inventado")
                check(home.attentionSystems.length === 2, "pendência deve refletir estado da plataforma")
                check(home.componentAttention === 1 && home.syncAttention === 2 && home.libraryAttention === 1,
                      "Home deve resumir somente pendências operacionais publicadas")
                home.libraryRequested("switch")
                check(requestedSystem === "switch", "ação de sistema deve preservar o destino")
                home.collectionRequested(home.primaryCollection.id)
                check(requestedCollection === "fixture-collection",
                      "coleção deve preservar o filtro publicado")
                home.continueRequested(home.featured)
                check(continueWasRequested, "retomada publicada deve preservar o jogo real")
                home.maintenanceRequested("sync")
                check(requestedMaintenance === "sync", "manutenção deve preservar o destino operacional")
                if (captureOutput !== "") {
                    contentItem.grabToImage(function(result) {
                        result.saveToFile(captureOutput)
                        width = 800
                        height = 1280
                        phase = 1
                    })
                    return
                }
                width = 800
                height = 1280
                phase = 1
                return
            }
            check(home.compact, "Home deve reflow em retrato")
            Qt.exit(failures === 0 ? 0 : 1)
        }
    }
}
