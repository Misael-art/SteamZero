# Evidência — 4ª fatia de RC-01: diálogo ES-DE do shell (2026-09-27)

Ramo `codex/rc01-shell-esde-dialog-2026-09-27`, base `190ea683` (o SHA aprovado
que destravou o gate de capturas). Workstream:
`docs/status/workstreams/rc01-shell-esde-dialog-2026-09-27.json`
(`WS-2026-09-RC01-SHELL-ESDE-DIALOG`, cartão `SZ-UI-DESKTOP-AUDIT`).

O que a fatia entrega: o diálogo de importação ES-DE do **shell**
(`Main.qml`, objeto `theme-import-esde-dialog`) passa a ter jornada completa e
tocável no Deck — abrir → examinar pela rota real → preencher o nome → navegar
com o D-pad → publicar ou cancelar — com corpo rolável, rodapé de ações fixo de
48 px, respeito à escala de texto do host e recusa legível. O diálogo duplicado
do **painel de temas** (`ThemeEditorPanel.qml`) não é esta fatia e não foi
tocado.

## Índice

| Arquivo | Conteúdo |
| --- | --- |
| `00-preflight.log` | checkout único; o defeito confirmado na base; conciliação do claim de `Main.qml` com o dono `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` (diff vazio medido com controle, autorização de RC-00 citada, blobs de `origin/main` e da frente do dono iguais). Registramos aqui o risco de medir com `rtk git` em vez de `rtk proxy git`. |
| `01-vermelho-geografia-medida.log` | a execução vermelha (`12 failed, 7 passed, 1 deselected in 61.18s`), as doze reprovações, e as cinco linhas `GEOMETRIA` verbatim que fecham o diagnóstico em quatro números. |
| `02-gate-focado-verde.log` | o verde (`20 passed in 67.62s` na árvore promovida; a corrida de `60.96s` está preservada em bruto e o motivo da re-medição está registrado no próprio arquivo), o denominador QtTest por cenário, a geografia declarada por cenário e as três leituras de 48 px. |
| `03-duas-reprovacoes-causa-medida.log` | as duas reprovações que sobraram depois de corrigir o produto (`2 failed, 18 passed in 59.34s`): as duas eram o **teste** medindo a grandeza errada, cada uma com a causa medida. |
| `04-capturas-inspecionadas.log` | sha256, bytes e dimensão de cada PNG (verde e os dois vermelhos preservados), igualdade com a árvore viva, e o que cada imagem mostra. |
| `05-alvo-de-captura-medido.log` | por que a captura é do `QQuickRootItem` da janela e não do `contentItem`, do overlay ou do `Popup` — medido, não presumido. |
| `06-gate-integral-unico.log` | a **única** execução dos gates integrais (`make check` + `make qml-visual`) sobre a árvore congelada, alvo por alvo, com o RC de cada um e a identidade da árvore extraída do log bruto (não re-medida depois). As duas corridas lado a lado: `1 failed, 6432 passed, 47 skipped` antes → `6433 passed, 47 skipped` agora, com o denominador reconciliado e o auto-hash do log explicado. |
| `07-integracao-encadeada-medida.log` | a medição que precede a integração #239 → #240 → #241: heads/bases lidos do remoto, ancestralidade, carga própria de cada elo, o que sobra do diff de cada PR depois de cada merge, e por que squash/rebase quebraria os elos seguintes. Nenhum merge é feito por esta frente. |
| `08-causa-medida-revelacao-e-oraculo.log` | os nove passos que fecham o "faltam 4 px" da escala 1.25: a banda que recorta é o `Flickable` (431 px) e não o `ScrollView` (491 px) — o corte real era de 64 px —, a causa do produto (revelação de foco one-shot), o vermelho determinístico sem carga, e as três corridas sob carga com a de árvore não congelada declarada como não-promotora. |
| `09-cobertura-delta-medido.log` | a queda de 85,54% para 85,52% contra a regra `Cobertura não regride` (AGENTS.md:115): o delta atribuído arquivo por arquivo (seis arquivos fora desta frente, nove statements, soma exata, statements totais idênticos) e três rodadas do mesmo comando na mesma árvore, que mostram duas das linhas flutuando sem código mudar — com as quatro restantes declaradas não reproduzidas. |
| `imagens/` | as cinco capturas verdes + `geometria.json` + `ambiente.json` + `saida-da-cena.txt`. |
| `imagens/vermelho/` | os dois PNGs vermelhos que sobreviveram à sobrescrita da corrida verde. |
| `logs/` | 18 arquivos: os 16 logs estáveis de `qmltestrunner`/`qml` desta fatia (`shell-esde-*.txt`, um por cenário × viewport × escala, refreshados na árvore congelada), `corrida-promovida.txt` (comando, ambiente, `20 passed` e o sha256 dos quatro arquivos testados) e `falha-integral-shell-esde-48px-escala-1.25.txt` (a reprovação da suíte integral **anterior** à correção, preservada como está). |
| `logs/carga-e-causa/` | os 7 artefatos brutos do item `08`: o antes-da-correção sob carga, o vermelho determinístico do `test_10`, o oráculo apertado reprovando em 1280×800, as três corridas de controle de carga e o gate focado final sem carga. |

