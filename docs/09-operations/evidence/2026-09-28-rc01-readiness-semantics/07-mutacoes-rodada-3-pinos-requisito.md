================================================================================
UX-03 — RODADA 3 DA BATERIA DE MUTAÇÕES: PINOS DE COR REESCRITOS COMO REQUISITOS
Lote: rc01-readiness-semantics-2026-09-28 · Data: 2026-09-28 (14:59–15:02)
================================================================================

1. POR QUE ESTA RODADA EXISTE
--------------------------------------------------------------------------------
O operador revisou duas conclusões antes da publicação e a segunda era desta
frente: "confira se os testes de cor expressam o contrato semântico/visual. A
bateria 6/6 não prova cobertura completa. Evite testes que apenas fixem uma
implementação ou cor exata sem requisito correspondente."

Duas acusações procedentes, ambas medidas antes de editar:

a) `tests/qml/check_readiness_surface.qml` continha pinos de hex literal —
   `Readiness.surface(atencao) === "#24180b"`,
   `objeto.readinessSurface() === "#2b1114"`,
   `Qt.colorEqual(pagina.readinessSurfaceColor, "#2b1114")`.
   Um hex fixo prova que ninguém trocou um caractere; não prova que a cor
   comunica o estado. Se o tema algum dia escurecer o âmbar de atenção, o teste
   verde continuará afirmando uma propriedade que deixou de existir.
b) A bateria anterior (05-mutacoes-rodada-1.log, 05-mutacoes-rodada-2-fundo-
   cartao.log) deixou 6/6 pegas, mas nenhuma das seis mutações mexia na
   relação tom→tinta do painel de contexto nem na elipse da causa — exatamente
   as regiões que a rodada 3 corrige. Declarar cobertura não é medir cobertura.

2. O QUE OS PINOS PASSARAM A EXIGIR (requisito, não implementação)
--------------------------------------------------------------------------------
Em `tests/qml/check_readiness_surface.qml` + `tests/qml/readiness_fixture.js`:

- todo tom observável tem fundo próprio (não vazio) e os três se distinguem
  entre si;
- família de matiz: `ready` verde-dominante; `blocked` vermelho fechado com o
  verde no canal mínimo; `attention` quente com o azul no canal mínimo — isto é,
  "bloqueio não pode ter a cor de atenção" como propriedade, não como string;
- `surface(unverified) === ""` — a ausência de verificação não tem tinta;
- WCAG: `contraste("#f2f6fb", fundo) >= 7` para os três fundos publicados
  (helpers `canais/minimo/luminancia/contraste` vivem no fixture de teste, com
  comentário dizendo que um hex não mede comunicação);
- a página delega: `objeto.readinessSurface() === Readiness.surface(estado)` e
  `!== objeto.surfaceColor`, com um segundo estado provando que ela acompanha o
  módulo em vez de guardar uma cor;
- causa não elidida: `elide === Text.ElideNone`, `maximumLineCount > 1`,
  `wrapMode === Text.WordWrap`, `lineCount > 1`, `contentWidth <= width + 1`.

3. ÁRVORE ANTES DA BATERIA (digests de partida, sha256)
--------------------------------------------------------------------------------
e9e4c08ba57816e8243891924efe210c29b5502ffd9136aea77826e73df78502  src/steamzero/ui/qml/Emulation.qml
c6522fa09ff86aa4574bfef724b7c62db36822b44cf02e565248161965de2e66  src/steamzero/ui/qml/SteamGameplay.qml
33bc908e87075bed51004cbcb933523d5994f35bf9280b73ba610a8a7ce1860c  src/steamzero/ui/qml/readiness.js
610994b405ccfed8394ff3fd9839d0f3311f2d4beba0d8238394344170286163  tests/qml/check_readiness_surface.qml
3b9949e1cfa870af54b894f96dd43a24e61efd21e7d87a7921f809e8c19e7117  tests/qml/readiness_fixture.js
0eb9656d2c80e2866e56da83797b12dae2300d19768e89c8266cf36c675b8e96  src/steamzero/domain/readiness.py

4. COMANDO
--------------------------------------------------------------------------------
Script: /tmp/ux03_mutacoes_rodada3.py (temporário próprio desta sessão, fora da
árvore versionada). Execução:

  rtk proxy timeout 1500 python3 /tmp/ux03_mutacoes_rodada3.py
  -> codigo_bateria=0

