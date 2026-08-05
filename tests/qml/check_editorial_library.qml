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
    property bool capturePending: false
    readonly property string captureOutput: {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; ++i) {
            if (args[i].startsWith("--capture-output="))
                return args[i].slice("--capture-output=".length)
        }
        return ""
    }
    readonly property bool captureHighContrast: hasArgument("--capture-high-contrast")
    readonly property bool captureReducedMotion: hasArgument("--capture-reduced-motion")
    readonly property string captureLibraryView: optionValue("--capture-view=", "carousel")
    readonly property string captureStage: optionValue("--capture-stage=", "library")

    function hasArgument(value) {
        return Qt.application.arguments.indexOf(value) >= 0
    }

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

    function optionValue(prefix, fallback) {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; ++i) {
            if (args[i].startsWith(prefix))
                return args[i].slice(prefix.length)
        }
        return fallback
    }

    function largeSteamFixture() {
        const rows = []
        for (let i = 0; i < 1200; ++i) {
            rows.push({
                "id": String(100000 + i),
                "name": "Large fixture " + i,
                "coverUrl": "",
                "state": "installed"
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

    function captureAndExit() {
        if (capturePending)
            return
        capturePending = true
        captureDelay.restart()
    }

    Timer {
        id: captureDelay
        interval: 120
        repeat: false
        onTriggered: {
            contentItem.grabToImage(function(result) {
                result.saveToFile(captureOutput)
                Qt.exit(0)
            })
        }
    }

    EditorialLibrary {
        id: library
        anchors.fill: parent
        steamGames: [
            {"id": "10", "name": "Fixture Steam One", "coverUrl": "", "state": "installed",
                "genre": "Action", "year": 2001, "developer": "Fixture Studio"},
            {"id": "20", "name": "Fixture Steam Two", "coverUrl": "", "state": "installed",
                "genre": "Puzzle", "year": 2002, "developer": "Other Studio"}
        ]
        emulation: {
            "platforms": [{
                "id": "switch", "name": "Fixture Switch", "state": "attention",
                "statusLabel": "Verificação pendente", "readiness": {"percent": 45},
                "requirements": {
                    "keys": {"status": "missing", "detail": "Keys próprias ainda não foram verificadas", "blocksPlay": true},
                    "firmware": {"status": "ok", "detail": "Firmware verificado", "blocksPlay": false}
                },
                "games": [{"id": "fixture-rom", "name": "Fixture ROM", "genre": "Adventure",
                    "year": 1998, "developer": "Fixture Studio"}]
            }]
        }
        playtime: ({"games": []})
        collections: ({
            "collections": [{"id": "pinned", "name": "Fixados", "members": ["steam:10"]}]
        })
        effectStacks: ({})
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
        reducedMotion: harness.captureReducedMotion
        highContrast: harness.captureHighContrast
    }

    Timer {
        interval: 100
        running: true
        repeat: true
        onTriggered: {
            if (phase === 0) {
                if (captureOutput !== "" && captureStage === "systems") {
                    captureAndExit()
                    return
                }
                check(library.systems.length === 2, "Steam e a plataforma emulada devem compor sistemas")
                check(library.games.length === 3, "catálogo deve preservar jogos Steam e emulados")
                check(library.contextualMediaSource({"heroUrl": "hero", "coverUrl": "cover"}) === "hero"
                      && library.contextualMediaSource({"coverUrl": "cover", "screenshotUrl": "shot"}) === "cover"
                      && library.contextualMediaSource({"screenshotUrl": "shot", "bannerUrl": "banner"}) === "shot",
                      "mídia contextual deve respeitar a ordem publicada sem varrer fontes locais")
                check(library.screenshotSources({"screenshotUrls": ["one", "one", "two"]}).length === 2
                      && library.screenshotSources({"screenshotUrl": "fallback"})[0] === "fallback",
                      "capturas devem usar somente fontes publicadas, deduplicadas e sem descoberta local")
                check(library.stateLabel("installed") === "Instalado"
                      && library.stateLabel("unverified") === "Não verificado",
                      "estados técnicos conhecidos devem usar rótulos PT-BR")
                check(library.view === "systems", "a jornada inicia em sistemas")
                library.openSystemDetails(1)
                check(library.view === "system" && library.selectedSystem.id === "switch",
                      "sistema deve possuir uma vista própria antes da biblioteca")
                check(library.requirementState("keys") === "blocked"
                      && library.requirementState("firmware") === "ready",
                      "requisitos publicados devem preservar missing bloqueante e ok compatível")
                library.emulation.platforms[0].requirements.firmware.status = "outdated"
                check(library.requirementState("firmware") === "attention",
                      "firmware desatualizado deve preservar atenção, não virar bloqueio ou dado ausente")
                library.emulation.platforms[0].requirements.firmware.status = "ok"
                if (captureOutput !== "" && captureStage === "system") {
                    captureAndExit()
                    return
                }
                library.goBack()
                library.openSystem(library.systems[0])
                phase = 1
                return
            }
            if (phase === 1) {
                check(library.view === "library", "sistema deve abrir biblioteca")
                check(library.visibleGames.length === 2, "filtro Steam deve usar somente a fonte selecionada")
                check(library.metadataValues("genre").length === 2
                      && library.metadataValues("year").length === 2,
                      "filtros de metadados devem usar somente valores publicados")
                library.genreFilter = "Action"
                check(library.visibleGames.length === 1 && library.selectedGame.genre === "Action",
                      "gênero publicado deve filtrar a biblioteca sem criar categorias")
                library.genreFilter = ""
                library.yearFilter = "2002"
                check(library.visibleGames.length === 1 && library.selectedGame.year === "2002",
                      "ano publicado deve filtrar a biblioteca")
                library.yearFilter = ""
                library.developerFilter = "Fixture Studio"
                check(library.visibleGames.length === 1 && library.selectedGame.developer === "Fixture Studio",
                      "desenvolvedor publicado deve filtrar a biblioteca")
                library.resetMetadataFilters()
                library.collectionFilter = "pinned"
                check(library.visibleGames.length === 1,
                      "coleções devem filtrar o catálogo pela referência publicada")
                library.collectionFilter = ""
                library.libraryView = "grid"
                check(library.gridControl.visible, "grade deve usar o mesmo catálogo filtrado")
                library.libraryView = "list"
                check(library.listControl.visible, "lista deve usar o mesmo catálogo filtrado")
                library.libraryView = "carousel"
                if (captureOutput !== "" && captureStage === "library") {
                    if (["carousel", "grid", "list"].indexOf(captureLibraryView) >= 0)
                        library.libraryView = captureLibraryView
                    contentItem.grabToImage(function(result) {
                        result.saveToFile(captureOutput)
                        library.openDossier(0)
                        phase = 2
                    })
                    return
                }
                library.openDossier(0)
                phase = 2
                return
            }
            if (phase === 2) {
                if (captureOutput !== "" && captureStage === "dossier") {
                    captureAndExit()
                    return
                }
                check(library.selectedGame.launchable, "Steam com app id numérico deve poder ser preparado")
                library.openLaunchReview()
                phase = 3
                return
            }
            if (phase === 3) {
                check(library.view === "launch", "dossiê deve abrir revisão de lançamento")
                library.openSystem(library.systems[1])
                check(library.visibleGames.length === 1 && !library.visibleGames[0].launchable,
                      "emulação sem launcher publicado deve permanecer honesta")
                width = 800
                height = 1280
                phase = 4
                return
            }
            if (phase === 4) {
                check(library.compact, "800×1280 deve usar a composição compacta")
                check(library.minimumTarget >= 48, "alvos touch devem manter 48 px")
                library.highContrast = true
                library.reducedMotion = true
                phase = 5
                return
            }
            if (phase === 5) {
                check(!library.contextualBackdropVisible,
                      "alto contraste deve ocultar o backdrop tratado")
                check(library.focusDuration === 0 && library.viewDuration === 0,
                      "movimento reduzido deve eliminar interpolação visual")
                width = 3840
                height = 2160
                phase = 6
                return
            }
            if (phase === 6) {
                check(library.wide, "4K deve usar composição ampla")
                library.initialFilter = "F"
                check(library.visibleGames.length === 1,
                      "filtro alfabético deve filtrar os títulos publicados")
                library.initialFilter = "A"
                check(library.visibleGames.length === 0,
                      "filtro alfabético sem títulos deve apresentar catálogo vazio")
                library.initialFilter = ""
                library.steamGames = largeSteamFixture()
                library.systemFilter = "steam"
                library.collectionFilter = ""
                library.selectedIndex = 0
                phase = 7
                return
            }
            check(library.visibleGames.length === 1200,
                  "biblioteca grande deve preservar todos os títulos publicados")
            check(library.carouselControl.contentItem.children.length < 80,
                  "carrossel virtualizado não deve materializar a biblioteca inteira")
            Qt.exit(failures === 0 ? 0 : 1)
        }
    }
}
