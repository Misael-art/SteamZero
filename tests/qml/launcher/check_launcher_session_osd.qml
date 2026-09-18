// SPDX-License-Identifier: GPL-3.0-or-later
//
// O harness prova a superfície, não a autoridade da sessão: o modelo chega
// pronto e a cena só pode selecionar uma ação e devolvê-la ao host.
import QtQuick
import "../../../src/steamzero/ui/qml/launcher"

Item {
    id: harness
    width: 1280
    height: 800

    property int failures: 0
    property int checks: 0
    property var dispatched: []
    property bool closed: false

    function check(condition, message) {
        checks += 1
        if (!condition) {
            failures += 1
            console.error("FAIL #" + checks + ": " + message)
        }
    }

    readonly property var baseModel: ({
        "sessionId": "session-1",
        "gameId": "celeste",
        "state": "running",
        "visible": true,
        "focusedAction": "pause",
        "actions": [
            {"id": "volume", "label": "Volume", "enabled": false,
             "reason": "Esta ação ainda não possui adapter de sessão."},
            {"id": "mute", "label": "Silenciar", "enabled": false,
             "reason": "Esta ação ainda não possui adapter de sessão."},
            {"id": "pause", "label": "Pausar", "enabled": true, "reason": ""},
            {"id": "screenshot", "label": "Captura", "enabled": false,
             "reason": "Esta ação ainda não possui adapter de sessão."}
        ],
        "criticalError": null,
        "diagnostic": null
    })

    readonly property var criticalModel: ({
        "sessionId": "session-1",
        "gameId": "celeste",
        "state": "running",
        "visible": true,
        "focusedAction": "pause",
        "actions": [
            {"id": "pause", "label": "Pausar", "enabled": false,
             "reason": "Erro crítico visível; confirme a recuperação na sessão."}
        ],
        "criticalError": {"code": "AURA-SESSION-FAIL-001",
                          "message": "O emulador perdeu a janela.",
                          "impact": "O jogo está pausado.",
                          "nextAction": "Verifique a sessão e tente novamente."},
        "diagnostic": "AURA-OSD-ERROR-004"
    })

    LauncherSessionOverlay {
        id: overlay
        anchors.fill: parent
        gameTitle: "Celeste"
        onActionRequested: function(actionId) { harness.dispatched.push(actionId) }
        onCloseRequested: harness.closed = true
    }

    Timer {
        interval: 100
        running: true
        repeat: false
        onTriggered: {
            overlay.openOverlay(harness.baseModel)
            harness.check(overlay.visible, "o OSD precisa abrir como superfície visível")
            harness.check(overlay.z === 100 && overlay.clip,
                          "o OSD precisa ocupar a camada superior e ser recortado")
            var backdrop = null
            var panel = null
            for (var childIndex = 0; childIndex < overlay.children.length; ++childIndex) {
                var child = overlay.children[childIndex]
                if (child.objectName === "sessionOverlayBackdrop")
                    backdrop = child
                if (child.objectName === "sessionOverlayPanel")
                    panel = child
            }
            harness.check(backdrop !== null && backdrop.color.a >= 0.99,
                          "o backdrop precisa ser opaco para impedir vazamento da página")
            harness.check(panel !== null && panel.opacity >= 0.99 && panel.z === 1,
                          "o painel precisa ser uma camada opaca acima do backdrop")
            harness.check(overlay.currentActionId === "pause",
                          "o foco publicado pelo bridge precisa chegar à cena")
            harness.check(overlay.actions.length === 4,
                          "a cena precisa renderizar todas as ações declaradas")
            harness.check(overlay.focusAction("volume"),
                          "uma ação desabilitada precisa poder receber foco")
            harness.check(overlay.activateFocused() === false,
                          "ação desabilitada não pode ser encaminhada")
            harness.check(harness.dispatched.length === 0,
                          "ação desabilitada não pode produzir dispatch")
            harness.check(overlay.localError.indexOf("não possui adapter") >= 0,
                          "a causa da indisponibilidade precisa ser visível")
            harness.check(overlay.focusAction("pause"), "a ação pause precisa ser focável")
            harness.check(overlay.activateFocused() === true,
                          "ação habilitada precisa voltar ao host")
            harness.check(harness.dispatched.length === 1
                          && harness.dispatched[0] === "pause",
                          "o dispatch precisa preservar o id semântico")

            overlay.setModel(harness.criticalModel)
            harness.check(overlay.criticalError.code === "AURA-SESSION-FAIL-001",
                          "erro crítico da sessão precisa chegar ao QML")
            harness.check(overlay.activateFocused() === false,
                          "erro crítico precisa bloquear uma ação aparentemente habilitada")
            harness.check(overlay.localError.indexOf("confirme a recuperação") >= 0,
                          "erro crítico precisa manter a orientação de recuperação")
            harness.check(overlay.closeOverlay(), "fechar o OSD precisa ser acionável")
            harness.check(!overlay.visible && harness.closed,
                          "fechar precisa ocultar a superfície e notificar o host")
            Qt.exit(harness.failures === 0 ? 0 : 1)
        }
    }
}
