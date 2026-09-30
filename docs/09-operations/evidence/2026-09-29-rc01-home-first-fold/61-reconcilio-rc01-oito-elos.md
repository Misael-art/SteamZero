# 61 — RC-01 reconciliada critério a critério com os oito elos (2026-09-29)

Documento-fonte desta tabela: `29-reconcilio-rc01-cinco-camadas.md` (pasta do sétimo elo,
`2026-09-29-rc01-retrofe-shell-late/`), que trouxe dez critérios nas cinco camadas com o HEAD do
sétimo elo. Aqui a mesma medição é refeita **contra a cabeça deste oitavo elo**, e o que muda é
declarado linha por linha — nada é copiado sem reconfirmação.

Enunciado normativo: `docs/12-roadmap/IMPLEMENTATION-ROADMAP.md` (lote RC-01 / P1):
"Home utilizável no orçamento aplicável; sem tela vazia enganosa; contraste essencial conforme
política; controles alcançáveis em viewport compacto e escala de texto; timeout/retry sem
corrida".

Camadas (item 8 do operador, sempre colunas, nunca uma no lugar da outra): **I** interface
implementada · **C** contrato testado offscreen · **G** código integrado em `main` · **P** artefato
empacotado · **H** experiência comprovada na release instalada.

## Fundo re-medido nesta cabeça (vale para a tabela inteira)

| grandeza | valor medido em 2026-09-29 | como conferir |
|---|---|---|
| `origin/main` | `3495c49d5d7c3244267e8292beee34475f70236b` | `git fetch origin main && git rev-parse origin/main` |
| elos abertos da fileira | #239 `069501ab` · #240 `c959be13` · #241 `190ea683` · #242 `5d95034b` · #243 `c0de54c9` · #244 `af6a5c6e` · #245 `2d6a8957` · #246 `22773047` | `gh pr view N --json headRefOid,state` |
| ancestralidade | linear e conferida par a par: `git merge-base --is-ancestor` de cada cabeça com a seguinte, todas **não** ancestrais de `origin/main` | `58-prs-antigas.sh` + a tabela do corpo do PR #246 |
| commits somados da fileira | 2+5+13+4+10+16+8+12 = **70** = `git rev-list --count origin/main..22773047` | reconcilia a contagem e prova que nada se duplicou nem se perdeu |
| arquivos novos fora de `main` | `git ls-tree -r --name-only origin/main -- src/steamzero/ui/qml/sizes.js src/steamzero/ui/qml/readiness.js` devolve **vazio** | os dois formatadores deste trabalho ainda não existem em `main` |
| release instalada | `2.0.0rc1-e2af2562ebba` (26/09), anterior à fileira inteira | `HOST-INSTALL.md` / leitura read-only no host |

Consequência fixa: **G = não** e **H = não** para todos os critérios abaixo, sem exceção,
independentemente do verde. Isto não é opinião sobre qualidade; é a medição de que nenhum SHA
desta fileira está em `main` nem no artefato instalado.

## Tabela

