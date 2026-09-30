# 28 — Fora de escopo deste elo, medido e com dono: o importador ES-DE continua sem contrato de geração

## O fato

Este elo (sétimo) fecha a **resposta tardia do importador RetroFE** com contrato de
geração do pedido. A varredura que motivou o corte procurou exatamente a mesma classe de
defeito nas outras entradas assíncronas do painel, e encontrou uma: o importador **ES-DE**,
no mesmo arquivo, não tem o contrato.

## Medição (árvore deste corte, `src/steamzero/ui/qml/ThemeEditorPanel.qml`)

```
grep -c esdeImportGeneration     src/steamzero/ui/qml/ThemeEditorPanel.qml -> 0
grep -c retrofeImportGeneration  src/steamzero/ui/qml/ThemeEditorPanel.qml -> 12
```

As cinco escritas incondicionais de estado em callbacks ES-DE:

| linha | função | escrita |
|---|---|---|
| 215 | `resetEsdeImport()` | `panel.esdeImportBusy = false` |
| 229 | `inspectEsdeImport()` — callback de sucesso | `panel.esdeImportBusy = false` |
| 239 | `inspectEsdeImport()` — callback de erro | `panel.esdeImportBusy = false` |
| 263 | `applyEsdeImport()` — callback de sucesso | `panel.esdeImportBusy = false` |
| 271 | `applyEsdeImport()` — callback de erro | `panel.esdeImportBusy = false` |

Propriedades envolvidas (`:72`-`:78`): `esdeImportSource`, `esdeImportSchemes`,
`esdeImportSchemeIndex`, `esdeImportName`, `esdeImportBusy`, `esdeImportNotice`,
`esdeImportNoticeIsError`.

Nenhuma delas é comparada a uma geração antes de escrever. Consequência, do mesmo modo que
os mutantes M1/M2 provaram no RetroFE: uma resposta de `theme.import.esde.inspect` que
chega depois de o diálogo ter fechado, ou depois de um segundo clique recusado por
deduplicação, reescreve `esdeImportSchemes`, `esdeImportBusy`, `esdeImportNotice` e
`esdeImportNoticeIsError` numa superfície que o usuário já deixou.

## Por que não foi corrigido aqui

AGENTS.md §2 e a serialização medida: `tests/qml/check_shell_esde_import_dialog_journey.qml`
e o gate `tests/integration/test_ui_shell_esde_import_dialog.py` pertencem à frente
`WS-2026-09-RC01-SHELL-ESDE-DIALOG` (base do PR #241/#242), e o cartão `docs/status/items/theme-import-surface.json`
("Importação de temas acessível pela área Temas", medido: `implementation=partial`,
`integration=feature-branch`, `verification=unit`, `distribution=not-packaged`) é o eixo
que registra a entrada ES-DE. Este corte já altera
`ThemeEditorPanel.qml` (compartilhado, com commit isolado) — abrir o contrato ES-DE aqui
mudaria duas capacidades em um elo e deixaria o oitavo sem uma frente coesa.

O precedente está a favor de um corte próprio: a correção do RetroFE saiu de um vermelho
reproduzido (`00-vermelho-reproduzido.md`, `07-vermelho-rollback-do-dedup.md`) e de uma
bateria de mutações (M1–M4 + guarda G, `08-bateria-de-mutacoes.md`). O ES-DE precisa dos
mesmos quatro mutantes antes de ser declarado fechado, e não de uma cópia da correção sem
vermelho.

## O que o elo seguinte precisa provar

1. **Vermelho**: examinar com atraso e fechar o diálogo → `esdeImportSchemes` reescrito
   depois do fechamento; e o par do `apply`.
2. **Rollback do dedup**: recusar um segundo clique por payload idêntico devolve
   `busy`/geração ao valor anterior, sem travar o botão em `busy=true` (o M1 do RetroFE
   era exatamente isso).
3. **Porta de teclado**: Enter no campo de origem exercendo a rota autenticada, com
   contagem reconciliada na ponte (o análogo do M4).
4. **Guarda de intenção**: o harness não pode chamar `inspectEsdeImport()` direto.
5. **Limite não removível**: o seletor nativo continua fora de prova sob offscreen
   (`06-medida-seletor-nativo-offscreen.md`) — a correção ES-DE não promove esse item.

## Situação

**Parcial, com dono nomeado.** Nada neste documento é alegação de comportamento na release
instalada: a fileira inteira ainda não chegou a `main`, e a release `2.0.0rc1-e2af2562ebba`
não contém nenhum destes painéis.
