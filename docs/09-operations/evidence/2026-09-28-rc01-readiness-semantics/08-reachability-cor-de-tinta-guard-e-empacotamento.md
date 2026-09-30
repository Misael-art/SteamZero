================================================================================
UX-03 — REACHABILIDADE MEDIDA, MENTIRA DE COR NO PAINEL, GUARD `ready` E
        EMPACOTAMENTO RE-registrado COMO PENDENTE
Lote: rc01-readiness-semantics-2026-09-28 · Data: 2026-09-28 (14:20–15:10)
Corrige duas conclusões deste lote apontadas pelo operador antes da publicação.
================================================================================

1. SONDAS
--------------------------------------------------------------------------------
a) `tests/qml/check_readiness_surface.qml` (harness versionado) — 103 verificações, exit 0
b) `/tmp/ux03_probe_reachability.qml` (temporário desta sessão, NÃO versionado) —
   14 visitas (7 larguras × 2 escopos), exit 0, saída integral abaixo
c) `tests/unit/test_readiness_contract.py` + `tests/unit/test_readiness_producers.py`
   — 50 passaram em 1.23 s
d) `/tmp/ux03_wheel/` — artefato do CI autorizado (run 36372744311, artifact id
   10949711675, `steamzero-wheel-5704c813…`), lido com `zipfile`

Comandos canônicos:

  rtk proxy env QT_QPA_PLATFORM=offscreen QT_LOGGING_RULES= QML_DISABLE_DISK_CACHE=1 \
      QT_FORCE_STDERR_LOGGING=1 timeout 120 /usr/sbin/qml6 tests/qml/check_readiness_surface.qml
  rtk proxy timeout 120 env QT_QPA_PLATFORM=offscreen QML_DISABLE_DISK_CACHE=1 \
      QT_FORCE_STDERR_LOGGING=1 /usr/sbin/qml6 /tmp/ux03_probe_reachability.qml
  rtk proxy .venv/bin/pytest tests/unit/test_readiness_contract.py tests/unit/test_readiness_producers.py -q

================================================================================
2. REACHABILIDADE DA CAIXA DE BLOQUEIOS — O QUE A SONDA MEDE (14/14)
================================================================================

Estado publicado: `blocked` 1/3, escopo `game` ou `global`, mesmas dez tintas de
tema em todas as visitas. `caixaExiste` = o objeto `readinessBlockersBox` está na
árvore; `caixaVisivel` = está na árvore COM a cadeia de pais visível (o helper do
harness percorre `parent`, porque `QQuickItem.visible` reporta visibilidade
efitiva).

LARGURA= 740 ESCOPO=game   isGameLibrary=true  showContextPanel=false compact=true  acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA= 900 ESCOPO=game   isGameLibrary=true  showContextPanel=false compact=true  acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA=1200 ESCOPO=game   isGameLibrary=true  showContextPanel=false compact=true  acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA=1499 ESCOPO=game   isGameLibrary=true  showContextPanel=false compact=false acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA=1500 ESCOPO=game   isGameLibrary=true  showContextPanel=false compact=false acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA=1600 ESCOPO=game   isGameLibrary=true  showContextPanel=false compact=false acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA=1800 ESCOPO=game   isGameLibrary=true  showContextPanel=false compact=false acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA= 740 ESCOPO=global isGameLibrary=false showContextPanel=false compact=true  acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA= 900 ESCOPO=global isGameLibrary=false showContextPanel=false compact=true  acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA=1200 ESCOPO=global isGameLibrary=false showContextPanel=false compact=true  acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA=1499 ESCOPO=global isGameLibrary=false showContextPanel=false compact=false acaoForaDoPainel=true  caixaExiste=true  caixaVisivel=false
LARGURA=1500 ESCOPO=global isGameLibrary=false showContextPanel=true  compact=false acaoForaDoPainel=false caixaExiste=true caixaVisivel=true
LARGURA=1600 ESCOPO=global isGameLibrary=false showContextPanel=true  compact=false acaoForaDoPainel=false caixaExiste=true caixaVisivel=true
LARGURA=1800 ESCOPO=global isGameLibrary=false showContextPanel=true  compact=false acaoForaDoPainel=false caixaExiste=true caixaVisivel=true

Leitura:
- A caixa existe em 14/14 e fica VISÍVEL só onde o painel de contexto abre:
  escopo não-`game`, não compacto e `width >= 1500`. Em todo o resto ela continua
  na árvore com a tinta certa, apenas invisível.
