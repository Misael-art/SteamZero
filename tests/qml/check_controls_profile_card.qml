// SPDX-License-Identifier: GPL-3.0-or-later
// G45: o cartão de perfil de controle precisa dizer a verdade em cada estado.
//
// O que este harness protege é a distinção que a G45 registra: "perfil salvo",
// "perfil traduzido" e "perfil efetivamente valendo" são três coisas, e só a
// terceira pode aparecer como pronta.
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 900
    height: 700
    property int failures: 0

    function check(condition, message) {
        if (!condition) {
            failures += 1
            console.error("FAIL: " + message)
        }
    }

    readonly property var bindingsResolvidos: [
        {"action": "game.primary", "input": "button.south", "key": "input_b_btn", "value": "0"},
        {"action": "game.up", "input": "hat.up", "key": "input_up_btn", "value": "h0up"}
    ]

    function perfil(estado, extras) {
        var autoconfig = null
        if (estado !== null) {
            autoconfig = {
                "state": estado,
                "statusLabel": "rótulo do backend",
                "detail": extras && extras.detail ? extras.detail : "",
                "device": extras && extras.device ? extras.device : null,
                "deviceReason": "matched",
                "autoconfigCandidates": [],
                "path": null,
                "directoryDeclared": true,
                "resolvedBindings": extras && extras.resolved ? extras.resolved : [],
                "unresolvedBindings": extras && extras.unresolved ? extras.unresolved : [],
                "withoutRetropadEquivalent": extras && extras.sem ? extras.sem : []
            }
        }
        return {
            "state": "ready",
            "statusLabel": "Perfil selecionado",
            "active": {"id": "standard-gamepad", "revision": 1, "orientation": "landscape"},
            "autoconfig": autoconfig
        }
    }

    ControlsProfileCard {
        id: card
        width: 820
        profile: harness.perfil("pending-write", {"resolved": harness.bindingsResolvidos})
        surfaceColor: "#f4f7f5"
        raisedColor: "#ffffff"
        borderColor: "#aebdbe"
        textColor: "#16212a"
        mutedColor: "#53616b"
        greenColor: "#167a45"
        amberColor: "#9a5a00"
        redColor: "#ae2634"
    }

    Timer {
        interval: 120
        running: true
        onTriggered: {
            // Tudo resolvido e ainda assim NÃO é "pronto": o arquivo não existe.
            // Este é o caso que separa "traduzido" de "valendo".
            check(card.autoconfigState() === "pending-write",
                  "estado resolvido-mas-não-gravado deve ser publicado como pending-write")
            check(!card.isApplied(),
                  "perfil não gravado NUNCA pode aparecer como aplicado")
            check(card.accentColor() !== card.greenColor,
                  "verde exige prova de aplicação, não apenas resolução")
            check(card.resolvedBindings.length === 2,
                  "os mapeamentos que serão aplicados precisam ser desenhados")
            check(String(card.honestMessage()).indexOf("ainda não foi gravado") >= 0,
                  "a mensagem precisa dizer por que o perfil ainda não vale")

            // Sem dispositivo: o índice não pode ser lido, e não será adivinhado.
            card.profile = harness.perfil("awaiting-device", {})
            check(!card.isApplied(), "sem dispositivo não pode aparecer como aplicado")
            check(String(card.honestMessage()).indexOf("não será adivinhado") >= 0,
                  "a tela precisa dizer que o índice não é adivinhado")

            // O caso real deste host: RetroArch nunca declarou a pasta de perfis.
            card.profile = harness.perfil("awaiting-emulator", {})
            check(!card.isApplied(), "sem pasta declarada não pode aparecer como aplicado")
            check(String(card.honestMessage()).indexOf("RetroArch") >= 0,
                  "a mensagem precisa nomear o que falta do lado do emulador")

            // Parcial: o que não vale precisa aparecer COM o motivo.
            card.profile = harness.perfil("partial", {
                "resolved": harness.bindingsResolvidos,
                "unresolved": [{
                    "action": "game.shoulder-left",
                    "input": "button.shoulder-left",
                    "reason": "dispositivo-nao-declara",
                    "reasonLabel": "O controle conectado não declara essa entrada."
                }]
            })
            check(!card.isApplied(), "perfil parcial não é perfil aplicado")
            check(card.accentColor() === card.amberColor,
                  "parcial precisa ser visualmente distinto de aplicado")
            check(card.unresolvedBindings.length === 1,
                  "binding sem índice físico precisa aparecer na tela")
            check(String(card.unresolvedBindings[0].reasonLabel).length > 0,
                  "o motivo precisa vir por extenso, senão não há ação possível")

            // Conflito: arquivo de terceiro não é sobrescrito, e isso é dito.
            card.profile = harness.perfil("conflict", {"detail": "arquivo sem marcador"})
            check(card.accentColor() === card.redColor,
                  "conflito precisa ser visualmente distinto")
            check(String(card.honestMessage()).indexOf("não será sobrescrito") >= 0,
                  "o usuário precisa saber que o arquivo dele está preservado")

            // Falha de escrita degrada sem prometer que o emulador quebrou.
            card.profile = harness.perfil("write-failed", {"detail": "permissão negada"})
            check(String(card.honestMessage()).indexOf("continua utilizável") >= 0,
                  "falha precisa deixar claro que o emulador segue usável")

            // Ações sem equivalente RetroPad aparecem mesmo sem autoconfig.
            card.profile = harness.perfil("partial", {
                "resolved": harness.bindingsResolvidos,
                "sem": ["game.axis-x", "game.axis-y"]
            })
            check(card.withoutEquivalent.length === 2,
                  "ações sem equivalente RetroPad precisam ser listadas")

            // Só aqui pode ficar verde.
            card.profile = harness.perfil("applied", {"resolved": harness.bindingsResolvidos})
            check(card.isApplied(), "perfil aplicado precisa ser reconhecido como aplicado")
            check(card.accentColor() === card.greenColor,
                  "perfil aplicado é o ÚNICO estado que pode ficar verde")

            // Sem perfil ativo, o cartão não inventa estado.
            card.profile = harness.perfil(null, {})
            check(card.autoconfigState() === "not-configured",
                  "ausência de autoconfig deve ser tratada como não configurado")
            check(!card.isApplied(), "ausência nunca é aplicação")

            if (harness.failures > 0) {
                console.error("check_controls_profile_card: " + harness.failures + " falha(s)")
                Qt.exit(1)
            } else {
                Qt.exit(0)
            }
        }
    }
}
