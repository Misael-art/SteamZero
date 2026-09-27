// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// RC-01 (UX-02, corte de governança de estado) — a re-consulta que uma mutação
// provoca não pode ser descartada por haver uma leitura antiga em andamento.
//
// O `refreshStatus()` tem um guarda de sobreposição desde a RC-01: duas consultas
// simultâneas deixariam "o último estado" indefinido, porque a mais lenta pode
// chegar por último e regravar uma leitura mais nova. O guarda está certo, a ação
// tomada não: a re-consulta é *descartada*. Uma mutação que termina enquanto uma
// leitura antiga ainda voa não é lida nunca — e a resposta antiga ainda pinta o
// estado pré-mutação na tela. O usuário vê "operação concluída" com os dados de antes.
//
// Este harness roda o `Main.qml` real contra a ponte do teste de integração e
// atravessa a sequência no objeto vivo:
//
//   leitura #1 -> ready -> leitura #2 em andamento
//     -> mutação real pela rota de contrato published (`library.scan`)
//     -> o produto chama refreshStatus("Biblioteca atualizada…")
//     -> leitura #2 resolve -> o que a tela apresenta?
//
// A travessia é a mesma nos três ramos; muda só qual leitura a ponte recusa:
//
//   success          — #2 chega boa
//   in-flight-fails  — #2 falha depois de já haver dado na tela
//   refresh-fails    — a re-consulta coerçada é que falha
//
// Nenhuma fase usa tempo de parede como premissa: cada transição espera um estado
// observável, e a ponte segura a leitura #2 aberta até a mutação acontecer. O
// resultado não depende de quão carregado o host está.
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    visible: true
    width: 1280
    height: 800

    property int failures: 0
    property int checks: 0
    property int firstFailure: 0
    property int phase: 0
    property int waited: 0
    property int ticks: 0

    /// "success" | "in-flight-fails" | "refresh-fails"
    readonly property string scene: {
        const prefix = "--scene="
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; ++i) {
            if (args[i].startsWith(prefix))
                return args[i].slice(prefix.length)
        }
        return "success"
    }

    /// Quantas vezes a confirmação da mutação apareceu no rodapé. Coerçar a
    /// re-consulta não pode transformar um "feito" em dois, e descartá-la não pode
    /// transformá-lo em zero.
    property int confirmations: 0
    onLastRequestChanged: {
        if (String(lastRequest).indexOf("Biblioteca atualizada") === 0)
            confirmations += 1
    }

    /// Observável da cena `in-flight-fails`: a recusa da leitura em andamento teve
    /// de chegar à tela antes de a re-consulta recuperá-la.
    property bool sawRenewalFailure: false

    /// Geração publicada pela última leitura que a tela apresenta.
    readonly property string generation: {
        const rows = window.emulatorItems
        if (!rows || rows.length === 0)
            return ""
        return String(rows[0].versionLabel || "")
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

    function finish() {
        console.log(`OK: ${checks} verificações da cena ${scene}, ${failures} falhas`)
        Qt.exit(failures === 0 ? 0 : firstFailure)
    }

    /// A cena não pode exigir que NENHUMA ação esteja pendente: a própria Central
    /// despacha ações para encher superfícies (o catálogo de temas, por exemplo).
    /// O que importa é a chave da mutação que a cena provoca.
    function mutationPending() {
        const keys = Object.keys(window.pendingActionKeys)
        for (let i = 0; i < keys.length; ++i) {
            if (String(keys[i]).indexOf("library.scan") === 0)
                return true
        }
        return false
    }

    function actionKeysText() {
        return "[" + Object.keys(window.pendingActionKeys).join(";") + "]"
    }

    /// Disparar pela ação publicada é o que faz da mutação uma mutação real: o
    /// contrato, o endpoint e a chave de idempotência vêm da matriz que a própria
    /// ponte serve, e a rota pós-mutação é a do produto, não uma cópia do teste.
    function mutateLibrary() {
        window.performEmulationAction({"id": "library.scan", "enabled": true})
    }

    function checkFinalScene() {
        check(window.statusAttempt === 3,
              `a mutação precisa produzir uma leitura nova (cena ${scene}): `
              + `tentativas = ${window.statusAttempt}`)
        check(window.confirmations === 1,
              `a confirmação da mutação apareceu ${window.confirmations} vezes, esperado 1`)
        check(window.pendingRequests === 0, "a cena não pode terminar com requições no ar")

        if (scene === "refresh-fails") {
            // A re-consulta coerçada falhou: o dado anterior continua sendo a
            // última verdade, agora marcada como não renovada, com retry oferecido.
            // Coerçar não pode apagar esse contrato.
            check(window.generation === "2407",
                  "sem leitura nova a tela mantém a última medição, não um vazio")
            check(window.statusStale, "a falha da re-consulta deve marcar não renovado")
            check(window.statusBandVisible, "a falha da re-consulta deve aparecer na tela")
            check(window.statusBandRetry, "com dado preservado o retry deve ser oferecido")
            check(window.statusFailure !== null, "a falha deve estar disponível para leitura")
            check(window.statusPhase === "ready",
                  "uma renovação falha não pode degradar a leitura boa anterior")
            return
        }

        check(window.generation === "2412",
              `a tela apresenta a geração ${window.generation}, `
              + `esperado a pós-mutação 2412 (cena ${scene})`)
        check(window.statusStale === false, "uma renovação bem-sucedida limpa o não renovado")
        check(window.statusBandVisible === false, "a faixa de fase sai quando há dado renovado")
        check(window.statusFailure === null, "o sucesso limpa a falha anterior")
        check(window.statusPhase === "ready", "o estado final é de leitura presente")
        if (scene === "in-flight-fails") {
            check(window.sawRenewalFailure,
                  "a recusa da consulta em andamento deveria aparecer antes da recuperação")
        }
    }

    function step() {
        ticks += 1
        if (ticks > 1500) {
            check(false, "a cena não convergiu em 30 s: fase " + phase
                + ", tentativa " + window.statusAttempt)
            finish()
            return
        }
        window.waited += 20

        // Latch da cena `in-flight-fails`: registra a recusa se o tick a pegar.
        if (window.statusStale && window.statusFailure !== null)
            window.sawRenewalFailure = true

        switch (phase) {
        case 0: {
            // A primeira leitura precisa ter chegado: sem contrato publicado não
            // existe mutação de verdade para disparar.
            if (window.statusAttempt === 1 && window.statusPhase === "ready") {
                check(window.generation === "2407",
                      "a primeira leitura deve publicar a geração pré-mutação")
                check(!mutationPending(),
                      "nenhuma ação pode estar pendente antes da mutação: "
                      + actionKeysText())
                phase = 1
                waited = 0
            }
            return
        }
        case 1: {
            // Uma leitura nova é pedida e fica em andamento: é a leitura antiga que
            // vai concorrer com a mutação. `refreshStatus("")` é a chamada que o
            // próprio shell faz ao navegar e ao renovar.
            if (window.waited >= 60) {
                window.refreshStatus("")
                phase = 2
                waited = 0
            }
            return
        }
        case 2: {
            if (window.statusAttempt === 2 && window.statusInFlight) {
                check(window.generation === "2407",
                      "com a leitura #2 no ar a tela ainda mostra a última medição")
                mutateLibrary()
                phase = 3
                waited = 0
            }
            return
        }
        case 3: {
            // A ponte só responde a leitura #2 depois de ver a mutação, então aqui
            // a sobreposição já é um fato e não uma aposta de timing.
            if (mutationPending())
                return
            if (window.statusAttempt === 2 && !window.statusInFlight) {
                check(false, "a leitura em andamento resolveu antes da mutação: a cena "
                    + "não exerceu a sobreposição")
                phase = 5
                finish()
                return
            }
            phase = 4
            waited = 0
            return
        }
        case 4: {
            if (window.statusInFlight || mutationPending())
                return
            if (window.waited > 900) {
                checkFinalScene()
                phase = 5
                finish()
            }
            return
        }
        default:
            return
        }
    }

    Component.onCompleted: {
        check(scene === "success" || scene === "in-flight-fails" || scene === "refresh-fails",
              `cena desconhecida: ${scene}`)
        check(window.statusPhase === "loading", "a cena parte de carregando, sem dado medido")
        check(window.statusAttempt === 0, "nenhuma consulta pode ter sido contada no boot")
    }

    Timer {
        interval: 20
        repeat: true
        running: window.phase < 5
        onTriggered: window.step()
    }
}
