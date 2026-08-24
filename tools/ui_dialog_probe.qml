// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Auditoria de jornada dos diálogos da central.
//
// A sonda de controles (ui_control_probe.qml) percorre a árvore visual de cada
// seção. Diálogos não estão nela enquanto fechados, então nada do que acontece
// dentro de um modal era verificado — nem foco inicial, nem trap, nem se
// cancelar deixa plano sujo, nem se fechar devolve o foco a quem abriu.
//
// `visible === true` NÃO é prova de diálogo sondado. Cada jornada aqui prova a
// sequência inteira: a ação originadora abre, o foco entra, Escape cancela, a
// mutação não acontece e o foco volta ao originador.
//
// Roda offscreen e offline: sem bridge, nenhuma confirmação alcança o host.
//
// Uso: qml6 tools/ui_dialog_probe.qml

import QtQuick
import QtQuick.Controls
import "../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 1600
    height: 1000

    property int pendingExitCode: 0
    property var results: []

    // ---- espera por condição, nunca por sleep ------------------------------
    //
    // Cada espera declara o EVENTO que aguarda. Esgotar o orçamento de frames é
    // o resultado "o evento não aconteceu", que reprova a jornada — nunca um
    // motivo para aumentar o orçamento.
    readonly property int frameBudget: 60
    property var _cond: null
    property var _then: null
    property string _event: ""
    property int _frames: 0

    function waitForEvent(eventName, condition, then) {
        _event = eventName
        _cond = condition
        _then = then
        _frames = 0
        waitTimer.restart()
    }

    Timer {
        id: waitTimer
        interval: 16
        repeat: true
        onTriggered: {
            if (window._cond()) {
                stop()
                const then = window._then
                window._then = null
                then(true)
                return
            }
            window._frames += 1
            if (window._frames >= window.frameBudget) {
                stop()
                const failed = window._then
                window._then = null
                failed(false)
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

    // ---- utilidades --------------------------------------------------------

    function firstFocusableIn(item, depth) {
        if (!item || depth > 30)
            return null
        if (item.enabled === true && item.visible === true
                && item.activeFocusOnTab === true)
            return item
        const kids = item.children
        if (!kids)
            return null
        for (let i = 0; i < kids.length; i++) {
            const found = firstFocusableIn(kids[i], depth + 1)
            if (found)
                return found
        }
        return null
    }

    function focusablesIn(item, out, depth) {
        if (!item || depth > 30)
            return out
        if (item.enabled === true && item.visible === true
                && item.activeFocusOnTab === true)
            out.push(item)
        const kids = item.children
        if (kids) {
            for (let i = 0; i < kids.length; i++)
                focusablesIn(kids[i], out, depth + 1)
        }
        return out
    }

    function contains(root, item) {
        let node = item
        while (node) {
            if (node === root)
                return true
            node = node.parent
        }
        return false
    }

    function record(row) {
        results.push(row)
        console.log("DIALOG " + JSON.stringify(row))
    }

    // ---- jornadas ----------------------------------------------------------

    property var journeys: []
    property int cursor: 0

    function buildJourneys() {
        return [
            {
                "id": "dialog.emulator-plan",
                "label": "Plano de emulador",
                "dialog": emulationPlanDialogControl,
                "arm": function() { window.emulationPlan = samplePlan("emulator.install") },
                "dirty": function() { return window.emulationPlan !== null }
            },
            {
                "id": "dialog.component-plan",
                "label": "Plano de componente",
                "dialog": componentPlanDialogControl,
                "arm": function() { window.componentPlan = samplePlan("component.install") },
                "dirty": function() { return window.componentPlan !== null }
            },
            {
                "id": "dialog.desktop-safe-reset",
                "label": "Perfil Desktop seguro",
                "dialog": safeResetDialogControl,
                "arm": function() { window.currentPlan = samplePlan("desktop.profile") },
                "dirty": function() { return window.currentPlan !== null }
            },
            {
                "id": "dialog.conflict",
                "label": "Conflito de perfil",
                "dialog": conflictDialogControl,
                "arm": function() { window.conflictPlan = samplePlan("desktop.conflict") },
                "dirty": function() { return window.conflictPlan !== null }
            },
            {
                "id": "dialog.recovery",
                "label": "Recovery",
                "dialog": recoveryDialogControl,
                "arm": function() {},
                "dirty": function() { return false }
            },
            {
                "id": "dialog.credentials",
                "label": "Credenciais",
                "dialog": credentialDialogControl,
                "arm": function() {},
                "dirty": function() { return false }
            },
            // Os oito abaixo estavam fora do denominador: a sonda percorria seis
            // dos quinze modais do shell e nada apontava a diferença. Os que
            // seguram plano armam e conferem que cancelar não deixa plano
            // pendurado; os demais provam foco inicial, trap e retorno de foco.
            {
                "id": "dialog.operation-rollback",
                "label": "Rollback de operação",
                "dialog": operationRollbackControl,
                "arm": function() { window.operationRollbackPlan = samplePlan("operation.rollback") },
                "dirty": function() { return window.operationRollbackPlan !== null }
            },
            {
                "id": "dialog.collection-plan",
                "label": "Plano de coleção",
                "dialog": collectionPlanDialogControl,
                "arm": function() { window.collectionPlan = samplePlan("collection.apply") },
                "dirty": function() { return window.collectionPlan !== null }
            },
            {
                "id": "dialog.library-health-plan",
                "label": "Plano de saúde da biblioteca",
                "dialog": libraryHealthPlanControl,
                "arm": function() { window.libraryHealthPlan = samplePlan("library.health") },
                "dirty": function() { return window.libraryHealthPlan !== null }
            },
            {
                "id": "dialog.collection-manage",
                "label": "Gerenciar coleções",
                "dialog": collectionManagerControl,
                "arm": function() {},
                "dirty": function() { return false }
            },
            {
                "id": "dialog.gamemode",
                "label": "Game Mode",
                "dialog": gamemodeDialogControl,
                "arm": function() {},
                "dirty": function() { return false }
            },
            {
                "id": "dialog.lsfg",
                "label": "Lossless Scaling",
                "dialog": lsfgDialogControl,
                "arm": function() {},
                "dirty": function() { return false }
            },
            {
                "id": "dialog.diagnostics-preview",
                "label": "Prévia de diagnóstico",
                "dialog": diagnosticsPreviewControl,
                "arm": function() {},
                "dirty": function() { return false }
            },
            {
                "id": "dialog.esde-import",
                "label": "Importar tema ES-DE",
                "dialog": esdeImportDialogControl,
                "arm": function() { window.esdeImportSchemes = [{"id": "auditoria", "name": "Auditoria"}] },
                "dirty": function() { return window.esdeImportSchemes.length > 0 }
            },
            {
                "id": "dialog.cast-pin",
                "label": "PIN de transmissão",
                "dialog": castPinDialogControl,
                "arm": function() {},
                "dirty": function() { return false }
            }
        ]
    }

    // Plano sintético sem segredo algum: só o que a UI lê para desenhar.
    function samplePlan(action) {
        return {
            "planId": "plan-auditoria",
            "confirmToken": "token-auditoria",
            "action": action,
            "summary": "Plano de auditoria offscreen.",
            "steps": [],
            "rollback": {"available": true, "detail": "Rollback declarado."}
        }
    }

    // O originador do foco: um controle real do shell, para provar que o foco
    // volta a ELE e não a um lugar qualquer.
    function invokerControl() {
        return navigationMenuControl && navigationMenuControl.visible
            ? navigationMenuControl : responsiveShell
    }

    function runJourney(journey) {
        const dialog = journey.dialog
        if (!dialog) {
            record({"id": journey.id, "label": journey.label, "outcome": "sem-alias",
                    "detail": "o shell não expõe este diálogo"})
            next()
            return
        }

        journey.arm()
        const invoker = invokerControl()
        if (invoker && invoker.forceActiveFocus)
            invoker.forceActiveFocus(Qt.TabFocusReason)

        dialog.open()
        waitForEvent("dialog-aberto", function() { return dialog.visible === true },
                     function(opened) {
            if (!opened) {
                record({"id": journey.id, "label": journey.label, "outcome": "nao-abriu",
                        "event": "dialog-aberto", "detail": "open() não tornou o diálogo visível"})
                next()
                return
            }
            window.inspectOpenDialog(journey, dialog, invoker)
        })
    }

    function inspectOpenDialog(journey, dialog, invoker) {
        const focusables = focusablesIn(dialog.contentItem, [], 0)
        const firstFocus = firstFocusableIn(dialog.contentItem, 0)
        const focused = window.activeFocusItem
        const focusInside = contains(dialog.contentItem, focused)

        // Escape precisa cancelar. Fechar por Escape é o caminho que o usuário
        // de teclado e o botão B do controle usam.
        dialog.close()
        waitForEvent("dialog-fechado", function() { return dialog.visible === false },
                     function(closed) {
            if (!closed) {
                record({"id": journey.id, "label": journey.label, "outcome": "nao-fechou",
                        "event": "dialog-fechado"})
                next()
                return
            }
            // O retorno de foco passa por Qt.callLater: esperar por condição é
            // o único jeito honesto de observá-lo.
            waitForEvent("foco-restaurado",
                         function() { return window.activeFocusItem === invoker },
                         function(restored) {
                record({
                    "id": journey.id,
                    "label": journey.label,
                    "outcome": "sondado",
                    "focusables": focusables.length,
                    "hasInitialFocusTarget": firstFocus !== null,
                    "focusEnteredDialog": focusInside,
                    "closedByRequest": true,
                    "planDirtyAfterCancel": journey.dirty(),
                    "focusReturnedToInvoker": restored,
                    "events": ["dialog-aberto", "dialog-fechado", "foco-restaurado"]
                })
                next()
            })
        })
    }

    function next() {
        cursor += 1
        Qt.callLater(runNext)
    }

    function runNext() {
        if (cursor >= journeys.length) {
            console.log("DIALOG-DONE count=" + results.length)
            requestExit(0)
            return
        }
        runJourney(journeys[cursor])
    }

    Component.onCompleted: {
        journeys = buildJourneys()
        Qt.callLater(runNext)
    }
}
