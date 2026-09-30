# Evidência do fechamento da fileira #239 → #247 integrada em `main` (2026-09-30)

Frente: fechamento documental pós-integração de RC-01. Branch desta entrega:
`codex/rc01-fileira-fechamento-2026-09-30`, base `7808374257db3059c1934cb4be6007d8a749346e`
(o `main` consolidado). Item normativo: `SZ-UI-DESKTOP-AUDIT`; workstreams encerrados: os oito
`WS-2026-09-RC01-*` dos nove elos.

Autorização que rege esta etapa (do operador, 2026-09-30): integrar #239 a #247 em `main` por
merge commit preservando ancestralidade, na sequência proposta e após as verificações; recolocar a
base de #245/#246/#247 em `main` nos pontos apropriados; o fechamento documental e seu merge estão
cobertos. **Não** cobre instalação, release nem alterações privilegiadas no host.

Nada aqui foi inferido de manchete: cada número vem de comando rodado nesta sessão e está no log
correspondente, que faz parte desta pasta.

---

## 1. Pré-voo (log `115`, seções iniciais)

| verificação | resultado medido |
|---|---|
| repo, checkout único, árvore | `/home/misael/Projects/Steam Zero/Canonical/2026-09-21`, `git status` limpo, um único `HEAD` |
| `origin/main` antes | `3495c49d5d7c3244267e8292beee34475f70236b` |
| nove cabeças, sem deriva | `239 069501ab · 240 c959be13 · 241 190ea683 · 242 5d95034b · 243 c0de54c9 · 244 af6a5c6e · 245 2d6a8957 · 246 c4975979 · 247 37040af3` — cada cabeça **IGUAL** a `origin/<branch>` (9×) |
| deriva desde a revisão | nenhuma: os mesmos SHAs medidos na rodada de preparação (`106`) |
| ancestralidade | linear, par a par (`merge-base --is-ancestor`): #239 → … → #247, todas descendentes de `main` |
| incrementos por elo | `2 + 5 + 13 + 4 + 10 + 16 + 8 + 16 + 9` = **83**; `git rev-list --count 3495c49d..78083742` = **92** commits (= 83 sem merge + 9 merge commits, conferidos separadamente com `--no-merges` e `--merges`) |
| diff da fileira vs `main` antigo | 524 arquivos, **+71 730 / −1 231** |
| mudanças inesperadas na árvore | nenhuma (`git status --porcelain` vazio antes e depois de cada passo) |

## 2. Gates e proteção: o que foi medido, e o risco achado

* Oito checks obrigatórios lidos **no SHA exato de cada cabeça**: `Python 3.11`, `Python 3.12`,
  `Python 3.14`, `Wheel limpo, smoke e supply chain`, `Smoke Ubuntu 24.04`, `Smoke Arch Linux`,
  `Smoke Manjaro`, `Gate visual QML (Linux)` — todos `SUCCESS` em todas as nove cabeças.
  `Sourcery review` = `SKIPPED`, `CodeRabbit` sem conclusão: **não são obrigatórios**, e não foram
  tratados como aprovação.
* `reviewDecision` vazio **não** foi lido como aprovação. Procurou-se a proteção real do servidor:
  branch protection clássica → **404 "Branch not protected"**; `rulesets` → `[]`; regras efetivas
  em `main` → `[]`; sem `CODEOWNERS`. **Consequência registrada: nada no GitHub barraria um merge
  com gate vermelho.** O compensatório usado foi mecânico, não de julgamento: o script `118` só
  executa `gh pr merge N --merge` se o PR estiver `OPEN`, `MERGEABLE/CLEAN` e os oito nomes
  obrigatórios constarem `SUCCESS` naquela cabeça; caso contrário sai com código de erro sem mesclar.
* Sem `--admin`, sem `--delete-branch`, sem force-push, sem bypass. O `118` **recusou** #243
  enquanto a composicao estava `UNKNOWN/UNKNOWN` (log `115`, linha `RECUSA`); mergede só depois de
  `MERGEABLE/CLEAN` resolver.
* A suíte exigida foi verificada como **executada**, não apenas como check verde: `.github/workflows/ci.yml`
  roda `python tools/run_tests_isolated.py -m "not visual" … --junitxml=… --cov=steamzero`, e os
  zips `test-results-*` de cada run trazem a contagem. Log `116` (por cabeça) e log `123` (no
  consolidado).

## 3. A integração, elo a elo

