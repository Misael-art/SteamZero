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
    property var runtimeTheme: null
    property bool runtimeVisible: false
    property bool runtimeThemeRefreshed: false
    property bool runtimeCaptureComplete: false
    property bool runtimeCaptureSucceeded: false
    readonly property url runtimeFixture: Qt.resolvedUrl(
        "../../tests/fixtures/themes/esde-mini/fundo.png")

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

    function refreshRuntimeTheme(callback) {
        harness.runtimeThemeRefreshed = false
        request("GET", "/status", {}, function(status) {
            const dashboard = status && status.dashboard ? status.dashboard : ({})
            const theme = dashboard.theme || null
            harness.runtimeTheme = theme
            if (theme) {
                panel.activeThemeId = String(theme.activeId || "")
                panel.activeThemeName = String(theme.activeName || "")
            }
            harness.runtimeThemeRefreshed = true
            if (callback)
                callback(theme)
        }, function(message) {
            harness.errors.push("/status: " + message)
        })
    }

    function findRuntimeMedia(item) {
        if (!item)
            return null
        if (item.objectName === "editorialFocusedCoverMedia")
            return item
        const visual = item.childItems !== undefined ? item.childItems : []
        for (let i = 0; i < visual.length; ++i) {
            const found = findRuntimeMedia(visual[i])
            if (found)
                return found
        }
        const objects = item.children !== undefined ? item.children : []
        for (let i = 0; i < objects.length; ++i) {
            if (visual.indexOf(objects[i]) >= 0)
                continue
            const found = findRuntimeMedia(objects[i])
            if (found)
                return found
        }
        return null
    }

    function captureRuntimeMedia(fileName) {
        const media = findRuntimeMedia(runtimeLibrary)
        runtimeCaptureComplete = false
        runtimeCaptureSucceeded = false
        if (!media) {
            runtimeCaptureComplete = true
            return
        }
        media.grabToImage(function(result) {
            runtimeCaptureSucceeded = result !== null
                && result.saveToFile(cfg.runtimeCaptureDir + "/" + fileName)
            runtimeCaptureComplete = true
        })
    }

    function captureRuntimeSurface(fileName) {
        runtimeCaptureComplete = false
        runtimeCaptureSucceeded = false
        runtimeLibrary.grabToImage(function(result) {
            runtimeCaptureSucceeded = result !== null
                && result.saveToFile(cfg.runtimeCaptureDir + "/" + fileName)
            runtimeCaptureComplete = true
        })
    }

    ThemeBridge {
        id: runtimeBridge
        _source: harness.runtimeTheme
    }

    EditorialLibrary {
        id: runtimeLibrary
        objectName: "authoringRuntimeLibrary"
        anchors.fill: parent
        visible: harness.runtimeVisible
        steamGames: [{
            "id": "fixture-theme-runtime",
            "name": "Fixture de tema",
            "coverUrl": harness.runtimeFixture.toString(),
            "heroUrl": harness.runtimeFixture.toString(),
            "state": "installed"
        }]
        emulation: ({platforms: []})
        playtime: ({games: []})
        collections: ({collections: []})
        steamGameplay: ({})
        sync: ({})
        effectStacks: runtimeBridge.effectStacks
        mediaRecipes: runtimeBridge.mediaRecipes
        backgroundColor: runtimeBridge.background
        surfaceColor: runtimeBridge.surface
        raisedColor: runtimeBridge.surfaceRaised
        borderColor: runtimeBridge.border
        textColor: runtimeBridge.text
        mutedColor: runtimeBridge.textMuted
        cyanColor: runtimeBridge.accent
        cyanDarkColor: runtimeBridge.accentStrong
        greenColor: runtimeBridge.success
        amberColor: runtimeBridge.warning
        redColor: runtimeBridge.danger
        reducedMotion: runtimeBridge.reducedMotion
        highContrast: runtimeBridge.highContrast
        themeMinimumTarget: runtimeBridge.minimumTarget
        themeFocusedScale: runtimeBridge.focusedScale
        themePeripheralOpacity: runtimeBridge.peripheralOpacity
        typography: runtimeBridge.typographyRoles
        view: "library"
        systemFilter: "steam"
        selectedIndex: 0
        libraryView: "carousel"
    }

    ThemeEditorPanel {
        id: panel
        anchors.fill: parent
        visible: !harness.runtimeVisible
        request: harness.request
        requestAction: harness.requestAction
        activeThemeId: "org.steamzero.default"
    }

    TestCase {
        id: suite
        name: "ThemeAuthoringE2E"
        when: windowShown
        property string themeId: ""
        property var targetMeasurements: ({})

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
            const visual = root.childItems !== undefined ? root.childItems : []
            for (let i = 0; i < visual.length; i++) {
                const hit = find(visual[i], name)
                if (hit)
                    return hit
            }
            const objects = root.children !== undefined ? root.children : []
            for (let i = 0; i < objects.length; i++) {
                if (visual.indexOf(objects[i]) >= 0)
                    continue
                const hit = find(objects[i], name)
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
            verify(item !== null, "reveal recebeu controle ausente")
            verify(typeof item.mapToItem === "function",
                   "reveal recebeu um controle que não é Item: " + item.objectName + " " + item)
            const objectName = String(item.objectName || "")
            for (let attempt = 0; attempt < 3; ++attempt) {
                wait(60)
                item = find(panel, objectName) || find(panel.effectColorDialogControl, objectName)
                    || pickerControl(objectName) || item
                const flick = scrollViewport(item)
                if (!flick)
                    return
                const point = item.mapToItem(flick, 0, 0)
                const margin = 48
                if (point.y >= margin && point.y + item.height <= flick.height - margin)
                    return
                if (point.y < margin)
                    flick.contentY = Math.max(0, flick.contentY + point.y - margin)
                else
                    flick.contentY += point.y + item.height - flick.height + margin
            }
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

        function assertTarget(item, name) {
            const minimumTarget = 48
            targetMeasurements[name] = {
                width: item.width,
                height: item.height,
                visualScale: panel.visualScale
            }
            verify(item.width >= minimumTarget && item.height >= minimumTarget,
                   name + " abaixo do alvo de " + minimumTarget + " × " + minimumTarget
                   + " px (escala " + panel.visualScale + "): " + inputGeometry(item))
        }

        function pickerControl(name) {
            const picker = panel.effectColorDialogControl
            if (!picker)
                return null
            if (name === "themeColorPickerHex")
                return picker.hexEditorControl
            if (name === "themeColorPickerApply")
                return picker.applyButtonControl
            if (name === "themeColorPickerCancel")
                return picker.cancelButtonControl
            return null
        }

        function click(name) {
            let item = find(panel, name) || find(harness, name)
                || find(panel.effectColorDialogControl, name)
                || pickerControl(name)
                || (name === "themeApplyConfirm" ? panel.applyConfirmControl : null)
            verify(item !== null, "controle ausente: " + name)
            tryVerify(function() { return item.visible && item.enabled }, 3000, name + " não ficou acionável")
            reveal(item)
            item = find(panel, name) || find(harness, name)
                || find(panel.effectColorDialogControl, name) || pickerControl(name) || item
            verify(fullyInsideViewport(item), name + " fora da viewport: " + inputGeometry(item))
            const target = item
            assertTarget(target, name)
            mousePress(target, target.width / 2, target.height / 2)
            if (!target.pressed)
                console.log("INPUT_DEBUG click " + name + " " + inputGeometry(target))
            verify(target.pressed, name + " não recebeu o toque (coberto ou fora da viewport): "
                   + inputGeometry(target))
            mouseRelease(target, target.width / 2, target.height / 2)
        }

        function chooseCombo(name, value) {
            const combo = find(panel, name)
            verify(combo !== null, "seletor ausente: " + name)
            reveal(combo)
            verify(fullyInsideViewport(combo), name + " fora da viewport: " + inputGeometry(combo))
            assertTarget(combo, name)
            const index = combo.model.indexOf(value)
            verify(index >= 0, "opção ausente em " + name + ": " + value)
            const previousIndex = combo.currentIndex
            mouseClick(combo, combo.width / 2, combo.height / 2)
            tryVerify(function() { return combo.popup.visible }, 3000, name + " não abriu")
            const direction = index >= previousIndex ? Qt.Key_Down : Qt.Key_Up
            for (let step = 0; step < Math.abs(index - previousIndex); ++step)
                keyClick(direction)
            keyClick(Qt.Key_Return)
            tryCompare(combo, "currentText", value, 3000,
                       name + " não aceitou a opção " + value)
        }

        function typeInto(name, text) {
            let item = find(panel, name) || find(panel.effectColorDialogControl, name)
                || pickerControl(name)
            verify(item !== null, "campo ausente: " + name)
            tryVerify(function() { return item.visible }, 3000, name + " invisível")
            reveal(item)
            item = find(panel, name) || find(panel.effectColorDialogControl, name)
                || pickerControl(name) || item
            verify(fullyInsideViewport(item), name + " fora da viewport: " + inputGeometry(item))
            assertTarget(item, name)
            const editor = typeof item.selectAll === "function" ? item
                : (item.contentItem && typeof item.contentItem.selectAll === "function"
                    ? item.contentItem : item)
            mouseClick(editor)
            if (!item.activeFocus && !editor.activeFocus)
                console.log("INPUT_DEBUG focus " + name + " " + inputGeometry(item))
            verify(item.activeFocus || editor.activeFocus,
                   name + " não recebeu o foco do clique: " + inputGeometry(item))
            editor.selectAll()
            for (let i = 0; i < text.length; i++)
                keyClick(text.charAt(i))
            keyClick(Qt.Key_Return)
        }

        function typeNumber(name, value) {
            const spin = find(panel, name)
            verify(spin !== null, "controle numérico ausente: " + name)
            assertTarget(spin, name)
            verify(spin.up !== undefined && spin.down !== undefined,
                   name + " não publicou incrementadores acessíveis")
            verify(spin.up.indicator !== null && spin.down.indicator !== null,
                   name + " não publicou áreas visíveis dos incrementadores")
            assertTarget(spin.up.indicator, name + " incrementar")
            assertTarget(spin.down.indicator, name + " decrementar")
            const text = Number(value).toLocaleString(spin.locale, "f", spin.rangeDecimals)
            typeInto(name, text)
        }

        function stepNumber(name, increase) {
            const spin = find(panel, name)
            verify(spin !== null, "controle numérico ausente: " + name)
            const button = increase ? spin.up.indicator : spin.down.indicator
            assertTarget(button, name + (increase ? " incrementar" : " decrementar"))
            reveal(button)
            verify(fullyInsideViewport(button), name + " incrementador fora da viewport: "
                   + inputGeometry(button))
            const before = spin.value
            const x = increase ? spin.width - button.width / 2 : button.width / 2
            mouseClick(spin, x, button.height / 2)
            tryVerify(function() {
                return spin.value === before + (increase ? spin.stepSize : -spin.stepSize)
            }, 3000, name + " não respondeu ao incremento/decremento")
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

        function captureItem(name, item) {
            if (!cfg.captureDir)
                return
            let done = false
            const popupItem = item.contentItem ? item.contentItem.parent : null
            const target = popupItem && typeof popupItem.grabToImage === "function"
                ? popupItem : (item.contentItem || item)
            target.grabToImage(function(result) {
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
            harness.refreshRuntimeTheme()
            // O primeiro snapshot real agrega o catálogo do dashboard e pode
            // levar mais de cinco segundos no cold path do backend de teste.
            tryVerify(function() { return harness.runtimeThemeRefreshed }, 10000,
                      "o refresh inicial do dashboard não respondeu: "
                      + JSON.stringify(harness.errors))
            tryVerify(function() {
                return runtimeBridge.active && runtimeBridge.themeId === "org.steamzero.default"
            }, 5000, "a AURA UI não publicou o tema runtime atual: bridge="
                + runtimeBridge.themeId + " active=" + runtimeBridge.active
                + " activeId=" + harness.runtimeTheme.activeId
                + " resolved=" + (harness.runtimeTheme.resolved
                    ? harness.runtimeTheme.resolved.themeId : "<missing>")
                + " errors=" + JSON.stringify(harness.errors))
            harness.runtimeVisible = true
            tryVerify(function() {
                const media = harness.findRuntimeMedia(runtimeLibrary)
                return media !== null && media.sourceStatus === Image.Ready
            }, 5000, "a biblioteca runtime não decodificou o fixture licenciado")
            const initialRuntimeMedia = harness.findRuntimeMedia(runtimeLibrary)
            verify(!initialRuntimeMedia.vignetteActive,
                   "o stack focado padrão deve servir como baseline sem vinheta")
            harness.captureRuntimeMedia("05-theme-runtime-baseline.png")
            tryVerify(function() { return harness.runtimeCaptureComplete }, 5000,
                      "captura do renderer runtime não concluiu")
            verify(harness.runtimeCaptureSucceeded, "não foi possível guardar o pixel baseline")
            harness.runtimeVisible = false

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
            stepNumber("effectParam_" + last + "_radius", true)
            tryVerify(function() { return effects("focusedCover")[last].radius === 25 }, 3000,
                      "o botão de incremento não chegou ao documento")
            stepNumber("effectParam_" + last + "_radius", false)
            tryVerify(function() { return effects("focusedCover")[last].radius === 24 }, 3000,
                      "o botão de decremento não restaurou o documento")
            chooseCombo("effectTypeToAdd", "vignette")
            click("effectAdd")
            tryVerify(function() { return effects("focusedCover").length === baseEffects + 2 }, 3000)
            typeInto("effectParam_" + (baseEffects + 1) + "_strength", "0.9")
            tryVerify(function() {
                return effects("focusedCover")[baseEffects + 1].strength === 0.9
            }, 3000, "o parâmetro da vinheta não chegou ao documento")
            click("effectUp_" + (baseEffects + 1))
            tryVerify(function() { return effects("focusedCover")[baseEffects + 1].radius === 24 }, 3000,
                      "mover para cima não reordenou o documento")
            chooseCombo("effectFallback_" + baseEffects, "minimal")
            tryVerify(function() {
                return effects("focusedCover")[baseEffects].fallback === "minimal"
            }, 3000, "o fallback fechado não chegou ao documento")

            // cor por seletor AURA: input Qt no hexadecimal e confirmação explícita.
            chooseCombo("effectTypeToAdd", "shadow")
            click("effectAdd")
            const shadowIndex = baseEffects + 2
            tryVerify(function() { return effects("focusedCover").length === baseEffects + 3 }, 3000)
            click("effectColorOpen_" + shadowIndex + "_color")
            tryVerify(function() {
                return panel.effectColorDialogControl !== null
                    && panel.effectColorDialogControl.visible
            }, 3000, "o seletor AURA de cor não abriu")
            captureItem("08-studio-seletor-cor", panel.effectColorDialogControl)
            typeInto("themeColorPickerHex", "#336699")
            click("themeColorPickerApply")
            tryVerify(function() {
                return effects("focusedCover")[shadowIndex].color === "#336699"
            }, 3000, "a cor escolhida não chegou ao documento")
            tryVerify(function() { return panel.effectColorDialogControl === null }, 3000,
                      "o seletor não fechou após aplicar")

            // rejeição do domínio: valor, declaração e histórico ficam intactos.
            const invalidColorDepth = panel.editorHistory.undoDepth
            typeInto("effectColorHex_" + shadowIndex + "_color", "#zz0000")
            tryVerify(function() { return panel.authoringNotice !== "" }, 3000,
                      "o domínio não explicou a cor inválida")
            verify(panel.authoringNotice.indexOf("cor") >= 0,
                   "a mensagem da cor não identifica o campo recusado")
            compare(panel.editorHistory.undoDepth, invalidColorDepth,
                    "cor recusada alterou o histórico")
            compare(panel.effectStackName, "focusedCover", "cor recusada alterou a seleção da pilha")
            compare(effects("focusedCover")[shadowIndex].color, "#336699",
                    "cor recusada alterou o documento")
            compare(harness.errors.length, 1,
                    "a cor inválida deve produzir exatamente um erro de domínio")
            click("effectRemove_" + shadowIndex)
            tryVerify(function() { return effects("focusedCover").length === baseEffects + 2 }, 3000,
                      "remover efeito não atualizou a pilha")
            tryVerify(function() { return find(panel, "effectParam_" + baseEffects + "_strength") !== null },
                      3000, "parâmetro da vinheta não apareceu para a captura")
            reveal(find(panel, "effectParam_" + baseEffects + "_strength"))
            capture("09-studio-vinheta-editada")

            // operação inválida: documento e histórico preservados, erro acionável
            const depth = panel.editorHistory.undoDepth
            typeNumber("effectParam_" + (baseEffects + 1) + "_radius", 9999)
            tryVerify(function() {
                return panel.authoringNotice.indexOf("0") >= 0
                    && panel.authoringNotice.indexOf("64") >= 0
            }, 3000, "a mensagem de limite do efeito não ficou visível")
            compare(panel.editorHistory.undoDepth, depth, "edição inválida alterou o histórico")
            compare(panel.effectStackName, "focusedCover", "entrada inválida alterou a seleção da pilha")
            compare(effects("focusedCover")[baseEffects + 1].radius, 24, "edição inválida alterou o documento")
            tryCompare(find(panel, "effectParam_" + (baseEffects + 1) + "_radius"), "displayText", "24", 3000,
                       "o campo continuou exibindo o valor recusado")

            // movimento: keyframe, timeline, clip (sem depender de Undo para atualizar a tela)
            chooseCombo("motionStateName", "loading")
            typeNumber("keyframe_scale", 1.2)
            tryVerify(function() {
                const st = ((panel.editorDeclared.sceneMotion || {}).states || {}).loading
                return st !== undefined && st.scale === 1.2
            }, 3000, "o estado loading/keyframe editado não chegou ao documento")
            chooseCombo("motionStateName", "focused")

            typeInto("motionTimelineName", "rascunho")
            chooseCombo("motionTimelineKind", "parallel")
            click("motionTimelineAdd")
            tryVerify(function() {
                const tl = ((panel.editorDeclared.sceneMotion || {}).timelines || {}).rascunho
                return tl !== undefined && tl.kind === "parallel"
            }, 3000, "a timeline paralela não chegou ao documento")
            click("motionTimelineRemove")
            tryVerify(function() {
                return !(((panel.editorDeclared.sceneMotion || {}).timelines || {}).rascunho)
            }, 3000, "remover timeline não atualizou o documento")

            typeInto("motionTimelineName", "entrada")
            chooseCombo("motionTimelineKind", "parallel")
            click("motionTimelineAdd")
            tryVerify(function() { return find(panel, "motionClipDuration_0") !== null }, 3000,
                      "a timeline criada não apareceu no modelo")
            chooseCombo("motionTimelineKind", "sequence")
            tryVerify(function() {
                const tl = ((panel.editorDeclared.sceneMotion || {}).timelines || {}).entrada
                return tl !== undefined && tl.kind === "sequence"
            }, 3000, "editar o tipo da timeline não atualizou o documento")
            typeNumber("motionTimelineRepeat", 2)
            tryVerify(function() {
                return ((panel.editorDeclared.sceneMotion || {}).timelines || {}).entrada.repeat === 2
            }, 3000, "o limite de repetições editado não chegou ao documento")

            click("motionClipAdd")
            tryVerify(function() { return find(panel, "motionClipDuration_1") !== null }, 3000,
                      "o primeiro clip não apareceu no inspetor")
            chooseCombo("motionClipState_1", "loading")
            typeNumber("motionClipDuration_1", 300)
            click("motionClipAdd")
            tryVerify(function() { return find(panel, "motionClipDuration_2") !== null }, 3000,
                      "o segundo clip não apareceu no inspetor")
            tryVerify(function() {
                const tl = ((panel.editorDeclared.sceneMotion || {}).timelines || {}).entrada
                return tl !== undefined && tl.clips.length === 3 && tl.clips[1].duration === 300
                    && tl.clips[1].state === "loading"
            }, 3000, "o inspetor não atualizou estado e duração do clip")
            click("motionClipUp_2")
            tryVerify(function() {
                const clips = ((panel.editorDeclared.sceneMotion || {}).timelines || {}).entrada.clips
                return clips[1].duration === 240 && clips[2].state === "loading"
            }, 3000, "mover clip para cima não reordenou a timeline")
            click("motionClipDown_1")
            tryVerify(function() {
                const clips = ((panel.editorDeclared.sceneMotion || {}).timelines || {}).entrada.clips
                return clips[1].state === "loading" && clips[1].duration === 300
            }, 3000, "mover clip para baixo não restaurou a ordem")

            const motionDepth = panel.editorHistory.undoDepth
            typeNumber("motionClipDuration_1", 9999)
            tryVerify(function() {
                return panel.authoringNotice.indexOf("0") >= 0
                    && panel.authoringNotice.indexOf("2000") >= 0
            }, 3000, "a duração fora do limite não explicou a recusa")
            compare(panel.editorHistory.undoDepth, motionDepth,
                    "duração recusada alterou o histórico")
            compare(panel.motionTimelineName, "entrada", "duração recusada alterou a timeline selecionada")
            compare(panel.motionStateName, "focused", "duração recusada alterou o estado selecionado")
            tryVerify(function() {
                const clips = ((panel.editorDeclared.sceneMotion || {}).timelines || {}).entrada.clips
                return clips[1].duration === 300
            }, 3000, "duração inválida alterou o documento")
            tryCompare(find(panel, "motionClipDuration_1"), "displayText", "300", 3000,
                       "duração inválida permaneceu no controle")
            click("motionClipRemove_2")
            tryVerify(function() {
                return ((panel.editorDeclared.sceneMotion || {}).timelines || {}).entrada.clips.length === 2
            }, 3000, "remover clip não atualizou a timeline")

            // undo/redo pelos botões
            const beforeUndo = JSON.stringify(panel.editorDeclared)
            click("themeEditorUndo")
            tryVerify(function() { return JSON.stringify(panel.editorDeclared) !== beforeUndo }, 3000)
            click("themeEditorRedo")
            tryVerify(function() { return JSON.stringify(panel.editorDeclared) === beforeUndo }, 3000,
                      "refazer não restaurou o documento")

            chooseCombo("motionStateName", "loading")
            capture("01-studio-efeitos-movimento")

            // salvar, fechar e reabrir
            themeId = panel.editorManifest.id
            click("themeEditorSave")
            tryCompare(panel, "editorDirty", false, 5000)
            const saved = JSON.stringify(panel.editorDeclared)
            click("themeEditorClose")
            compare(panel.editorSessionId, "")
            tryVerify(function() { return find(panel, "themeEditButton_" + themeId) !== null },
                      5000, "o tema salvo não entrou no catálogo do Studio")
            click("themeEditButton_" + themeId)
            tryVerify(function() { return panel.editorSessionId !== "" }, 5000, "reabrir falhou: " + themeId + " " + JSON.stringify(harness.errors))
            compare(JSON.stringify(panel.editorDeclared), saved, "o tema reaberto difere do salvo")
            click("themeEditorClose")
            tryVerify(function() { return panel.editorSessionId === "" }, 3000,
                      "o editor não fechou antes da aplicação runtime")

            // Aplicação explícita pela UI à central; o renderer usado é o da
            // biblioteca editorial real, alimentado pela bridge publicada em /status.
            click("themeApplyButton_" + themeId)
            tryVerify(function() { return panel.applyPlan !== null }, 5000,
                      "a confirmação de aplicação não abriu")
            click("themeApplyConfirm")
            tryVerify(function() { return panel.applyPlan === null }, 5000,
                      "a aplicação do tema não concluiu")
            harness.refreshRuntimeTheme()
            tryVerify(function() { return harness.runtimeThemeRefreshed }, 10000,
                      "o refresh do dashboard não respondeu: " + JSON.stringify(harness.errors))
            tryVerify(function() {
                return runtimeBridge.active && runtimeBridge.themeId === themeId
            }, 5000, "o dashboard runtime não publicou o tema aplicado: bridge="
                + runtimeBridge.themeId + " theme=" + JSON.stringify(harness.runtimeTheme)
                + " errors=" + JSON.stringify(harness.errors))
            verify(panel.isActiveTheme(themeId), "o catálogo não marcou o tema em uso")
            harness.runtimeVisible = true
            tryVerify(function() {
                const media = harness.findRuntimeMedia(runtimeLibrary)
                return media !== null && media.sourceStatus === Image.Ready
                    && media.vignetteActive
            }, 5000, "EditorialLibrary/MediaEffectLayer não consumiu o efeito salvo")
            const appliedMedia = harness.findRuntimeMedia(runtimeLibrary)
            compare(appliedMedia.vignetteEffect.strength, 0.9,
                    "o renderer não recebeu o valor persistido da vinheta")
            harness.captureRuntimeMedia("06-theme-runtime-aplicado.png")
            tryVerify(function() { return harness.runtimeCaptureComplete }, 5000,
                      "captura do tema aplicado não concluiu")
            verify(harness.runtimeCaptureSucceeded, "não foi possível guardar a captura runtime")
            harness.captureRuntimeSurface("07-aura-library-theme-applied.png")
            tryVerify(function() { return harness.runtimeCaptureComplete }, 5000,
                      "captura da biblioteca editorial não concluiu")
            verify(harness.runtimeCaptureSucceeded, "não foi possível guardar a captura da superfície")
            harness.runtimeVisible = false
            compare(harness.errors.length, 1,
                    "só a cor inválida proposital podia falhar: " + JSON.stringify(harness.errors))
            console.log("THEME_ID=" + themeId)
            console.log("THEME_RUNTIME_APPLIED=" + runtimeBridge.themeId)
        }

        function test_02_viewport_compacto_alcanca_os_inspetores() {
            harness.cfg = readConfig()
            panel.compactLayout = true
            harness.width = 640
            harness.height = 560
            panel._closeEditor()
            panel.visualScale = 1.5
            panel.duplicateAndEdit("org.steamzero.default", "Compacto V4")
            tryVerify(function() { return panel.editorSessionId !== "" }, 5000)
            const base = effects("focusedCover").length
            // No compacto o painel direito some; os inspetores precisam seguir alcançáveis por rolagem.
            chooseCombo("effectTypeToAdd", "blur")
            click("effectAdd")
            tryVerify(function() { return effects("focusedCover").length === base + 1 }, 3000,
                      "inspetor de efeitos inalcançável no viewport compacto")
            tryVerify(function() { return find(panel, "effectParam_" + base + "_radius") !== null },
                      3000, "parâmetro do efeito compacto não apareceu")
            reveal(find(panel, "effectParam_" + base + "_radius"))
            capture("02-studio-compacto")
            typeInto("motionTimelineName", "compacta")
            click("motionTimelineAdd")
            tryVerify(function() { return find(panel, "motionClipDuration_0") !== null }, 3000)
            reveal(find(panel, "motionClipAdd"))
            verify(fullyInsideViewport(find(panel, "motionClipAdd")),
                   "Adicionar clip não cabe no viewport compacto: "
                   + inputGeometry(find(panel, "motionClipAdd")))
            click("motionClipAdd")
            tryVerify(function() { return find(panel, "motionClipDuration_1") !== null }, 3000, "clip: " + JSON.stringify(harness.errors) + " tl=" + panel.motionTimelineName + " " + JSON.stringify((panel.editorDeclared.sceneMotion || {}).timelines))
            reveal(find(panel, "motionClipDuration_1"))
            capture("04-studio-compact-movimento")
            panel._closeEditor()
            panel.visualScale = 1.0
        }

        function test_03_binding_de_layout_pelos_controles() {
            harness.cfg = readConfig()
            panel.visualScale = 1.0
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

        function test_04_abre_jornadas_pelo_studio_e_retorna_com_bridge_ausente() {
            harness.runtimeVisible = false
            harness.width = 1100
            harness.height = 900
            panel._closeEditor()
            panel.journeyMode = false
            panel.compactLayout = false
            panel.visualScale = 1.0
            panel.requestAction = function(actionId, payload, callback, errorCallback) {
                if (String(actionId).indexOf("journey.studio.") === 0)
                    return false
                return harness.requestAction(actionId, payload, callback, errorCallback)
            }

            const openButton = find(panel, "openExperienceJourneys")
            verify(openButton !== null && openButton.visible)
            verify(openButton.height >= 48, "a entrada de Jornadas precisa ter alvo de 48 px")
            mouseClick(openButton)

            const journeyPanel = panel.journeyPanelControl
            tryVerify(function() { return panel.journeyMode && journeyPanel.visible }, 3000)
            tryVerify(function() {
                return journeyPanel.notice.indexOf("ações de Jornada não estão disponíveis") >= 0
            }, 3000, "a ausência da bridge precisa explicar por que a edição está desativada")
            const createButton = find(journeyPanel, "journeyCreate")
            verify(createButton !== null && !createButton.enabled)

            const closeButton = find(journeyPanel, "journeyClose")
            verify(closeButton !== null && closeButton.height >= 48)
            mouseClick(closeButton)
            tryVerify(function() { return !panel.journeyMode && !journeyPanel.visible }, 3000)
            verify(openButton.visible, "voltar às Jornadas deve conservar a rota do Studio")
        }

        function cleanupTestCase() {
            console.log("TARGET_DIMENSIONS=" + JSON.stringify(targetMeasurements))
        }
    }
}
