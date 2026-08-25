// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Harness de auditoria UI: percorre seções, sub-áreas Steam, áreas de emulação,
// views da biblioteca editorial e overlays. Grava PNGs em --steamzero-outdir.
// Não é um teste de gate; é instrumento de diagnóstico visual/UX.

import QtQuick
import "../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 1600
    height: 1000

    property int captureIndex: 0
    property string outDir: "/tmp/steamzero-ui-audit"
    property var queue: []
    property bool busy: false

    readonly property var sectionIds: {
        const ids = []
        for (let i = 0; i < navigationSections.length; i++)
            ids.push(navigationSections[i].id)
        return ids
    }

    function parseOutDir() {
        const args = Qt.application.arguments
        const marker = args.indexOf("--steamzero-outdir")
        if (marker >= 0 && marker + 1 < args.length)
            outDir = args[marker + 1]
    }

    function pathFor(name) {
        return outDir + "/" + name + ".png"
    }

    function resetTransientUi() {
        if (responsiveTaskDrawer && responsiveTaskDrawer.visible)
            responsiveTaskDrawer.close()
        if (responsiveDrawer && responsiveDrawer.visible)
            responsiveDrawer.close()
        if (credentialDialogControl && credentialDialogControl.visible)
            credentialDialogControl.close()
        if (diagnosticsPreviewControl && diagnosticsPreviewControl.visible)
            diagnosticsPreviewControl.close()
        if (operationRollbackControl && operationRollbackControl.visible)
            operationRollbackControl.close()
        if (collectionManagerControl && collectionManagerControl.visible)
            collectionManagerControl.close()
        if (libraryHealthPlanControl && libraryHealthPlanControl.visible)
            libraryHealthPlanControl.close()
        if (emulationControl) {
            emulationControl.gameDetailsOpen = false
            emulationControl.globalManagementActive = true
            emulationControl.areaIndex = 0
            emulationControl.platformIndex = 0
            emulationControl.scopeIndex = 0
        }
        if (editorialLibraryControl) {
            editorialLibraryControl.view = "systems"
            editorialLibraryControl.libraryView = "carousel"
            editorialLibraryControl.systemFilter = "all"
            editorialLibraryControl.collectionFilter = ""
            editorialLibraryControl.selectedIndex = 0
        }
        steamArea = "performance"
    }

    function buildQueue() {
        const items = []
        const viewports = [
            {"w": 1280, "h": 800, "tag": "deck"},
            {"w": 1600, "h": 1000, "tag": "studio"},
            {"w": 1920, "h": 1080, "tag": "fullhd"}
        ]

        // Todas as seções do shell em três breakpoints
        for (let v = 0; v < viewports.length; v++) {
            const vp = viewports[v]
            for (let s = 0; s < sectionIds.length; s++) {
                items.push({
                    "kind": "section",
                    "section": sectionIds[s],
                    "width": vp.w,
                    "height": vp.h,
                    "name": vp.tag + "-" + sectionIds[s]
                })
            }
        }

        // Sub-áreas Steam (desempenho / controles / biblioteca / desktop)
        const steamAreas = ["performance", "controls", "library", "desktop"]
        for (let a = 0; a < steamAreas.length; a++) {
            items.push({
                "kind": "steam-area",
                "section": "steam",
                "steamArea": steamAreas[a],
                "width": 1600,
                "height": 1000,
                "name": "steam-area-" + steamAreas[a]
            })
        }

        // Emulação: gestão global + plataforma + áreas default
        items.push({
            "kind": "emulation-global",
            "section": "emulators",
            "width": 1600,
            "height": 1000,
            "name": "emulation-global-management"
        })
        const emuAreas = [
            "overview", "keysFirmware", "updatesDlc", "modsCheats",
            "graphicsPerformance", "controls", "saves", "shaderCache",
            "media", "storage", "advanced"
        ]
        for (let e = 0; e < emuAreas.length; e++) {
            items.push({
                "kind": "emulation-area",
                "section": "emulators",
                "areaId": emuAreas[e],
                "width": 1600,
                "height": 1000,
                "name": "emulation-area-" + emuAreas[e]
            })
        }

        // Biblioteca editorial: sistemas + vistas de jogos
        items.push({
            "kind": "library-view",
            "section": "library",
            "libView": "systems",
            "width": 1600,
            "height": 1000,
            "name": "library-systems"
        })
        const libLayouts = ["carousel", "grid", "list"]
        for (let l = 0; l < libLayouts.length; l++) {
            items.push({
                "kind": "library-view",
                "section": "library",
                "libView": "library",
                "libraryView": libLayouts[l],
                "width": 1600,
                "height": 1000,
                "name": "library-games-" + libLayouts[l]
            })
        }

        // Overlays / drawers no viewport deck (onde o rail compacto importa)
        items.push({
            "kind": "overlay-task-drawer",
            "section": "overview",
            "width": 1280,
            "height": 800,
            "name": "overlay-task-drawer"
        })
        items.push({
            "kind": "overlay-nav-drawer",
            "section": "overview",
            "width": 949,
            "height": 593,
            "name": "overlay-nav-drawer-handheld"
        })
        items.push({
            "kind": "overlay-credentials",
            "section": "system",
            "width": 1600,
            "height": 1000,
            "name": "overlay-credentials"
        })

        // Ultrawide e compacto extremos
        items.push({
            "kind": "section",
            "section": "overview",
            "width": 2560,
            "height": 1080,
            "name": "ultrawide-overview"
        })
        items.push({
            "kind": "section",
            "section": "sync",
            "width": 2560,
            "height": 1080,
            "name": "ultrawide-sync"
        })
        items.push({
            "kind": "section",
            "section": "overview",
            "width": 949,
            "height": 593,
            "name": "handheld-overview"
        })
        items.push({
            "kind": "section",
            "section": "emulators",
            "width": 949,
            "height": 593,
            "name": "handheld-emulation"
        })
        items.push({
            "kind": "section",
            "section": "library",
            "width": 949,
            "height": 593,
            "name": "handheld-library"
        })

        return items
    }

    function applyItem(item) {
        resetTransientUi()
        width = item.width
        height = item.height

        const idx = sectionIndexOf(item.section)
        if (idx >= 0)
            sectionIndex = idx

        if (item.kind === "steam-area") {
            steamArea = item.steamArea
            if (steamGameplayControl)
                steamGameplayControl.workspaceIndex =
                    steamGameplayControl.areaIndex(item.steamArea)
        }

        if (item.kind === "emulation-global" && emulationControl) {
            emulationControl.globalManagementActive = true
            emulationControl.areaIndex = 0
        }

        if (item.kind === "emulation-area" && emulationControl) {
            emulationControl.globalManagementActive = false
            // Escolhe a primeira plataforma real se existir
            if (emulationControl.platforms && emulationControl.platforms.length > 0)
                emulationControl.platformIndex = 0
            const areas = emulationControl.areas || []
            let found = 0
            for (let i = 0; i < areas.length; i++) {
                if (areas[i].id === item.areaId) {
                    found = i
                    break
                }
            }
            emulationControl.areaIndex = found
        }

        if (item.kind === "library-view" && editorialLibraryControl) {
            if (item.libView === "systems") {
                editorialLibraryControl.view = "systems"
            } else {
                editorialLibraryControl.view = "library"
                editorialLibraryControl.systemFilter = "all"
                if (item.libraryView)
                    editorialLibraryControl.libraryView = item.libraryView
            }
        }

        if (item.kind === "overlay-task-drawer" && responsiveTaskDrawer)
            responsiveTaskDrawer.open()

        if (item.kind === "overlay-nav-drawer" && responsiveDrawer)
            responsiveDrawer.open()

        if (item.kind === "overlay-credentials" && credentialDialogControl) {
            if (typeof credentialDialogControl.refresh === "function")
                credentialDialogControl.refresh()
            credentialDialogControl.open()
        }
    }

    // Contexto que o manifesto precisa registrar por captura. Sem isto o PNG não
    // diz em que resolução, tema ou origem de dados foi tirado, e duas auditorias
    // ficam incomparáveis.
    function captureMetadata(item) {
        return JSON.stringify({
            "name": item.name,
            "section": item.section,
            "kind": item.kind,
            "viewport": item.width + "x" + item.height,
            "scaleFactor": Screen.devicePixelRatio,
            "themeId": _themeBridge.themeId,
            "themeVersion": _themeBridge.themeVersion,
            "highContrast": highContrast,
            "reducedMotion": reducedMotion,
            "dataOrigin": (apiUrl !== "" && apiToken !== "") ? "bridge-live" : "fallback-qml"
        })
    }

    property int pendingExitCode: 0

    // Sair de dentro do callback de grabToImage derruba o processo por sinal —
    // foi a causa do qmlReturncode=-11 registrado na auditoria de 2026-08-11.
    // O pedido de saída passa a atravessar o event loop.
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

    function grabCurrent() {
        const item = queue[captureIndex]
        const target = responsiveShell ? responsiveShell : window.contentItem
        const metadata = captureMetadata(item)
        target.grabToImage(function(result) {
            const path = pathFor(item.name)
            if (!result.saveToFile(path)) {
                console.error("AUDIT-FAIL save " + path)
                requestExit(1)
                return
            }
            console.log("AUDIT-OK " + path)
            console.log("AUDIT-META " + metadata)
            captureIndex += 1
            busy = false
            Qt.callLater(nextCapture)
        })
    }

    function nextCapture() {
        if (busy)
            return
        if (captureIndex >= queue.length) {
            console.log("AUDIT-DONE count=" + queue.length + " outDir=" + outDir)
            requestExit(0)
            return
        }
        busy = true
        applyItem(queue[captureIndex])
        // Espera layout + eventual refresh da bridge
        settleTimer.restart()
    }

    Timer {
        id: settleTimer
        interval: 650
        onTriggered: window.grabCurrent()
    }

    // Espera a bridge popular o dashboard antes de capturar
    Timer {
        id: bridgeWait
        interval: 1800
        onTriggered: {
            queue = buildQueue()
            console.log("AUDIT-START count=" + queue.length + " sections="
                + sectionIds.join(",") + " outDir=" + outDir)
            nextCapture()
        }
    }

    Component.onCompleted: {
        parseOutDir()
        // Se há API, deixa o refreshStatus rodar; senão captura fallbacks
        if (apiUrl !== "" && apiToken !== "")
            bridgeWait.start()
        else {
            queue = buildQueue()
            console.log("AUDIT-START-OFFLINE count=" + queue.length
                + " outDir=" + outDir)
            nextCapture()
        }
    }
}
