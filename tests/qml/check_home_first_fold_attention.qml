// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 SteamZero contributors
//
// RC-01 (oitava fatia) — primeira dobra da Home no cenário de atenção máxima.
//
// A lacuna estava registrada desde 26/09 ("as três superfícies empurram
// Pendências e Recentes para baixo da dobra em 800 px"), mas aquela nota forçava
// `bridgeUnavailable`, que os bindings de produção nunca deixam verdade junto de
// dados reais: `apiUrl`/`apiToken` vêm de argumento na inicialização e uma
// renovação recusada com dados preservados acende a faixa E empilha um cartão de
// erro pelo mesmo código (`request` → `notify(..., errObj)` → `pushError`).
//
// Este harness não recebe a cena por argumento. O argv é o da produção
// (`adapters/desktop_ui.py:990`-`:1001`: `qml6 Main.qml -- --steamzero-api … --steamzero-token …`),
// e o que distingue uma jornada da outra é apenas o comportamento da ponte. Assim
// a dobra nunca é medida numa janela aberta de modo diferente do modo real.
//
// O harness mede e imprime testemunhas; quem decide o veredito é o gate pytest,
// que também exige o estado que cada cena declara — um harness mudo reprova.
import QtQuick
import QtQuick.Controls
import "../../src/steamzero/ui/qml"

