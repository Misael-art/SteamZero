// SPDX-License-Identifier: GPL-3.0-or-later
//
// V4 — autoria pela UI real. O ThemeEditorPanel fala com o DesktopControlServer
// REAL (loopback, dashboard real, dados em diretório temporário) e cada edição é
// disparada por evento Qt (mouseClick/keyClick) sobre os controles do inspetor,
// nunca por chamada direta ao domínio. A URL e o token são efêmeros (build/).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtTest
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 1100
    height: 900

    property var cfg: ({})
    property var errors: []

    function xhr(method, path, payload, callback, errorCallback) {
        const request = new XMLHttpRequest()
        request.open(method, cfg.apiUrl + path)
        request.setRequestHeader("X-SteamZero-Token", cfg.apiToken)
        request.setRequestHeader("Content-Type", "application/json")
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            let body = {}
            try { body = JSON.parse(request.responseText || "{}") } catch (e) { body = {} }
            if (request.status === 200) {
                callback(body)
            } else {
                const err = body.error || {}
                errorCallback(typeof err === "string" ? err : (err.detail || err.message || err.code || "erro"))
            }
        }
        request.send(method === "GET" ? undefined : JSON.stringify(payload || {}))
    }

    function requestAction(actionId, payload, callback, errorCallback) {
        // O contrato publica `theme.editor.load` como GET com query (themeId).
        const isLoad = actionId === "theme.editor.load"
        const path = "/" + actionId.split(".").join("/")
            + (isLoad ? "?themeId=" + encodeURIComponent(payload.themeId) : "")
        xhr(isLoad ? "GET" : "POST", path, payload, callback, function(message) {
            errors.push(actionId + ": " + message + " " + JSON.stringify(payload))
            if (errorCallback)
                errorCallback(message)
        })
        return true
    }

    function request(method, path, payload, callback, errorCallback) {
        xhr(method, path, payload, callback, errorCallback || function() {})
    }

    ThemeEditorPanel {
        id: panel
        anchors.fill: parent
        request: harness.request
        requestAction: harness.requestAction
        activeThemeId: "org.steamzero.default"
    }

    TestCase {
        id: suite
        name: "ThemeAuthoringE2E"
        when: windowShown
        property string themeId: ""

        function readConfig() {
            const r = new XMLHttpRequest()
            r.open("GET", Qt.resolvedUrl("../../build/ui-theme-authoring-e2e.json"), false)
            r.send()
            return JSON.parse(r.responseText)
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

        // Rola o Flickable ancestral até o controle caber na janela: um clique fora
        // da área visível não chega ao controle, e isso também reprovaria o usuário.
        function scrollViewport(item) {
            let flick = item.parent
            while (flick && flick.contentY === undefined)
                flick = flick.parent
            return flick
        }

        function reveal(item) {
            const flick = scrollViewport(item)
            if (!flick)
                return
            const y = item.mapToItem(flick.contentItem, 0, 0).y
            if (y < flick.contentY || y + item.height > flick.contentY + flick.height)
                flick.contentY = Math.max(0, y - 40)
            wait(60)
        }

        function fullyInsideViewport(item) {
            const flick = scrollViewport(item)
            if (!flick)
                return true
            const point = item.mapToItem(flick, 0, 0)
            const epsilon = 0.5
            return point.x >= -epsilon && point.y >= -epsilon
                && point.x + item.width <= flick.width + epsilon
                && point.y + item.height <= flick.height + epsilon
        }

        function inputGeometry(item) {
            let flick = item.parent
            while (flick && flick.contentY === undefined)
                flick = flick.parent
            const point = item.mapToItem(harness, 0, 0)
            if (!flick)
                return "scene=" + point.x + "," + point.y
                    + " size=" + item.width + "x" + item.height
            const viewportPoint = item.mapToItem(flick, 0, 0)
            const contentPoint = item.mapToItem(flick.contentItem, 0, 0)
            return "scene=" + point.x + "," + point.y
                + " size=" + item.width + "x" + item.height
                + " viewport=" + viewportPoint.x + "," + viewportPoint.y
                + " flick=" + flick.width + "x" + flick.height
                + " content=" + flick.contentWidth + "x" + flick.contentHeight
                + " contentY=" + flick.contentY
                + " contentPoint=" + contentPoint.x + "," + contentPoint.y
        }

        function click(name) {
            const item = find(panel, name)
            verify(item !== null, "controle ausente: " + name)
            tryVerify(function() { return item.visible && item.enabled }, 3000, name + " não ficou acionável")
            reveal(item)
            verify(fullyInsideViewport(item), name + " fora da viewport: " + inputGeometry(item))
            const target = item
            // alvo mínimo (acessibilidade): o controle clicável precisa caber um toque
            verify(target.width >= 40 && target.height >= 36, name + " abaixo do alvo mínimo")
            mousePress(target, target.width / 2, target.height / 2)
            if (!target.pressed)
                console.log("INPUT_DEBUG click " + name + " " + inputGeometry(target))
            verify(target.pressed, name + " não recebeu o toque (coberto ou fora da viewport): "
                   + inputGeometry(target))
            mouseRelease(target, target.width / 2, target.height / 2)
        }

        function typeInto(name, text) {
            const item = find(panel, name)
            verify(item !== null, "campo ausente: " + name)
            tryVerify(function() { return item.visible }, 3000, name + " invisível")
            reveal(item)
            verify(fullyInsideViewport(item), name + " fora da viewport: " + inputGeometry(item))
            mouseClick(item)
            if (!item.activeFocus)
                console.log("INPUT_DEBUG focus " + name + " " + inputGeometry(item))
            verify(item.activeFocus, name + " não recebeu o foco do clique: " + inputGeometry(item))
            item.selectAll()
            for (let i = 0; i < text.length; i++)
                keyClick(text.charAt(i))
            keyClick(Qt.Key_Return)
        }

        // Captura opcional (cfg.captureDir): o quadro real do painel para inspeção visual.
        function capture(name) {
            if (!cfg.captureDir)
                return
            let done = false
            panel.grabToImage(function(result) {
                result.saveToFile(cfg.captureDir + "/" + name + ".png")
                done = true
            })
            tryVerify(function() { return done }, 3000, "captura " + name + " não concluiu")
        }

        function effects(stack) {
            return (panel.editorDeclared.effects || {})[stack] || []
        }

        function test_01_jornada_de_autoria_pelos_controles() {
            cfg = readConfig()
            harness.cfg = cfg
            panel.duplicateAndEdit("org.steamzero.default", "Jornada V4")
            tryVerify(function() { return panel.editorSessionId !== "" }, 5000, "a sessão real não abriu")
            tryVerify(function() { return find(panel, "effectAdd") !== null && find(panel, "effectAdd").visible }, 5000, "o inspetor de efeitos não apareceu para um tema do usuário")
            const baseEffects = effects("focusedCover").length

            // efeitos: adicionar dois, parametrizar, reordenar
            click("effectAdd")
            tryCompare(panel, "editorDirty", true)
            tryVerify(function() { return effects("focusedCover").length === baseEffects + 1 }, 3000,
                      "o efeito adicionado não chegou ao inspetor sem Undo/reabertura")
            const last = baseEffects
            typeInto("effectParam_" + last + "_radius", "24")
            tryVerify(function() { return effects("focusedCover")[last].radius === 24 }, 3000,
                      "o parâmetro editado não chegou ao documento")
            click("effectAdd")
            tryVerify(function() { return effects("focusedCover").length === baseEffects + 2 }, 3000)
            click("effectUp_" + (baseEffects + 1))
            tryVerify(function() { return effects("focusedCover")[baseEffects + 1].radius === 24 }, 3000,
                      "mover para cima não reordenou o documento")

            // operação inválida: documento e histórico preservados, erro acionável
            const depth = panel.editorHistory.undoDepth
            typeInto("effectParam_" + (baseEffects + 1) + "_radius", "9999")
            tryVerify(function() { return panel.authoringNotice !== "" }, 3000, "o erro não ficou visível")
            compare(panel.editorHistory.undoDepth, depth, "edição inválida alterou o histórico")
            compare(effects("focusedCover")[baseEffects + 1].radius, 24, "edição inválida alterou o documento")
            tryCompare(find(panel, "effectParam_" + (baseEffects + 1) + "_radius"), "text", "24", 3000,
                       "o campo continuou exibindo o valor recusado")

            // movimento: keyframe, timeline, clip (sem depender de Undo para atualizar a tela)
            typeInto("keyframe_scale", "1.2")
            tryVerify(function() {
                const st = ((panel.editorDeclared.sceneMotion || {}).states || {}).focused
                return st !== undefined && st.scale === 1.2
            }, 3000, "o keyframe editado não chegou ao documento")
            typeInto("motionTimelineName", "entrada")
            click("motionTimelineAdd")
            tryVerify(function() { return find(panel, "motionClipDuration_0") !== null }, 3000,
                      "a timeline criada não apareceu")
            click("motionClipAdd")
            tryVerify(function() { return find(find(panel, "motionClipRepeater"), "motionClipDuration_1") !== null
                                   || find(panel, "motionClipDuration_1") !== null }, 3000,
                      "o clip adicionado não apareceu no inspetor (regressão do modelo desatualizado)")
            typeInto("motionClipDuration_1", "300")
            tryVerify(function() {
                const tl = ((panel.editorDeclared.sceneMotion || {}).timelines || {}).entrada
                return tl !== undefined && tl.clips.length > 1 && tl.clips[1].duration === 300
            }, 3000)

            // undo/redo pelos botões
            const beforeUndo = JSON.stringify(panel.editorDeclared)
            click("themeEditorUndo")
            tryVerify(function() { return JSON.stringify(panel.editorDeclared) !== beforeUndo }, 3000)
            click("themeEditorRedo")
            tryVerify(function() { return JSON.stringify(panel.editorDeclared) === beforeUndo }, 3000,
                      "refazer não restaurou o documento")

            capture("01-studio-efeitos-movimento")

            // salvar, fechar e reabrir
            themeId = panel.editorManifest.id
            click("themeEditorSave")
            tryCompare(panel, "editorDirty", false, 5000)
            const saved = JSON.stringify(panel.editorDeclared)
            panel._closeEditor()
            compare(panel.editorSessionId, "")
            panel.requestAction("theme.editor.load", {themeId: themeId}, function(r) {
                panel._openEditor(r.sessionId, r.manifest, r.preview, r.declared)
            })
            tryVerify(function() { return panel.editorSessionId !== "" }, 5000, "reabrir falhou: " + themeId + " " + JSON.stringify(harness.errors))
            compare(JSON.stringify(panel.editorDeclared), saved, "o tema reaberto difere do salvo")
            compare(harness.errors.length, 1,
                    "só a edição inválida proposital podia falhar: " + JSON.stringify(harness.errors))
            console.log("THEME_ID=" + themeId)
        }

        function test_02_viewport_compacto_alcanca_os_inspetores() {
            harness.cfg = readConfig()
            panel.compactLayout = true
            harness.width = 640
            harness.height = 560
            panel._closeEditor()
            panel.duplicateAndEdit("org.steamzero.default", "Compacto V4")
            tryVerify(function() { return panel.editorSessionId !== "" }, 5000)
            const base = effects("focusedCover").length
            // No compacto o painel direito some; os inspetores precisam seguir alcançáveis por rolagem.
            click("effectAdd")
            tryVerify(function() { return effects("focusedCover").length === base + 1 }, 3000,
                      "inspetor de efeitos inalcançável no viewport compacto")
            capture("02-studio-compacto")
            typeInto("motionTimelineName", "compacta")
            click("motionTimelineAdd")
            tryVerify(function() { return find(panel, "motionClipDuration_0") !== null }, 3000)
            reveal(find(panel, "motionClipAdd"))
            verify(fullyInsideViewport(find(panel, "motionClipAdd")),
                   "Adicionar clip não cabe no viewport compacto: "
                   + inputGeometry(find(panel, "motionClipAdd")))
            capture("04-studio-compact-movimento")
            click("motionClipAdd")
            tryVerify(function() { return find(panel, "motionClipDuration_1") !== null }, 3000, "clip: " + JSON.stringify(harness.errors) + " tl=" + panel.motionTimelineName + " " + JSON.stringify((panel.editorDeclared.sceneMotion || {}).timelines))
        }

        function test_03_binding_de_layout_pelos_controles() {
            harness.cfg = readConfig()
            panel.compactLayout = false
            harness.width = 1100
            harness.height = 900
            panel._closeEditor()
            // Tema sem layouts: o inspetor explica o próximo passo em vez de ficar vazio.
            panel.duplicateAndEdit("org.steamzero.default", "Sem layouts")
            tryVerify(function() { return panel.editorSessionId !== "" }, 5000)
            tryVerify(function() { return find(panel, "bindingEmpty") !== null && find(panel, "bindingEmpty").visible }, 3000,
                      "o estado vazio dos bindings não orienta o usuário")
            panel._closeEditor()

            panel.duplicateAndEdit("org.steamzero.asset-recipes-demo", "Com layouts")
            tryVerify(function() { return panel.editorSessionId !== "" }, 5000)
            tryVerify(function() { return find(panel, "bindingApply") !== null && find(panel, "bindingApply").visible }, 3000)
            tryVerify(function() { return panel.bindingLayoutName !== "" && panel.bindingPropName !== "" }, 3000,
                      "layout/propriedade não foram selecionados por padrão")
            const layout = panel.bindingLayoutName
            const prop = panel.bindingPropName
            const field = find(panel, "bindingField")
            field.currentIndex = field.model.indexOf("genre")
            typeInto("bindingFallback", "Sem genero")
            click("bindingApply")
            tryVerify(function() {
                const layouts = (panel.editorDeclared.sceneLayouts || {}).layouts || {}
                const p = (((layouts[layout] || {}).template || {}).properties || {})[prop]
                return p !== undefined && p.binding === "item.genre" && p.fallback === "Sem genero"
            }, 3000, "o binding ligado não chegou ao documento")
            tryVerify(function() { return find(panel, "bindingCurrent_" + prop) !== null
                                   && find(panel, "bindingCurrent_" + prop).text.indexOf("item.genre") >= 0 }, 3000,
                      "o inspetor não mostra o binding atual")
            capture("03-studio-binding")
            click("themeEditorUndo")
            tryVerify(function() {
                const layouts = (panel.editorDeclared.sceneLayouts || {}).layouts || {}
                return layouts[layout].template.properties[prop].binding === "item.title"
            }, 3000, "desfazer não restaurou o binding herdado")
        }
    }
}