- Onde ela não é visível, `acaoForaDoPainel=true`: a próxima ação é entregue
  inline. Nenhum viewport medido perde a jornada estado→causa→ação; ela só muda
  de hospedagem. Isso é o que a regra de `showContextPanel` em Emulation.qml
  produz, e agora está medido em vez de presumido.
- Consequência para o harness: o pino de tinta do painel usa viewport 1600×900
  com `selectedScope: "global"` exatamente por esta medição. Uma asserção feita
  em 1360×820 no escopo do jogo leria um item invisível.

Affirmação anterior desta frente que a sonda derruba: eu havia registrado que
`readinessContextAction` era alcançável "nos dois layouts". Medido: a versão
inline depende de `!showContextPanel`, e o painel só aparece ≥1500 não compacto
fora da biblioteca de jogos. A redação correta é a tabela acima.

================================================================================
3. MENTIRA DE COR ENCONTRADA E CORRIGIDA — O PAINEL PINTAVA BLOQUEIO COMO ATENÇÃO
================================================================================

Produção, antes: a caixa "Antes de continuar" tinha `color: "#24180b"` e
`border.color` âmbar fixos — o âmbar de atenção do tema. Um estado `blocked`
(vermelho no cartão, vermelho no tom publicado por `Readiness.tone`) chegava ao
painel como "atenção": a mesma categoria com a cor errada que a auditoria
(AUDA) registra como causa raiz de UX-03.

Correção (Emulation.qml):

  function readinessBlockersSurface() {
      const tint = Readiness.surface(readiness)
      return tint === "" ? raisedColor : tint
  }

  Rectangle { objectName: "readinessBlockersBox"
              color: page.readinessBlockersSurface()
              border.color: page.readinessColor() }

O fallback é `raisedColor` e não uma cor de estado: a caixa mora sobre um painel
que já é `surfaceColor`, então sem estado ela precisa de relevo próprio, nunca de
tinta. Prova de não-vacuidade: M-c (fundo preso em `raisedColor`) PEGOU 2 falhas,
e o pino `check(!Qt.colorEqual(caixa.color, "#24180b"))` continua exigindo que um
bloqueio não vista a roupa da atenção.

================================================================================
4. GUARD DE CONTRATO — "PRONTO" SOBRE MERA EXISTÊNCIA PASSA A SER RECUSADO
================================================================================

Pedido do operador (item 3): "não confunda readiness com gameplay certificado".
O vocabulário de `basis` já distinguia verificação de existência, mas o
construtor não vigiava a combinação: `state="ready"` aceitaria
`basis="inventory_existence"`, que é literalmente "existe um jogo" — a origem do
100% que a auditoria acusou.

Vermelho observado antes da correção (não reconstruído depois):

  tests/unit/test_readiness_contract.py::test_pronto_com_base_de_mera_existencia_e_recusado
  -> Failed: DID NOT RAISE <class 'ValueError'>

Correção (src/steamzero/domain/readiness.py):

  READY_BASES = frozenset({"preflight", "demonstrated_gameplay"})
  ...
  if resolved_basis not in READY_BASES:
      raise ValueError(
          f"readiness: state 'ready' exige basis de evidência de verificação "
          f"({sorted(READY_BASES)}), veio {resolved_basis!r}")

Auditoria dos produtores antes de apertar o guard (para não quebrar uma alegação
viva): `adapters/emulation.py:221` publica `inventory_existence` com estado
`unverified`; `domain/cloud_platforms.py:129` publica `existence_only` com
`attention`/`unavailable`; `adapters/steam_gameplay.py:200`,
`domain/emulation_workspace.py:566` e `domain/platform_composer.py:372` usam
`preflight`. Nenhum publicava `ready` sobre base de existência: o guard fecha um
buraco latente sem reescrever nenhuma alegação atual.

Teste companheiro contra o apertamento excessivo:
`test_bases_de_existencia_continuam_legitimas_para_outros_estados` garante que
as duas bases seguem válidas para `unverified` — o guard atinge a combinação
enganosa, não o vocabulário. Verde: 50 passaram (1.23 s). Invariante 6 de
docs/06-api/JSON-SCHEMAS.md foi atualizada com a regra.

================================================================================
5. EMPACOTAMENTO DE readiness.js — CONCLUSÃO ANTERIOR REBAIXADA PARA PENDENTE
================================================================================

O que 05-consumidores-qml.log §6.6 afirmou: "o arquivo NÃO é ignorado, portanto
entra no wheel". A segunda conclusão pedida pelo operador: "não estar ignorado
pelo Git não prova empacotamento; verifique a configuração efetiva e o conteúdo
do wheel produzido pelo CI autorizado; se ainda não houver artefato, registre a
prova como pendente até inspecioná-lo."

