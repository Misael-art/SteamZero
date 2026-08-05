// SPDX-License-Identifier: GPL-3.0-or-later
// Fixture visual/dev: os dados abaixo não são apresentados pelo produto.
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 800
    height: 1280
    property int failures: 0

    function canonicalPlatforms() {
        const rows = []
        for (let index = 0; index < 36; ++index) {
            rows.push({
                "id": "canonical-" + index,
                "name": "Canonical fixture " + index,
                "shortName": "Fixture " + index,
                "games": [],
                "state": "unverified",
                "statusLabel": "Nenhum jogo inventariado",
                "readiness": {"percent": 0},
                "requirements": {},
                "subsystems": []
            })
        }
        return rows
    }

    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    EditorialLibrary {
        id: library
        anchors.fill: parent
        steamGames: []
        emulation: ({"editorialPlatforms": canonicalPlatforms()})
        playtime: ({"games": []})
        collections: ({"collections": []})
        effectStacks: ({})
        mediaRecipes: ({})
        backgroundColor: "#000000"
        surfaceColor: "#0d1924"
        raisedColor: "#122131"
        borderColor: "#78909c"
        textColor: "#ffffff"
        mutedColor: "#b5c0c9"
        cyanColor: "#13bdf2"
        cyanDarkColor: "#0a5f85"
        greenColor: "#59d35d"
        amberColor: "#ffb000"
        redColor: "#ff6b73"
        highContrast: true
        reducedMotion: true
    }

    Timer {
        interval: 180
        running: true
        repeat: false
        onTriggered: {
            check(library.systems.length === 37,
                  "Steam e todas as 36 plataformas canônicas devem permanecer na jornada")
            check(library.systemRepeaterControl.count === 37,
                  "o repeater de Sistemas deve materializar todos os destinos publicados")
            check(library.systemRepeaterControl.itemAt(0).height >= library.systemCardHeight,
                  "o card compacto deve reservar espaço para o estado acessível")
            for (let index = 0; index < 36; ++index)
                check(library.handleNavigationIntent("next"), "próximo sistema deve ser navegável")
            check(library.selectedSystemIndex === 36,
                  "a navegação por intent deve alcançar a última plataforma canônica")
            Qt.exit(failures === 0 ? 0 : 1)
        }
    }
}