| critério | I | C | G | P | H | situação nesta cabeça | evidência |
|---|---|---|---|---|---|---|---|
| Contraste essencial conforme política | sim | sim | **não** | não | não | **parcial — travado por decisão de produto (4,5:1 vs ≥7:1)**, não por falta de teste | `2026-09-26-rc01-central-loading/14-contraste-politica-normativa.log` |
| Loading/erro/vazio explícitos, sem tela vazia enganosa | sim | sim | **não** | não | não | **parcial** — falta integrar e provar na release | `#240`, gates `check_central_loading.qml` + `check_status_refresh_coalesced.qml` |
| `timeout/retry` sem corrida | sim | sim | **não** | não | não | **parcial** | `2026-09-26-rc01-central-loading/09-refresh-coercido.log` |
| Custo da consulta de status (latência) | parcial | sim, medido antes/depois | **não** | não | não | **parcial — cauda de ~11,4 s em `emulation` segue aberta**, é backend, fora das fatias de UI | `01/02-baseline-e-final-status-probe.log` |
| Semântica da prontidão (UX-03) | sim | sim | **não** | sim (`readiness.js` no wheel de `af6a5c6e`, batido com o blob) | não | **parcial — F-1 (`memoryGb`) e F-2 (prosa do plano) ainda não implementados**, medido de novo nesta cabeça | `#243`; `2026-09-28-rc01-readiness-semantics/` |
| Unidades de armazenamento (UX-04) | sim | sim (109 → 145 verificações, matriz de locales, 8/8 mutações) | **não** | **sim**, provado no artefato (`sizes.js` 2 377 bytes, `6d5ca418…` idêntico ao blob) | não | **parcial** — empacotado no CI, não integrado | `#244`; varredura 619/619 do wheel |
| **Primeira dobra da Home** | **sim** (regra em `Main.qml` + forma compacta em `ErrorCard.qml`) | **sim, e o pior caso está corrigido**: alvo 36 → 48 px, chrome 264 → 205 px, primeiro alvo terminando em 449/468 px dentro de banda de 493 px, `cabe=SIM` nas quatro cenas, 13 verificações + 4 mutantes (M1 5, M2 3, M3 3, M4 6) | **não** | **não** (ainda não varrido no wheel desta cabeça) | não | **parcial → gap funcional (a) da leitura de 28/09 FECHADO em contrato offscreen**; o que resta é G/P/H, não código | este lote: `38`, `39`, `40`, `46`, `47`, `48`, `52` |
| Foco, escala e alcance dos controles (UX-05/UX-07) | sim | sim, **só para as superfícies exercitadas** | **não** | sim | não | **parcial — cinco superfícies roláveis seguem não medidas** (`Emulation.qml`, `SectionNavigator.qml`, `SteamGameplay.qml`, os dois diálogos de `ThemeEditorPanel.qml`) | `#241`, `#242` |
| ES-DE dentro do shell | sim | sim para a jornada; **resposta tardia do `inspect` continua sem contrato de geração** | **não** | sim | não | **parcial — gap funcional (b) AINDA ABERTO**, re-medido nesta cabeça: `grep -c esdeImportGeneration ThemeEditorPanel.qml` = **0** contra `retrofeImportGeneration` = **12**; cinco escritas incondicionais de `panel.esdeImportBusy = false` nas linhas **215, 229, 239, 263, 271** | `ThemeEditorPanel.qml`; o precedente de correção está no mesmo arquivo, via #245 |
| RetroFE dentro do shell | sim | sim (9 cenas, 10 testemunhos, mutações) | **não** | **não ainda** — o CI terminal na cabeça `2d6a8957` foi lido (`32-ci-terminal-pr245-2d6a8957.log`), mas o wheel deste elo **não foi varrido** | não | **parcial — falta a prova P** (varredura do artefato), depois G e H | sétimo elo, `2026-09-29-rc01-retrofe-shell-late/` |
| Respostas tardias, reabertura, erro e recuperação | sim no RetroFE; **não** no ES-DE | sim no RetroFE | **não** | não | não | **parcial — o par (b) é exatamente este critério visto pelo lado do ES-DE** | limite declarado: o pedido em voo não é cancelado, descarta-se o efeito (`retrofeImportGeneration` :95-103) |
| Seletor nativo de diretório | existe na árvore (`FolderDialog`) | **não dirigível por evento sob offscreen** (medido) | **não** | não | não | **PENDENTE, e continua pendente embora a porta por Enter funcione** — caminho alternativo não promove o caminho não testado | `06-medida-seletor-nativo-offscreen.md`, `17-sonda-qmltestrunner-dialogo-nativo.log` |
| Captura visual certificada em CI | — | parcial (9 capturas byte-idênticas às baselines no artefato, run 36341332344) | **não** | — | não | **parcial — `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` segue aberto**, também para este oitavo elo: nenhuma PNG é alegada | `2026-09-27-gate-visual-causa-e-contrato/` |

## O que mudou desde a leitura do sétimo elo

1. **A linha "Primeira dobra da Home" moveu de (a) para resolvido em C.** Antes: "pior caso medido
   e **não corrigido**". Agora a correção existe, com vermelho antes (`5 failed, 3 passed`),
   atribuição por arquivo sob o M1 e quatro mutantes mortos. **Nenhuma outra coluna dessa linha
   mudou**: G, P e H continuam não.
2. **Nada mais se moveu por decreto.** As linhas de ES-DE, F-1/F-2, latência, cinco superfícies
   roláveis, seletor nativo e captura ficaram onde estavam, e foram **re-medidas** nesta cabeça
   (os dois `grep -c` e as cinco linhas de `esdeImportBusy` acima são saída de hoje, não cópia).
3. **Passou a existir prova empacotada só para UX-04** (`sizes.js`) e UX-03 (`readiness.js`). Os
   dois elos seguintes (RetroFE, dobra) ainda não têm varredura de wheel; isso é trabalho
   mensurável, não opinião.

## O que falta para a RC-01, em ordem de dependência

* **G** — decisão do operador: mergear a fileira na ordem de ancestralidade (#239 → #246). Nada
  aqui depende de mim.
* **P** — varrer os artefatos dos elos 7 e 8 (procedimento já provado no #244: baixar o wheel do
  run, comparar `sha256` de cada QML com o blob da cabeça, registrar a varredura).
* **H** — validação física do conjunto integrado, **preparada** em
  `62-preparacao-de-validacao-fisica.md`, sujeita à autorização específica de instalação.
* **Funcional executável dentro do escopo desta frente**: contrato de geração do importador ES-DE
  (b) e F-1 `memoryGb` → `memoryBytes` (c, parte 1). Ambos sem dono exclusivo no catálogo, com
  precedente adjacente no mesmo arquivo/formatador.
* **Funcional fora do escopo desta frente**: F-2 vive em `adapters/emulation.py`, cujo dono
  exclusivo é `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` — fica declarado, não editado.
* **Decisão de produto**: contraste (4,5:1 vs ≥7:1). **Limitação de plataforma**: seletor nativo
  fora do offscreen. Nenhum dos dois se resolve com teste.
