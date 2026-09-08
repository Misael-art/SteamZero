// SPDX-License-Identifier: GPL-3.0-or-later
// Jornada da área Temas: descobrir importação → inspecionar → escolher
// esquema → criar tema editável, sem aplicar silenciosamente.
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 1100
    height: 720

    property int failures: 0
    property int inspectRequests: 0
    property int applyRequests: 0
    property int packageInspectRequests: 0
    property int packageApplyRequests: 0
    property int retrofeInspectRequests: 0
    property int retrofeApplyRequests: 0
    property string lastScheme: ""
    property string lastName: ""
    property bool lastPackageOverwrite: true
    property string lastRetrofeLayout: ""
    property string lastRetrofeSceneId: ""
    property bool lastRetrofeOverwrite: true

    function request(method, path, _payload, callback, _errorCallback) {
        if (method === "GET" && path === "/theme/list")
            callback({"themes": []})
    }

    function requestAction(actionId, payload, callback, errorCallback) {
        if (actionId === "theme.import.esde.inspect") {
            inspectRequests += 1
            if (payload.source === "/bad") {
                errorCallback("tema ilegível")
                return
            }
            callback({"schemes": [
                {"scheme": "dark", "isMonochrome": false},
                {"scheme": "mono", "isMonochrome": true}
            ]})
            return
        }
        if (actionId === "theme.import.esde.apply") {
            applyRequests += 1
            lastScheme = payload.scheme || ""
            lastName = payload.name || ""
            callback({"themeId": "user.imported"})
            return
        }
        if (actionId === "theme.import.package.inspect") {
            packageInspectRequests += 1
            callback({
                "themeId": "org.example.imported",
                "name": "Tema empacotado",
                "version": "1.2.0",
                "author": "Autor",
                "license": "CC0-1.0",
                "alreadyInstalled": false
            })
            return
        }
        if (actionId === "theme.import.package.apply") {
            packageApplyRequests += 1
            lastPackageOverwrite = payload.overwrite === true
            callback({"themeId": "org.example.imported"})
            return
        }
        if (actionId === "theme.import.retrofe.inspect") {
            retrofeInspectRequests += 1
            callback({"layouts": [
                {"id": "main", "name": "Main", "report": {"elements": 8, "degraded": 1},
                    "assets": {"available": ["assets/logo.png"], "missing": [], "refused": [], "ready": true}}
            ]})
            return
        }
        if (actionId === "theme.import.retrofe.apply") {
            retrofeApplyRequests += 1
            lastRetrofeLayout = payload.layout || ""
            lastRetrofeSceneId = payload.sceneId || ""
            lastRetrofeOverwrite = payload.overwrite === true
            callback({"sceneId": lastRetrofeSceneId, "activated": false})
        }
    }

    ThemeEditorPanel {
        id: panel
        anchors.fill: parent
        request: harness.request
        requestAction: harness.requestAction
        activeThemeId: "org.steamzero.default"
    }

    function check(condition, message) {
        if (condition)
            return
        failures += 1
        console.error("FAIL: " + message)
    }

    Component.onCompleted: {
        check(panel.editorThemeList.length === 0, "a lista inicial deve carregar")
        panel.esdeImportSource = "/tmp/es-de-theme"
        panel.inspectEsdeImport()
        check(inspectRequests === 1, "examinar deve chamar o contrato uma vez")
        check(panel.esdeImportSchemes.length === 2, "examinar deve publicar os esquemas")
        check(panel.esdeImportSchemeIndex === 0, "o primeiro esquema deve receber foco lógico")
        panel.esdeImportName = "Tema importado"
        panel.applyEsdeImport()
        check(applyRequests === 1, "importar deve chamar o contrato uma vez")
        check(lastScheme === "dark", "importar deve enviar o identificador scheme, não o objeto")
        check(lastName === "Tema importado", "importar deve enviar o nome informado")
        check(panel.editorThemeList.length === 0, "refresh após importação deve atualizar a lista")
        panel.esdeImportSource = "/bad"
        panel.inspectEsdeImport()
        check(panel.esdeImportNoticeIsError === true, "erro de inspeção deve ficar visível")
        check(panel.esdeImportBusy === false, "erro não pode deixar importação ocupada")
        panel.packageImportSource = "/tmp/theme.zip"
        panel.inspectPackageImport()
        check(packageInspectRequests === 1, "examinar pacote deve chamar o contrato uma vez")
        check(panel.packageImportPreview.themeId === "org.example.imported",
              "inspeção deve publicar o manifesto do pacote")
        check(panel.packageImportOverwrite === false,
              "pacote novo não deve habilitar sobrescrita por padrão")
        panel.applyPackageImport()
        check(packageApplyRequests === 1, "instalar pacote deve chamar o contrato uma vez")
        check(lastPackageOverwrite === false, "pacote novo não deve sobrescrever")
        panel.retrofeImportSource = "/tmp/retrofe"
        panel.inspectRetrofeImport()
        check(retrofeInspectRequests === 1, "examinar RetroFE deve chamar o contrato uma vez")
        check(panel.retrofeImportLayouts.length === 1, "examinar RetroFE deve publicar os layouts")
        check(panel.retrofeImportLayoutIndex === 0, "o primeiro layout deve receber foco lógico")
        panel.retrofeImportSceneId = "org.example.retrofe"
        panel.retrofeImportName = "Cena RetroFE"
        panel.retrofeImportAuthor = "Autor RetroFE"
        panel.retrofeImportLicense = "CC0-1.0"
        panel.applyRetrofeImport()
        check(retrofeApplyRequests === 1, "publicar RetroFE deve chamar o contrato uma vez")
        check(lastRetrofeLayout === "main", "publicar RetroFE deve enviar o id do layout")
        check(lastRetrofeSceneId === "org.example.retrofe", "publicar RetroFE deve enviar o id da cena")
        check(lastRetrofeOverwrite === false, "RetroFE novo não deve sobrescrever por padrão")
        Qt.exit(failures)
    }
}
