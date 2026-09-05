// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// Sonda COMPORTAMENTAL do painel de catálogo de temas.
//
// Os cliques são reais (`mouseClick`) e o que se verifica é a CHAMADA que sai
// do painel — id da ação e payload. Conferir que um botão existe provaria que
// alguém o desenhou, não que ele faz alguma coisa, e um controle que não age é
// o defeito que este projeto vem removendo da UI.
import QtQuick
import QtTest
import QtQuick.Controls
import "../../src/steamzero/ui/qml"

Item {
    id: harness
    width: 900
    height: 700

    property var calls: []
    property var listResponse: ({
        "entries": [
            {"id": "org.esde.iconic", "name": "Iconic", "license": "CC0-1.0",
             "credits": ["Siddy212"], "installed": false, "installedVersion": "",
             "upToDate": false},
            {"id": "org.esde.xmb-menu", "name": "XMB Menu", "license": "CC-BY-NC-SA-2.0",
             "credits": ["anthonycaccese", "InitialDin (XML original)"],
             "installed": true, "installedVersion": "afe3b7b61cb2", "upToDate": true},
            {"id": "org.esde.modern", "name": "Modern", "license": "CC-BY-NC-SA-4.0",
             "credits": ["ES-DE"], "installed": true, "installedVersion": "aaaaaaaaaaaa",
             "upToDate": false}
        ],
        "excluded": [
            {"repo": "Weestuarty-es-de/slick-es-de", "reason": "não declara licença"}
        ],
        "storeUsage": {"blobs": 474, "bytes": 69324695}
    })
    property bool failNextCall: false

    ThemeCatalogPanel {
        id: panel
        anchors.fill: parent
        requestAction: function(actionId, payload, callback, errorCallback) {
            harness.calls.push({"id": actionId, "payload": payload})
            if (harness.failNextCall) {
                harness.failNextCall = false
                errorCallback({"detail": "falha simulada"})
                return
            }
            if (actionId === "theme.catalog.list")
                callback(harness.listResponse)
            else if (actionId === "theme.catalog.install")
                callback({"operationId": "01OPERACAO", "themeId": payload.themeId})
            else if (actionId === "theme.store.gc")
                callback({"dryRun": payload.apply !== true, "orphans": 474,
                          "reclaimedBytes": 69324695})
            else
                callback({"restoredPrevious": true})
        }
    }

    // `Dialog` é um Popup, não um Item, e por isso NÃO aparece em `children`.
    // Uma busca por `children` nunca o encontraria — foi o que deixou um modal
    // aberto bloqueando os cliques do teste seguinte, com o sintoma aparecendo
    // longe da causa. `findChild` do QtTest percorre a árvore de QObject.
    function locate(node, name) {
        return testCase.findChild(node, name)
    }

    TestCase {
        id: testCase
        name: "ThemeCatalogPanel"
        when: windowShown

        // Diálogo modal deixado aberto por um teste engole os cliques do
        // seguinte, e o sintoma aparece longe da causa: foi assim que o teste
        // de instalar passou a ver zero chamadas por culpa do teste do GC.
        function cleanup() {
            const dialogs = ["uninstallDialog", "gcDialog"]
            for (let i = 0; i < dialogs.length; ++i) {
                const dialog = harness.locate(panel, dialogs[i])
                if (dialog && dialog.visible) {
                    dialog.close()
                    tryVerify(function() { return !dialog.visible })
                }
            }
        }

        function init() {
            harness.calls = []
            harness.failNextCall = false
            panel.lastOperation = ({})
            panel.gcPreview = null
            panel.errorText = ""
            panel.refresh()
            harness.calls = []
        }

        function test_loads_the_catalog_on_creation() {
            compare(panel.entries.length, 3)
            compare(panel.excluded.length, 1)
            compare(panel.storeUsage.blobs, 474)
        }

        function test_waits_for_the_bridge_contract_during_bootstrap() {
            harness.calls = []
            panel.contractsReady = false
            panel.refresh()
            compare(harness.calls.length, 0)

            const refresh = harness.locate(panel, "refreshButton")
            verify(refresh !== null)
            verify(!refresh.enabled)
            verify(String(refresh.Accessible.description).length > 0)

            panel.contractsReady = true
            tryVerify(function() {
                return harness.calls.filter(c => c.id === "theme.catalog.list").length === 1
            })
            compare(panel.entries.length, 3)
        }

        function test_install_button_actually_calls_the_route() {
            const button = harness.locate(panel, "installButton_org.esde.iconic")
            verify(button !== null, "botão de instalar não encontrado")

            mouseClick(button)

            const install = harness.calls.filter(c => c.id === "theme.catalog.install")
            compare(install.length, 1)
            compare(install[0].payload.themeId, "org.esde.iconic")
            // Tema ainda não instalado: sobrescrever seria mentira.
            compare(install[0].payload.overwrite, false)
        }

        function test_reinstalling_an_installed_theme_sends_overwrite() {
            const button = harness.locate(panel, "installButton_org.esde.xmb-menu")
            verify(button !== null)

            mouseClick(button)

            const install = harness.calls.filter(c => c.id === "theme.catalog.install")
            compare(install[0].payload.overwrite, true)
        }

        function test_installed_and_out_of_date_are_distinct_states() {
            // O backend distingue os dois, e a tela precisa distinguir também:
            // um selo só esconderia que há atualização disponível.
            const upToDate = harness.locate(panel, "stateBadge_org.esde.xmb-menu")
            const stale = harness.locate(panel, "stateBadge_org.esde.modern")
            verify(upToDate !== null && upToDate.visible)
            verify(stale !== null && stale.visible)
            verify(upToDate.color !== stale.color)

            // Tema não instalado não exibe selo nenhum.
            const none = harness.locate(panel, "stateBadge_org.esde.iconic")
            verify(none === null || !none.visible)
        }

        function test_uninstall_requires_confirmation_before_calling() {
            const button = harness.locate(panel, "uninstallButton_org.esde.xmb-menu")
            verify(button !== null)

            mouseClick(button)

            // Só o diálogo abriu; nada foi removido ainda.
            compare(harness.calls.filter(c => c.id === "theme.catalog.uninstall").length, 0)
            const dialog = harness.locate(panel, "uninstallDialog")
            verify(dialog !== null)
            // `opened` só fica true ao fim da transição de entrada.
            tryVerify(function() { return dialog.opened })

            dialog.accept()
            const removed = harness.calls.filter(c => c.id === "theme.catalog.uninstall")
            compare(removed.length, 1)
            compare(removed[0].payload.themeId, "org.esde.xmb-menu")
        }

        function test_garbage_collection_previews_before_deleting() {
            const preview = harness.locate(panel, "gcPreviewButton")
            mouseClick(preview)

            const calls = harness.calls.filter(c => c.id === "theme.store.gc")
            compare(calls.length, 1)
            // A primeira chamada NÃO apaga.
            verify(calls[0].payload.apply !== true)
            verify(panel.gcPreview !== null)

            const apply = harness.locate(panel, "gcApplyButton")
            verify(apply !== null && apply.visible, "botão de recuperar deve aparecer")
            mouseClick(apply)

            // Ainda assim exige confirmação: apagar é destrutivo.
            compare(harness.calls.filter(c => c.id === "theme.store.gc").length, 1)
            const dialog = harness.locate(panel, "gcDialog")
            verify(dialog !== null)
            tryVerify(function() { return dialog.opened })
            dialog.accept()

            const applied = harness.calls.filter(
                c => c.id === "theme.store.gc" && c.payload.apply === true)
            compare(applied.length, 1)
        }

        function test_apply_button_is_hidden_when_there_is_nothing_to_reclaim() {
            panel.gcPreview = {"dryRun": true, "orphans": 0, "reclaimedBytes": 0}
            const apply = harness.locate(panel, "gcApplyButton")
            verify(apply === null || !apply.visible,
                   "um botão que não faz nada ensina a ignorá-lo")
        }

        function test_undo_appears_only_after_an_install_in_this_session() {
            let undo = harness.locate(panel, "rollbackButton_org.esde.iconic")
            verify(undo === null || !undo.visible)

            mouseClick(harness.locate(panel, "installButton_org.esde.iconic"))

            undo = harness.locate(panel, "rollbackButton_org.esde.iconic")
            verify(undo !== null && undo.visible)
            mouseClick(undo)

            const rolled = harness.calls.filter(c => c.id === "theme.catalog.rollback")
            compare(rolled.length, 1)
            compare(rolled[0].payload.operationId, "01OPERACAO")
        }

        function test_excluded_themes_are_shown_with_the_reason() {
            // A ausência não pode parecer esquecimento.
            const section = harness.locate(panel, "excludedSection")
            verify(section !== null && section.visible)
        }

        function test_catalog_failure_stays_on_screen() {
            // Uma lista vazia seria indistinguível de "nenhum tema disponível";
            // o erro precisa ficar visível, não sumir num toast.
            harness.failNextCall = true
            panel.refresh()

            const label = harness.locate(panel, "errorLabel")
            verify(label !== null && label.visible)
            verify(String(label.text).indexOf("falha simulada") >= 0)
        }
    }
}
