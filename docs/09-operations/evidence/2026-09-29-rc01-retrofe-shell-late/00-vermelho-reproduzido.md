# Vermelho reproduzido — resposta tardia do importador RetroFE dentro do shell

Corte 63 de RC-01 (fatia 5ª do eixo "RetroFE na shell"). Este lote **só reproduz**:
nenhum arquivo de produto foi tocado. O verde é o corte seguinte (64).

## Identidade da árvore no momento do vermelho

| campo | valor |
| --- | --- |
| branch | `codex/rc01-retrofe-shell-late-response-2026-09-29` |
| HEAD | `af6a5c6ed8523c04030d25b1d391e885a3b3b48e` (= cabeça do PR #244) |
| `git status --short` | `?? tests/integration/test_ui_shell_retrofe_import_late_response.py`, `?? tests/qml/check_shell_retrofe_import_late_response.qml`, `?? docs/09-operations/evidence/2026-09-29-rc01-retrofe-shell-late/` |
| `git diff --stat -- src/steamzero/ui/qml/` | vazio — `ThemeEditorPanel.qml` e `Main.qml` intocados |

## Comando e resultado

```
PATH="$PWD/.venv/bin:$PATH" QT_QPA_PLATFORM=offscreen \
  python -m pytest tests/integration/test_ui_shell_retrofe_import_late_response.py -q
```

`1 failed, 8 passed in 13.14s` → `01-pytest-arquivo-novo.log`. A falha é a
asserção de contrato do produto, não infraestrutura:

```
AssertionError: a resposta tardia do apply re-listou temas depois de a superfície
fechar (1 GET /theme_list após o último POST, posição 11 de 14):
[('POST', '/theme/import/retrofe/apply', '/media/retrofe/cena-curta-aplicar-tardio'),
 ('GET', '/theme/list', ''), ('GET', '/status', '')]
```

Os 8 verdes são as 7 guardas sem Qt + a testemunha `test_a_ordem_de_resposta_inverte`
(que prova que a corrida existiu — ver abaixo).

## Os quatro defeitos, cada um com sua testemunha medida

Do runner (`02-runner-jornada.log`, mesmas 4 falhas em `04-runner-ordem.log`, pois o
`qmltestrunner` roda a suíte inteira em cada gate):

| cena | o que a superfície fez | onde está no produto |
| --- | --- | --- |
| `test_02` | `a resposta tardia reescreveu 3 layouts num diálogo fechado` (`layouts=3, indice=0, aviso=66` com `dialogo=fechado`) | `inspectRetrofeImport()` escreve estado sem conferir a geração — `ThemeEditorPanel.qml:338-363`; o `onClosed` só limpa, não invalida — `:1168` → `resetRetrofeImport()` `:324-336` |
| `test_03` | `a resposta do pedido ANTERIOR substituiu o resultado do pedido mais novo: layouts=3, esperado 1` | mesma escrita incondicional; `Main.qml:1119` só deduplica payload idêntico, então dois exames em voo convivem |
| `test_04` | `a resposta tardia do apply anunciou 'Cena RetroFE publicada com assets validados; ela ainda não foi ativada.' num diálogo fechado` | `applyRetrofeImport()` `:365-397` |
| `test_05` | `reabrir mostrou '/media/retrofe/cena-curta-reabertura' no campo de origem, sendo que o estado do importador está vazio` | `TextField { text: panel.retrofeImportSource … onTextChanged: … }` `:1216-1224` — a primeira edição quebra o binding e o `onClosed` não o reafirma; o guard do "Examinar" lê o ESTADO (`:1242`), então botão e texto discordam |

`test_01` passa: a rota real do shell (seção Temas → aba "Editar aparência" → botão →
examinar → publicar) funciona e publica `activated: False`.

## Reconciliação com a ponte (não é narração do teste)

`03-ponte-jornada.log` / `05-ponte-ordem.log` — 14 eventos atendidos,
`status_calls=5`, `unauthorized=0`:

- inspects = 5 (`ESPERADO_INSPECT`), applies = 2 (`ESPERADO_APPLY`) — as contagens da
  asserção batem com o artefato;
- o `/theme/list` da posição **12** vem depois do último `apply` (posição **11**): é o
  `panel.refreshThemeList()` (`:391` → função `:196`) disparado pela resposta tardia;
- a corrida está registrada nas duas listas: chegaram `cena-lenta-anterior` (03) antes de
  `cena-rapida-mais-novo` (04), mas **saíram** `cena-rapida-mais-novo` (03) antes de
  `cena-lenta-anterior` (04). A ordem de resposta inverteu de fato — sem isso o
  `test_03` poderia passar sem nunca ter medido resposta fora de ordem. A ponte é
  `ThreadingHTTPServer` por design: com uma thread só o atraso serializaria e a
  inversão jamais aconteceria.

## Limites declarados deste corte

1. **Nada aqui cancela requisição.** O vermelho mostra efeito tardio sendo aplicado; a
   correção planejada descarta o efeito por geração do pedido, não aborta o `XMLHttpRequest`
   em voo. A alegação de "falha degradada, nunca travada" continua sendo do shell, não desta fatia.
2. A ponte é um servidor HTTP local com atraso artificial (`atraso_ms` 120/1500): prova o
   contrato de resposta da camada de UI, não o importador real nem o disco.
3. **Nenhum PNG é entregue por este lote** — a captura canônica de artefatos QML continua
   com o `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` aberto.
4. `atraso_ms` nunca é lido pelo harness: o tempo de voo só existe na ponte, então o
   teste não afina atraso para passar.

## Dois falsos vermelhos encontrados e corrigidos neste lote (registro honesto)

1. O harness navegava para `sectionIndexOf("system")` (índice 6). O botão do importador
   RetroFE está na seção **Temas** (`navigationSections[7]`), aba "Editar aparência": com
   índice 6 o `themeEditorTab` existia mas nascia `visible=false` (página inativa do
   `contentStack`) e a ponte contava **0** inspects. Medido com sonda descartável; a
   primeira execução falhou por culpa do teste, e não foi gravada como vermelho.
2. Contar controles `checkable` dava `opções=3, layouts=2` — a `CheckBox`
   `themeImportRetrofeOverwrite` entrava na conta. O filtro passou a ser pelo prefixo da
   alavanca, e a caixa virou testemunha de não-vacuidade (continua sendo procurada).

Também corrigida a testemunha de ordem: ela comparava o `returncode` do runner com
`0/1`, mas o `qmltestrunner` devolve a **contagem de falhas** (aqui `4`, com
`Totals: 3 passed, 4 failed`) — a asserção reprovaria pelo defeito do produto e
esconderia um abort real. Passou a ler `Totals:` e a reconciliar com o retorno.
