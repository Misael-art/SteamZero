================================================================================
UX-03 — RODADA 4: A LISTA DE BLOQUEIOS NUNCA CHEGAVA À PÁGINA (QVariantList),
        TINTA DO CABEÇALHO DO PAINEL E A AÇÃO REPETIDA COMO BLOQUEIO
Lote: rc01-readiness-semantics-2026-09-28 · Data: 2026-09-28 (15:04–15:31)
Achado pela INSPEÇÃO VISUAL da captura nova de 1656×954 — não por teste.
================================================================================

0. POR QUE ESTA RODADA EXISTE
--------------------------------------------------------------------------------
A diretiva pede reprodução → causa → correção → regressão → inspeção visual. As
seis capturas promovidas em 05-consumidores-qml.log §5 eram todas de 1208×696 ou
949×593, onde o painel de contexto não abre. Adicionei uma captura em 1656×954
(`steamzero-readiness-emulation-blocked-panel.png`) porque a medição de
reachabilidade (log 08 §2) mostrou que só ali a caixa "Antes de continuar" é
visível. A captura expôs três defeitos que nenhum dos 103 pinos anteriores via.

1. DEFETO 1 — `Readiness.blockers()` devolvia lista VAZIA na página montada
--------------------------------------------------------------------------------
Sintoma na captura: a caixa mostrava o cabeçalho e a ação, e a lista de bloqueios
simplesmente não existia.

Causa, medida em sonda (`/tmp/ux03_probe_formas.qml`, `/tmp/ux03_probe_blockers.qml`):

  SONDA antes_fronteira isArray=true
        | pagina.emulation.platforms[0].readiness.blockers isArray=false
        | pagina.readiness.blockers isArray=false
  SONDA raw_blockers=["Instale ou ative Gamescope (SteamZero).",
                      "Importe keys e firmware próprios antes de iniciar jogos."]
        isArray=false
  SONDA blockers_len=0        (o guard `Array.isArray(value) ? value : []` descartou)

A lista nasce como Array JS (função de biblioteca, `JSON.parse`, escopo de
componente — os três medidos como `isArray=SIM`), mas ao cruzar a fronteira de
`required property var emulation` da página ela chega como lista do Qt: conteúdo
íntegro, `length` numérico, `Array.isArray === false`. O guard do módulo, escrito
como defesa, era o modo de falha: devolvia `[]` sem erro nem aviso.

Mesma fronteira, outro dado: `Main.qml:4173/4542/6597` alimentam a página com
`root.emulationData`, que vem de `desktopStatus.dashboard` — ou seja, o caminho de
produção é justamente o que produz a lista não-Array. Não é artefato de harness.

Correção (src/steamzero/ui/qml/readiness.js): `_lista()` aceita Array JS e lista
com `length` numérico, copiando a segunda; `blockers()` e o `blockers` do
`normalize()` legado passam por ela.

Redução do claim (para não repetir o erro de 06.6): isto prova o defeito para
`blockers`. Não verifiquei os outros 14 usos de `Array.isArray` no QML
(`launcher/*.qml`, `EditorialLibrary.qml:142/166/194`, `SceneEsdeView.qml:88/611`,
`SteamComboBox.qml:66`, `Main.qml:1061`), que podem estar do lado certo da
fronteira ou do errado. Ficam registrados como pendência de auditoria própria,
fora deste lote.

2. DEFEITO 2 — cabeçalho e glifo do painel pintados por outra paleta
--------------------------------------------------------------------------------
O texto do cabeçalho é `selectedPlatform.statusLabel`, e `statusLabel` vem do
mesmo `compute_readiness` que publica o estado (`adapters/emulation.py:792-795`).
Ele era colorido por `page.stateColor(...)`, onde `blocked` é âmbar
(Emulation.qml:373-375). Resultado na captura: cartão vermelho, caixa vermelha,
cabeçalho âmbar — a mesma categoria com duas cores na mesma tela, que é a causa
que a auditoria atribui a UX-03.

