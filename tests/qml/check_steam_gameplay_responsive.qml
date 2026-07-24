// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 1208
    height: 696
    property int failures: 0
    property int checks: 0
    property int firstFailure: 0
    property int phase: 0

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
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
            "hud": {
                "viewport": {"width": 1280, "height": 800},
                "evidence": {"state": "verified-offscreen",
                    "humanReview": {"state": "PENDING-HUMAN"}}
            },
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
        if (phase === 0) {
            check(page.compactLayout, "Deck deve ativar Steam Gameplay compacto")
            check(!page.showSupplementaryPanels,
                  "painéis suplementares não devem sufocar o formulário no Deck")
            check(page.reviewApplyControl.visible,
                  "CTA Revisar e aplicar perfil deve permanecer visível")
            check(page.reviewApplyControl.enabled,
                  "CTA deve permanecer acionável quando há jogo selecionado")
            check(page.minimumTouchTarget >= 48,
                  "CTA deve manter alvo mínimo de 48 px")
            check(page.gameplay.hud.evidence.humanReview.state === "PENDING-HUMAN",
                  "evidência HUD não deve promover revisão visual humana")
            check(page.payload().vkBasalt === "off",
                  "vkBasalt deve iniciar completamente desligado")
            check(page.vkBasaltControl.Accessible.description.length > 0,
                  "vkBasalt indisponível deve explicar a dependência")
            width = 1656
            height = 954
            phase = 1
            return
        }
        if (phase === 1) {
            check(!page.compactLayout, "Full HD deve preservar Steam Gameplay desktop")
            check(page.showSupplementaryPanels,
                  "Full HD deve recuperar painéis suplementares")
            width = 2296
            height = 954
            phase = 2
            return
        }
        check(page.ultrawideLayout, "21:9 deve ativar Steam Gameplay ultrawide")
        check(page.contentMaxWidth === 1400,
              "Steam Gameplay ultrawide deve limitar conteúdo a 1400 px")
        responsiveTimer.stop()
        Qt.exit(failures === 0 ? 0 : firstFailure)
    }

    Timer {
        id: responsiveTimer
        interval: 100
        running: true
        repeat: true
        onTriggered: runChecks()
    }
}
