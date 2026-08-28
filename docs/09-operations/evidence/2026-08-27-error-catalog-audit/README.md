# Auditoria do catálogo de erros — 2026-08-27

Item: `SZ-AGG-CORE` (dono de `docs/06-api/ERROR-CATALOG.md` e `src/steamzero/core`).
Branch: `codex/error-catalog-audit`, base `e93e8da`. Nenhuma entrega física no
host nesta etapa; **a correção não tem superfície gráfica** — por isso não há
captura PNG aqui (ERROR-UX: captura decorativa é proibida).

## Pergunta da auditoria

Para cada código do catálogo: a `probableCause` é a causa real e a `manualAction`
resolve? Método: varredura de todos os literais `E-*` em `src/` (sítios de
emissão) e confronto com os textos fixos de `messages_pt_br.py`.

## Achado 1 — quatro códigos emitidos fora do catálogo (defeito vivo)

`E-CHEAT-CODE-INVALID`, `E-CHEAT-BUILD-ID-MISMATCH`, `E-MOD-TITLE-ID-NOT-FOUND`
e `E-SESSION-ORPHANED` eram emitidos sem registro. `SteamZeroError` recusa
código não registrado (ValueError), então as recusas de import de cheat/mod e o
reaproveitador de sessões órfãs produziam erro interno, nunca o erro de domínio.
Ver `01-baseline-codigos-fora-do-catalogo.txt`.

Por que 5266 testes verdes não pegaram: os testes do `cheat.import` cobriam só
o caminho feliz; e `test_errors.py` validava registro→i18n, nunca emissão→registro.
A promessa "CI falha se código emitido não consta no catálogo" estava no doc, mas
sem execução. Agora executada por `test_every_code_literal_in_src_is_registered`.

## Achado 2 — textos que anunciavam a causa errada (o padrão da sessão anterior, em escala)

| Código | Sítios | Mentira corrigida |
|---|---|---|
| `E-STATE-INTEGRITY` | 131 | Texto acusava "corrupção do SQLite" e "escritas suspensas"; os sítios recusam operações por dados persistidos inválidos (plano Flatpak corrompido, `es_systems.xml` inválido etc.), sem suspender escrita global. Ação "restaure o backup por rescan" não resolvia. |
| `E-TX-STALE-PLAN` | ~205 | Metade dos sítios recusa plano INVÁLIDO na construção (ciclo, symlink, duplicidade, plano inexistente) — nada "mudou entre plan e apply", e "gere um novo plano e aplique" não resolvia. Título virou "Plano recusado"; ação aponta para o detalhe. |
| `E-CONTENT-INCOMPLETE` | 39+ | "Refaça o dump a partir da mídia original" para backups de preservação e artefatos baixados (cache de shader vazio não é dump de mídia). Ação agora cobre dump, download e backup. |
| `E-SESSION-LAUNCH-FAILED` | 37+ | Impacto afirmava "O Game Mode foi encerrado" também para lançamentos de emulador pelo desktop, onde não há Game Mode. |
| `E-SUPPLY-OFFLINE` | 1 real | Impacto afirmava "enfileirada e retomará" — não existe fila no único sítio de emissão (`lsfg.py`). |

## O que ficou fora e por quê

- Sítios de emissão em `adapters/emulation.py` NÃO foram editados (arquivo
  compartilhado por múltiplas frentes; a correção pela fonte do catálogo é
  completa e sem conflito). Os códigos emitidos foram REGISTRADOS com textos
  honestos, não o contrário.
- `E-COMPONENT-DEGRADED` (81 sítios): o defeito drift→"reparar" já está
  corrigido na branch não mergeada `codex/launch-gate-drift-outdated`
  (`ca69b2a`); não dupliquei. O texto do catálogo fica verdadeiro após o merge.
- `E-UI-ACTION` (Main.qml) é marcador interno de tarefa de UI, não erro do
  catálogo; registar seria categoria errada. Observação registrada.
- Códigos registrados e nunca emitidos (ex.: `E-CHEAT-INVALID-CODES`,
  `E-MOD-BUILD-ID-MISSING`, `E-SAVES-CONFLICT`) permanecem registrados (regra:
  remoção = deprecado); marcados como reservados quando há irmão emitido.
- Verificação profunda sítio a sítio do restante da cauda longa
  (`E-TX-VERIFY-FAILED`, `E-TX-ROLLBACK-FAILED`, famílias SCRAPE/THEME/DESKTOP)
  segue como `nextAction` do item.

## Provas

- `tests/unit/test_errors.py::test_every_code_literal_in_src_is_registered` —
  o gate que faltava (falharia no estado de `e93e8da`; ver baseline).
- `tests/unit/test_emulation_controller.py::test_cheat_and_mod_refusals_emit_registered_catalog_codes`
  — as recusas de import agora retornam erro de domínio registrado, com
  `manualAction` e `probableCause` preenchidos.
- Focais: `test_errors.py` + `test_i18n.py` + `test_emulation_controller.py`:
  125 passed.
