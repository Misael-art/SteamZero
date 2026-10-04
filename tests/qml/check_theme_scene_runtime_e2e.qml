// SPDX-License-Identifier: GPL-3.0-or-later
//
// V2 — a cena resolvida pela bridge REAL é desenhada pelo SceneEsdeView e a
// imagem é de fato decodificada: o teste lê pixels do quadro renderizado, não só
// a URI. Dois consumidores de origem: tema ES-DE instalado (`theme.scene.render`)
// e cena RetroFE importada (`theme.scene.render-imported`), ambos com dados
// sintéticos isolados. URL e token são efêmeros (build/).
import QtQuick
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 800
    height: 600

    SceneEsdeView {
        id: view
        anchors.fill: parent
        viewData: ({"id": "vazia", "elements": []})
        runtimeModel: ({})
    }

    TestCase {
        id: suite
        name: "ThemeSceneRuntimeE2E"
        when: windowShown

        function readConfig() {
            const r = new XMLHttpRequest()
            r.open("GET", Qt.resolvedUrl("../../build/ui-theme-scene-runtime-e2e.json"), false)
            r.send()
            return JSON.parse(r.responseText)
        }

        function post(cfg, path, payload) {
            const r = new XMLHttpRequest()
            r.open("POST", cfg.apiUrl + path, false)
            r.setRequestHeader("X-SteamZero-Token", cfg.apiToken)
            r.setRequestHeader("Content-Type", "application/json")
            r.send(JSON.stringify(payload))
            return {status: r.status, body: JSON.parse(r.responseText || "{}")}
        }

        function find(root, name) {
            if (!root)
                return null
            if (root.objectName === name)
                return root
            const kids = root.childItems !== undefined ? root.childItems : root.children
            for (let i = 0; kids && i < kids.length; i++) {
                const hit = find(kids[i], name)
                if (hit)
                    return hit
            }
            return null
        }

        // O Image fica dentro do Loader do SceneEsdeView, sem objectName: acha-se pela
        // URL de origem que a cena resolvida declarou (blob endereçado por hash).
        function imageFor(root, fileName) {
            if (!root)
                return null
            if (root.status !== undefined && root.fillMode !== undefined && root.source !== undefined
                    && String(root.source) === fileName)
                return root
            const kids = root.childItems !== undefined ? root.childItems : root.children
            for (let i = 0; kids && i < kids.length; i++) {
                const hit = imageFor(kids[i], fileName)
                if (hit)
                    return hit
            }
            return null
        }

        function show(rendered) {
            view.runtimeModel = rendered.runtimeModel
            view.viewData = rendered.scene.views[0]
        }

        // O gradiente do fixture muda da esquerda para a direita; uma imagem não
        // decodificada (ou um placeholder) não tem essa variação de pixel.
        function assertGradient(imageItem, firstDominant, lastDominant) {
            tryCompare(imageItem, "status", Image.Ready, 5000, imageItem.objectName + " não decodificou")
            verify(imageItem.sourceSize.width > 0 && imageItem.sourceSize.height > 0)
            wait(100)
            const grabbed = grabImage(imageItem)
            verify(grabbed !== null && grabbed.width > 8, "captura vazia")
            const left = grabbed.pixel(Math.min(8, Math.floor(grabbed.width / 8)), Math.floor(grabbed.height / 2))
            const right = grabbed.pixel(grabbed.width - 1 - Math.min(8, Math.floor(grabbed.width / 8)), Math.floor(grabbed.height / 2))
            const channel = function(c, i) { return 255 * [c.r, c.g, c.b][i] }
            verify(channel(left, firstDominant) > channel(left, lastDominant) + 40,
                   "lado esquerdo sem a cor esperada")
            verify(channel(right, lastDominant) > channel(right, firstDominant) + 40,
                   "lado direito sem a cor esperada")
        }

        function test_01_esde_instalado_desenha_pixels_do_asset() {
            const cfg = readConfig()
            const response = post(cfg, "/theme/scene/render",
                {themeId: cfg.esdeId, aspectRatio: "16:10", synthetic: true})
            compare(response.status, 200)
            show(response.body)
            const declared = response.body.scene.views[0].elements.filter(
                function(e) { return e.name === "fundo" })[0].source
            tryVerify(function() { return imageFor(view, declared) !== null }, 5000,
                      "a imagem 'fundo' não foi instanciada pelo SceneEsdeView")
            const fundo = imageFor(view, declared)
            assertGradient(fundo, 0, 2)  // vermelho → azul
            compare(response.body.runtimeModel.isolated, true)
            // asset ausente: diagnóstico no resultado, sem trocar por outra cena
            verify(JSON.stringify(response.body.assets).indexOf("nao-existe.png") >= 0)
        }

        function test_02_retrofe_importado_desenha_pixels_do_asset() {
            const cfg = readConfig()
            const response = post(cfg, "/theme/scene/render-imported", {sceneId: cfg.retrofeId})
            compare(response.status, 200)
            compare(response.body.origin, "retrofe")
            show(response.body)
            const declared = response.body.scene.views[0].elements.filter(
                function(e) { return e.source })[0].source
            tryVerify(function() { return imageFor(view, declared) !== null }, 5000,
                      "o logo RetroFE não foi instanciado pelo SceneEsdeView")
            const logo = imageFor(view, declared)
            assertGradient(logo, 1, 0)  // verde → magenta
        }
    }
}