Harness por mutação (timeout obrigatório de 150 s, lição de 05-consumidores-qml.log §3):

  rtk proxy env QT_QPA_PLATFORM=offscreen QT_LOGGING_RULES= QML_DISABLE_DISK_CACHE=1 \
      QT_FORCE_STDERR_LOGGING=1 timeout 150 /usr/sbin/qml6 tests/qml/check_readiness_surface.qml

Guardas do próprio script: voo prévio verde na árvore íntegra (senão a bateria
não significaria nada), alvo de cada mutação encontrado exatamente 1x, bytes
originais guardados antes de qualquer escrita, restauração + conferência de
digest dos 4 arquivos após CADA mutação (a bateria aborta se qualquer digest
diferir), voo posterior verde.

5. RESULTADO — 8/8 PEGAS
--------------------------------------------------------------------------------
M-a Emulation readinessSurface() presa na superfície neutra ......... PEGOU (3)
  - o fundo do cartão é a tinta que o módulo publica para o estado atual
  - com estado observado o cartão não fica na superfície neutra da página
  - a página segue o módulo quando o estado muda, em vez de guardar uma cor
M-b página decide pelo percentual (regra local >= 80) ............... PEGOU (3)
  - o cartão da Emulação colore pelo estado, não pelo percentual
  - sem observação o cartão não pode parecer sucesso nem falha
  - 100% medido não salva um bloqueio na superfície da plataforma
M-c caixa de bloqueios com relevo constante (raisedColor) ........... PEGOU (2)
  - o fundo da caixa é a tinta do estado publicado, não uma cor presumida
  - mudado o estado, a caixa muda de tinta com o módulo
M-d módulo publicado sem âmbar próprio .............................. PEGOU (4)
  - estado observado tem fundo próprio, em vez da superfície neutra do tema
  - o fundo de atenção é quente (azul é o canal mínimo): âmbar, não vermelho
  - todo fundo publicado mantém a tinta do tema em 7:1 ou mais — a norma de
    contraste do projeto para superfícies fixas
  - a página segue o módulo quando o estado muda, em vez de guardar uma cor
M-e um único fundo para todos os tons ............................... PEGOU (2)
  - os três tons observáveis se distinguem entre si: um fundo único para tudo
    recria a regra que apagava a diferença
  - o fundo do bloqueio é vermelho fechado (verde é o canal mínimo), e não o
    âmbar de atenção — é a mesma distinção que o tom exige
M-f causa da plataforma volta a ser elidida ......................... PEGOU (3)
  - a causa não é truncada: elipse cortaria o texto que o contrato publicou
  - a causa tem mais de uma linha disponível — o limite de uma linha era a elipse
  - com a largura do cartão a causa longa ocupa mais de uma linha, então houve
    quebra de linha e não corte
M-g cartão do ambiente perde a próxima ação ......................... PEGOU (2)
  - o cartão do ambiente entrega a próxima ação, não só o estado
  - a ação exibida é a publicada no contrato, palavra por palavra
M-h causa do ambiente volta a ser elidida ........................... PEGOU (2)
  - a causa do ambiente não é cortada
  - a causa longa do ambiente ocupa mais de uma linha em vez de sumir em reticências

PRE-VOO harness: codigo=0 verificacoes_falhando=0
POS-VOO harness: codigo=0 falhas=0
RESTAURO byte a byte conferido em cada rodada (4 arquivos, 8 rodadas).

6. NUANCE REGISTRADA — M-d terminou por timeout
--------------------------------------------------------------------------------
M-d devolveu `codigo=124`, não 1: o harness imprimiu as quatro falhas e depois
não encerrou dentro dos 150 s. Isso é uma propriedade do qml6 já documentada
nesta frente (um handler de Timer que levanta TypeError não termina o processo;
ver 05-consumidores-qml.log §3), não do produto. A captura de M-d conta pelas
linhas `qml: FAIL` produzidas, e o `timeout` obrigatório é o que impede a
bateria de pendurar — registre-se aqui para que o 124 não seja lido como
execução inválida nem como defeito da Emulation.

7. O QUE ESTA RODADA PROVA E O QUE NÃO PROVA
--------------------------------------------------------------------------------
Prova: cada pino de cor/linha reescrito cai quando o requisito que declara deixa
de existir na produção (8 mutações em 3 arquivos de produção + 1 regra local
substituída por percentual). Nenhum deles é satisfied por um valor exato
copiado da implementação.

Não prova: cobertura de todos os estados × todas as superfícies (a matriz
explícita está em 05-consumidores-qml.log §1–2), nem qualquer comportamento em
hardware real — o eixo físico de RC-01 continua parcial.
