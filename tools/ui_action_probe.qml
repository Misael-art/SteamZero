// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Sonda comportamental do despacho da central: para cada ação que os read
// models publicam, pergunta ao próprio shell o que acontece ao clicar.
//
// Não é captura de tela nem gate de layout. É a prova de que nenhum botão
// habilitado termina em silêncio — o defeito P0-4 da auditoria de 2026-08-11,
// em que "Instalar" estava enabled e não chamava nada.
//
// Roda offline de propósito: sem bridge, toda ação roteada morre na checagem de
// contrato de requestAction e registra qual contrato tentou alcançar. É isso que
// distingue "roteada" de "sem rota" sem tocar no host.
//
// Uso: qml6 tools/ui_action_probe.qml -- --steamzero-actions /caminho/acoes.json

import QtQuick
import "../src/steamzero/ui/qml"

Main {
    id: window
    visible: false
    width: 1600
    height: 1000

    property var probeActions: []
    property int probeIndex: 0
    property int pendingExitCode: 0

    function argumentValue(name) {
        const args = Qt.application.arguments
        const marker = args.indexOf(name)
        if (marker >= 0 && marker + 1 < args.length)
            return args[marker + 1]
        return ""
    }

    function loadActions(path) {
        const request = new XMLHttpRequest()
        request.open("GET", "file://" + path, false)
        request.send(null)
        return JSON.parse(request.responseText)
    }

    // O contrato que a ação tentou alcançar fica no job de falha que
    // recordActionFailure empilha. Offline, é a assinatura de "roteada".
    function attemptedContract() {
        if (!liveTasks || liveTasks.length === 0)
            return ""
        const task = liveTasks[0]
        if (!task || !task.result)
            return ""
        return String(task.result.actionId || "")
    }

    // Efeito observável que não passa pelo backend: navegar, abrir um overlay.
    // Sem medir isto, uma ação de navegação legítima seria acusada de no-op.
    function observableState() {
        return JSON.stringify({
            "section": sectionIndex,
            "steamArea": steamArea,
            "emulationPlatform": emulationControl ? emulationControl.platformIndex : -1,
            "emulationGlobal": emulationControl ? emulationControl.globalManagementActive : true,
            "credentialDialog": credentialDialogControl
                ? credentialDialogControl.visible : false
        })
    }

    function verdictFor(action, attempted, message, changed) {
        // Desabilitada é decisão de produto, não defeito — desde que explique.
        if (action.enabled !== true)
            return message === "" ? "blocked-silent" : "blocked-explained"
        if (attempted !== "")
            return "routed"
        if (message.indexOf("não reconhecida") >= 0 || message.indexOf("não tem rota") >= 0)
            return "unrouted"
        if (changed)
            return "handled-locally"
        if (message === "")
            return "silent-no-op"
        return "handled-locally"
    }

    function probeOne(entry) {
        lastRequest = ""
        lastRequestIsError = false
        liveTasks = []

        const action = entry.action
        const before = observableState()
        if (entry.dispatch === "emulation")
            performEmulationAction(action)
        else
            performRowAction({"id": entry.rowId || "probe", "name": entry.rowName || "Probe",
                              "action": action})

        const attempted = attemptedContract()
        const message = String(lastRequest || "")
        const changed = observableState() !== before
        console.log("PROBE " + JSON.stringify({
            "surface": entry.surface || "",
            "actionId": action.id || "",
            "actionKind": action.kind || "",
            "label": action.label || "",
            "enabled": action.enabled === true,
            "declaredReason": action.reason || "",
            "attemptedContract": attempted,
            "message": message,
            "isError": lastRequestIsError === true,
            "changedState": changed,
            "verdict": verdictFor(action, attempted, message, changed)
        }))
    }

    function runProbe() {
        for (let i = 0; i < probeActions.length; i++)
            probeOne(probeActions[i])
        console.log("PROBE-DONE count=" + probeActions.length)
        requestExit(0)
    }

    // Sair pelo event loop, nunca de dentro de um callback do runtime.
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

    Component.onCompleted: {
        const path = argumentValue("--steamzero-actions")
        if (path === "") {
            console.error("PROBE-FAIL --steamzero-actions é obrigatório")
            requestExit(2)
            return
        }
        probeActions = loadActions(path)
        Qt.callLater(runProbe)
    }
}
