# 17 — A alegação sobre os donos de `Main.qml` estava errada; re-medida

Instrução do operador (2026-09-28, item 6): *resolver a coordenação da cadeia de
integração — cabeças, bases e dependências atuais **sem presumir merges** — e
apresentar a sequência concreta e os bloqueios ao operador.* Item 7: *reconciliar
claims antes de mexer em arquivo compartilhado.*

Na rodada 16 esta frente escreveu, no cartão `SZ-UI-DESKTOP-AUDIT`, no workstream
`WS-2026-09-RC01-READINESS-SEMANTICS` e em `docs/WORKLOG.md`:

> `Main.qml` tem **DOIS** donos exclusivos ativos simultaneamente
> (`WS-2026-09-AURA-LAUNCHER-EXIT` e `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT`)

**Essa frase é falsa.** Foi produzida por leitura de nome de workstream, não por
pertença de caminho, e é exatamente o tipo de alegação que o cartão normativo não
pode carregar. Corrigida por medição nesta rodada; o erro fica registrado aqui em
vez de apagado.

## 1. Como se mediu (reprodutível)

`17-claim-de-donos-re-medido.log` é a saída crua do script abaixo, executado no
checkout canônico. Três detalhes importam, e os três erram em quem mede depressa:

- só entram workstreams com `state == "active"` (10 dos 100 arquivos da pasta);
- a comparação é **pertença exata de caminho** (`t in exclusivePaths` /
  `t in sharedPaths`), não `endswith`, não basename — `endswith("qml")` faz
  `Main.qml` casar com `LaunchMain.qml` e inventa donos;
- `exclusivePaths` e `sharedPaths` são conjuntos diferentes: um arquivo pode ter
  um dono exclusivo e vários compartilhantes, e isso **não** é conflito de dono.

```bash
.venv/bin/python - <<'PY'
import json, glob
alvos = ["src/steamzero/ui/qml/Main.qml", "src/steamzero/adapters/emulation.py", ...]
for p in sorted(glob.glob("docs/status/workstreams/*.json")):
    d = json.load(open(p))
    if d.get("state") != "active": continue
    ex, sh = set(d["exclusivePaths"]), set(d["sharedPaths"])
    ...
PY
```

## 2. O que a medição diz

| arquivo | dono exclusivo | compartilhado por |
| --- | --- | --- |
| `src/steamzero/ui/qml/Main.qml` | `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` (um) | CENTRAL-LOADING, READINESS-FOCUS, READINESS-SEMANTICS, SHELL-ESDE-DIALOG (quatro) |
| `src/steamzero/adapters/emulation.py` | `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` (um) | EMULATION-REAL-DUMP-VALIDATION, EMULATION-RUNTIME-REMEDIATION, HIGH-END-RUNTIME-READINESS, MULTIDISC-MATERIALIZATION-INGESTION, READINESS-SEMANTICS (cinco) |
| `src/steamzero/ui/qml/Emulation.qml` | nenhum | READINESS-FOCUS, READINESS-SEMANTICS |
| `src/steamzero/ui/qml/SteamGameplay.qml` | nenhum | READINESS-SEMANTICS |
| `src/steamzero/ui/qml/ThemeCatalogPanel.qml` | nenhum | nenhum |
| `src/steamzero/ui/qml/ThemeEditorPanel.qml` | nenhum | READINESS-FOCUS |
| `src/steamzero/schemas/emulation-workspace-v1.schema.json` | nenhum | READINESS-SEMANTICS |

`WS-2026-09-AURA-LAUNCHER-EXIT` não reivindica `Main.qml`: as `exclusivePaths`
dele são de launcher (`src/steamzero/ui/qml/launcher/*.qml`, `SteamLauncher.qml`,
os testes correspondentes). A frase da rodada 16 confundiu "existe um claim de
launcher ativo" com "é dono deste arquivo".

Consequência para o item 6: **não há bloqueio de dono exclusivo em `Main.qml`.**
O que existe é a serialização de quatro claims compartilhados, que é decisão de
ordem de merge do operador — e a regra aplicada por esta frente continua a mesma
(AGENTS.md §2: mudança em arquivo compartilhado vai em commit próprio, por último).

## 3. Correção do vermelho da UX-04, na mesma passada

A rodada 16 também registrou o vermelho da UX-04 como *validado por execução em
cópia isolada*. A cópia (`/tmp/rp`) serviu para escrever e depurar o harness, e é
dela o stdout bruto gravado em `/tmp/ux04_vermelho_forma.log`:

```
qml: check_storage_units: 30 falha(s) de 72 (primeira em #5)
```

Depois o harness foi copiado para `tests/qml/check_storage_units.qml` (mesmo
`sha256` `cb72549006b57ea5…`) e registrado na lista parametrizada de
`tests/integration/test_qml_handheld_offscreen.py`, que é o gate visual que o CI
executa. O vermelho **dentro do checkout** é re-rodado com log bruto na pasta de
evidência da UX-04 (`18-vermelho-no-gate-visual-do-checkout.md`), não aqui: esta
rodada é da frente da prontidão e não deixa prova de outra frente no seu escopo.
O que se corrige aqui é a procedência da alegação — o verde/vermelho que conta é
o do gate, não o da cópia.

As 30 falhas cobrem as sete exigências da sonda, convertida de descritiva em
normativa: convergência entre as quatro superfícies, rótulo binário sobre divisor
binário, ausência ≠ `0 B`, zero medido ≠ "não publicado", 512 B não pode sumir,
existir andar acima de GiB, separador decimal do locale. A primeira falha (#5) é
de convergência — dois formatadores já discordam no primeiro valor não trivial.

## 4. O que mudou nesta rodada, e o que não mudou

Mudou: o texto de `nextAction` do cartão e do workstream (a alegação falsa
substituída pela tabela medida), as visões `docs/STATUS.md` e
`docs/ACTIVE-WORK.md` (regeradas por `tools/project_status.py render --write`,
nunca à mão), este par de arquivos de evidência, e o `scopeDigest` do cartão,
renovado **depois** de escrever a evidência (a pasta de evidência está em
`scopePaths`; o cartão e o workstream não estão — verificado por pertença).

Não mudou: nenhum arquivo de produto, de schema ou de teste. A suíte integral não
foi re-rodada — esta rodada é documental e o conteúdo funcional enviado é o mesmo
do checkpoint 13, com `sha256` do harness conferido.

`docs/WORKLOG.md` é apêndice-only por instrução (§2): a frase falsa da sessão de
fechamento da rodada 16 **não** foi editada retroativamente; a correção é
declarada na sessão seguinte, que aponta para este arquivo.
