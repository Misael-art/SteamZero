// SPDX-License-Identifier: GPL-3.0-or-later
// Identidade AURA no editor: abrir → editar → preview → cancelar → reabrir.
// Também cobre o fluxo theme.apply → confirm e a ausência de document.*.
// O preview resolve os tokens editados no ThemeBridge; cancelar restaura a
// aparência (fallback) e devolve a lista de temas ao primeiro plano.
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 1280
    height: 800

    property int failures: 0
    property int checks: 0
    property int firstFailure: 0
    property int phase: 0
    property var cancelRequests: 0
    property string lastLoadId: ""
    property string lastApplyThemeId: ""
    property int applyRequests: 0
    property string lastConfirmPlanId: ""
    property string lastCreateExtends: ""
    property int appliedSignals: 0

    readonly property var auraColors: ({
        "background": "#0b1020",
        "sidebar": "#0d1326",
        "surface": "#141a2e",
        "surfaceRaised": "#1c2440",
        "surfaceSelected": "#1a2542",
        "border": "#262f4d",
        "text": "#e8ecf7",
        "textMuted": "#8b93a8",
        "textDisabled": "#5d6579",
        "accent": "#22d3ee",
        "accentStrong": "#0e7490",
        "success": "#59d35d",
        "successSurface": "#16301c",
        "warning": "#ff9f1a",
        "warningSurface": "#3b2a0e",
        "danger": "#ff6b73",
        "dangerSurface": "#3b1619",
        "focus": "#22d3ee"
    })

    readonly property var auraManifest: ({
        "id": "org.steamzero.aura",
        "name": "AURA",
        "version": "1.0.0",
        "author": "SteamZero contributors",
        "license": "GPL-3.0-or-later",
        "extends": "org.steamzero.default",
        "readOnly": true
    })

    function previewObject(resolvedTokens) {
        return {
            "schemaVersion": 1,
            "themeId": "org.steamzero.aura",
            "themeVersion": "1.0.0",
            "highContrast": false,
            "reducedMotion": false,
            "resolved": resolvedTokens,
            "effects": {},
            "mediaRecipes": {},
            "effectDiagnostics": []
        }
    }

    // Envelope do painel: URL/método vêm do backend, o harness só responde.
    property var request: function(method, path, payload, callback) {
        if (path === "/theme/list")
            callback({"themes": [
                {
                    "id": "org.steamzero.default", "name": "Default", "version": "1.0.0",
                    "author": "SteamZero", "origin": "builtin",
                    "state": "available", "compatible": true
                },
                {
                    "id": "org.steamzero.aura", "name": "AURA", "version": "1.0.0",
                    "author": "SteamZero contributors", "origin": "builtin",
                    "state": "available", "compatible": true
                },
                {
                    "id": "user.custom", "name": "Custom", "version": "0.1.0",
                    "author": "Tester", "origin": "user",
                    "state": "available", "compatible": true
                }
            ]})
    }

    property var requestAction: function(actionId, payload, callback) {
        if (actionId === "theme.editor.load") {
            lastLoadId = payload.themeId
            callback({"sessionId": "edit-aura-fixture",
                      "manifest": auraManifest,
                      "preview": previewObject({"color": auraColors})})
            return
        }
        if (actionId === "theme.editor.set-tokens") {
            var merged = JSON.parse(JSON.stringify(editor.editorTokens))
            if (!merged.color) merged.color = {}
            for (var k in payload.values)
                merged.color[k] = payload.values[k]
            callback({"preview": previewObject(merged)})
            return
        }
        if (actionId === "theme.editor.cancel") {
            cancelRequests += 1
            callback({"status": "cancelled", "sessionId": payload.sessionId})
            return
        }
        if (actionId === "theme.apply") {
            applyRequests += 1
            lastApplyThemeId = payload.themeId || ""
            callback({
                "planId": "plan-theme-apply-1",
                "confirmToken": "token-theme-1",
                "preview": "Operação: theme.preference.activate\nGarantia de rollback: G-FULL",
                "rollbackGuarantee": "G-FULL"
            })
            return
        }
        if (actionId === "theme.apply.confirm") {
            lastConfirmPlanId = payload.planId || ""
            callback({"status": "applied", "operationId": "op-theme-1"})
            return
        }
        if (actionId === "theme.editor.create") {
            lastCreateExtends = payload.extends || ""
            callback({
                "sessionId": "edit-copy-fixture",
                "manifest": {
                    "id": "user.copy",
                    "name": payload.name || "Cópia",
                    "version": "0.1.0",
                    "author": "Tester",
                    "readOnly": false,
                    "extends": payload.extends || "org.steamzero.default"
                },
                "preview": previewObject({"color": auraColors})
            })
            return
        }
    }

    ThemeEditorPanel {
        id: editor
        anchors.fill: parent
        request: harness.request
        requestAction: harness.requestAction
        activeThemeId: "org.steamzero.default"
        onApplied: harness.appliedSignals += 1
    }

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    function openAura() {
        harness.requestAction("theme.editor.load", {"themeId": "org.steamzero.aura"},
                              function(r) { editor._openEditor(r.sessionId, r.manifest, r.preview) })
    }

    function runPhase() {
        if (phase === 0) {
            check(editor.editorSessionId === "", "sem sessão o editor mostra a lista")
            check(editor.editorThemeList.length === 3, "lista deve carregar do catálogo")
            check(editor.editorThemeList[1].name === "AURA",
                  "catálogo deve publicar a identidade AURA")
            check(editor.activeThemeId === "org.steamzero.default",
                  "activeThemeId deve refletir o tema ativo do shell")
            check(editor.isActiveTheme("org.steamzero.default") === true,
                  "default deve ser reconhecido como ativo")
            check(editor.isActiveTheme("org.steamzero.aura") === false,
                  "AURA não deve estar ativo no fixture")
            editor.beginApply("org.steamzero.default")
            check(applyRequests === 0, "tema ativo não deve abrir plano de aplicação")
            check(editor.applyPlan === null, "tema ativo não deve criar confirmação")
            openAura()
            phase = 1
            return
        }
        if (phase === 1) {
            check(lastLoadId === "org.steamzero.aura", "abrir deve carregar o AURA")
            check(editor.editorSessionId === "edit-aura-fixture",
                  "abrir deve iniciar uma sessão de edição")
            check(editor.editorReadOnly === true, "tema builtin abre como leitura")
            check(editor.editorTokens.color.background === "#0b1020",
                  "sessão deve carregar a paleta AURA")
            check(String(editor._previewBridge.background) === "#0b1020",
                  "preview ao vivo deve aplicar o fundo AURA")
            check(String(editor._previewBridge.accent) === "#22d3ee",
                  "preview ao vivo deve aplicar o acento ciano AURA")
            check(String(editor._previewBridge.text) === "#e8ecf7",
                  "preview ao vivo deve aplicar o texto AURA")
            phase = 2
            return
        }
        if (phase === 2) {
            // Mesmo caminho do CategorySection: marcar sujo e despachar o
            // envelope; a resposta do backend alimenta o preview do painel.
            var values = JSON.parse(JSON.stringify(auraColors))
            values.accent = "#ff0000"
            editor.editorDirty = true
            editor.requestAction("theme.editor.set-tokens",
                {sessionId: editor.editorSessionId, category: "color", values: values},
                function(r) {
                    if (r.preview && r.preview.resolved) {
                        editor.editorPreviewObject = r.preview
                        editor.editorTokens = r.preview.resolved
                    }
                })
            check(editor.editorDirty === true, "editar deve marcar a sessão como não salva")
            check(editor.editorTokens.color.accent === "#ff0000",
                  "token editado deve entrar nos tokens da sessão")
            check(String(editor._previewBridge.accent) === "#ff0000",
                  "preview ao vivo deve refletir a edição")
            phase = 3
            return
        }
        if (phase === 3) {
            editor._closeEditor()
            check(cancelRequests === 1, "fechar sessão suja deve cancelar no backend")
            check(editor.editorSessionId === "", "cancelar deve encerrar a sessão")
            check(editor.editorDirty === false, "cancelar deve limpar o estado sujo")
            check(String(editor._previewBridge.background) === "#e7eceb",
                  "cancelar deve restaurar a aparência padrão (fallback)")
            check(editor.editorThemeList.length === 3,
                  "cancelar deve devolver a lista de temas ao primeiro plano")
            phase = 4
            return
        }
        if (phase === 4) {
            openAura()
            check(editor.editorTokens.color.accent === "#22d3ee",
                  "reabrir deve restaurar os tokens originais do AURA")
            check(String(editor._previewBridge.accent) === "#22d3ee",
                  "reabrir deve restaurar o preview AURA")
            editor._closeEditor()
            phase = 5
            return
        }
        if (phase === 5) {
            // Fluxo apply → confirm (sem document.* / browser APIs).
            editor.beginApply("org.steamzero.aura")
            check(lastApplyThemeId === "org.steamzero.aura",
                  "Aplicar deve chamar theme.apply com themeId")
            check(applyRequests === 1, "somente o tema não ativo deve pedir aplicação")
            check(editor.applyPlan !== null && editor.applyPlan.planId === "plan-theme-apply-1",
                  "theme.apply deve preencher applyPlan com planId")
            check(editor.applyPlan.confirmToken === "token-theme-1",
                  "theme.apply deve preencher confirmToken")
            editor.confirmApply()
            check(lastConfirmPlanId === "plan-theme-apply-1",
                  "confirm deve chamar theme.apply.confirm com planId")
            check(editor.applyPlan === null, "após confirm applyPlan deve limpar")
            check(appliedSignals === 1, "confirm deve emitir applied()")
            // Duplicar builtin usa create com extends.
            editor.duplicateAndEdit("org.steamzero.aura", "AURA")
            check(lastCreateExtends === "org.steamzero.aura",
                  "Duplicar e editar deve criar com extends do builtin")
            check(editor.editorSessionId === "edit-copy-fixture",
                  "Duplicar e editar deve abrir sessão editável")
            check(editor.editorReadOnly === false, "cópia do usuário não é somente leitura")
            phase = 6
            return
        }
        check(checks > 0, "o harness precisa executar ao menos uma verificação")
        Qt.exit(failures === 0 ? 0 : firstFailure)
    }

    Timer {
        interval: 20
        repeat: true
        running: true
        onTriggered: harness.runPhase()
    }
}
