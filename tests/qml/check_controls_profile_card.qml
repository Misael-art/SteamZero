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

    property var acaoAplicar: ({
        "id": "controls.autoconfig.apply",
        "label": "Aplicar perfil no RetroArch",
        "enabled": true,
        "reason": null,
        "requiresConfirmation": true
    })

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
            "autoconfig": autoconfig,
            // A fachada só oferece a ação em `pending-write`; o cartão reflete
            // isso em vez de decidir por conta própria.
            "applyAutoconfigAction": estado === "pending-write" ? harness.acaoAplicar : null
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
            // Rota de produção: sem o botão, o perfil resolvido nunca chega ao
            // disco e a integração fica inerte.
            check(card.applyAction !== null,
                  "resolvido-mas-não-gravado precisa oferecer a ação de aplicar")
            var aplicou = null
            card.applyAutoconfigRequested.connect(function (acao) { aplicou = acao })
            card.applyAutoconfigRequested(card.applyAction)
            check(aplicou !== null && String(aplicou.id) === "controls.autoconfig.apply",
                  "a ação emitida precisa ser a que a fachada executa")
            check(aplicou.requiresConfirmation === true,
                  "gravar no host exige confirmação explícita")

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

            // Perfil por JOGO não é aplicável: o autoconfig vale por controle, e
            // gravar aqui aplicaria o perfil da PLATAFORMA — outro perfil.
            card.profile = harness.perfil("unsupported-scope", {})
            check(!card.isApplied(), "escopo não suportado nunca é aplicação")
            check(card.applyAction === null,
                  "não se oferece gravar o que gravaria OUTRO perfil")
            check(String(card.honestMessage()).indexOf("por jogo") >= 0,
                  "a tela precisa dizer por que o perfil do jogo não vale aqui")

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
            check(card.applyAction === null,
                  "já aplicado não pode oferecer uma confirmação que não muda nada")
            // Alcance: o perfil vale via --appendconfig no lançamento do
            // SteamZero. Prometer que vale sempre seria falso.
            check(String(card.honestMessage()).indexOf("pelo SteamZero") >= 0,
                  "aplicado precisa dizer em que condição vale")

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
