# 18/19 — vermelho e verde do gate de unidades (UX-04)

## O que foi reproduzido antes de editar

`tests/qml/check_storage_units.qml` executa as **quatro páginas reais**
(`Emulation`, `Main`, `SteamGameplay`, `ThemeCatalogPanel`) sob `qml6
QT_QPA_PLATFORM=offscreen` e exige, por requisito da auditoria
(`AUDIT.md:124` — "unidades localizadas e consistentes"), que a mesma grandeza
tenha a mesma leitura em qualquer superfície.

| arquivo | conteúdo |
|---|---|
| `18-vermelho-no-gate-visual-do-checkout.log` | saída crua do gate no checkout **antes** de qualquer correção |
| `19-verde-no-gate-visual.log` | saída do mesmo gate **depois**, com as contagens |

Comando gravado nos dois logs:

```
.venv/bin/python tools/run_tests_isolated.py \
  tests/integration/test_qml_handheld_offscreen.py -m visual -k check_storage_units -q
```

## Vermelho medido (18)

* árvore: branch `codex/rc01-storage-units-2026-09-28`, head `c0de54c9` (UX-03 já
  corrigido, nada da UX-04 aplicado).
* harness na hora do vermelho: `sha256=cb72549006b57ea5a7d21f31b0e96e20777a49720daa23c002544e317e2a5f72`.
* resultado: **30 falhas de 72 checagens, primeira em #5** — `1 failed, 57 deselected`,
  código de saída do pytest `1`.
* estado real da árvore antes e depois da execução: idêntico (o gate não escreve).

As 30 falhas não são 30 defeitos: são os mesmos 6 defeitos × páginas. Por requisito:

1. **convergência** — o mesmo número lia `1.4 GB`, `1.40 GiB`, `139,70 GiB` e
   `1500000000 byte(s)` conforme a página;
2. **rótulo** — divisor 1024 rotulado em unidade decimal (`MB`/`GB`), o que afirma
   grandeza ~7 % menor que a medida;
3. **ausência** — `undefined` virava frase ("Tamanho não publicado") numa página e
   `0 B` em outra;
4. **zero medido** — virava "não publicado";
5. **teto** — sem andar acima de GiB, 1 TiB saía como `1024.00 GiB`;
6. **locale** — separador decimal fixo `.` em todos os formatadores próprios.

## Verde medido (19)

* harness atual: `sha256=bf437d2bc270735873f6919f83ff8debfcf5ffd71030609b65befcca9f967e67`
  (cresceu: dois grupos novos — cartão medido e prosa localizada, mais normalização);
* `sizes.js`: `sha256=6d5ca418e514258fe6e55d1e9e5c2011fc9e306b6eb023bda77ee6be315a4829`;
* resultado: `1 passed, 57 deselected`, e o próprio harness declara
  **109 verificação(ões) ok** com código de saída 0.

A contagem de verificações vem de rodar o harness direto com `qml6` no mesmo
ambiente do gate, capturando a saída por `subprocess` — o pipe do `rtk` retém o
`stderr` do Qt, e isso já enganou uma leitura anterior (registrado no log 19).

## Diferença de verificação entre as duas execuções

18 usou `tools/run_tests_isolated.py` (blindado, um processo por suíte). 19 usou
`pytest -k check_storage_units` direto, porque só esse arquivo estava sendo
iterado. O gate registrado no CI é o parametrizado em
`tests/integration/test_qml_handheld_offscreen.py:253`, que roda dos dois jeitos.
