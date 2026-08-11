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
    property int viewLayoutCheck: 0
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
    readonly property int requestedSystemCount: optionNumber("--system-count=", 3)
    readonly property bool longSystemStatus: hasArgument("--long-system-status")
    readonly property bool geometryOnly: hasArgument("--geometry-only")

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

    function editorialSystemFixture() {
        const rows = [library.emulation.platforms[0]]
        const status = longSystemStatus
            ? "Verificação pendente: firmware, chaves e configuração precisam de atenção"
            : "Nenhum jogo inventariado"
        for (let i = 2; i < requestedSystemCount; ++i) {
            rows.push({
                "id": "fixture-platform-" + i,
                "name": "Fixture Platform " + i,
                "state": "unverified",
                "statusLabel": status,
                "readiness": {"percent": 0},
                "requirements": {},
                "subsystems": [],
                "games": []
            })
        }
        return rows
    }

    function checkSystemCardGeometry() {
        const count = library.systems.length
        const columns = library.compact ? 1 : library.wide ? 4 : 3
        const first = library.systemRepeaterControl.itemAt(0)
        const last = library.systemRepeaterControl.itemAt(count - 1)
        console.log("G36 geometry: systems=" + count + " viewport=" + width + "x" + height
            + " first=" + first.height + "/" + first.implicitHeight
            + " preferred=" + first.reportedLayoutPreferredHeight
            + " minimum=" + first.reportedLayoutMinimumHeight
            + " grid=" + library.systemGridControl.height + "/"
            + library.systemGridControl.implicitHeight + " firstY=" + first.y
            + " last=" + last.height + "/" + last.implicitHeight + " lastY=" + last.y)
        check(first.height >= library.systemCardHeight
              && first.implicitHeight >= library.systemCardHeight
              && first.reportedLayoutPreferredHeight >= library.systemCardHeight
              && first.reportedLayoutMinimumHeight >= library.systemCardHeight,
              "card de sistema deve tornar a altura mínima efetiva no GridLayout")
        check(last.height >= library.systemCardHeight
              && last.y + last.height <= library.systemGridControl.implicitHeight,
              "último sistema deve receber a mesma altura mínima do card")
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

    // Captura uma vista já composta sem percorrer a jornada pelo timer. A
    // jornada completa continua sendo exercida quando não há captura; isolar
    // o frame evita que um artefato visual dependa de timers ou de uma troca
    // de vista que ainda esteja em andamento no Qt Quick.
    function captureRequestedStage() {
        if (captureOutput === "")
            return false
        if (captureStage === "systems") {
            captureAndExit()
            return true
        }
        if (captureStage === "system") {
            library.view = "system"
            captureAndExit()
            return true
        }
        if (["library", "dossier", "launch"].indexOf(captureStage) < 0)
            return false
        library.systemFilter = "steam"
        library.collectionFilter = ""
        library.initialFilter = ""
        library.resetMetadataFilters()
        library.selectedIndex = 0
        if (captureStage === "library"
                && ["carousel", "grid", "list"].indexOf(captureLibraryView) >= 0)
            library.libraryView = captureLibraryView
        library.view = captureStage
        captureAndExit()
        return true
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
        mediaRecipes: ({
            "contextualBackdrop": {
                "sourceOrder": ["banner", "cover"],
                "fit": "contain",
                "effectStack": "contextualBackdrop"
            },
            "focusedCover": {"sourceOrder": ["cover"], "fit": "contain"},
            "peripheralCover": {"sourceOrder": ["cover"], "fit": "crop"}
        })
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
                if (captureRequestedStage())
                    return
                // REATRIBUI o objeto inteiro em vez de mutar uma chave interna.
                // `systems` é um binding sobre `emulation`; mutar
                // `emulation.editorialPlatforms` não troca a referência de
                // `emulation`, então o QML não reavalia e o harness comparava
                // contra a lista antiga — 898 falhas em laço, sem sair.
                library.emulation = {
                    "platforms": library.emulation.platforms,
                    "editorialPlatforms": editorialSystemFixture()
                }
                // Repeater entrega os delegates neste turno; GridLayout só
                // recalcula as linhas no próximo polish. Medir antes disso
                // observaria 37 cards sobrepostos na primeira célula.
                phase = -1
                return
            }
            if (phase === -1) {
                check(library.systems.length === requestedSystemCount,
                      "a jornada deve incluir Steam e as plataformas editoriais publicadas")
                check(library.systems[2].id === "fixture-platform-2" && library.systems[2].gameCount === 0,
                      "plataforma canônica sem ROM deve permanecer visível sem jogos inventados")
                check(library.games.length === 3, "catálogo deve preservar jogos Steam e emulados")
                check(library.contextualMediaSource({"heroUrl": "hero", "coverUrl": "cover"}) === "hero"
                      && library.contextualMediaSource({"coverUrl": "cover", "screenshotUrl": "shot"}) === "cover"
                      && library.contextualMediaSource({"screenshotUrl": "shot", "bannerUrl": "banner"}) === "shot",
                      "mídia contextual deve respeitar a ordem publicada sem varrer fontes locais")
                check(library.recipeMediaSource({"coverUrl": "cover", "bannerUrl": "banner"}, "contextualBackdrop") === "banner"
                      && library.recipeFillMode("contextualBackdrop") === Image.PreserveAspectFit
                      && library.recipeFillMode("peripheralCover") === Image.PreserveAspectCrop,
                      "receita deve escolher apenas fontes publicadas e preservar o fit declarado")
                check(library.screenshotSources({"screenshotUrls": ["one", "one", "two"]}).length === 2
                      && library.screenshotSources({"screenshotUrl": "fallback"})[0] === "fallback",
                      "capturas devem usar somente fontes publicadas, deduplicadas e sem descoberta local")
                check(library.stateLabel("installed") === "Instalado"
                      && library.stateLabel("unverified") === "Não verificado",
                      "estados técnicos conhecidos devem usar rótulos PT-BR")
                check(library.view === "systems", "a jornada inicia em sistemas")
                checkSystemCardGeometry()
                if (geometryOnly) {
                    check(!library.contextualBackdropVisible === library.highContrast,
                          "alto contraste deve preservar a geometria sem mostrar backdrop")
                    Qt.exit(failures === 0 ? 0 : 1)
                    return
                }
                check(library.handleNavigationIntent("next")
                      && library.selectedSystem.id === "switch",
                      "intent semântico deve mover o foco entre sistemas")
                for (let i = 2; i < library.systems.length; ++i)
                    check(library.handleNavigationIntent("next"),
                          "navegação semântica deve alcançar o último sistema")
                check(library.selectedSystemIndex === library.systems.length - 1,
                      "navegação semântica deve alcançar o último sistema publicado")
                for (let i = 2; i < library.systems.length; ++i)
                    check(library.handleNavigationIntent("previous"),
                          "navegação semântica deve retornar do último sistema")
                check(library.handleNavigationIntent("confirm"),
                      "intent de confirmação deve abrir o sistema focado")
                check(library.view === "system" && library.selectedSystem.id === "switch",
                      "sistema deve possuir uma vista própria antes da biblioteca")
                check(library.requirementState("keys") === "blocked"
                      && library.requirementState("firmware") === "ready",
                      "requisitos publicados devem preservar missing bloqueante e ok compatível")
                library.emulation.platforms[0].requirements.firmware.status = "outdated"
                check(library.requirementState("firmware") === "attention",
                      "firmware desatualizado deve preservar atenção, não virar bloqueio ou dado ausente")
                library.emulation.platforms[0].requirements.firmware.status = "ok"
                library.goBack()
                library.openSystem(library.systems[0])
                phase = 1
                return
            }
            if (phase === 1) {
                if (viewLayoutCheck === 0) {
                    check(library.view === "library", "sistema deve abrir biblioteca")
                    check(library.visibleGames.length === 2, "filtro Steam deve usar somente a fonte selecionada")
                    check(library.metadataValues("genre").length === 2
                          && library.metadataValues("year").length === 2,
                          "filtros de metadados devem usar somente valores publicados")
                    check(library.isPublishedMetadataValue("") === false
                          && library.isPublishedMetadataValue("não publicado") === false
                          && library.isPublishedMetadataValue("Action") === true,
                          "metadados vazios ou 'não publicado' não contam como publicados")
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
                    viewLayoutCheck = 1
                    return
                }
                if (viewLayoutCheck === 1) {
                    check(library.gridControl.visible
                          && library.gridControl.y <= library.carouselControl.y + 24,
                          "a grade não deve reservar o espaço do carrossel oculto")
                    library.libraryView = "list"
                    viewLayoutCheck = 2
                    return
                }
                if (viewLayoutCheck === 2) {
                    check(library.listControl.visible
                          && library.listControl.y <= library.carouselControl.y + 24,
                          "a lista não deve manter espaço das outras vistas ocultas")
                    library.libraryView = "carousel"
                    viewLayoutCheck = 3
                    return
                }
                check(library.handleNavigationIntent("next") && library.selectedIndex === 1
                      && library.handleNavigationIntent("previous") && library.selectedIndex === 0,
                      "intents devem navegar pelo catálogo com retorno previsível")
                check(library.handleNavigationIntent("confirm") && library.view === "dossier",
                      "confirmação na biblioteca deve abrir o dossiê do jogo focado")
                phase = 2
                return
            }
            if (phase === 2) {
                check(library.selectedGame.launchable, "Steam com app id numérico deve poder ser preparado")
                check(library.handleNavigationIntent("confirm"),
                      "confirmação no dossiê deve abrir a revisão de lançamento")
                phase = 3
                return
            }
            if (phase === 3) {
                check(library.view === "launch", "dossiê deve abrir revisão de lançamento")
                check(library.handleNavigationIntent("back") && library.view === "dossier",
                      "voltar deve preservar a seleção ao sair da revisão")
                library.goBack()
                library.openSystem(library.systems[1])
                check(library.visibleGames.length === 1 && !library.visibleGames[0].launchable,
                      "emulação sem launcher publicado deve permanecer honesta")
                // A guarda mora no DOSSIÊ, não na biblioteca. Inspecionar um
                // jogo sem launcher é legítimo — é assim que o usuário vê o
                // rótulo "Sem launcher". Barrar já na biblioteca esconderia a
                // informação em vez de proteger o lançamento.
                //
                // A asserção anterior exigia `false` já na biblioteca e, por
                // nunca chegar ao dossiê, teria passado mesmo se a guarda real
                // não existisse.
                check(library.handleNavigationIntent("confirm") && library.view === "dossier",
                      "jogo sem launcher deve poder ser inspecionado no dossiê")
                check(!library.handleNavigationIntent("confirm") && library.view === "dossier",
                      "confirmação não deve abrir lançamento sem contrato seguro")
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
