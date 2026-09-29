// SPDX-License-Identifier: GPL-3.0-or-later
// UX-04 — gate das unidades de armazenamento nas SUPERFÍCIES REAIS do shell
// (AUDIT.md:124 exige "unidades localizadas e consistentes"). Cada checagem
// abaixo enuncia um requisito legível na auditoria; a falha dela cita o defeito
// concreto que o usuário veria. O vermelho originals (30 de 72, antes do
// formatador compartilhado) está na pasta de evidência
// docs/09-operations/evidence/2026-09-28-rc01-storage-units/.
//
// Coberto aqui: convergência entre as quatro páginas, rótulo IEC para divisor
// 1024, ausência ≠ zero, zero ≠ "não publicado", nada some abaixo da menor
// unidade, andar acima de GiB, separador decimal do locale e o cartão medido
// que chega do contrato como inteiro (`metricBytes`/`capacityBytes`).
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"

Window {
    id: harness
    visible: true
    width: 1400
    height: 900

    property int checks: 0
    property int failures: 0
    property int firstFailure: 0

    property var locale: Qt.locale("pt_BR")
    property var valores: [0, 512, 1000000, 1048576, 1073741824, 1500000000, 5368709120, 1099511627776]

    property var cores: {
        "backgroundColor": "#071019",
        "surfaceColor": "#0d1924",
        "raisedColor": "#122131",
        "borderColor": "#2a3a49",
        "textColor": "#f2f6fb",
        "mutedColor": "#9eabba",
        "cyanColor": "#13bdf2",
        "cyanDarkColor": "#0a5f85",
        "greenColor": "#59d35d",
        "amberColor": "#ff9f1a",
        "redColor": "#ff6b73"
    }

    Component {
        id: emuComp
        Emulation {}
    }
    Component {
        id: mainComp
        Main {}
    }
    Component {
        id: gameplayComp
        SteamGameplay {}
    }
    Component {
        id: themeComp
        ThemeCatalogPanel {}
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

    function pagina(nome, componente, extras) {
        const inicial = {}
        if (extras !== undefined) {
            for (const chave in cores)
                inicial[chave] = cores[chave]
            for (const chave in extras)
                inicial[chave] = extras[chave]
        }
        const objeto = componente.createObject(harness, inicial)
        check(objeto !== null, nome + " deve instanciar para a sonda de unidades")
        return objeto
    }

    function formatar(objeto, valor) {
        if (objeto === null)
            return "SEM OBJETO"
        const fn = objeto.formatBytes !== undefined ? "formatBytes" : "humanBytes"
        return String(objeto[fn](valor))
    }

    // Requisito: o mesmo número produz o mesmo texto em qualquer superfície.
    function testConvergencia() {
        const emu = pagina("Emulation", emuComp, {"emulation": {}, "sidebarColor": "#09131d"})
        const main = pagina("Main", mainComp, undefined)
        const game = pagina("SteamGameplay", gameplayComp, {"gameplay": {}})
        const tema = pagina("ThemeCatalogPanel", themeComp, undefined)
        const referencias = {
            "Emulation": emu,
            "Main": main,
            "SteamGameplay": game,
            "ThemeCatalogPanel": tema
        }
        for (let i = 0; i < valores.length; ++i) {
            const valor = valores[i]
            const esperado = formatar(main, valor)
            for (const nome in referencias) {
                const saida = formatar(referencias[nome], valor)
                check(saida === esperado,
                      "o valor " + valor + " B lê " + saida + " em " + nome
                      + " e " + esperado + " em Main — uma única grandeza não pode ter várias leituras")
            }
        }
    }

    // Requisito: divisor binário exige rótulo binário (KiB/MiB/GiB/TiB).
    function testRotuloBinaRio() {
        const emu = pagina("Emulation", emuComp, {"emulation": {}, "sidebarColor": "#09131d"})
        const tema = pagina("ThemeCatalogPanel", themeComp, undefined)
        const casos = [
            [emu, 1073741824, "GiB"],
            [emu, 1048576, "MiB"],
            [tema, 1073741824, "GiB"],
            [tema, 1048576, "MiB"]
        ]
        for (let i = 0; i < casos.length; ++i) {
            const saida = formatar(casos[i][0], casos[i][1])
            check(saida.indexOf(casos[i][2]) >= 0,
                  "valor " + casos[i][1] + " saiu como \"" + saida
                  + "\": divisor 1024 com rótulo decimal afirma uma grandeza "
                  + (casos[i][1] === 1073741824 ? "7 % menor que a real" : "que não é a medida")
                  + "; o rótulo tem de dizer IEC (" + casos[i][2] + ")")
        }
    }

    // Requisito: grandeza ausente não é medida, e não pode virar zero nem frase.
    function testAusencia() {
        const nomes = ["Emulation", "Main", "SteamGameplay", "ThemeCatalogPanel"]
        const componentes = [emuComp, mainComp, gameplayComp, themeComp]
        const extras = [{"emulation": {}, "sidebarColor": "#09131d"}, undefined, {"gameplay": {}}, undefined]
        for (let i = 0; i < nomes.length; ++i) {
            const paginaObj = pagina(nomes[i], componentes[i], extras[i])
            const ausente = formatar(paginaObj, undefined)
            check(ausente === "—",
                  nomes[i] + " lê ausência como \"" + ausente
                  + "\": dado não medido tem representação própria (traço), não 0 B nem prosa")
        }
    }

    // Requisito: zero medido é zero, não "não publicado".
    function testZeroReal() {
        const emu = pagina("Emulation", emuComp, {"emulation": {}, "sidebarColor": "#09131d"})
        const saida = formatar(emu, 0)
        check(saida === "0 B",
              "Emulation lê zero medido como \"" + saida
              + "\": confundir 0 byte com dado ausente é a mesma troca de grandeza "
              + "que a UX-03 fechou em readiness.percent")
    }

    // Requisito: nenhum valor não nulo pode sumir abaixo da menor unidade.
    function testNadaSome() {
        const nomes = ["Emulation", "Main", "SteamGameplay", "ThemeCatalogPanel"]
        const componentes = [emuComp, mainComp, gameplayComp, themeComp]
        const extras = [{"emulation": {}, "sidebarColor": "#09131d"}, undefined, {"gameplay": {}}, undefined]
        for (let i = 0; i < nomes.length; ++i) {
            const saida = formatar(pagina(nomes[i], componentes[i], extras[i]), 512)
            check(saida.indexOf("0 ") !== 0 && saida !== "0 B" && saida.indexOf("0.0") !== 0 && saida !== "0",
                  nomes[i] + " mostra 512 B como \"" + saida
                  + "\": um arquivo pequeno não pode desaparecer da tela")
        }
    }

    // Requisito: há andar acima de GiB (o acervo mede TB).
    function testTeto() {
        const nomes = ["Emulation", "Main", "SteamGameplay", "ThemeCatalogPanel"]
        const componentes = [emuComp, mainComp, gameplayComp, themeComp]
        const extras = [{"emulation": {}, "sidebarColor": "#09131d"}, undefined, {"gameplay": {}}, undefined]
        for (let i = 0; i < nomes.length; ++i) {
            const saida = formatar(pagina(nomes[i], componentes[i], extras[i]), 1099511627776)
            check(saida.indexOf("TiB") >= 0,
                  nomes[i] + " lê 1 TiB como \"" + saida
                  + "\": sem andar superior o usuário compara 1024.00 GiB com 1048576.0 MB "
                  + "para a mesma grandeza")
        }
    }

    // Requisito do auditor: unidades LOCALIZADAS — separador decimal do locale.
    function testLocalizado() {
        const nomes = ["Emulation", "Main", "SteamGameplay", "ThemeCatalogPanel"]
        const componentes = [emuComp, mainComp, gameplayComp, themeComp]
        const extras = [{"emulation": {}, "sidebarColor": "#09131d"}, undefined, {"gameplay": {}}, undefined]
        for (let i = 0; i < nomes.length; ++i) {
            const saida = formatar(pagina(nomes[i], componentes[i], extras[i]), 1500000000)
            check(saida.indexOf(locale.decimalPoint) >= 0,
                  nomes[i] + " imprime " + saida + " com separador de milhar/decimal "
                  + "estrangeiro: o locale medido é " + locale.name
                  + " e usa \"" + locale.decimalPoint + "\" como separador decimal")
        }
    }

    // Requisito: o cartão medido mostra a medida do contrato, formatada uma única
    // vez. `adapters/emulation.py` publica `metricBytes`/`capacityBytes` inteiros;
    // a página não pode ecoar texto cru, perder o total do volume, nem trocar
    // ausência por zero.
    function testCartaoMedido() {
        const emu = pagina("Emulation", emuComp, {"emulation": {}, "sidebarColor": "#09131d"})
        const livro = {
            "id": "storage-volume",
            "title": "Volume de dados",
            "detail": "Espaço livre do volume de dados.",
            "state": "ready",
            "statusLabel": "Espaço disponível",
            "metricBytes": 150000000000,
            "capacityBytes": 536870912000
        }
        const saida = emu.cardMetric(livro)
        check(saida === emu.formatBytes(livro.metricBytes) + " / " + emu.formatBytes(livro.capacityBytes),
              "o cartão do volume saiu como \"" + saida + "\": a grandeza medida viaja inteira "
              + "no contrato, então a tela deve ler os dois números pelo formatador compartilhado "
              + "— nem texto cru, nem total escondido")
        check(saida.toLowerCase().indexOf("byte") < 0,
              "o cartão do volume saiu como \"" + saida + "\": byte cru na tela é a troca de "
              + "grandeza que a UX-04 veio fechar")

        const bucket = {
            "id": "storage-roms",
            "title": "ROMs",
            "detail": "3 arquivo(s).",
            "state": "ready",
            "statusLabel": "Verificado",
            "metricBytes": 1073741824
        }
        const saidaBucket = emu.cardMetric(bucket)
        check(saidaBucket === emu.formatBytes(bucket.metricBytes),
              "o cartão de bucket saiu como \"" + saidaBucket
              + "\": sem capacidade publicada não há segundo número a inventar")

        const zero = {
            "id": "storage-saves",
            "title": "Saves",
            "detail": "0 arquivo(s).",
            "state": "empty",
            "statusLabel": "Vazio",
            "metricBytes": 0
        }
        check(emu.cardMetric(zero) === "0 B",
              "zero medido no cartão saiu como \"" + emu.cardMetric(zero)
              + "\": 0 byte é uma medida, não ausência")

        const ausente = {
            "id": "storage-volume",
            "title": "Volume de dados",
            "detail": "Espaço do volume indisponível.",
            "state": "attention",
            "statusLabel": "Não verificado",
            "metricBytes": null,
            "capacityBytes": null
        }
        check(emu.cardMetric(ausente) === "—",
              "ausência no cartão saiu como \"" + emu.cardMetric(ausente)
              + "\": dado não medido tem traço próprio")

        const legado = {
            "id": "controller-count",
            "title": "Controles",
            "detail": "2 dispositivo(s).",
            "state": "ready",
            "statusLabel": "Pronto",
            "metric": "2"
        }
        check(emu.cardMetric(legado) === "2",
              "um cartão sem medida de bytes regrediu para \"" + emu.cardMetric(legado)
              + "\": metric/count/installed/required continuam sendo a fonte dos demais cartões")
    }

    // Requisito: onde a frase é necessária, a grandeza dentro dela continua
    // localizada. Dois textos do shell imprimiam o número cru do contrato.
    function testProsaLocalizada() {
        const main = pagina("Main", mainComp, undefined)
        const resumo = main.taskResultSummary({
            "state": "completed",
            "type": "library.bitrot",
            "result": {"checked": 12, "bytesRead": 1073741824, "suspect": 1}
        })
        check(resumo.indexOf("byte") < 0,
              "o resumo da varredura saiu como \"" + resumo + "\": byte cru na tela não tem "
              + "separador decimal nem andar, e é a grandeza que o usuário compara com o volume")
        check(resumo === "12 arquivo(s), 1,00 GiB, 1 suspeito(s)",
              "o resumo da varredura saiu como \"" + resumo
              + "\": a contagem de arquivos e suspeitos é do jeito que está, só a medida muda")

        const rotulo = main.auditItemLabel({
            "category": "duplicate",
            "relativePath": "steamapps/common/Jogo",
            "sizeBytes": 1500000000
        })
        check(rotulo.indexOf("bytes") < 0,
              "a linha da quarentena saiu como \"" + rotulo
                      + "\": o caminho e a categoria continuam legíveis; o que muda é a medida")
        check(rotulo === "duplicate · steamapps/common/Jogo · 1,40 GiB",
              "a linha da quarentena saiu como \"" + rotulo
              + "\": categoria e caminho continuam legíveis, a medida sai do formatador")
        check(main.auditItemLabel({"category": "update", "relativePath": "x", "sizeBytes": 0})
              === "update · x · 0 B",
              "a linha da quarentena perdeu o zero medido")
    }

    // Requisito: a leitura é normalizada — nunca cai abaixo da unidade escolhida.
    // É o que separa um andar binário de um limiar decimal aplicado a um divisor
    // binário: 1.000.000 B lido como "0,95 MiB" afirma uma grandeza menor do que é.
    function testNormalizacao() {
        const nomes = ["Emulation", "Main", "SteamGameplay", "ThemeCatalogPanel"]
        const componentes = [emuComp, mainComp, gameplayComp, themeComp]
        const extras = [{"emulation": {}, "sidebarColor": "#09131d"}, undefined, {"gameplay": {}}, undefined]
        const casos = [1000000, 1024, 1048576, 1073741824]
        for (let i = 0; i < nomes.length; ++i) {
            const paginaObj = pagina(nomes[i], componentes[i], extras[i])
            for (let j = 0; j < casos.length; ++j) {
                const saida = formatar(paginaObj, casos[j])
                check(saida.indexOf("0" + locale.decimalPoint) !== 0,
                      nomes[i] + " lê " + casos[j] + " B como \"" + saida
                      + "\": a mantissa abaixo de 1 significa que o andar escolhido não é "
                      + "o andar do divisor usado")
            }
        }
    }

    function grupo(nome, execucao) {
        // Uma função ausente na página lança e abortaria o Timer inteiro: o gate
        // travaria até o timeout sem nomear o defeito. Cada grupo é isolado.
        try {
            execucao()
        } catch (erro) {
            check(false, nome + " não pôde ser verificado: " + erro)
        }
    }

    function encerrar() {
        if (failures === 0)
            console.log("check_storage_units: " + checks + " verificação(ões) ok")
        else
            console.log("check_storage_units: " + failures + " falha(s) de " + checks
                        + " (primeira em #" + firstFailure + ")")
        Qt.exit(failures === 0 ? 0 : 1)
    }

    Timer {
        interval: 120
        running: true
        repeat: false
        onTriggered: {
            grupo("convergência", testConvergencia)
            grupo("rótulo binário", testRotuloBinaRio)
            grupo("ausência", testAusencia)
            grupo("zero medido", testZeroReal)
            grupo("nenhum valor some", testNadaSome)
            grupo("andar acima de GiB", testTeto)
            grupo("separador localizado", testLocalizado)
            grupo("cartão medido", testCartaoMedido)
            grupo("prosa localizada", testProsaLocalizada)
            grupo("normalização", testNormalizacao)
            harness.encerrar()
        }
    }
}