Merge commit por PR, na ordem autorizada (`9fc1c594 239` · `cba3fe42 240` · `67e30afc 241` ·
`231ba4d3 242` · `5f6ff508 243` · `c4385308 244` · `66b442b6 245` · `cb71a527 246` · `78083742 247`).
Em cada um dos nove passos, quatro coisas foram conferidas antes de passar para o seguinte:

1. `state=MERGED` com `mergeCommit` e `base=main` lidos da API;
2. o merge commit tem **2 pais** (merge commit de verdade, não squash/rebase);
3. **`árvore(merge) == árvore(cabeça testada no CI)`** — é isto que transfere o verde, e ele foi
   medido, não presumido (log `117`, saída `IGUAIS? SIM` nos nove);
4. o **diff exclusivo** do próximo elo recalculado contra o novo `main`.

Recolocação de base (#245, #246, #247) só foi feita no ponto em que o elo anterior já estava
integrado, e antes de cada `gh pr edit N --base main` mediu-se `árvore(main novo) == árvore(base
antiga do ramo)`: `c4385308 == af6a5c6e` (`cffe5779dbb2`), `66b442b6 == 2d6a8957` (`c67dc3ade19d`),
`cb71a527 == c4975979` (`622b176c093d`) — as três **IGUAIS**, o que prova que a mudança de base não
introduziu conteúdo novo e, por isso, não gerou nova execução obrigatória. Diff exclusivo de #247
antes (`105 arquivos, +12 118/−103`) e depois da mudança de base: **o mesmo número**.

Zero conflito. Nada foi apagado: branches, bundles, backups e acervo permanecem.

## 4. Resultado histórico da suíte integral — preservado, não redeclarado

A suíte integral local da nona rodada fechou com **1 failed, 6 528 passed, 47 skipped**
(`2026-09-29-rc01-esde-import-generation/100-checkpoint-integral-nono-elo.log`). **Essa corrida não
é declarada aprovada aqui.** O único falho era o gate de governança (`test_committed_catalog_and_generated_views_are_consistent`,
11 `scopeDigest` envelhecidos, todos atribuíveis por leitura dos cartões aos arquivos daquele elo), e
o seu remédio — renovação de digests no valor impresso pela ferramenta + `render --write` — foi
registrado **separadamente** (`105-renovar-digests.log`, `105b-status-check-depois-da-renovacao.log`,
`110-gate-visual-apos-governanca.log`), exatamente como a autorização pede.

Depois do consolidado, a suíte obrigatória foi re-executada pelo CI no `main` (log `123`): nos três
interpretadores, **6 199 itens coletados, 0 falhas, 0 erros, 47 pulados** (= 6 152 aprovados), e o
gate visual **365 passed, 12 skipped, 6199 deselected**. Correcção inclusa: o "377 passed, zero
pulados" que circula nas rodadas é do gate **local**, não do CI; as duas corridas de CI (cabeça de
#247 e `main` consolidado) têm contagens idênticas.

## 5. Estado final do `main` consolidado

`7808374257db3059c1934cb4be6007d8a749346e` · árvore `2a4d29fcd190` · **8/8 checks obrigatórios em
SUCCESS** por push direto (run 878 / id 36689372443), lidos pelo observador `119` e por verificação
direta às 08:48:34Z.

* `src/steamzero/ui/qml/sizes.js` e `readiness.js` presentes, com **consumidores** apontando para
  eles: `Sizes.bytes` 10× em `Emulation.qml`, `Main.qml`, `SteamGameplay.qml`,
  `ThemeCatalogPanel.qml`, `ThemeEditorPanel.qml`; `readiness.js` importado em `EditorialLibrary.qml`,
  `Emulation.qml`, `Main.qml`, `SteamGameplay.qml` e no harness `tests/qml/check_readiness_surface.qml`.
* Correções da fileira presentes e com contagem de símbolo: `esdeImportGeneration` 24×,
  `retrofeImportGeneration` 13×, `resetEsdeImport` 3×, `resetRetrofeImport` 4×, `ocupadoAntes` 16×.
* **Empacotamento** (log `122`): o wheel `steamzero-2.0.0rc1-py3-none-any.whl` do run do próprio SHA
  consolidado tem proveniência `commit = 7808374257db…`, `sourceTreeState = clean`, `sha256` batendo
  com `SHA256SUMS` e com a proveniência (`a1cd3709b73f…`), `pip-audit` limpo em 9 dependências,
  625 arquivos, 61 `.qml`. Varredura do delta: **os 20 arquivos de `src/` que a fileira mudou estão
  todos no pacote, byte-idênticos ao `main`**.
* Existência de arquivo **não** foi tratada como prova de pacote, e pacote **não** é release
  instalada: nada foi instalado (log `122`, §4).

## 6. Preservação do que ainda estava em temporário, e varredura de segredo (logs `120`, `127`)

Todas as referências a `/home/misael/steamzero-retrofe-tmp` feitas por arquivos versionados foram
extraídas, copiadas para `/home/misael/steamzero-evidencia-integracao-2026-09-30/` e reconciliadas:
**79/79 cópias byte-idênticas aos originais**; `LC_ALL=C sha256sum -c MANIFEST.sha256` → **86/86 OK**.
O manifesto e o leia-me desse arquivo estão nesta pasta (`120b`, `120c`), então o fechamento não
depende do temporário. Nada foi apagado do temporário.

Sobre segredo e dado pessoal a afirmação é medida, não juízo — script `127-varredura-de-segredos.sh`,
resultado `127-varredura-de-segredos-e-dados-pessoais.log`, com dois alvos declarados: **A** =
conteúdo integral dos arquivos versionados desta pasta (o script e o próprio log ficam fora, por
auto-correspondência declarada no log); **B** = as linhas adicionadas nos arquivos já versionados.
Os totais de cada alvo — arquivos e linhas — os imprime o log `127`, corrido como última escrita
antes do commit, para que nenhum número deste parágrafo envelheça ao editar este README. Seis
classes — token GitHub, chave PEM, segredo atribuído a chave de config, e-mail, JWT, caminho
absoluto pessoal fora do repositório — deram **zero em A e zero em B**. O zero não é ausência de
procura: o mesmo log aplica os seis padrões a uma *fixture* sintética com seis linhas plantadas em
`/tmp` (uma por classe, nunca commitada) e acha as seis. Os únicos caminhos absolutos que esta
entrega publica são o do checkout, o do temporário e o do acervo durável, necessários para repetir
o comando.

O log `127` também registra o que ele **não** cobre, com número remedido: sete linhas de
`docs/WORKLOG.md` trazem caminho absoluto do acervo pessoal (firmware e ProdKeys de Switch, BIOS
pack, coleções RetroFE, psvita) — e são **as mesmas sete em `3495c49d`**, a base anterior à fileira.
A fileira não acrescentou nenhuma (0 nas linhas adicionadas pelos seus 524 arquivos), e este
fechamento também não (0). Reescrevê-las seria apagar fato registrado, o que a ordem proíbe; ficam
como pendência declarada ao operador, não como alegação de limpeza do arquivo inteiro. E o zero do
parágrafo anterior não é ausência de procura: a mesma passada sobre uma *fixture* sintética com seis
linhas plantadas — uma por classe — acha as seis.

## 7. Quadro final da RC-01

Camadas: **I** interface implementada · **C** contrato testado offscreen · **G** código integrado em
`main` · **P** artefato empacotado no SHA consolidado · **H** experiência comprovada na release
instalada. Fonte das linhas: `104-reconcilio-rc01-nono-elo.md` (nono elo), re-confrontada agora.

| critério | comportamento disponível | teste/evidência | SHA integrado | P | H | pendência concreta |
|---|---|---|---|---|---|---|
| Contraste essencial conforme política | tinta por estado do contrato v2, inclusive cabeçalho do painel | `#243`/`#247`; bateria de mutações; `2026-09-26-rc01-central-loading/14-contraste-politica-normativa.log` | `5f6ff508`/`78083742` | sim | **não** | decisão de produto 4,5:1 vs ≥7:1; prova física |
| Loading/erro/vazio explícitos, sem tela vazia enganosa | central legível durante carregamento, erro com causa e retry | `check_central_loading.qml`, `check_status_refresh_coalesced.qml` | `cba3fe42` (#240) | sim | **não** | prova física na release instalada |
| `timeout`/`retry` sem corrida | refresh pendente coerçado sem perder erro/retry | `2026-09-26-rc01-central-loading/09-refresh-coercido.log` | `cba3fe42` | sim | **não** | prova física |
| Custo da consulta de status | medição antes/depois no mesmo catálogo | `01/02-baseline-e-final-status-probe.log` | — (backend fora do escopo) | — | **não** | cauda de ~11,4 s em `emulation` continua aberta, no backend |
| Semântica da prontidão (UX-03) | contrato `readiness.js` v2: estado, número nullable, dimensão nomeada, recusa de "pronto" por existência | `#243` + `tests/qml/check_readiness_surface.qml` + mutações | `5f6ff508` | sim (`readiness.js` idêntico no wheel) | **não** | F-1 (`memoryGb` → bytes) ainda não implementado |
| Unidades de armazenamento (UX-04) | um formatador `Sizes.bytes` para as quatro vistas | matriz de locales, 8/8 mutações, varredura 619/619 | `c4385308` (#244) | sim (`sizes.js` 2 377 B, `6d5ca418…`) | **não** | prova física no locale do host |
| Primeira dobra da Home | contrato da dobra no pior caso alcançável (264 px cortados; primeiro alvo 449/468 px) | oitavo elo: `38`, `39`, `40`, `46`, `47`, `48`, `52` | `cb71a527` (#246) | sim | **não** | prova física com compositor real |
| Foco, escala e alcance (UX-05/UX-07) | navegação por teclado e alvos ≥48 px nas superfícies exercitadas | `#241`, `#242` (QtTest de eventos reais) | `67e30afc`, `231ba4d3` | sim | **não** | cinco superfícies roláveis ainda não medidas |
| ES-DE dentro do shell — resposta tardia | contrato de geração nas duas rotas (painel e raiz) | nono elo: `70`, `73`, `74`, `98`, `100`, `110`; 10 cenas com atraso real, 9/10 mutantes mortos | `78083742` (#247) | sim | **não** | prova física; M9 declarado equivalente e pinado |
| RetroFE dentro do shell — resposta tardia | mesma classe de contrato, rollback do dedup corrigido | sétimo elo `2026-09-29-rc01-retrofe-shell-late/` | `66b442b6` (#245) | sim | **não** | prova física |
| Reabertura, erro e recuperação de respostas tardias | par (a)+(b) sem exceção: descartar o efeito, não a bandeira | duas baterias de mutação, testemunhos | `66b442b6`, `78083742` | sim | **não** | pedido em voo **não** é cancelado (limite declarado) |
| Seletor nativo de diretório | `FolderDialog` existe e a rota por Enter funciona | `06-medida-seletor-nativo-offscreen.md`, `17-sonda-qmltestrunner-dialogo-nativo.log` | já estava em `main` antes da fileira | — | **não** | **PENDENTE**: não é dirigível por evento sob offscreen; a rota por Enter não promove a rota não testada |
| Captura visual certificada em CI | — | 9 capturas byte-idênticas no run 36341332344 | — | — | **não** | `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` segue aberto; nenhuma PNG é alegada |

**O que este fechamento move:** a coluna **G** passa de "não" para **sim em todas as linhas** — com
prova de árvore por elo, não com a manchete do CI. A coluna **P** passa a "sim" apoiada na varredura
dos 20 arquivos de `src/` dentro do wheel do SHA consolidado. **Nenhuma linha move H**: prova física
não foi executada, e validação offscreen não promove hardware. Isto é a diferença entre *código
integrado* e *experiência comprovada na release instalada*, e ela continua sendo a pendência real da
RC-01.

## 8. Situação no host e próxima intervenção (arquivo `125`)

O plano está em `125-preparacao-do-host-no-sha-consolidado.md`, derivado de
`2026-09-29-rc01-home-first-fold/62-preparacao-de-validacao-fisica.md` (mesmos cenários, mesmas
separaciones de "prova/não prova"). Pré-condição 1 (fileira integrada) está **satisfeita**; 2
(release governada), 3 (autorização específica de instalação) e 4 (rollback confirmado no host)
continuam do operador. **Nada foi instalado.**

## 9. Próxima decisão concreta

Autorizar a construção da release candidata a partir de `7808374257db3059c1934cb4be6007d8a749346e`
pelo fluxo governado (`tools/release_host.py`), com `--source-commit` completo e verificação de
bundle/proveniência, e então conceder (ou recusar) a autorização específica de instalação com token.
Sem isso, a coluna H continua "não" para os treze critérios, por razão legítima e não por falta de
teste. Fora disso, ficam abertos dentro do escopo: F-1 (`memoryGb`), as cinco superfícies roláveis
não medidas, e — dependente de decisão de produto — a política de contraste.