### Caminhos pessoais nos logs

Nenhum log desta pasta é copiado cru. A normalização tem três regras e nenhuma
linha medida é reescrita: o caminho do checkout vira `<CHECKOUT>`, o tmp do
pytest vira `/tmp/pytest-of-<USER>`, e — como o pytest trunca linhas longas com
`...`, o que deixa prefixo pessoal cortado para trás — `/home/<usuario>` vira
`<HOME>`. Binários (PNG) são pulados com `-I`, porque editar um PNG quebraria a
evidência visual. A prova de que sobrou nada é uma contagem que **falha** se for
diferente de zero, não uma frase: a última verificação devolveu
`0 ocorrências do nome de usuário` nesta pasta.

## Como conferir sem depender desta narrativa

```
.venv/bin/python -m pytest tests/integration/test_ui_shell_esde_import_dialog.py -q
```

Vermelho recuperável por Git, sem recriar nada: `git diff 190ea683 -- src/steamzero/ui/qml/Main.qml`
mostra a forma que produziu as linhas de `01`. Os números de `logs/` são as saídas
verbatim das corridas; `imagens/geometria.json` é o que a cena de captura escreveu,
não o que este arquivo afirma.

## Limites desta fatia (não promovidos pelo verde acima)

- Alvos de 48 px **deste diálogo**. O resto do shell não foi medido alvo a alvo.
- A revelação de foco revalidada (`focusedRevealScroll` + `onHeightChanged` /
  `onContentHeightChanged` em `Main.qml`) cobre o caminho que a jornada exercita.
  As outras cinco superfícies roláveis do shell (`Emulation.qml`,
  `SectionNavigator.qml`, `SteamGameplay.qml` e dois diálogos de
  `ThemeEditorPanel.qml`) **não** foram medidas com banda mudando sob foco e não
  se alega que estejam corrigidas nem quebradas — é terreno não provado.
- Limite conhecido e não corrigido: fechado o diálogo, uma resposta antiga de
  `/inspect` ainda pode chegar e regravar `esdeImportSchemes`. Nada disso é
  visível na jornada provada (a lista é limpa na reabertura) e nenhum teste
  depende disso; registrar antes de tocar no transporte.
- RC-01 continua aberta: primeira dobra da Home, UX-03 (percentuais de prontidão),
  UX-04, RetroFE dentro do shell e validação física instalada. Nada aqui autoriza
  promover essas capacidades.
- Foco visível é medido como *propriedade declarada + geometria do anel de foco*,
  não como percepção humana em painel físico.
- Rode no Deck real antes de qualquer claim de usabilidade física: aqui o host é
  `offscreen`.
