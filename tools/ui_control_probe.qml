// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Inventário de controles da central: percorre a árvore de objetos viva de cada
// superfície e registra TODO elemento interativo — não apenas os `.action` que
// os read models publicam.
//
// A sonda anterior (ui_action_probe.qml) despachava payloads. Ela não via
// Button estático, ToolButton, aba, combobox, slider, delegate clicável nem
// botão de diálogo, porque nenhum deles nasce de um payload. Um botão desses
// pode estar morto sem que nenhuma matriz de ações perceba.
//
// Esta sonda roda offscreen e offline. Ela ENUMERA; a ativação e a observação
// de efeito ficam na fase seguinte, para que a contagem de controles não
// dependa de nenhum clique ter dado certo.
//
// Uso: qml6 tools/ui_control_probe.qml -- --steamzero-out /caminho/saida.json

import QtQuick
import QtQuick.Controls
import "../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 1600
    height: 1000

    property string outPath: ""
    property var collected: []
    property int pendingExitCode: 0
    property int sectionCursor: 0

    // Espera por condição, nunca por tempo arbitrário. Se a condição não
    // acontecer dentro do orçamento de quadros, a sonda REPROVA — aumentar o
    // orçamento para pintar de verde seria esconder o defeito que ela procura.
    property var _waitCondition: null
    property var _waitThen: null
    property string _waitLabel: ""
    property int _waitFrames: 0
    readonly property int maxWaitFrames: 180

    function waitFor(label, condition, then) {
        _waitLabel = label
        _waitCondition = condition
        _waitThen = then
        _waitFrames = 0
        waitTimer.restart()
    }

    Timer {
        id: waitTimer
        interval: 16
        repeat: true
        onTriggered: {
            if (window._waitCondition()) {
                stop()
                const then = window._waitThen
                window._waitThen = null
                then()
                return
            }
            window._waitFrames += 1
            if (window._waitFrames >= window.maxWaitFrames) {
                stop()
                console.error("PROBE-FAIL condição nunca satisfeita: " + window._waitLabel)
                window.requestExit(3)
            }
        }
    }

    function requestExit(code) {
        pendingExitCode = code
        exitTimer.restart()
    }

    Timer {
        id: exitTimer
        interval: 0
        repeat: false
        onTriggered: Qt.exit(window.pendingExitCode)
    }

    function argumentValue(name) {
        const args = Qt.application.arguments
        const marker = args.indexOf(name)
        return (marker >= 0 && marker + 1 < args.length) ? args[marker + 1] : ""
    }

    // Índice da seção a que o controle pertence, para restaurar o shell entre
    // ativações. Superfícies transversais (sidebar, drawers) devolvem a seção
    // corrente: elas não pertencem a nenhuma.
    function sectionIndexFor(surface) {
        for (let i = 0; i < navigationSections.length; i++) {
            if (navigationSections[i].id === surface)
                return i
        }
        return 0
    }

    // Duck typing em vez de instanceof: o tipo concreto vem do estilo (Breeze),
    // então checar a classe amarraria o inventário ao tema do host.
    function controlKind(item) {
        if (item.from !== undefined && item.to !== undefined && item.value !== undefined
                && item.stepSize !== undefined)
            return "slider"
        if (item.currentIndex !== undefined && item.model !== undefined
                && item.displayText !== undefined)
            return "combobox"
        if (item.checkable === true)
            return "toggle"
        if (item.clicked !== undefined && typeof item.clicked.connect === "function")
            return "button"
        if (item.tapped !== undefined && typeof item.tapped.connect === "function")
            return "tap"
        return ""
    }

    // Estado observável da central. Um clique que não move nada disto e não
    // notifica nada é, por definição, um botão que não faz nada.
    function observableState() {
        return JSON.stringify({
            "section": sectionIndex,
            "steamArea": steamArea,
            "request": lastRequest,
            "requestError": lastRequestIsError,
            "jobs": liveTasks ? liveTasks.length : -1,
            "emulationPlatform": emulationControl ? emulationControl.platformIndex : -1,
            "emulationGlobal": emulationControl ? emulationControl.globalManagementActive : true,
            "emulationArea": emulationControl ? emulationControl.areaIndex : -1,
            "libraryView": editorialLibraryControl ? editorialLibraryControl.view : "",
            "libraryMode": editorialLibraryControl ? editorialLibraryControl.libraryView : "",
            "librarySelected": editorialLibraryControl ? editorialLibraryControl.selectedIndex : -1,
            "librarySystem": editorialLibraryControl
                ? editorialLibraryControl.selectedSystemIndex : -1,
            "drawer": responsiveDrawer ? responsiveDrawer.visible : false,
            "taskDrawer": responsiveTaskDrawer ? responsiveTaskDrawer.visible : false,
            "credentials": credentialDialogControl ? credentialDialogControl.visible : false,
            "focus": activeFocusItem ? String(activeFocusItem) : "",
            // Diálogos e drawers vivem no overlay, fora da árvore da seção.
            // Sem contá-los, todo botão que abre modal parecia não fazer nada.
            "popups": overlaySignature()
        })
    }

    function overlaySignature() {
        const layer = Overlay.overlay
        if (!layer || !layer.children)
            return "sem-overlay"
        let open = 0
        for (let i = 0; i < layer.children.length; i++) {
            if (layer.children[i] && layer.children[i].visible === true)
                open += 1
        }
        return layer.children.length + "/" + open
    }

    // Assinatura da própria árvore de controles. Observar só propriedades
    // nomeadas do shell não bastou: abas, presets de FPS, cards de perfil e
    // disclosures mudam estado LOCAL que nenhuma lista fixa de propriedades
    // alcança, e a sonda os acusava de no-op. Comparar a árvore inteira pega
    // qualquer mudança de habilitado, visibilidade, marcação ou rótulo —
    // inclusive as que ainda não existem.
    function treeSignature(root) {
        const parts = []
        signatureWalk(root, parts, 0)
        return parts.join("|")
    }

    function signatureWalk(item, parts, depth) {
        if (!item || depth > 40)
            return
        if (controlKind(item) !== "") {
            parts.push((item.enabled === true ? "1" : "0")
                + (item.visible === true ? "1" : "0")
                + (item.checked === true ? "1" : "0")
                + (item.currentIndex !== undefined ? String(item.currentIndex) : "")
                + (item.value !== undefined ? String(item.value) : "")
                + String(item.text || ""))
        }
        const kids = item.children
        if (!kids)
            return
        for (let i = 0; i < kids.length; i++)
            signatureWalk(kids[i], parts, depth + 1)
    }

    function fullState(sectionIdx) {
        const page = responsiveContent.children[sectionIdx]
        return observableState() + "##" + treeSignature(page)
            + "##" + treeSignature(responsiveShell)
    }

    // Nome do tipo QML sem o endereco: "Button_QMLTYPE_42(0x55f...)" vira
    // "Button". O endereco muda a cada execucao e nao serve como identidade.
    function typeNameOf(item) {
        const raw = String(item)
        const cut = raw.indexOf("_QMLTYPE_")
        let base = cut >= 0 ? raw.slice(0, cut) : raw.split("(")[0]
        // Componentes do proprio produto vem como "EditorialButton_QML_148":
        // o numero e um contador de revisao do engine e muda entre execucoes.
        base = base.replace(/_QML_\d+$/, "")
        return base.replace(/^QQuick/, "")
    }

    // Identidade estavel do controle. Coordenada visual nao entra: ela muda com
    // viewport, escala e tema, e a matriz precisa casar o mesmo botao entre
    // cenarios diferentes. O que entra e superficie + tipo + objectName + rotulo
    // ou nome acessivel + posicao ESTRUTURAL na arvore (cadeia de indices).
    function controlIdentity(record) {
        return [record.surface, record.type, record.objectName,
                record.label || record.accessibleName, record.path].join("|")
    }

    function describe(item, kind, surface) {
        let label = ""
        if (item.text !== undefined && item.text !== null)
            label = String(item.text)
        if (label === "" && item.displayText !== undefined)
            label = String(item.displayText)
        let accessible = ""
        try {
            accessible = String(item.Accessible.name || "")
        } catch (e) {
            accessible = ""
        }
        let description = ""
        try {
            description = String(item.Accessible.description || "")
        } catch (e) {
            description = ""
        }
        return {
            "surface": surface,
            "kind": kind,
            "type": typeNameOf(item),
            "path": "",
            "controlId": "",
            "objectName": String(item.objectName || ""),
            "label": label,
            "accessibleName": accessible,
            "accessibleDescription": description,
            "enabled": item.enabled === true,
            "visible": item.visible === true,
            "width": Math.round(item.width || 0),
            "height": Math.round(item.height || 0)
        }
    }

    // Percorre filhos visuais. Popups (diálogos, drawers) não estão aqui
    // enquanto fechados; são visitados à parte, abertos de propósito.
    function walk(item, surface, out, depth, path) {
        if (!item || depth > 40)
            return
        const kind = controlKind(item)
        if (kind !== "") {
            const record = describe(item, kind, surface)
            record.item = item
            record.path = path
            record.sectionIndex = sectionIndexFor(surface)
            record.controlId = controlIdentity(record)
            out.push(record)
        }
        const kids = item.children
        if (!kids)
            return
        for (let i = 0; i < kids.length; i++)
            walk(kids[i], surface, out, depth + 1, path + "/" + i)
    }

    // ---- Ativação -----------------------------------------------------------
    //
    // Só controles habilitados E visíveis são acionados: um botão invisível não
    // é uma promessa ao usuário. Os demais ficam registrados como `not-probed`
    // com o motivo, para que a matriz não finja tê-los verificado.

    property var activationQueue: []
    property int activationCursor: 0

    // O produto usa ToolButton desabilitado como ICONE: sem texto, sem nome
    // acessivel, fundo vazio. Isso e decoracao, nao promessa ao usuario, e
    // exigir dele um "motivo" produziria 35 acusacoes falsas. So e cobrado
    // quem se apresenta como acionavel — quem tem rotulo ou nome acessivel.
    function isPromise(record) {
        return record.label !== "" || record.accessibleName !== ""
    }

    function isActivatable(record) {
        return record.enabled && record.visible && record.kind !== "slider"
            && record.kind !== "combobox"
    }

    function activate(record) {
        const item = record.item
        if (record.kind === "toggle" && item.toggle !== undefined) {
            item.toggle()
            return true
        }
        if (item.clicked !== undefined && typeof item.clicked === "function") {
            item.clicked()
            return true
        }
        return false
    }

    // Restaura o shell entre ativações. Sem isto, um clique que navega
    // contaminaria o veredito de todos os controles seguintes.
    function restoreShell(sectionIdx) {
        if (responsiveDrawer && responsiveDrawer.visible)
            responsiveDrawer.close()
        if (responsiveTaskDrawer && responsiveTaskDrawer.visible)
            responsiveTaskDrawer.close()
        if (credentialDialogControl && credentialDialogControl.visible)
            credentialDialogControl.close()
        // Restaurar so a secao nao basta. Um card de sistema poe a biblioteca
        // em view="system" e a deixa la: do segundo clique em diante o estado
        // "antes" ja era o estado "depois", e 37 cards viraram falso no-op.
        if (editorialLibraryControl) {
            editorialLibraryControl.view = "systems"
            editorialLibraryControl.libraryView = "carousel"
            editorialLibraryControl.selectedSystemIndex = 0
            editorialLibraryControl.selectedIndex = 0
            editorialLibraryControl.systemFilter = "all"
            editorialLibraryControl.collectionFilter = ""
        }
        if (emulationControl) {
            emulationControl.globalManagementActive = true
            emulationControl.platformIndex = 0
            emulationControl.areaIndex = 0
            emulationControl.gameDetailsOpen = false
        }
        steamArea = "performance"
        sectionIndex = sectionIdx
        lastRequest = ""
        lastRequestIsError = false
        liveTasks = []
    }

    // Controles cujo efeito é um diálogo NATIVO do sistema (FileDialog). Sob
    // QT_QPA_PLATFORM=offscreen não existe seletor de arquivo, então a ausência
    // de efeito é limitação da bancada e não do produto. Fica `not-probed` com
    // o motivo, em vez de virar acusação falsa.
    readonly property var nativeDialogLabels: ["Pacote de suporte", "Exportar estado",
        "Salvar estado", "Exportar"]

    function opensNativeDialog(record) {
        for (let i = 0; i < nativeDialogLabels.length; i++) {
            if (record.label === nativeDialogLabels[i])
                return true
        }
        return false
    }

    function verdictFor(record, changed, message) {
        if (!record.enabled)
            return message === "" ? "blocked-silent" : "blocked-explained"
        if (record.attemptedContract !== "")
            return "routed"
        if (message.indexOf("não reconhecida") >= 0 || message.indexOf("não tem rota") >= 0)
            return "unrouted"
        if (!changed && message === "" && opensNativeDialog(record)) {
            record.probeNote = "abre FileDialog nativo; indisponível na plataforma offscreen"
            return "not-probed"
        }
        if (changed)
            return "handled-locally"
        if (message !== "")
            return "handled-locally"
        return "silent-no-op"
    }

    // O StackLayout mantém TODAS as seções instanciadas ao mesmo tempo: varrer
    // o shell inteiro por seção contava 283 controles nove vezes. Cada seção é
    // atribuída ao seu próprio item da pilha.
    function collectSection(sectionId, index) {
        const page = responsiveContent.children[index]
        const out = []
        walk(page, sectionId, out, 0, "")
        for (let i = 0; i < out.length; i++)
            collected.push(out[i])
        console.log("PROBE-SECTION " + JSON.stringify({
            "surface": sectionId,
            "controls": out.length,
            "enabled": out.filter(function(c) { return c.enabled && c.visible }).length
        }))
    }

    // A sidebar vive fora da pilha e serve todas as seções: é contada uma vez.
    function collectChrome() {
        const surfaces = [
            {"id": "sidebar", "root": responsiveNavigation ? responsiveNavigation.parent : null},
            {"id": "handheld-drawer", "root": responsiveDrawer},
            {"id": "task-drawer", "root": responsiveTaskDrawer}
        ]
        for (let s = 0; s < surfaces.length; s++) {
            const entry = surfaces[s]
            if (!entry.root)
                continue
            const out = []
            const base = entry.root.contentItem !== undefined && entry.root.contentItem
                ? entry.root.contentItem : entry.root
            walk(base, entry.id, out, 0, "")
            for (let i = 0; i < out.length; i++)
                collected.push(out[i])
            console.log("PROBE-SECTION " + JSON.stringify({
                "surface": entry.id,
                "controls": out.length,
                "enabled": out.filter(function(c) { return c.enabled }).length
            }))
        }
    }

    function nextSection() {
        if (sectionCursor >= navigationSections.length) {
            collectChrome()
            beginActivation()
            return
        }
        const section = navigationSections[sectionCursor]
        sectionIndex = sectionCursor
        // Espera o shell de fato trocar de seção antes de contar controles.
        waitFor("seção " + section.id + " ativa",
                function() { return window.sectionIndex === window.sectionCursor },
                function() {
                    window.collectSection(section.id, window.sectionCursor)
                    window.sectionCursor += 1
                    Qt.callLater(window.nextSection)
                })
    }

    // Espera até que o efeito apareça OU o orçamento de quadros se esgote.
    // Esgotar o orçamento não é erro do instrumento: é o resultado
    // "nenhum efeito observável", que reprova o controle. Por isso o orçamento
    // nunca é aumentado para obter verde.
    readonly property int effectBudgetFrames: 30

    function waitForEffect(before, sectionIdx, then) {
        let frames = 0
        effectTimer.tick = function() {
            if (window.fullState(sectionIdx) !== before) {
                effectTimer.stop()
                then(true)
                return
            }
            frames += 1
            if (frames >= window.effectBudgetFrames) {
                effectTimer.stop()
                then(false)
            }
        }
        effectTimer.restart()
    }

    Timer {
        id: effectTimer
        property var tick: null
        interval: 16
        repeat: true
        onTriggered: if (tick) tick()
    }

    function probeNextControl() {
        if (activationCursor >= activationQueue.length) {
            finish()
            return
        }
        const record = activationQueue[activationCursor]
        restoreShell(record.sectionIndex)
        const before = fullState(record.sectionIndex)
        const fired = activate(record)
        if (!fired) {
            record.verdict = "not-probed"
            record.probeNote = "sem sinal de ativação conhecido"
            activationCursor += 1
            Qt.callLater(probeNextControl)
            return
        }
        waitForEffect(before, record.sectionIndex, function(changed) {
            // Um controle pode legitimamente não mudar nada a partir de um
            // estado — o item de navegação da seção em que já estamos é o caso
            // óbvio. Antes de acusar no-op, tenta de outra posição.
            if (!changed && String(window.lastRequest || "") === "" && !record.retried) {
                record.retried = true
                record.sectionIndex = (record.sectionIndex + 4)
                    % window.navigationSections.length
                Qt.callLater(window.probeNextControl)
                return
            }
            const message = String(window.lastRequest || "")
            record.attemptedContract = (window.liveTasks && window.liveTasks.length > 0
                && window.liveTasks[0].result)
                ? String(window.liveTasks[0].result.actionId || "") : ""
            record.message = message
            record.changedState = changed
            record.verdict = window.verdictFor(record, changed, message)
            window.activationCursor += 1
            Qt.callLater(window.probeNextControl)
        })
    }

    function beginActivation() {
        for (let i = 0; i < collected.length; i++) {
            const record = collected[i]
            record.attemptedContract = ""
            record.message = ""
            record.changedState = false
            if (isActivatable(record)) {
                activationQueue.push(record)
            } else if (record.visible && !record.enabled && isPromise(record)) {
                // Desabilitado é decisão de produto, não pendência de sondagem.
                // Classificar como `not-probed` tornava o gate blocked-silent
                // incapaz de medir o que existe para medir: um controle apagado
                // que não diz por quê.
                const reason = record.accessibleDescription !== ""
                    ? record.accessibleDescription : record.probeReason || ""
                record.message = reason
                record.verdict = reason !== "" ? "blocked-explained" : "blocked-silent"
            } else {
                record.verdict = "not-probed"
                record.probeNote = !record.visible ? "invisível neste estado"
                    : !record.enabled ? "ícone decorativo (sem rótulo nem nome acessível)"
                    : "tipo " + record.kind + " exige gesto, não clique"
            }
        }
        console.log("PROBE-ACTIVATION queue=" + activationQueue.length
            + " skipped=" + (collected.length - activationQueue.length))
        Qt.callLater(probeNextControl)
    }

    // Uma linha por controle. Escrever o JSON inteiro por XHR devolvia arquivo
    // vazio; a linha marcada é o mesmo transporte que a sonda de ações já usa e
    // sobrevive ao redirecionamento de log do Qt.
    function finish() {
        console.log("PROBE-CONTEXT " + JSON.stringify({
            "scenario": scenarioName,
            "viewport": width + "x" + height,
            "themeId": _themeBridge.themeId,
            "highContrast": highContrast,
            "reducedMotion": reducedMotion,
            "dataOrigin": (apiUrl !== "" && apiToken !== "") ? "bridge-live" : "fallback-qml"
        }))
        for (let i = 0; i < collected.length; i++) {
            const record = collected[i]
            const copy = {"scenario": scenarioName}
            for (const key in record) {
                if (key !== "item")
                    copy[key] = record[key]
            }
            console.log("PROBE-CONTROL " + JSON.stringify(copy))
        }
        console.log("PROBE-DONE controls=" + collected.length)
        requestExit(0)
    }

    property string scenarioName: "offline"

    // Carrega um cenario determinista em desktopStatus. Sem isto, 215 dos 288
    // controles ficam invisiveis: sem bridge o shell cai nos fallbacks vazios,
    // e um controle invisivel nao e prova de nada.
    function loadScenario(path) {
        const request = new XMLHttpRequest()
        request.open("GET", "file://" + path, false)
        request.send(null)
        const fixture = JSON.parse(request.responseText)
        scenarioName = String(fixture.scenario || "desconhecido")
        if (fixture.status === null || fixture.status === undefined)
            return
        const payload = fixture.status
        if (fixture.dashboard)
            payload.dashboard = fixture.dashboard
        desktopStatus = payload
    }

    Component.onCompleted: {
        outPath = argumentValue("--steamzero-out")
        const scenario = argumentValue("--steamzero-scenario")
        if (scenario !== "")
            loadScenario(scenario)
        Qt.callLater(nextSection)
    }
}