A primeira parte está certa (medido novamente nesta árvore):
  `git check-ignore -v src/steamzero/ui/qml/readiness.js` -> exit 1, sem regra
  `.gitignore` não menciona `js`; `pyproject.toml:33` usa
  `packages = ["src/steamzero"]`; `tools/hatch_build.py` não filtra extensão.

A segunda parte NÃO estava provada, e o wheel do CI autoriza a duda:

  artefato steamzero-wheel-5704c813… (run 36372744311), wheel
  dist/steamzero-2.0.0rc1-py3-none-any.whl
  sha256 6d1977f268ac5ebc453827fa136a71d5ce6ca12700ccce88e5b1d355aed369ef
  (confere com build/SHA256SUMS — leitura independente, não a alegação do CI)
  entradas = 622
  extensões = .py 298 · .json 183 · .qml 61 · .svg 39 · .png 28 · .md 5
              · (sem extensão) 4 · .txt 2 · .cfg 1 · .html 1
  arquivos .js no wheel = 0
  contém steamzero/ui/qml/readiness.js = FALSO

Esse wheel foi construído em `5704c813`, SHA anterior à criação do arquivo — o
`readiness.js` simplesmente não existia na árvore empacotada. A ausência não
prova que hatchling descarta `.js`; prova apenas que **não há evidência
empacotada**. O precedente medido é parcial: outros não-`.py` (`.qml`, `.svg`,
`.png`, `.md`, `.txt`, `.cfg`, `.html`) viajam pelo mesmo `packages =`, mas
`readiness.js` é o ÚNICO `.js` em `src/` (`find src -name '*.js'` -> 1 arquivo) e
não está rastreado (`git ls-files` -> nenhum `.js`). Sem precedente para a
extensão.

Por que isso não é burocracia: quatro páginas de produção importam o módulo por
caminho relativo — `Main.qml:6`, `Emulation.qml:7`, `SteamGameplay.qml:7`,
`EditorialLibrary.qml:14`, todos `import "readiness.js" as Readiness`. Se o
arquivo não chegar ao wheel, as quatro páginas falham ao carregar na release
instalada; o sintoma seria a UI vazia, não um aviso.

REGISTRO: a prova de empacotamento de `readiness.js` está **PENDENTE**. Ela se
fecha assim, nesta ordem, sem construir release fora do fluxo do operador
(AGENTS.md §4):
  1. commitar o arquivo nesta branch;
  2. deixar o CI autorizado construir o wheel no SHA final do lote;
  3. baixar o artefato `steamzero-wheel-<sha>` dentro do checkout
     (`gh run download <run> -n steamzero-wheel-<sha> -D <tmp>`) e confirmar
     `steamzero/ui/qml/readiness.js` na lista do wheel + a soma em SHA256SUMS.
Nenhum passo acima foi executado por mim fora do CI, e nenhum wheel foi montado
localmente.

================================================================================
6. GATES RECORRIDOS DEPOIS DAS EDIÇÕES DE GEOMETRIA
================================================================================
A causa passou a quebrar linha e o cartão do ambiente ganhou o rótulo de próxima
ação, então a geometria mudou e os gates visuais foram reexecutados (uma suíte
por vez, árvore íntegra):

  tests/integration/test_qml_handheld_offscreen.py   57 passaram (93.70 s)  exit 0
  tests/integration/test_qml_visual_capture.py       48 passaram (12.35 s)  exit 0
  ruff check src tools tests                          All checks passed!   exit 0
  ruff format --check src tools tests                 676 files already formatted  exit 0
  mypy src                                            Success: no issues found in 298 source files  exit 0
  make independence boundaries                        independência OK; lint de fronteiras OK (0 violações)  exit 0

Capturas: as seis PNG de UX-03 promovidas em 05-consumidores-qml.log §5 são
anteriores à quebra de linha da causa. A reinspeção visual com a nova geometria
está pendente deste log e é o item imediato seguinte, antes do congelamento.

================================================================================
7. SUÍTE INTEGRAL DE 13:14 — SEM VEREDICTO, NÃO CONTADA COMO VERDE
================================================================================
`06-suíte-integral.log` termina em `..............................................`
na linha 26, ~26% do total, sem linha de resultado. A sessão foi interrompida no
meio da execução; o processo morreu junto. Não houve falha nem sucesso — não há
veredicto. O arquivo fica como está (evidência append-only), e a suíte integral
deste lote é a única execução que será contada: árvore congelada, um disparo,
sem mutações durante a execução. Nenhum teste focado desta frente (50 unidade,
57+48 visuais, 103 superfície QML) será apresentado no lugar dela.