Correção: `color: page.readinessColor()` no Label e `iconColor:
page.readinessColor()` no ModernIcon ao lado. O GLIFO (escolha do ícone
`dialog-warning` vs `dialog-error`) não foi alterado — é decisão de design, não a
cor errada; registrado como pendência de design, não como defeito corrigido.

3. DEFEITO 3 — a próxima ação aparecia duas vezes na caixa
--------------------------------------------------------------------------------
`compute_readiness` publica `blockers=list(dict.fromkeys(action for _cause, action
in findings))` e `nextAction=findings[0][1]` (domain/emulation_workspace.py:553-558):
o primeiro elemento da lista É a próxima ação. A caixa mostrava a frase como ação
e de novo como primeiro bloco.

Correção na superfície, não no contrato: `readinessBlockerRows()` remove da lista
exatamente o item igual à ação exibida; o contrato continua publicando a lista
completa. A próxima ação permanece legível (pinado), então deduplicar não é
esconder.

4. SEQUÊNCIA TDD (vermelho observado antes de cada correção)
--------------------------------------------------------------------------------
Instrumentação primeiro, para o vermelho falhar pelo requisito e não por item
ausente: os dois `objectName` novos entraram, o harness continuou verde (103 ok),
e só então os pinos foram escritos.

  RED 1  codigo=1, 3 falhas de 109 (primeira em #98):
         - o cabeçalho do painel usa a tinta do estado publicado
         - um bloqueio não é anunciado com a cor de atenção
         - a caixa renderiza um bloco por impedimento, não a ação repetida duas vezes
  RED 2  codigo=1, 2 falhas de 111: glifo + contagem de blocos
         (a contagem falhou com 0 blocos — foi assim que se descobriu o defeito 1;
         a hipótese inicial "ação duplicada" estava incompleta)
  VERDE  codigo=0, 112 verificações ok

5. BATERIA DE MUTAÇÕES — RODADA 4: 6/6 PEGAS COM FALHA REAL
--------------------------------------------------------------------------------
`/tmp/ux03_mutacoes_rodada4.py` e `/tmp/ux03_mutacoes_rodada4b.py` (temporários da
sessão), pré/pós-voo verdes, digest dos arquivos conferido após cada rodada:

  M-i  `blockers()` volta ao guard `Array.isArray` ............ PEGOU (1)
  M-j  `_lista()` descarta o que não é Array JS .............. PEGOU (1)
  M-k' cabeçalho volta para `stateColor` ...................... PEGOU (2), 0 erros de carga
  M-l  glifo volta para `stateColor` .......................... PEGOU (1)
  M-m  caixa volta a listar `Readiness.blockers` direto ....... PEGOU (1)
  M-n  deduplicação remove tudo em vez do item repetido ...... PEGOU (1)

Correção de método registrada aqui: a M-k da primeira execução "pegou" com
`codigo=1` e ZERO linhas FAIL — a mutação inseria uma segunda propriedade `color`
no mesmo Label, e o QML rejeita duplicata em tempo de carga. Isso não prova pino
nenhum. A M-k foi refeita como substituição (4b) e derrubou os dois pinos com
falhas nomeadas. O mesmo critério foi aplicado a M-d na rodada 3 (log 07 §6).

6. INSPEÇÃO VISUAL REFEITA COM OS TRÊS CORRETIVOS
--------------------------------------------------------------------------------
Captura `steamzero-readiness-emulation-blocked-panel.png` (1656×954, escopo
global, blocked 1/3): cabeçalho "Ação necessária" vermelho com glifo vermelho,
caixa com fundo e borda vermelhos, "Instale ou ative Gamescope (SteamZero)." uma
única vez, e um bloco "• Importe keys e firmware próprios antes de iniciar
jogos.". As outras seis capturas (ready / unverified / blocked / steam blocked,
mais as duas handheld 949×593) foram regeneradas e inspecionadas: causa e ação
quebram linha sem elipse, `unverified` mostra "—" e nenhuma barra, handheld
mantém o cartão acima da dobra com a ação inline.

7. GATES DEPOIS DESTA RODADA
--------------------------------------------------------------------------------
Ver tabela em 10-gates-do-checkpoint.md — os gates visuais foram reexecutados
porque a geometria do painel mudou de novo nesta rodada.