Main {
    id: window
    width: 1280
    height: 800
    visible: true

    property int ticks: 0
    property bool witnessEmitted: false
    property bool renewalTried: false
    property bool clicked: false
    property bool expandedEmitted: false
    property int alturaExpandida: -1
    property string clickGatilho: "nunca"
    property int clickTick: -1
    property bool referenciaTrocada: false
    property bool referenceEmitted: false
    property int alturaReferencia: -1

    function findByObjectName(node, name) {
        if (node === null || node === undefined)
            return null
        if (node.objectName === name)
            return node
        const nodes = node.children
        if (!nodes)
            return null
        for (let index = 0; index < nodes.length; ++index) {
            const found = window.findByObjectName(nodes[index], name)
            if (found !== null)
                return found
        }
        return null
    }

    // O cartão de erro é alcançado por duck-typing da própria interface que o
    // `Main.qml` já passa a ele: sem isto a medição exigiria mudar a produção
    // antes de poder provar o vermelho.
    //
    // A travessia começa no `contentItem`: com `ApplicationWindow` na raiz,
    // `children` da janela não expõe o conteúdo, e a cena pareceria vazia sem
    // estar — foi assim que a primeira versão deste harness mediu `cartoes=0`
    // com um cartão de erro na tela.
    readonly property var rootSurface: window.contentItem !== undefined
        && window.contentItem !== null ? window.contentItem : window

    function errorCards(node, found) {
        if (node === null || node === undefined)
            return found
        if (node.errorObject !== undefined && node.errorObject !== null
                && node.errorObject.code !== undefined && node.errorObject.code !== "")
            found.push(node)
        const kids = node.children
        if (kids) {
            for (let i = 0; i < kids.length; ++i)
                window.errorCards(kids[i], found)
        }
        return found
    }

    // Só conta o alvo que está NA TELA: localizar um botão oculto e acioná-lo por
    // programa diria "ação preservada" justamente na mutação que a corta. A
    // varredura exige `visible`, então um cartão que esconde o "Ver detalhes"
    // responde `gatilho=ausente` e o gate reprova.
    function buttonByLabel(node, label) {
        if (node === null || node === undefined)
            return null
        if (node.text !== undefined && String(node.text) === label && node.visible === true)
            return node
        const kids = node.children
        if (kids) {
            for (let i = 0; i < kids.length; ++i) {
                const found = window.buttonByLabel(kids[i], label)
                if (found !== null)
                    return found
            }
        }
        return null
    }

    // Prosa do cartão = todo texto fora de botão. O discriminador é o tipo:
    // `AbstractButton` expõe `down`, `Label` não — e aqui não se desce dentro do
    // botão, porque o `IconLabel`/`MnemonicLabel` interno dele repete o rótulo
    // acionável e contá-lo como prosa inflaria a testemunha. (Medido: `Label`
    // NÃO expõe `contentItem` nesta versão do Qt, então exigir `contentItem`
    // fazia a varredura devolver zero nós — foi assim que a primeira versão da
    // sonda alegou `prosa_itens=0` diante de quatro rótulos de orientação.)
    function proseNodes(node, found) {
        if (node === null || node === undefined)
            return found
        if (node.down !== undefined)
            return found
        if (node.text !== undefined && String(node.text).length > 0)
            found.push(node)
        const kids = node.children
        if (kids) {
            for (let i = 0; i < kids.length; ++i)
                window.proseNodes(kids[i], found)
        }
        return found
    }

    // "Na tela" exige altura de linha real: um rótulo visível com altura zero não
    // é informação, é supressão disfarçada.
    function prosaNaTela(cartao) {
        const nos = window.proseNodes(cartao, [])
        let naTela = 0
        let caracteres = 0
        let caracteresNaTela = 0
        for (let i = 0; i < nos.length; ++i) {
            const texto = String(nos[i].text)
            caracteres += texto.length
            const alturaMinima = nos[i].font.pixelSize
            if (nos[i].visible === true && nos[i].height >= alturaMinima && nos[i].width > 0) {
                naTela += 1
                caracteresNaTela += texto.length
            }
        }
        return {
            "itens": nos.length,
            "naTela": naTela,
            "caracteres": caracteres,
            "caracteresNaTela": caracteresNaTela,
        }
    }

    function tracoProsa(estagio, cartao) {
        if (cartao === null || cartao === undefined)
            return
        const nos = window.proseNodes(cartao, [])
        for (let i = 0; i < nos.length; ++i) {
            console.log("PROSA|estagio=" + estagio
                + "|i=" + i
                + "|vis=" + (nos[i].visible === true ? 1 : 0)
                + "|h=" + Math.round(nos[i].height)
                + "|w=" + Math.round(nos[i].width)
                + "|fonte=" + nos[i].font.pixelSize
                + "|chars=" + String(nos[i].text).length)
        }
    }

    // SONDAGEM (geografia da árvore do cartão): dump por nó, preservado no log do
    // gate para inspeção independente da testemunha agregada.
    function sondear(node, profundidade) {
        if (node === null || node === undefined)
            return
        const texto = node.text !== undefined ? String(node.text) : ""
        console.log("SONDA|p=" + profundidade
            + "|no=" + node
            + "|temTexto=" + (node.text !== undefined ? 1 : 0)
            + "|temCI=" + (node.contentItem !== undefined ? 1 : 0)
            + "|temDown=" + (node.down !== undefined ? 1 : 0)
            + "|temFonte=" + (node.font !== undefined ? 1 : 0)
            + "|vis=" + (node.visible === true ? 1 : 0)
            + "|h=" + Math.round(node.height)
            + "|chars=" + texto.length
            + "|fim=" + texto.slice(0, 28))
        const kids = node.children
        if (kids) {
            for (let i = 0; i < kids.length; ++i)
                window.sondear(kids[i], profundidade + 1)
        }
    }

    function witness() {
        const scroll = window.overviewScrollControl
        const home = window.editorialHomeControl
        if (scroll === null || home === null) {
            console.error("FAIL: a Home não montou — sem scroll ou sem editorialHome")
            return
        }
        const flick = scroll.contentItem
        if (flick === null || flick === undefined) {
            console.error("FAIL: o ScrollView da Home não expõe contentItem")
            return
        }
        // Todo alvo acionável publicado pela Home, ordenado por posição. A
        // primeira dobra é aferida contra o PRIMEIRO deles, não contra um nome
        // fixo: se a Home mudar de ordem, a testemunha continua dizendo o que
        // está no topo, e o gate continua sem armadilha de caminho.
        const nomes = ["overview.open-library", "overview.open-system",
                       "overview.open-recent", "overview.all-systems"]
        const alvos = []
        for (let i = 0; i < nomes.length; ++i) {
            const node = window.findByObjectName(home, nomes[i])
            if (node === null)
                continue
            const point = node.mapToItem(flick, 0, 0)
            alvos.push({
                "nome": node.objectName,
                "y": Math.round(point.y),
                "h": Math.round(node.height),
                "visivel": node.visible === true,
            })
        }
        alvos.sort(function (a, b) { return a.y - b.y })
        if (alvos.length === 0) {
            console.error("FAIL: nenhum alvo acionável da Home foi encontrado — a cena é vacua")
            return
        }
        const primeiro = alvos[0]
        const cartoes = window.errorCards(window.rootSurface, [])
        let prosa = {"itens": 0, "naTela": 0, "caracteres": 0, "caracteresNaTela": 0}
        let cartaoH = -1
        let cartaoDiag = 0
        let cartaoDetalhe = 0
        let cartaoAlvoH = -1
        let cartaoCompacto = -1
        if (cartoes.length > 0) {
            const cartao = cartoes[0]
            cartaoH = Math.round(cartao.height)
            const diag = window.buttonByLabel(cartao, "Exportar diagnóstico")
            const detalhe = window.buttonByLabel(cartao, "Ver detalhes")
                            || window.buttonByLabel(cartao, "Ocultar detalhes")
            cartaoDiag = diag !== null ? 1 : 0
            cartaoDetalhe = detalhe !== null ? 1 : 0
            cartaoAlvoH = diag !== null ? Math.round(diag.height) : -1
            // `compact` é a superfície que o oitavo elo introduce: a testemunha
            // registra o valor lido, não o valor pedido — a correção tem de se
            // provar no estado do cartão, não numa intenção declarada.
            cartaoCompacto = cartao.compact === undefined ? -1 : (cartao.compact ? 1 : 0)
            prosa = window.prosaNaTela(cartao)
            window.tracoProsa("compacto", cartao)
            window.sondear(cartao, 0)
        }
        const pend = window.findByObjectName(home, "overview.open-system")
        const pendPonto = pend ? pend.mapToItem(flick, 0, 0) : null
        console.log("TESTEMUNHO|escala=" + window.visualScale
            + "|band=" + (window.statusBandVisible ? 1 : 0)
            + "|banner=" + (window.showAttentionBanner ? 1 : 0)
            + "|ponte=" + (window.bridgeUnavailable ? 1 : 0)
            + "|erros=" + window.activeErrors.length
            + "|cartoes=" + cartoes.length
            + "|scroll_h=" + Math.round(scroll.height)
            + "|home_h=" + Math.round(home.height)
            + "|primeiro=" + primeiro.nome
            + "|primeiro_y=" + primeiro.y
            + "|primeiro_h=" + primeiro.h
            + "|primeiro_visivel=" + (primeiro.visivel ? 1 : 0)
            + "|pend_y=" + (pendPonto ? Math.round(pendPonto.y) : -1)
            + "|pend_h=" + (pend ? Math.round(pend.height) : -1)
            + "|cartao_h=" + cartaoH
            + "|cartao_diag=" + cartaoDiag
            + "|cartao_detalhe=" + cartaoDetalhe
            + "|cartao_alvo_h=" + cartaoAlvoH
            + "|cartao_compacto=" + cartaoCompacto
            + "|prosa_itens=" + prosa.itens
            + "|prosa_na_tela=" + prosa.naTela
            + "|prosa_caracteres=" + prosa.caracteres
            + "|prosa_caracteres_na_tela=" + prosa.caracteresNaTela
            + "|alvos=" + alvos.length)
        window.witnessEmitted = true
    }

    Timer {
        id: pump
        interval: 120
        repeat: true
        running: true
        onTriggered: {
            window.ticks += 1
            // Traço por tick, preservado no log do gate: sem isto uma cena que
            // não acendeu é indistinguível de uma que acendeu entre duas amostras.
            console.log("TRAÇO|tick=" + window.ticks
                + "|fase=" + window.statusPhase
                + "|band=" + (window.statusBandVisible ? 1 : 0)
                + "|banner=" + (window.showAttentionBanner ? 1 : 0)
                + "|erros=" + window.activeErrors.length
                + "|voo=" + (window.statusInFlight ? 1 : 0)
                + "|dados=" + (window.statusHasData ? 1 : 0))
            // A renovação é provocada pela mesma função que o botão "Tentar de
            // novo" da faixa invoca (precedente: check_central_loading.qml:334),
            // uma única vez, quando há dado preservado em tela. O que a faz ser
            // recusada é a ponte — não o harness.
            if (!window.renewalTried && window.ticks >= 8 && window.statusHasData
                    && !window.statusInFlight) {
                window.renewalTried = true
                window.retryStatus()
            }
            // Testemunha no ponto assentado: depois da renovação, sem consulta
            // em voo, com dado preservado OU com a fase de erro declarada.
            if (!window.witnessEmitted && window.ticks >= 18 && !window.statusInFlight
                    && (window.statusHasData || window.statusHasFailed))
                window.witness()
            if (window.ticks >= 40 && !window.witnessEmitted) {
                console.error("FAIL: a cena não produziu testemunha (band="
                    + (window.statusBandVisible ? 1 : 0)
                    + " banner=" + (window.showAttentionBanner ? 1 : 0)
                    + " erros=" + window.activeErrors.length
                    + " fase=" + window.statusPhase + ")")
                window.witnessEmitted = true
                pump.stop()
                Qt.exit(1)
            }
            // Segunda etapa: o "Ver detalhes" do cartão é ACIONADO (o `click()`
            // dispara o handler do controle, não impõe estado), e a altura depois
            // dele é testemunhada. É o que distingue "dobrou a orientação" de
            // "apagou a orientação".
            if (window.witnessEmitted && !window.clicked && window.ticks >= 24) {
                const cartoes = window.errorCards(window.rootSurface, [])
                const botao = cartoes.length > 0
                    ? window.buttonByLabel(cartoes[0], "Ver detalhes") : null
                if (botao !== null)
                    botao.click()
                window.clickGatilho = botao !== null ? "clique" : "ausente"
                window.clicked = true
                window.clickTick = window.ticks
            }
            // A altura expandida é lida dois ticks DEPOIS do clique: no mesmo
            // tick do `click()` o handler já roda, mas o `Layout.preferredHeight`
            // alterado só vira geometria na passada de layout seguinte. Medir no
            // tick do clique lia a forma compacta e o gate reprovaria um cartão
            // que devolve texto — foi assim que a bancada mediu "cresceu 0 px".
            if (window.clicked && !window.expandedEmitted && window.ticks >= window.clickTick + 2) {
                const cartoes = window.errorCards(window.rootSurface, [])
                if (cartoes.length > 0)
                    window.alturaExpandida = Math.round(cartoes[0].height)
                const prosa = cartoes.length > 0
                    ? window.prosaNaTela(cartoes[0])
                    : {"itens": 0, "naTela": 0, "caracteres": 0, "caracteresNaTela": 0}
                if (cartoes.length > 0)
                    window.tracoProsa("expandido", cartoes[0])
                // A prosa dobrada tem de voltar TODA. Um "Ver detalhes" que
                // re-oculta qualquer rótulo não devolve informação, e nenhuma
                // asserção de altura do gate perceberia isso sozinha.
                if (prosa.itens > 0 && prosa.naTela !== prosa.itens)
                    console.log("PROSA_INCOMPLETA|esperava=" + prosa.itens
                        + "|na_tela=" + prosa.naTela
                        + "|caracteres=" + prosa.caracteres
                        + "|caracteres_na_tela=" + prosa.caracteresNaTela)
                console.log("TESTEMUNHO2|cartao_expandido_h=" + window.alturaExpandida
                    + "|gatilho=" + window.clickGatilho
                    + "|tick_clique=" + window.clickTick
                    + "|tick_leitura=" + window.ticks
                    + "|compacto=" + (cartoes.length > 0 && cartoes[0].compact ? 1 : 0)
                    + "|detalhado=" + (cartoes.length > 0 && cartoes[0].detailed ? 1 : 0)
                    + "|prosa_na_tela_expandida=" + prosa.naTela
                    + "|prosa_caracteres_na_tela_expandida=" + prosa.caracteresNaTela)
                window.expandedEmitted = true
            }
            // Terceira etapa: a REFERÊNCIA. O mesmo cartão, com `compact` posto em
            // false, é a forma estendida que o produto mostraria sem a regra do
            // oitavo elo. Comparar a forma compacta expandida com ela é o que faz
            // "dobrou" ser verificável: a alternativa seria confiar num modelo de
            // altura por linha que a bancada teria de adivinhar.
            //
            // A atribuição quebra o binding vindo do `Main.qml` — aceitável aqui
            // porque esta é a última medição da janela, e a testemunha da forma
            // compacta (etapa 1) já foi impressa ANTES de qualquer mutação.
            if (window.expandedEmitted && !window.referenciaTrocada
                    && window.ticks >= window.clickTick + 4) {
                const cartoes = window.errorCards(window.rootSurface, [])
                if (cartoes.length > 0)
                    cartoes[0].compact = false
                window.referenciaTrocada = true
            }
            if (window.referenciaTrocada && !window.referenceEmitted
                    && window.ticks >= window.clickTick + 6) {
                const cartoes = window.errorCards(window.rootSurface, [])
                if (cartoes.length > 0)
                    window.alturaReferencia = Math.round(cartoes[0].height)
                const prosa = cartoes.length > 0
                    ? window.prosaNaTela(cartoes[0])
                    : {"itens": 0, "naTela": 0, "caracteres": 0, "caracteresNaTela": 0}
                if (cartoes.length > 0)
                    window.tracoProsa("referencia", cartoes[0])
                console.log("TESTEMUNHO3|cartao_referencia_h=" + window.alturaReferencia
                    + "|prosa_itens_ref=" + prosa.itens
                    + "|prosa_na_tela_ref=" + prosa.naTela
                    + "|prosa_caracteres_ref=" + prosa.caracteres
                    + "|prosa_caracteres_na_tela_ref=" + prosa.caracteresNaTela
                    + "|tick_leitura=" + window.ticks)
                window.referenceEmitted = true
            }
            if (window.ticks >= 44) {
                pump.stop()
                Qt.exit(window.witnessEmitted && window.expandedEmitted
                    && window.referenceEmitted ? 0 : 1)
            }
        }
    }
}
