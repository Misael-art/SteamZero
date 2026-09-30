// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// RC-01 (UX-02) — a Central é legível e utilizável durante o carregamento.
//
// Este harness não inventa estado: ele roda o `Main.qml` real contra a ponte
// HTTP do teste de integração e cobra as quatro transições que o usuário
// atravessa num host onde /status leva segundos:
//
//   loading -> ready -> stale (renovação falhou com dados preservados) -> ready
//
// Cada fase é verificada no objeto vivo, não numa cópia de dicionário em
// Python: só aqui existe o binding do Qt que decide se a Home pode dizer
// "Nenhum jogo publicado ainda" antes de qualquer medição. A primeira fase é
// aferida de forma síncrona no Component.onCompleted, antes de qualquer volta
// do event loop, para que "carregando" não dependa de timing.
import QtQuick
import "../../src/steamzero/ui/qml"

Main {
    id: window
    // Sem pedido de quadro a janela continua invisível: a cena que o gate afere
    // é exatamente a de sempre. Uma captura precisa de janela exposta, porque
    // o grabToImage recusa item que nunca chegou à cena.
    visible: window.captureOutput !== ""
    width: 1280
    height: 800

    property int failures: 0
    property int checks: 0
    property int firstFailure: 0
    property int phase: 0
    property int waited: 0

    // Um frame por execução, como no harness editorial: a evidência da batch
    // precisa mostrar o que a asserção afirma, e o gate continua sem custo de
    // gravação quando nenhum `--capture-phase` é pedido.
    readonly property string capturePhase: {
        const prefix = "--capture-phase="
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; ++i) {
            if (args[i].startsWith(prefix))
                return args[i].slice(prefix.length)
        }
        return ""
    }
    readonly property string captureOutput: {
        const prefix = "--capture-output="
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; ++i) {
            if (args[i].startsWith(prefix))
                return args[i].slice(prefix.length)
        }
        return ""
    }
    property string capturedPhase: ""
    property int capturesPending: 0
    property bool exitPending: false
    property bool staleChecked: false
    property int ticks: 0
    /// Contador de tentativas na fase em que a sondagem de sobreposição começou.
    property int probeBaseAttempt: 0

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    // Sair de dentro do callback do grabToImage derruba o processo por sinal
    // (foi o -11 do harness DarkButton), então a saída atravessa o loop.
    function requestExit() {
        exitPending = false
        exitTimer.restart()
    }

    // Toda aferição passa por aqui: um acesso a propriedade inexistente lança
    // para fora do handler, o timer pararia e o processo ficaria pendurado até
    // o timeout do subprocess — sem veredito nenhum. O harness deve sempre
    // poder dizer o que faltou.
    function guard(body, label) {
        try {
            body()
        } catch (error) {
            const detalhe = error && error.message ? error.message : String(error)
            check(false, label + " lançou exceção: " + detalhe)
            finish()
        }
    }

    function finish() {
        // Sem parar o timer, um `finish()` que adia a saída pelo quadro ainda
        // em composição reentraria a cada tick e repetiria o veredito.
        sceneTimer.stop()
        if (failures > 0)
            console.error("FALHAS: " + failures + " de " + checks
                + " (primeira: " + firstFailure + ")")
        else
            console.log("check_central_loading: " + checks + " contratos verificados")
        // Só uma execução verde deve o quadro de evidência: numa execução que
        // já falhou não há nada a esperar, e adiar a saída ali deixaria o
        // processo pendurado até o timeout do subprocess — sem veredito.
        if (failures === 0 && capturePhase !== "" && capturedPhase !== capturePhase) {
            exitPending = true
            // O pedido pode ter sido aceito e nunca composto; sem este limite o
            // processo esperaria pelo callback até o timeout do subprocess.
            captureWatchdog.restart()
            return
        }
        Qt.exit(failures === 0 ? 0 : 1)
    }

    // true quando a cena pode seguir: nada foi pedido para esta fase, ou o
    // quadro já foi gravado. A recusa do grab (janela ainda não exposta ao
    // compositor) e o pedido aceito ainda em composição voltam a perguntar no
    // próximo tick — o orçamento de ticks acima é o que limita a espera.
    function captureSettled(name) {
        if (capturePhase !== name)
            return true
        if (capturedPhase === name)
            return true
        if (capturesPending > 0)
            return false
        // `responsiveShell` é a superfície que os capturadores do projeto já
        // usam: o contentItem de uma ApplicationWindow não tem engine e o grab
        // é recusado ("item has no QML engine").
        const grabbed = window.responsiveShell.grabToImage(function(result) {
            window.capturesPending -= 1
            const ok = result !== null && result.saveToFile(window.captureOutput)
            if (ok)
                console.log("HARNESS-CAPTURED " + window.captureOutput)
            window.check(ok, "o quadro `" + name + "` não foi gravado em "
                + window.captureOutput)
            window.capturedPhase = name
            if (window.exitPending)
                window.requestExit()
        })
        if (!grabbed)
            console.log("captura `" + name + "` recusada pelo compositor; nova tentativa")
        else
            capturesPending += 1
        return false
    }

    Timer {
        id: exitTimer
        interval: 0
        repeat: false
        onTriggered: Qt.exit(window.failures === 0 ? 0 : 1)
    }

    Timer {
        id: captureWatchdog
        interval: 5000
        repeat: false
        onTriggered: {
            window.check(false, "o quadro pedido não foi composto em 5 s: "
                + window.capturePhase)
            window.requestExit()
        }
    }

    function fail(message) {
        check(false, message)
        finish()
    }

    // FASE 0 — o primeiro frame, antes de qualquer resposta.
    function checkLoadingPhase() {
        check(window.statusPhase === "loading", "a fase inicial deve ser loading")
        check(window.statusIsLoading, "statusIsLoading deve ser verdadeiro sem resposta")
        check(window.statusHasData === false, "sem resposta não pode haver dado")
        check(window.statusAttempt === 0,
              "nenhuma consulta pode ter sido concluída nesta fase")
        check(window.statusBandVisible, "a faixa de fase deve estar visível durante o carregamento")
        check(window.statusBandTitle.length > 0, "a faixa de fase deve ter título")
        check(window.statusBandRetry === false,
              "não se oferece retry enquanto a primeira consulta ainda vai chegar")
        check(window.showAttentionBanner === false,
              "o banner de atenção não pode afirmar um veredito antes da primeira medição")
        check(window.needsAttention === false,
              "needsAttention deve esperar uma leitura real")
        check(window.editorialHomeControl.loading,
              "a Home tem de saber que ainda não existe medição")

        // Nenhuma linha publicada pode afirmar ausência sem medição. Com o seed
        // atual isso vale para as duas listas que o shell projeta.
        const linhas = window.emulatorItems.concat(window.steamItems)
        let afirmaAusencia = []
        for (let i = 0; i < linhas.length; ++i) {
            if (linhas[i].state === "pending")
                continue
            afirmaAusencia.push(String(linhas[i].id) + "=" + String(linhas[i].state))
        }
        check(afirmaAusencia.length === 0,
              "fallback não verificado não pode afirmar ausência: " + afirmaAusencia.join(", "))

        // O helper que protege o caminho de fallback, cobrado diretamente: se o
        // seed mudar e as linhas de referência voltarem a aparecer antes da
        // leitura, esta é a asserção que continua provando o contrato.
        const fallback = window.fallbackComponents
        check(fallback.length > 0 && fallback[0].statusLabel === "Não instalado",
              "a cena parte de um fallback que afirma ausência")
        const protegidos = window.pendingRows(fallback)
        check(protegidos.length === fallback.length,
              "pendingRows preserva todas as linhas de referência")
        let todosConsultando = true
        for (let j = 0; j < protegidos.length; ++j) {
            if (protegidos[j].state === "pending" && protegidos[j].statusLabel === "Consultando")
                continue
            todosConsultando = false
            console.error("  linha " + String(protegidos[j].id) + " publica state="
                + String(protegidos[j].state) + " statusLabel="
                + String(protegidos[j].statusLabel))
        }
        check(todosConsultando, "pendingRows neutraliza toda afirmação de ausência")
        check(fallback[0].statusLabel === "Não instalado",
              "pendingRows não pode regravar o fallback compartilhado")
    }

    // FASE 1 — a primeira resposta chegou.
    function checkReadyPhase() {
        check(window.statusPhase === "ready", "a primeira resposta deve publicar ready")
        check(window.statusHasData, "deve haver dado medido")
        check(window.statusInFlight === false, "a consulta concluída não pode ficar em andamento")
        check(window.statusAttempt === 1, "uma única consulta deve ter sido feita")
        check(window.statusFailure === null, "sem falha nesta fase")
        check(window.statusBandVisible === false, "a faixa de fase deve sair quando há dado")
        const row = window.emulatorItems.length > 0 ? window.emulatorItems[0] : null
        check(row !== null && row.state === "installed" && row.statusLabel === "Instalado",
              "o estado medido pela ponte deve substituir o fallback")
        check(window.desktopStatus.truthState === "stale",
              "a ponte publicou o veredito da cena")
        check(window.showAttentionBanner,
              "com leitura real o veredito de atenção pode finalmente aparecer")
        check(window.needsAttention, "a pendência medida deve chegar ao shell")
    }

    // FASE 2 — a renovação falhou, mas os dados bons continuam na tela.
    function checkStalePhase() {
        check(window.statusPhase === "ready",
              "uma renovação falha não pode apagar a última leitura")
        check(window.statusStale, "a leitura preservada deve estar marcada como não renovada")
        check(window.statusHasData, "o dado preservado continua sendo dado")
        check(window.desktopStatus.truthState === "stale",
              "o estado anterior deve ser preservado, não substituído por fallback")
        check(window.statusBandVisible, "a falha de renovação deve ser declarada na tela")
        check(window.statusBandRetry, "com dado preservado o retry deve ser oferecido")
        check(window.statusFailure !== null, "a falha deve estar disponível para leitura")
        check(window.emulatorItems[0].state === "installed",
              "as linhas medidas não podem voltar a pending")
        check(window.showAttentionBanner,
              "o veredito medido permanece enquanto o dado permanece")

        // A oferta de retry é o único caminho de recuperação da fase: na faixa
        // escura ela herdava o texto escuro do tema claro e ficava ilegível.
        const retry = window.statusBandRetryButton
        check(retry.visible, "a faixa oferece o botão de retry no estado não renovado")
        const ratio = window._contrastRatio(retry.labelColor, window.statusBandBackground)
        check(ratio === ratio && ratio >= 4.5,
              "o rótulo de retry fica em " + ratio.toFixed(2) + ":1 sobre a faixa")
    }

    // FASE 3 — o retry recuperou a leitura.
    function checkRecoveredPhase() {
        check(window.statusStale === false, "uma renovação bem-sucedida limpa o estado não renovado")
        check(window.statusBandVisible === false, "a faixa de erro sai com a leitura recuperada")
        check(window.statusAttempt === 3, "as três consultas da cena devem ter ocorrido")
        check(window.statusFailure === null, "o sucesso limpa a falha anterior")
    }

    function advance(nextPhase) {
        window.phase = nextPhase
        window.waited = 0
    }

    // Um passo da cena. Os ramos que esperam o quadro ou a resposta saem por
    // `return`, então o watchdog tem de vir antes deles: colocá-lo no fim do
    // handler deixava uma fase presa esperar para sempre.
    function step() {
        window.waited += 25
        window.ticks += 1
        if (window.waited > 12000) {
            fail("tempo esgotado aguardando a fase " + window.phase)
            return
        }
        // Um quadro que nunca compõe não pode virar verde silencioso nem
        // pendurar a suíte: reprova e deixa a cena seguir.
        if (window.capturePhase !== "" && window.capturedPhase !== window.capturePhase
                && window.ticks > 320) {
            check(false, "nenhum quadro foi composto para a captura " + window.capturePhase)
            window.capturedPhase = window.capturePhase
        }
        if (window.phase === 1 && window.statusInFlight) {
            if (window.capturePhase === "loading" && window.capturedPhase === ""
                    && window.capturesPending === 0) {
                check(window.statusPhase === "loading",
                      "o quadro de carregamento foi pedido depois da primeira resposta")
            }
            // A cena só avança com o frame de "carregando" gravado: a resposta
            // da ponte chegaria antes e a evidência mostraria a Home pronta.
            if (!window.captureSettled("loading"))
                return
        }
        if (window.phase === 1 && !window.statusInFlight
                && window.statusPhase === "ready") {
            // A resposta pode chegar antes de o quadro compor: a cena espera o
            // frame de "carregando" nos dois casos, senão a evidência seria da
            // Home pronta.
            if (!window.captureSettled("loading"))
                return
            window.advance(2)
            return
        }
        if (window.phase === 2 && window.statusPhase === "ready" && !window.statusInFlight) {
            window.checkReadyPhase()
            window.refreshStatus("")
            window.advance(3)
            return
        }
        if (window.phase === 3 && window.statusStale) {
            if (!window.staleChecked) {
                window.staleChecked = true
                window.checkStalePhase()
            }
            // O retry trocaria a cena do quadro aferido: a evidência tem de ser
            // o estado não renovado, não a recuperação.
            if (!window.captureSettled("stale"))
                return
            window.retryStatus()
            window.advance(4)
            return
        }
        if (window.phase === 4 && !window.statusStale && !window.statusInFlight) {
            window.checkRecoveredPhase()
            window.advance(5)
            return
        }
        // FASE 5 — o guarda de sobreposição, aferido com uma consulta viva.
        // Ele já esteve aqui no meio da cena, onde a segunda `refreshStatus`
        // era descartada; agora a chamada excedente fica devendo uma relênia, e
        // testá-la no meio renumeraria as respostas da ponte e apagaria a fase
        // "stale" que a cena veio medir. A sondagem é a última coisa da cena.
        if (window.phase === 5) {
            window.probeOverlapGuard()
            return
        }
        if (window.phase === 6 && !window.statusInFlight) {
            window.checkOverlapDrained()
            window.finish()
        }
    }

    /// Duas chamadas na mesma janela de uma consulta em andamento: a segunda não
    /// pode abrir uma consulta concorrente, nem pode simplesmente sumir.
    function probeOverlapGuard() {
        const tentativas = window.statusAttempt
        window.refreshStatus("")
        window.refreshStatus("")
        check(window.statusAttempt === tentativas + 1,
              "consultas não podem se sobrepor: houve "
              + (window.statusAttempt - tentativas) + " tentativa(s) nova(s)")
        check(window.statusRefreshQueued,
              "a chamada feita durante a consulta tem de ficar coerçada")
        window.probeBaseAttempt = tentativas
        window.advance(6)
    }

    function checkOverlapDrained() {
        const esperado = window.probeBaseAttempt + 2
        check(window.statusAttempt === esperado,
              "a relênia coerçada tinha de sair: tentativa " + window.statusAttempt
              + ", esperado " + esperado)
        check(window.statusRefreshQueued === false, "a fila de relênia esvazia ao emitir")
        check(window.statusPhase === "ready", "a cena termina com leitura presente")
        check(window.statusStale === false, "a relênia bem-sucedida não deixa rastro de falha")
        check(window.statusBandVisible === false, "sem pendência medida, sem faixa de fase")
    }

    Timer {
        id: sceneTimer
        interval: 25
        repeat: true
        onTriggered: window.guard(window.step, "um passo da cena")
    }

    Component.onCompleted: {
        const args = Qt.application.arguments
        const hasBridge = args.indexOf("--steamzero-api") >= 0
            && args.indexOf("--steamzero-token") >= 0
        if (!hasBridge) {
            window.fail("o harness exige --steamzero-api e --steamzero-token da ponte do teste")
            return
        }
        window.guard(function () {
            window.checkLoadingPhase()
            window.phase = 1
            sceneTimer.start()
        }, "a aferição da fase de carregamento")
    }
}
