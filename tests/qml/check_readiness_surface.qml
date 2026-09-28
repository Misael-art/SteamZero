// SPDX-License-Identifier: GPL-3.0-or-later
// UX-03: a superfície consome o contrato de prontidão em vez de adivinhar por
// percentual.
//
// O que este harness protege é a regra que a auditoria (docs/01-product/AUDA)
// registrou como causa: um único `percent >= 80` pintava categoria codificada,
// proporção real e simples existência de jogos com a mesma cor, e um número
// ausente era transformado em 0%. Aqui o estado decide a cor, o número só
// aparece quando existe medição com dimensão nomeada, e um payload antigo (v1)
// continua legível sem ser promovido a "pronto".
import QtQuick
import QtQuick.Window
import "../../src/steamzero/ui/qml"
import "../../src/steamzero/ui/qml/readiness.js" as Readiness
import "readiness_fixture.js" as Fixtures

Window {
    id: harness
    visible: true
    width: 1400
    height: 900
    property int failures: 0
    property int checks: 0
    property int firstFailure: 0

    function check(condition, message) {
        checks += 1
        if (condition)
            return
        if (firstFailure === 0)
            firstFailure = checks
        failures += 1
        console.error("FAIL: " + message)
    }

    function allChildren(item, result) {
        if (!item)
            return result
        const children = item.childItems !== undefined ? item.childItems : item.children
        if (!children)
            return result
        for (let index = 0; index < children.length; index++) {
            const child = children[index]
            result.push(child)
            allChildren(child, result)
        }
        return result
    }

    function itemWithObjectName(root, name) {
        const children = allChildren(root, [])
        for (let index = 0; index < children.length; index++) {
            const candidate = children[index]
            if (candidate.objectName !== name)
                continue
            let current = candidate
            let visible = true
            while (current) {
                if (current.visible === false) {
                    visible = false
                    break
                }
                current = current.parent
            }
            if (visible)
                return candidate
        }
        return null
    }

    // Versão plural do procurador: uma lista renderizada tem N delegados com o
    // mesmo objectName, e o que se cobra é quantos deles existem.
    function itemsWithObjectName(root, name) {
        const children = allChildren(root, [])
        const encontrados = []
        for (let index = 0; index < children.length; index++) {
            const candidate = children[index]
            if (candidate.objectName !== name)
                continue
            let current = candidate
            let visible = true
            while (current) {
                if (current.visible === false) {
                    visible = false
                    break
                }
                current = current.parent
            }
            if (visible)
                encontrados.push(candidate)
        }
        return encontrados
    }

    // --- fixtures do contrato v2 ---------------------------------------------
    readonly property var cores: ({
        "green": "#59d35d", "amber": "#ff9f1a", "red": "#ff6b73", "muted": "#9eabba"
    })

    function medido(estado, numerador, denominador, extras) {
        return Fixtures.medido(estado, numerador, denominador, extras)
    }

    // Gameplay com bloqueio e medidor cheio: o único formato que distingue
    // "a página pergunta ao contrato" de "a página decide pelo número".
    function comBloqueioMedido() {
        return {
            "games": [{"id": "3311720", "name": "Gimmick! 2 Demo"}],
            "environment": [],
            "readiness": medido("blocked", 4, 4, {
                "label": "Ação necessária", "cause": "Perfil ausente.",
                "action": "Crie um perfil antes de iniciar."}),
            "hardware": {"tdpMin": 3, "tdpMax": 15, "refreshHz": 60},
            "currentProfile": {"gameId": "3311720", "scope": "game"}
        }
    }

    function semMedicao(estado) {
        return Fixtures.semMedicao(estado, ({}))
    }

    // O contrato que o app publicava antes da UX-03: número sem dimensão.
    readonly property var legado: ({
        "percent": 85,
        "title": "Pronto com 1 ajuste recomendado",
        "detail": "Hardware compatível · Perfil seguro disponível",
        "blockers": []
    })

    function testSemanticaDoContrato() {
        const pronto = medido("ready", 3, 3)
        const atencao = medido("attention", 2, 3)
        const bloqueado = medido("blocked", 2, 3, {
            "label": "Ação necessária",
            "cause": "Gamescope não está disponível (SteamZero).",
            "action": "Instale ou ative Gamescope (SteamZero).",
            "blockers": ["Instale ou ative Gamescope (SteamZero)."]})
        const naoVerificado = semMedicao("unverified")

        check(Readiness.state(pronto) === "ready", "estado vem do contrato")
        check(Readiness.tone(pronto) === "green", "pronto é verde")
        check(Readiness.tone(atencao) === "amber", "atenção é âmbar")
        check(Readiness.tone(bloqueado) === "red",
              "impedimento observado é vermelho, não a mesma cor de atenção — era isso que "
              + "a regra única de percentual apagava")
        check(Readiness.tone(naoVerificado) === "muted",
              "sem observação não há cor de sucesso nem de falha")
        check(Readiness.tone({}) === "muted", "payload vazio nunca é verde")
        check(Readiness.tone({"state": "blocked", "measure": {"percent": 100}}) === "red",
              "um percentual alto não pode salvar um bloqueio")

        check(Readiness.percent(atencao) === 67, "proporção medida mostra o número")
        check(Readiness.percentText(atencao, "—") === "67%", "número vem formatado")
        check(Readiness.ratioText(atencao) === "2/3", "numerador e denominador ficam visíveis")
        check(Readiness.dimensionText(atencao) === "requisitos obrigatórios atendidos",
              "a dimensão precisa ser nomeada: 67% de quê?")

        check(Readiness.isMeasured(naoVerificado) === false,
              "denominador zero não é uma medição")
        check(Readiness.percent(naoVerificado) === null, "percentual ausente é null, não 0")
        check(Readiness.percentText(naoVerificado, "—") === "—",
              "o número ausente aparece como traço, nunca como 0%")
        check(Readiness.showsProgress(naoVerificado) === false,
              "sem medição não há barra de progresso")
        check(Readiness.ratioText(naoVerificado) === "", "sem numerador não há fração")

        check(Readiness.headline(legado) === "Pronto com 1 ajuste recomendado",
              "payload antigo continua legível via title")
        check(Readiness.cause(legado) === "Hardware compatível · Perfil seguro disponível",
              "payload antigo continua legível via detail")
        check(Readiness.isMeasured(legado) === false,
              "um percentual sem dimensão conhecida não é exibido como medição")
        check(Readiness.tone(legado) === "muted",
              "payload antigo não tem estado verificado; promover a verde seria pintura")
        check(Readiness.accent(bloqueado, harness.cores) === harness.cores.red,
              "a tinta sai do tom: uma página reimplementando essa troca reabre a UX-03")
        check(Readiness.accent(naoVerificado, harness.cores) === harness.cores.muted,
              "estado não observado não recebe verde nem vermelho")
        // --- o fundo do cartão comunica o tom --------------------------------
        // O requisito não é o hexagonal que a escolha caiu: é (a) cada tom
        // observado ter fundo próprio, (b) os três serem distinguíveis entre si e
        // carregarem a família de matiz daquele tom, (c) o estado não observado
        // não receber tinta nenhuma, e (d) a tinta clara do tema continuar
        // legível sobre cada fundo publicado. Cobrir isso por literal de cor
        // deixaria o requisito sem prova e puniria qualquer reimplementação
        // equivalente.
        const fundoPronto = Readiness.surface(pronto)
        const fundoBloqueado = Readiness.surface(bloqueado)
        const fundoAtencao = Readiness.surface(atencao)
        check(fundoPronto !== "" && fundoBloqueado !== "" && fundoAtencao !== "",
              "estado observado tem fundo próprio, em vez da superfície neutra do tema")
        check(fundoPronto !== fundoBloqueado && fundoBloqueado !== fundoAtencao
                && fundoPronto !== fundoAtencao,
              "os três tons observáveis se distinguem entre si: um fundo único para tudo "
              + "recria a regra que apagava a diferença")
        const canaisPronto = Fixtures.canais(fundoPronto)
        const canaisBloqueado = Fixtures.canais(fundoBloqueado)
        const canaisAtencao = Fixtures.canais(fundoAtencao)
        check(canaisPronto !== null && canaisPronto.g > canaisPronto.r
                && canaisPronto.g > canaisPronto.b,
              "o fundo de 'pronto' é da família do verde: é a cor do sucesso, não uma cor qualquer")
        check(canaisBloqueado !== null && canaisBloqueado.r > canaisBloqueado.g
                && canaisBloqueado.r > canaisBloqueado.b
                && canaisBloqueado.g === Fixtures.minimo(canaisBloqueado),
              "o fundo do bloqueio é vermelho fechado (verde é o canal mínimo), e não o âmbar "
              + "de atenção — é a mesma distinção que o tom exige")
        check(canaisAtencao !== null && canaisAtencao.b === Fixtures.minimo(canaisAtencao)
                && canaisAtencao.r > canaisAtencao.b && canaisAtencao.g > canaisAtencao.b,
              "o fundo de atenção é quente (azul é o canal mínimo): âmbar, não vermelho")
        check(Readiness.surface(naoVerificado) === "",
              "sem estado não há tinta de sucesso: a página usa a cor neutra do tema")
        const tintaClara = "#f2f6fb"
        check(Fixtures.contraste(tintaClara, fundoPronto) >= 7
                && Fixtures.contraste(tintaClara, fundoBloqueado) >= 7
                && Fixtures.contraste(tintaClara, fundoAtencao) >= 7,
              "todo fundo publicado mantém a tinta do tema em 7:1 ou mais — a norma de "
              + "contraste do projeto para superfícies fixas")

        check(Readiness.cause(atencao) === "Requisito ausente.",
              "causa é campo próprio do contrato")
        check(Readiness.action(bloqueado) === "Instale ou ative Gamescope (SteamZero).",
              "próxima ação vem do contrato")
        check(Readiness.blockers(bloqueado).length === 1, "bloqueios seguem listados")
        check(Readiness.dimensionCaption(atencao) === "requisitos obrigatórios atendidos",
              "o número medido chega acompanhado do que foi medido")
        check(Readiness.dimensionCaption(naoVerificado) === "",
              "sem medição a chave do contrato não vira texto de interface")

        // --- o estado "não observamos", que antes só existia como 0% ---------
        // O formato abaixo é o que `not_measured()` do domínio publica; conferido
        // chave a chave porque o leitor QML precisa sobreviver a ele.
        const inspecionado = Readiness.notInspected("Verificação indisponível",
            "A bridge local ainda não publicou o catálogo.", null,
            ["Backend de emulação ainda não conectado"])
        check(Object.keys(inspecionado).join(",") === Object.keys(pronto).join(","),
              "o fallback tem exatamente as onze chaves que um produtor publica")
        check(Object.keys(inspecionado.measure).join(",")
                === Object.keys(pronto.measure).join(","),
              "e o measure tem as sete chaves do contrato, nem uma a mais")
        check(inspecionado.measure.dimension === "not_measured",
              "dimensão do fallback é not_measured, como no domínio")
        check(Readiness.contractVersion(inspecionado) === 2,
              "uma página sem backend publica prontidão v2, não um número solto")
        check(Readiness.tone(inspecionado) === "muted", "fallback não alega cor de sucesso")
        check(Readiness.percentText(inspecionado, "—") === "—",
              "fallback não vira 0%")
        check(Readiness.absentReason(inspecionado) === "not_measured",
              "a ausência de número vem nomeada, como exige o contrato")
        check(Readiness.headline(inspecionado) === "Verificação indisponível",
              "o fallback diz o que está havendo")
        check(Readiness.blockers(inspecionado).length === 1, "o fallback pode ter bloqueios")

        const legadoConvertido = Readiness.normalize(legado, inspecionado)
        check(Readiness.contractVersion(legadoConvertido) === 2,
              "payload antigo é lido como v2 em vez de estourar")
        check(Readiness.headline(legadoConvertido) === "Pronto com 1 ajuste recomendado",
              "o texto publicado permanece, só muda a alegação")
        check(Readiness.percent(legadoConvertido) === null,
              "um percentual legado não é reconstruído: sem dimensão não há proporção")
        check(Readiness.absentReason(legadoConvertido) === "legacy_contract",
              "a razão da ausência de número fica registrada")
        check(Readiness.tone(legadoConvertido) === "muted",
              "payload antigo não promove nada a verde")
        const prontoNormalizado = Readiness.normalize(pronto, inspecionado)
        check(prontoNormalizado === pronto, "prontidão v2 passa intacta")
        check(Readiness.normalize({"foo": 1}, inspecionado) === inspecionado,
              "dicionário que não é prontidão cai no fallback declarado")
    }

    function testEmulationRenderizaONumeroSomenteComMedicao() {
        const objeto = emulationComponent.createObject(harness, {
            "width": 1360, "height": 820,
            "backgroundColor": "#071019", "sidebarColor": "#09131d",
            "surfaceColor": "#0d1924", "raisedColor": "#122131",
            "borderColor": "#2a3a49", "textColor": "#f2f6fb", "mutedColor": "#9eabba",
            "cyanColor": "#13bdf2", "cyanDarkColor": "#0a5f85",
            "greenColor": harness.cores.green, "amberColor": harness.cores.amber,
            "redColor": harness.cores.red,
            "emulation": {
                "platforms": [{
                    "id": "switch", "name": "Nintendo Switch", "iconKey": "switch",
                    "state": "blocked", "statusLabel": "Ação necessária",
                    "selectedScope": "global", "selectedArea": "overview",
                    "readiness": harness.medido("blocked", 0, 1, {
                        "label": "Ação necessária", "cause": "Keys ausente.",
                        "action": "Importe keys e firmware próprios antes de iniciar jogos.",
                        "blockers": ["Importe keys e firmware próprios antes de iniciar jogos."]
                    }),
                    "emulators": [{"id": "eden", "name": "Eden", "state": "ready"}],
                    "games": []
                }]
            }
        })
        check(objeto !== null,
              "a página de emulação constrói — sem ela nenhuma verificação abaixo acontece")
        if (!objeto)
            return
        objeto.globalManagementActive = false
        check(objeto.readinessTone() === "red",
              "o cartão da Emulação colore pelo estado, não pelo percentual")

        const titulo = harness.itemWithObjectName(objeto, "readinessHeadline")
        const causa = harness.itemWithObjectName(objeto, "readinessCause")
        const valor = harness.itemWithObjectName(objeto, "readinessValue")
        check(titulo !== null && titulo.text === "Ação necessária",
              "o título do cartão é o label publicado")
        check(causa !== null && causa.text === "Keys ausente.",
              "a causa publicada chega ao usuário")
        check(valor !== null && valor.text === "0%",
              "com medição real o número aparece (0/1 é uma proporção legível)")
        const dimensaoMedida = harness.itemWithObjectName(objeto, "readinessDimension")
        check(dimensaoMedida !== null
                && dimensaoMedida.text === "requisitos obrigatórios atendidos",
              "o cartão da Emulação nomeia a dimensão do número que exibe")

        objeto.emulation = {
            "platforms": [{
                "id": "switch", "name": "Nintendo Switch", "iconKey": "switch",
                "state": "unverified", "statusLabel": "Verificação pendente",
                "selectedScope": "global", "selectedArea": "overview",
                "readiness": harness.semMedicao("unverified"),
                "emulators": [], "games": []
            }]
        }
        check(objeto.readinessTone() === "muted",
              "sem observação o cartão não pode parecer sucesso nem falha")
        const valorAusente = harness.itemWithObjectName(objeto, "readinessValue")
        check(valorAusente !== null && valorAusente.text === "—",
              "denominador zero mostra traço; 0% seria inventar uma medição")
        const dimensaoAusente = harness.itemWithObjectName(objeto, "readinessDimension")
        check(dimensaoAusente === null,
              "sem medição a linha da dimensão não aparece: não há número para qualificar")
        check(Qt.colorEqual(objeto.readinessSurface(), objeto.surfaceColor),
              "sem estado conhecido o cartão fica na superfície neutra da página")

        // --- a página delega, não reimplementa -------------------------------
        // Descoberto por mutação: trocar `Readiness.tone(readiness)` por uma regra
        // local `percent >= 80` passava por todas as verificações acima, porque
        // nenhuma delas punha a página diante de um bloqueio com percentual alto.
        // É o caso que a UX-03 existe para responder, e ele precisa ser pinado na
        // superfície, não só na biblioteca compartilhada.
        const bloqueioMedido = harness.medido("blocked", 4, 4, {
            "label": "Ação necessária", "cause": "Perfil ausente.",
            "action": "Crie um perfil antes de iniciar."
        })
        objeto.emulation = {
            "platforms": [{
                "id": "switch", "name": "Nintendo Switch", "iconKey": "switch",
                "state": "blocked", "statusLabel": "Ação necessária",
                "selectedScope": "global", "selectedArea": "overview",
                "readiness": bloqueioMedido,
                "emulators": [], "games": []
            }]
        }
        check(objeto.readinessTone() === "red",
              "100% medido não salva um bloqueio na superfície da plataforma")
        check(Qt.colorEqual(objeto.readinessColor(), harness.cores.red),
              "a tinta do cartão vem do estado publicado")
        // Bateria de mutações: deixar o fundo fixo em `surfaceColor` escapava de
        // todas as verificações acima — a borda vinha do estado, e o cartão inteiro
        // continuava com a superfície neutra de um bloqueio. O pin é a delegação,
        // não o valor: uma página que escrevesse a tinta à mão passaria num estado
        // e falharia no próximo.
        check(objeto.readinessSurface() === Readiness.surface(bloqueioMedido),
              "o fundo do cartão é a tinta que o módulo publica para o estado atual")
        check(objeto.readinessSurface() !== objeto.surfaceColor,
              "com estado observado o cartão não fica na superfície neutra da página")

        // --- a causa e a ação chegam inteiras, não cortadas ------------------
        // Estado → causa → próxima ação é a jornada que a UX-03 exige. Um
        // `ElideRight` com `maximumLineCount: 1` deixava ver o estado e o número
        // e escondia justamente as duas frases que dizem o que fazer: o texto
        // estava no contrato, nunca no cartão.
        const causaEmulacao = harness.itemWithObjectName(objeto, "readinessCause")
        check(causaEmulacao !== null && causaEmulacao.elide === Text.ElideNone,
              "a causa não é truncada: elipse cortaria o texto que o contrato publicou")
        check(causaEmulacao !== null && causaEmulacao.maximumLineCount > 1,
              "a causa tem mais de uma linha disponível — o limite de uma linha era a elipse")
        check(causaEmulacao !== null && causaEmulacao.wrapMode === Text.WordWrap,
              "a causa quebra palavra em vez de estourar a largura do cartão")
        const acaoEmulacao = harness.itemWithObjectName(objeto, "readinessAction")
        check(acaoEmulacao !== null && acaoEmulacao.text === "Crie um perfil antes de iniciar.",
              "a próxima ação publicada aparece no cartão da plataforma")
        check(acaoEmulacao !== null && acaoEmulacao.elide === Text.ElideNone,
              "a ação também não é cortada: instrução truncada não é instrução")

        // Uma causa de produtor real, do comprimento que a elipse matava.
        const atencaoLonga = harness.medido("attention", 2, 3, {
            "label": "Catálogo não verificado",
            "cause": "Confirme conta, assinatura, região e catálogo no serviço: "
                + "nada disso foi verificado aqui.",
            "action": "Disponibilize um abridor padrão (xdg-open) para abrir o serviço."
        })
        objeto.emulation = {
            "platforms": [{
                "id": "steamlink", "name": "Steam Link", "iconKey": "steam",
                "state": "unverified", "statusLabel": "Verificação pendente",
                "selectedScope": "global", "selectedArea": "overview",
                "readiness": atencaoLonga,
                "emulators": [], "games": []
            }]
        }
        const causaLonga = harness.itemWithObjectName(objeto, "readinessCause")
        check(causaLonga !== null && causaLonga.lineCount > 1,
              "com a largura do cartão a causa longa ocupa mais de uma linha, então houve "
              + "quebra de linha e não corte")
        check(causaLonga !== null
                && causaLonga.contentWidth <= causaLonga.width + 1,
              "o texto quebrado continua dentro da largura do cartão")
        // Segundo estado, mesma página: é isto que impede uma tinta escrita à mão
        // de passar por delegação no único caso que o teste exercitava antes.
        check(objeto.readinessSurface() === Readiness.surface(atencaoLonga),
              "a página segue o módulo quando o estado muda, em vez de guardar uma cor")
        check(objeto.readinessSurface() !== Readiness.surface(bloqueioMedido),
              "atenção e bloqueio têm fundos distintos na mesma superfície")
        objeto.destroy()
    }

    function testSteamGameplayRenderizaOCampoPublicado() {
        const pagina = gameplayComponent.createObject(harness, {
            "width": 1208, "height": 696,
            "backgroundColor": "#071019", "surfaceColor": "#0d1924",
            "raisedColor": "#122131", "borderColor": "#2a3a49",
            "textColor": "#f2f6fb", "mutedColor": "#9eabba",
            "cyanColor": "#13bdf2", "cyanDarkColor": "#0a5f85",
            "greenColor": harness.cores.green, "amberColor": harness.cores.amber,
            "redColor": harness.cores.red,
            "desktopStatus": ({}),
            "gameplay": {
                "games": [{"id": "3311720", "name": "Gimmick! 2 Demo"}],
                "environment": [],
                "readiness": harness.medido("blocked", 2, 3, {
                    "label": "Ação necessária",
                    "cause": "Gamescope não está disponível (SteamZero).",
                    "action": "Instale ou ative Gamescope (SteamZero)."
                }),
                "hardware": {"tdpMin": 3, "tdpMax": 15, "refreshHz": 60},
                "currentProfile": {"gameId": "3311720", "scope": "game"}
            }
        })
        check(pagina !== null,
              "a página do ambiente constrói — sem ela nenhuma verificação abaixo acontece")
        if (!pagina)
            return
        const titulo = harness.itemWithObjectName(pagina, "gameplayReadinessHeadline")
        const causa = harness.itemWithObjectName(pagina, "gameplayReadinessCause")
        const valor = harness.itemWithObjectName(pagina, "gameplayReadinessValue")
        check(pagina.readinessTone() === "red",
              "gameplay bloqueado é vermelho mesmo com 67% medido")
        check(titulo !== null && titulo.text === "Ação necessária",
              "o cabeçalho do ambiente usa o label publicado")
        check(causa !== null && causa.text === "Gamescope não está disponível (SteamZero).",
              "a causa chega ao usuário em vez de um resumo inventado")
        check(valor !== null && valor.text === "67%",
              "com medição o número aparece, acompanhado da dimensão")
        const dimensao = harness.itemWithObjectName(pagina, "gameplayReadinessDimension")
        check(dimensao !== null && dimensao.text === "requisitos obrigatórios atendidos",
              "67% sem dimensão nomeada repete o problema que a UX-03 eliminou")

        // Mesmo caso da Emulação: um bloqueio com o medidor cheio. A regra local
        // `percent >= 80` só é pega se a página for posta diante dele.
        const ambienteBloqueado = harness.comBloqueioMedido()
        pagina.gameplay = ambienteBloqueado
        check(pagina.readinessTone() === "red",
              "100% medido não salva um bloqueio no cartão do ambiente")
        check(Qt.colorEqual(pagina.readinessColor(), harness.cores.red),
              "a tinta do cartão do ambiente vem do estado publicado")
        // A borda vinha do estado; o fundo é a outra metade da leitura de
        // "isto está bloqueado". O pino é a delegação ao módulo, não o valor:
        // trocar `readinessSurface()` por uma cor fixa passava no harness, e é
        // o que a segunda estado abaixo continua a pegar.
        check(Qt.colorEqual(pagina.readinessSurfaceColor,
                            Readiness.surface(ambienteBloqueado.readiness)),
              "o fundo do cartão do ambiente é a tinta que o módulo publica para o estado atual")
        check(!Qt.colorEqual(pagina.readinessSurfaceColor, pagina.surfaceColor),
              "com bloqueio publicado o cartão do ambiente deixa a superfície neutra do tema")

        // No ambiente faltava metade da jornada: o cartão dizia o estado e o
        // número, mas nem a causa inteira nem a próxima ação publicada pelo
        // contrato chegavam à tela.
        const causaAmbiente = harness.itemWithObjectName(pagina, "gameplayReadinessCause")
        check(causaAmbiente !== null && causaAmbiente.elide === Text.ElideNone,
              "a causa do ambiente não é cortada")
        check(causaAmbiente !== null && causaAmbiente.wrapMode === Text.WordWrap,
              "a causa do ambiente quebra palavra em vez de estourar o cartão")
        const acaoAmbiente = harness.itemWithObjectName(pagina, "gameplayReadinessAction")
        check(acaoAmbiente !== null,
              "o cartão do ambiente entrega a próxima ação, não só o estado")
        check(acaoAmbiente !== null
                && acaoAmbiente.text === "Crie um perfil antes de iniciar.",
              "a ação exibida é a publicada no contrato, palavra por palavra")
        pagina.gameplay = {
            "games": [{"id": "3311720", "name": "Gimmick! 2 Demo"}],
            "environment": [],
            "readiness": harness.medido("blocked", 1, 4, {
                "label": "Ação necessária",
                "cause": "Gamescope não está disponível (SteamZero). Instale ou ative o "
                    + "compositor para que o perfil de lançamento seja verificado.",
                "action": "Instale Gamescope e reabra a verificação do ambiente."}),
            "hardware": {"tdpMin": 3, "tdpMax": 15, "refreshHz": 60},
            "currentProfile": {"gameId": "3311720", "scope": "game"}
        }
        const causaLongaAmbiente = harness.itemWithObjectName(pagina, "gameplayReadinessCause")
        check(causaLongaAmbiente !== null && causaLongaAmbiente.lineCount > 1,
              "a causa longa do ambiente ocupa mais de uma linha em vez de sumir em reticências")

        // Outro tom na mesma página: uma tinta escrita à mão sobreviveria ao
        // bloqueio acima e cairia aqui.
        const ambienteEmAtencao = harness.medido("attention", 2, 3, {
            "label": "Ajuste recomendado",
            "cause": "Um requisito opcional está desatualizado.",
            "action": "Atualize o opcional quando for abrir o jogo."})
        pagina.gameplay = {
            "games": [{"id": "3311720", "name": "Gimmick! 2 Demo"}],
            "environment": [],
            "readiness": ambienteEmAtencao,
            "hardware": {"tdpMin": 3, "tdpMax": 15, "refreshHz": 60},
            "currentProfile": {"gameId": "3311720", "scope": "game"}
        }
        check(pagina.readinessTone() === "amber",
              "a página do ambiente acompanha a mudança de estado publicada")
        check(Qt.colorEqual(pagina.readinessSurfaceColor,
                            Readiness.surface(ambienteEmAtencao)),
              "mudado o estado, o fundo do cartão do ambiente muda com o módulo")
        check(!Qt.colorEqual(pagina.readinessSurfaceColor,
                             Readiness.surface(ambienteBloqueado.readiness)),
              "atenção e bloqueio têm fundos distintos no cartão do ambiente")
        pagina.destroy()
    }

    // --- o painel de contexto pinta o estado, não uma suposição --------------
    // A caixa "Antes de continuar" existe para bloqueios vindos do contrato. Ela
    // tinha fundo e borda âmbar fixos: um estado `blocked` (vermelho no cartão,
    // vermelho no tom publicado) chegava ao painel como "atenção" — a mesma
    // categoria pintada com a cor errada que a UX-03 registra como causa.
    function testPainelDeContextoUsaATintaDoEstado() {
        const bloqueado = harness.medido("blocked", 1, 3, {
            "label": "Ação necessária",
            "cause": "Gamescope não está disponível (SteamZero).",
            "action": "Instale ou ative Gamescope (SteamZero).",
            "blockers": ["Instale ou ative Gamescope (SteamZero)."]})
        const objeto = emulationComponent.createObject(harness, {
            "width": 1600, "height": 900,
            "backgroundColor": "#071019", "sidebarColor": "#09131d",
            "surfaceColor": "#0d1924", "raisedColor": "#122131",
            "borderColor": "#2a3a49", "textColor": "#f2f6fb", "mutedColor": "#9eabba",
            "cyanColor": "#13bdf2", "cyanDarkColor": "#0a5f85",
            "greenColor": harness.cores.green, "amberColor": harness.cores.amber,
            "redColor": harness.cores.red,
            "emulation": {
                "platforms": [{
                    "id": "switch", "name": "Nintendo Switch", "iconKey": "switch",
                    "state": "blocked", "statusLabel": "Ação necessária",
                    "selectedScope": "global", "selectedArea": "overview",
                    "readiness": bloqueado,
                    "emulators": [{"id": "eden", "name": "Eden", "state": "ready"}],
                    "games": [{"id": "a", "name": "Mario", "titleId": "010000000000A000",
                              "state": "ready", "statusLabel": "NSZ"}]
                }]
            }
        })
        // Uma página que não constrói não verifica nada: o `return` mudo fazia o
        // harness inteiro perder esta função e ainda assim devolver verde.
        check(objeto !== null,
              "a página abre — o painel de contexto só existe acima de 1500 px, "
              + "medido em sonda: a 1360 ele está fora da tela")
        if (!objeto)
            return
        objeto.syncPublishedSelection()
        check(objeto.isGameLibrary() === false,
              "o painel está na coluna de área, que é onde a caixa de bloqueios vive")
        const caixa = harness.itemWithObjectName(objeto, "readinessBlockersBox")
        check(caixa !== null, "a caixa de bloqueios aparece com bloqueio publicado")
        if (caixa === null) {
            objeto.destroy()
            return
        }
        check(Qt.colorEqual(caixa.color, Readiness.surface(bloqueado)),
              "o fundo da caixa é a tinta do estado publicado, não uma cor presumida")
        check(Qt.colorEqual(caixa.border.color, harness.cores.red),
              "a borda da caixa vem do tom do estado (vermelho para bloqueio)")

        // O cabeçalho do painel é texto de prontidão: `statusLabel` sai do mesmo
        // `compute_readiness` que publica o estado (adapters/emulation.py:792-795).
        // Ele era pintado pela paleta de estado da plataforma, onde `blocked` é
        // âmbar — na mesma tela o cartão ficava vermelho e o cabeçalho âmbar.
        const titulo = harness.itemWithObjectName(objeto, "readinessContextHeadline")
        check(titulo !== null, "o cabeçalho do painel de contexto está na tela")
        if (titulo !== null) {
            check(Qt.colorEqual(titulo.color, objeto.readinessColor()),
                  "o cabeçalho do painel usa a tinta do estado publicado")
            check(!Qt.colorEqual(titulo.color, harness.cores.amber),
                  "um bloqueio não é anunciado com a cor de atenção")
        }
        // O glifo ao lado divide a linha com o texto: âmbar com vermelho ao lado
        // é a mesma categoria pintada duas vezes na mesma tela.
        const glifo = harness.itemWithObjectName(objeto, "readinessContextHeadlineIcon")
        check(glifo !== null, "o glifo de estado acompanha o cabeçalho do painel")
        if (glifo !== null)
            check(Qt.colorEqual(glifo.iconColor, objeto.readinessColor()),
                  "o glifo recebe a mesma tinta do cabeçalho, não a paleta de estado da plataforma")

        // Segundo estado na mesma página: a tinta tem de acompanhar, o que uma
        // cor escrita à mão não faz.
        const atencao = harness.medido("attention", 2, 3, {
            "label": "Ajuste recomendado",
            "cause": "Um requisito opcional está desatualizado.",
            "action": "Atualize o opcional quando for abrir o jogo.",
            "blockers": ["Requisito opcional desatualizado."]})
        objeto.emulation = {
            "platforms": [{
                "id": "switch", "name": "Nintendo Switch", "iconKey": "switch",
                "state": "attention", "statusLabel": "Ajuste recomendado",
                "selectedScope": "global", "selectedArea": "overview",
                "readiness": atencao,
                "emulators": [{"id": "eden", "name": "Eden", "state": "ready"}],
                "games": [{"id": "a", "name": "Mario", "titleId": "010000000000A000",
                          "state": "ready", "statusLabel": "NSZ"}]
            }]
        }
        objeto.syncPublishedSelection()
        check(objeto.readinessTone() === "amber", "a página acompanhou o novo estado")
        const caixaReaberta = harness.itemWithObjectName(objeto, "readinessBlockersBox")
        check(caixaReaberta !== null, "a caixa continua lá com o segundo estado")
        if (caixaReaberta === null) {
            objeto.destroy()
            return
        }
        check(Qt.colorEqual(caixaReaberta.color, Readiness.surface(atencao)),
              "mudado o estado, a caixa muda de tinta com o módulo")
        check(!Qt.colorEqual(caixaReaberta.color, Readiness.surface(bloqueado)),
              "atenção e bloqueio não dividem a mesma caixa")

        // Terceiro estado: sem cor de estado, a caixa precisa continuar visível no
        // painel (que é surfaceColor) sem receber verde nem vermelho.
        const naoObservadoComBloqueio = harness.medido("unverified", 1, 3, {
            "label": "Verificação pendente",
            "cause": "Nenhum requisito foi verificado nesta plataforma.",
            "action": "Verifique emulador, BIOS e requisitos da plataforma.",
            "blockers": ["Backend de emulação ainda não conectado."],
            "verification": "not_performed", "basis": "none"})
        objeto.emulation = {
            "platforms": [{
                "id": "switch", "name": "Nintendo Switch", "iconKey": "switch",
                "state": "unverified", "statusLabel": "Verificação pendente",
                "selectedScope": "global", "selectedArea": "overview",
                "readiness": naoObservadoComBloqueio,
                "emulators": [{"id": "eden", "name": "Eden", "state": "ready"}],
                "games": []
            }]
        }
        objeto.syncPublishedSelection()
        const caixaMuda = harness.itemWithObjectName(objeto, "readinessBlockersBox")
        check(caixaMuda !== null, "a caixa continua visível sem cor de estado: bloqueios "
              + "publicados não desaparecem por causa da tinta")
        if (caixaMuda === null) {
            objeto.destroy()
            return
        }
        check(Qt.colorEqual(caixaMuda.color, objeto.raisedColor),
              "estado não observado usa o relevo neutro da página, não uma tinta de estado")
        check(Qt.colorEqual(caixaMuda.border.color, harness.cores.muted),
              "estado não observado não recebe borda verde nem vermelha")
        objeto.destroy()
    }

    // --- a caixa não repete a próxima ação como bloqueio ----------------------
    // `compute_readiness` publica `blockers` com a ação de cada impedimento e
    // `nextAction` com a primeira delas (domain/emulation_workspace.py:553-558).
    // Na caixa "Antes de continuar" a frase aparecia duas vezes — foi o que a
    // captura de 1656x954 mostrou, e não é artefato de fixture: a fixture segue
    // a forma que o produtor publica.
    function testPainelNaoRepeteAProximaAcao() {
        const acao = "Instale ou ative Gamescope (SteamZero)."
        const payload = harness.medido("blocked", 1, 3, {
            "label": "Ação necessária",
            "cause": "Gamescope não está disponível (SteamZero).",
            "action": acao,
            "blockers": [acao, "Importe keys e firmware próprios antes de iniciar jogos."]})
        const objeto = emulationComponent.createObject(harness, {
            "width": 1600, "height": 900,
            "backgroundColor": "#071019", "sidebarColor": "#09131d",
            "surfaceColor": "#0d1924", "raisedColor": "#122131",
            "borderColor": "#2a3a49", "textColor": "#f2f6fb", "mutedColor": "#9eabba",
            "cyanColor": "#13bdf2", "cyanDarkColor": "#0a5f85",
            "greenColor": harness.cores.green, "amberColor": harness.cores.amber,
            "redColor": harness.cores.red,
            "emulation": {
                "platforms": [{
                    "id": "switch", "name": "Nintendo Switch", "iconKey": "switch",
                    "state": "blocked", "statusLabel": "Ação necessária",
                    "selectedScope": "global", "selectedArea": "overview",
                    "readiness": payload,
                    "emulators": [{"id": "eden", "name": "Eden", "state": "ready"}],
                    "games": []
                }]
            }
        })
        check(objeto !== null, "a página abre no escopo onde o painel de contexto existe")
        if (!objeto)
            return
        objeto.syncPublishedSelection()
        const linhas = harness.itemsWithObjectName(objeto, "readinessBlockerRow")
        check(linhas.length === 1,
              "a caixa renderiza um bloco por impedimento, não a ação repetida duas vezes")
        if (linhas.length === 1)
            check(linhas[0].text.indexOf("Importe keys") === 2,
                  "o bloco restante é o segundo impedimento: nada foi perdido pela deduplicação")
        // A próxima ação continua na tela — deduplicar não é esconder.
        const acaoExibida = harness.itemWithObjectName(objeto, "readinessContextAction")
        check(acaoExibida !== null && acaoExibida.text === acao,
              "a próxima ação publicada permanece legível na caixa")
        objeto.destroy()
    }

    Component {
        id: emulationComponent
        Emulation {}
    }

    Component {
        id: gameplayComponent
        SteamGameplay {}
    }

    Timer {
        interval: 150
        running: true
        onTriggered: {
            testSemanticaDoContrato()
            testEmulationRenderizaONumeroSomenteComMedicao()
            testSteamGameplayRenderizaOCampoPublicado()
            testPainelDeContextoUsaATintaDoEstado()
            testPainelNaoRepeteAProximaAcao()
            // `Qt.exit()` não interrompe o script: sem o `else`, a linha de sucesso
            // rodava depois da falha e o segundo `Qt.exit(0)` sobrescrevia o código
            // de saída — o harness tinha falha e o gate lia verde.
            if (harness.failures > 0) {
                console.error("check_readiness_surface: " + harness.failures
                    + " falha(s) de " + harness.checks + " (primeira em #" + harness.firstFailure + ")")
                Qt.exit(1)
                return
            }
            console.info("check_readiness_surface: " + harness.checks + " verificação(ões) ok")
            Qt.exit(0)
        }
    }
}
