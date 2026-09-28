// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"
import "readiness_fixture.js" as Fixtures

Window {
    id: harness
    visible: true
    color: "#071019"
    property int captureIndex: 0

    // UX-03: os três casos que a inspeção visual precisa distinguir. Um número
    // pintado de verde não prova nada; o que tem de ser visto é a cor vir do
    // estado, o número só existir com medição, e a legenda da dimensão caber no
    // cartão quando o nome do que foi medido é longo.
    readonly property var prontidoPronto: Fixtures.medido("ready", 3, 3,
        {"label": "Pronto", "cause": "Ambiente pronto para uso."})
    readonly property var prontidoBloqueado: Fixtures.medido("blocked", 2, 3, {
        "label": "Ação necessária",
        "cause": "Keys e firmware próprios ainda não foram importados.",
        "action": "Importe keys e firmware próprios antes de iniciar jogos."})
    readonly property var prontidoNaoMedido: Fixtures.semMedicao("unverified",
        {"label": "Verificação pendente", "cause": "Nenhum requisito foi observado ainda."})
    // O painel de contexto lista bloqueios; um payload de produção bloqueado os
    // traz preenchidos, então a captura do painel usa a forma completa.
    readonly property var prontidoBloqueadoComLista: Fixtures.medido("blocked", 1, 3, {
        "label": "Ação necessária",
        "cause": "Gamescope não está disponível (SteamZero).",
        "action": "Instale ou ative Gamescope (SteamZero).",
        "blockers": ["Instale ou ative Gamescope (SteamZero).",
                     "Importe keys e firmware próprios antes de iniciar jogos."]})

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
         "path": "/tmp/steamzero-responsive-2560x1080-steam.png"},
        {"width": 1208, "height": 696, "page": "emulation", "platformView": true,
         "estado": "ready", "readiness": harness.prontidoPronto,
         "path": "/tmp/steamzero-readiness-emulation-ready.png"},
        {"width": 1208, "height": 696, "page": "emulation", "platformView": true,
         "estado": "blocked", "readiness": harness.prontidoBloqueado,
         "path": "/tmp/steamzero-readiness-emulation-blocked.png"},
        {"width": 1208, "height": 696, "page": "emulation", "platformView": true,
         "estado": "unverified", "readiness": harness.prontidoNaoMedido,
         "path": "/tmp/steamzero-readiness-emulation-unverified.png"},
        {"width": 1208, "height": 696, "page": "steam",
         "readiness": harness.prontidoBloqueado,
         "path": "/tmp/steamzero-readiness-steam-blocked.png"},
        {"width": 949, "height": 593, "page": "emulation", "platformView": true,
         "estado": "blocked", "readiness": harness.prontidoBloqueado,
         "path": "/tmp/steamzero-readiness-emulation-blocked-handheld.png"},
        {"width": 949, "height": 593, "page": "steam",
         "readiness": harness.prontidoBloqueado,
         "path": "/tmp/steamzero-readiness-steam-blocked-handheld.png"},
        // A caixa "Antes de continuar" só é visível com o painel de contexto
        // aberto — medido: escopo não-`game`, não compacto e `width >= 1500`.
        // Sem esta captura, a única superfície corrigida nesta frente (a tinta
        // que pintava um bloqueio como "atenção") ficaria sem inspeção visual.
        {"width": 1656, "height": 954, "page": "emulation",
         "estado": "blocked", "readiness": harness.prontidoBloqueadoComLista,
         "path": "/tmp/steamzero-readiness-emulation-blocked-panel.png"}
    ]

    function comProntidao(payload, readiness) {
        const copia = {}
        const chaves = Object.keys(payload)
        for (let i = 0; i < chaves.length; i += 1)
            copia[chaves[i]] = payload[chaves[i]]
        copia.readiness = readiness
        return copia
    }

    function plataformaComProntidao(base, capture) {
        // Objeto NOVO de ponta a ponta. Mutar `base` no lugar faria o `selectedPlatform`
        // guardar a mesma referência JS de antes: o QML não emite change, a ligação
        // de `readiness` não reavalia e o cartão permanece pintado com o estado da
        // captura anterior — que foi exatamente o que este harness mostrou antes
        // desta linha existir. A bridge publica dicionários novos a cada resposta,
        // então o risco é do harness, não da produção.
        const plataforma = {}
        const chaves = Object.keys(base)
        for (let i = 0; i < chaves.length; i += 1)
            plataforma[chaves[i]] = base[chaves[i]]
        plataforma.readiness = capture.readiness
        plataforma.state = capture.estado
        plataforma.statusLabel = capture.readiness.label
        return plataforma
    }

    function applyReadiness(item, capture) {
        if (capture.platformView === true)
            item.globalManagementActive = false
        if (capture.readiness === undefined)
            return
        if (capture.page === "emulation") {
            const plataformas = []
            plataformas.push(harness.plataformaComProntidao(
                item.emulation.platforms[0], capture))
            for (let i = 1; i < item.emulation.platforms.length; i += 1)
                plataformas.push(item.emulation.platforms[i])
            item.emulation = {"contextLabel": item.emulation.contextLabel,
                              "platforms": plataformas}
            return
        }
        item.gameplay = harness.comProntidao(item.gameplay, capture.readiness)
    }

    function prepareCapture() {
        if (captureIndex >= captures.length) {
            Qt.exit(0)
            return
        }
        const capture = captures[captureIndex]
        width = capture.width
        height = capture.height
        // Página nova a cada captura: com o mesmo Componente o Loader reaproveitava
        // o item anterior, e a captura seguinte saía com o estado da anterior.
        pageLoader.active = false
        pageLoader.sourceComponent = capture.page === "emulation"
            ? emulationComponent : steamComponent
        pageLoader.active = true
        applyReadiness(pageLoader.item, capture)
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
                    "readiness": Fixtures.medido("ready", 3, 3,
                        {"label": "Pronto", "cause": "Ambiente pronto para uso."}),
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
                "readiness": Fixtures.medido("ready", 4, 4, {
                    "label": "Pronto para configurar",
                    "cause": "Hardware compatível • Perfil seguro disponível"}),
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
