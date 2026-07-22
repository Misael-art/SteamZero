// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: false
    width: 1208
    height: 696
    property int failures: 0

    function check(condition, message) {
        if (condition)
            return
        failures += 1
        console.error("FAIL: " + message)
    }

    SteamGameplay {
        id: page
        anchors.fill: parent
        gameplay: ({
            "games": [{"id": "3311720", "name": "Gimmick! 2 Demo"}],
            "environment": [],
            "readiness": {"percent": 100, "title": "Pronto"},
            "hardware": {"tdpMin": 3, "tdpMax": 15, "refreshHz": 60},
            "currentProfile": {"gameId": "3311720", "scope": "game"}
        })
        desktopStatus: ({})
        backgroundColor: "#071019"
        surfaceColor: "#0d1924"
        raisedColor: "#122131"
        borderColor: "#2a3a49"
        textColor: "#f2f6fb"
        mutedColor: "#9eabba"
        cyanColor: "#13bdf2"
        cyanDarkColor: "#0a5f85"
        greenColor: "#59d35d"
        amberColor: "#ff9f1a"
        redColor: "#ff6b73"
    }

    function runChecks() {
        check(page.compactLayout, "Deck deve ativar Steam Gameplay compacto")
        check(!page.showSupplementaryPanels,
              "painéis suplementares não devem sufocar o formulário no Deck")
        check(page.reviewApplyControl.visible,
              "CTA Revisar e aplicar perfil deve permanecer visível")
        check(page.reviewApplyControl.enabled,
              "CTA deve permanecer acionável quando há jogo selecionado")
        check(page.reviewApplyControl.height >= 46,
              "CTA deve manter alvo mínimo de 46 px")

        width = 1656
        height = 954
        check(!page.compactLayout, "Full HD deve preservar Steam Gameplay desktop")
        check(page.showSupplementaryPanels,
              "Full HD deve recuperar painéis suplementares")

        width = 2296
        height = 954
        check(page.ultrawideLayout, "21:9 deve ativar Steam Gameplay ultrawide")
        check(page.contentMaxWidth === 1400,
              "Steam Gameplay ultrawide deve limitar conteúdo a 1400 px")
        Qt.exit(failures === 0 ? 0 : 1)
    }

    Component.onCompleted: Qt.callLater(runChecks)
}
