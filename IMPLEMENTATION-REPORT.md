# IMPLEMENTATION-REPORT — SteamZero

**Data:** 2026-07-15 · **Sessão:** implementação 1 · **Escopo entregue:** Fases 1–2 (M1–M6) + Fase 3 (M8–M9 done, M7 parcial)

> Este relatório será reexecutado e auditado por revisão externa independente.
> Cada afirmação abaixo é verificável com os comandos citados. Nada é marcado
> "validado" sem teste; nada foi validado em hardware Steam Deck (não disponível).

Ambiente de verificação: Linux (Manjaro, kernel 6.18), **Python 3.14.6**, git 2.55.
Rótulo global desta entrega: **`verified-dev`** (VM/estação de desenvolvimento) —
ver §6. Nenhuma célula da matriz de hardware foi exercitada.

---

## 1. Estado por marco (M1–M15)

| Marco | Fase | Estado | Evidência |
|---|---|---|---|
| **M1** Kill-proof core (SIGKILL em toda etapa) | 1 | **done** | `pytest tests/failure_injection -q` → **22 passed**; kill in-process em 8 etapas × {alvo existe/ausente} + kept pós-commit + recovery idempotente + **SIGKILL real** de subprocesso (apply.intent/activate/done/commit). AC-TX-02 provado. |
| **M2** CLI contratada (envelope v2 + golden) | 1 | **done** | `steamzero doctor --json` valida contra `envelope-v2.schema.json` (status=ok, 4 checks); `steamzero --contract-version` → `2.0`. `pytest tests/golden -q` → **8 passed**. |
| **M3** Jobs resilientes (pausa/resume/cancel/reboot-recovery) | 1 | **done** | `pytest tests/integration/test_jobs.py -q` → **13 passed**; recovery running→interrupted→{queued\|rolled-back\|completed}. |
| **M4** Deck-aware (modos + display + microSD UUID) | 2 | **done** (verified-dev) | `pytest tests/integration/test_{device,mode,storage}.py` → **18 passed**; classificação DMI, cadeia de fallback de display (FM-18/AC-SD-01), microSD por UUID com bloqueio de escrita fantasma (FM-06/AC-SD-02/FI-07). Portas fake — **não** em hardware. |
| **M5** Helper privilegiado auditado | 2 | **done** (verified-dev) | `pytest -m security` → **29 passed**; allowlist enum, fuzzing (parametrizado + hypothesis) prova zero execução sem gate (AC-PR-01/ST-01), allowlist só privilegiada (AC-PR-02), audit log. Efetor **dry** — sem root/sysfs real. |
| **M6** Sessão segura (suspend/resume checkpoint) | 2 | **done** (verified-dev) | `pytest tests/integration/test_{session,offline}.py` → **14 passed**; suspend pausa jobs + checkpoint (FI-09/AC-SV-02), fallback flush (E-SAVES-FLUSH-TIMEOUT), close escala até SIGKILL c/ confirmação (FM-08), offline-first (AC-OF-01). Porta fake. |
| **M7** Biblioteca transacional (10k fixtures) | 3 | **partial** | `pytest tests/integration/test_library.py tests/integration/test_convert.py tests/failure_injection/test_safezip.py` → **27 passed**: scan read-only (AC-LB-01), import verificado c/ origem intocada (RT-07/AC-LB-02), dedupe, multidisco, safezip (FI-16/17/18/AC-LB-03), conversão original-até-commit (RT-06). **Falta**: pipeline generalizado scan→plan→apply→rollback de organização + benchmark 10k + RT-08..11. |
| **M8** BIOS center + saves timeline | 3 | **done** | `pytest tests/integration/test_bios.py tests/integration/test_saves.py` → **13 passed**: BIOS store hash-only (CONTENT-POLICY), ausente sem link (AC-BI-02), hash/key nunca em log (AC-BI-01/SR-14); saves timeline append-only, restauração byte-idêntica (AC-SV-03), conflito preserva ambos (AC-SV-01). |
| **M9** Sync não-destrutivo | 3 | **done** | `pytest tests/integration/test_sync.py` → **5 passed**: feature flag, fila offline (DF-4), conflito remoto≠local preserva ambos e marca conflicted (J6/AC-SV-01), nunca sobrescreve. Porta CloudPort fake. |
| M10 Engine de adapters + 3 emuladores | 4 | not-started | — |
| M11 Frontends (Steam/SRM/ES-DE) | 4 | not-started | — |
| M12 Game Mode UI (focus graph) | 5 | not-started | — |
| M13 Adoção EmuDeck/RetroDECK em HW real | 5 | not-started | — |
| M14 Flatpak + canais + update/rollback | 6 | not-started | — |
| M15 Release 1.0 stable (SBOM/assinaturas) | 6 | not-started | — |

**Critério de saída da Fase 1** (`AC-TX-01..04 verdes; kill em cada etapa recuperável`):
**atingido.** Entregas de infraestrutura da Fase 1 além dos marcos numerados, todas
`done`: repositório com lints de fronteira em CI; `core.fs` (atomic/staging/containment/
path-safety); núcleo transacional + journal WAL + locks + quarentena; State Store SQLite
+ migração 0001; Job Manager; CLI envelope v2; catálogo de erros; logging JSONL; doctor.

**Critério de saída da Fase 2** (`AC-SD-01/02, AC-OF-01, AC-PR-01/02 em VM`):
**atingido em nível de domínio (verified-dev), com portas fake/efetor dry.** As
capacidades de hardware (aplicar TDP/sysctl real, DRM/KMS, montagem de removível,
DMI real) dependem de adapters concretos + hardware/root — **não** exercitadas
(ver §6/§7). A lógica de domínio (máquinas de estado, fallback, containment,
allowlist) está provada. Compat Matrix inicial: a tabela `compat_fact` existe
(migração 0001); o serviço de reconciliação SteamOS ficou como dívida (M-Compat).

**Critério de saída da Fase 3** (`AC-LB-*, AC-BI-*, AC-SV-*; RT-06..11`):
**parcialmente atingido.** AC-LB-01/02/03, AC-BI-01/02, AC-SV-01/03, RT-06/07
provados; safezip (FI-16/17/18) verde. **Falta para fechar M7**: o pipeline
generalizado de organização (scan→plan→apply→rollback de move/rename) sobre 10k
fixtures + benchmark, e RT-08 (links BIOS)/RT-09 (restore de save)/RT-10 (sync
interrompido)/RT-11 (mídia). Conversões reais (chdman/dolphin-tool) usam porta
**fake** — não há binário de conversão exercitado (verified-dev).

### Reprodução do build limpo (prova do §5)
Clone fresco + venv do lockfile (hash-verified) + `pip install --no-deps -e .`
(reproduzido na Fase 1; a suíte cresceu para 270 desde então — reexecutável):
```
ruff OK · ruff format OK · boundaries OK (0 violações) · mypy --strict OK
pytest → 270 passed · steamzero doctor --json → status ok
```

---

## 2. Resultado completo da suíte

Contagem por categoria (por diretório/ marcador):

| Categoria | Contagem | Onde |
|---|---|---|
| Unit | 95 | `tests/unit/` |
| Integração | 106 | `tests/integration/` (transação, state, jobs, cli, device, mode, storage, session, offline, library, bios, saves, sync, convert) |
| Injeção de falha (FI) | 32 | `tests/failure_injection/` (marcador `fi`) — inclui FI-16/17/18 (safezip) |
| Rollback (RT) | 5 | marcador `rt` — RT-06 (conversão). RT-01..05 provados em `test_transaction` sem a etiqueta; RT-08..14 pendentes |
| Segurança (ST) | 29 | `tests/security/` (marcador `security`) — fuzzing do helper |
| Golden (contrato) | 8 | `tests/golden/` (marcador `golden`) |
| Sistema (VMs) | 0 | não iniciado (Fase 5/6) |
| UI (focus graph) | 0 | não iniciado (Fase 5) |
| **Total** | **270** | `pytest -q` → **270 passed** |

**Falhas: 0. Skips: 0. xfails: 0.** (Nenhum teste silenciado.)

Cobertura (`pytest --cov=steamzero`):

| Módulo do núcleo | Cobertura |
|---|---|
| core/fs.py | 95% |
| core/journal.py | 97% |
| core/state.py | 96% |
| core/transaction.py | 93% |
| core/lock.py | 94% |
| core/ids.py · errors.py · secret.py | 100% |
| domain/{device,mode,storage,session} | 91–98% |
| domain/{library,bios,saves,sync,convert} | 94–100% |
| core/safezip.py | 98% |
| privileged/{protocol,helper,client} | 90–100% |
| jobs/manager.py | 93% |
| **TOTAL (pacote)** | **94%** |

Meta TEST-STRATEGY (≥90% núcleo transacional/core.fs): **atingida**.

**Mapeamento AC → teste (ACCEPTANCE-CRITERIA.md):**
- AC-TX-01 (stale-plan, sem mutação) → `test_transaction::test_ac_tx_01_stale_plan_no_mutation`
- AC-TX-02 (SIGKILL em qualquer ponto → rollback byte-idêntico) → `test_fi04_killproof::*`, `test_fi04_sigkill_subprocess::*`
- AC-TX-03 (dry-run sem escrita no alvo) → `test_transaction::test_ac_tx_03_dry_run_no_writes`
- AC-TX-04 (confirmToken obrigatório) → `test_transaction::test_ac_tx_04_confirm_required`
- RB-3 (rollback idempotente) → `test_transaction::test_rb3_rollback_idempotent`
- RB-4 / T-09 (backup adulterado → E-TX-ROLLBACK-FAILED) → `test_transaction::test_rb4_tampered_backup_fails_rollback`
- FI-06 (preflight de espaço) → `test_transaction::test_space_preflight_blocks`
- FI-15 (lock órfão) → `test_lock::test_orphan_by_*`
- AC-SD-01 (transição de modo + fallback de display) → `test_mode::test_*fall*` (verified-dev)
- AC-SD-02 (microSD removido → unavailable, zero escrita fantasma, restauração UUID) → `test_storage::*` (verified-dev)
- AC-OF-01 (offline: local funciona, remoto enfileira) → `test_offline::*`
- AC-PR-01 (helper rejeita fora da allowlist; fuzzing sem execução arbitrária) → `test_helper::test_fuzz_*` (ST-01)
- AC-PR-02 (nenhum fluxo comum exige root) → `test_helper::test_ac_pr_02_*`
- AC-SV-02 (suspensão dispara checkpoint) → `test_session::test_suspend_resume_with_checkpoint` (parcial — perda de energia real não testada)
- FI-07/09/12 (microSD/suspensão/display) → cobertos em nível de domínio com portas fake; variantes de hardware pendentes
- AC-LB-01 (scan read-only) → `test_library::test_scan_is_read_only`
- AC-LB-02/03 (original até commit; archive inseguro→quarentena) → `test_library::*`, `test_convert::*`, `test_safezip::*`
- RT-06 (conversão: ENOSPC/timeout/falha, original intacto) → `test_convert::*` (marcador `rt`)
- RT-07 (import não altera a fonte) → `test_library::test_import_copies_and_source_untouched`
- FI-16/17/18 (zip bomb/traversal/limites) → `test_safezip::*`
- AC-BI-01/02 (hash/key nunca em log; ausente sem link) → `test_bios::test_ac_bi_01_*`, `test_bios::test_status_missing_*`
- AC-SV-01/03 (conflito preserva ambos; restauração byte-idêntica) → `test_saves::*`, `test_sync::test_conflict_*` (J6)
- AC-UI, RT-08..14, benchmark 10k → **não implementados** (M7 parcial; Fases 4–6).

---

## 3. Divergências da documentação

Cada uma registrada (não silenciosa):

1. **`interrupted → completed` na máquina de estados de job (roll-forward).** O diagrama
   do JOB-LIFECYCLE mostra `interrupted → queued|rolling-back`; o TEXTO §Recuperação diz
   "se passou de activate+verify, tenta completar o commit". Adotei a interpretação do
   texto. Registro: WORKLOG (Sessão 2) + mensagem do commit do Job Manager. Não exigiu
   ADR (é o comportamento documentado, não uma decisão nova).
2. **State Store não passa por `core.fs`.** MODULE-BOUNDARIES diz "core.fs é a única porta
   de escrita em disco"; ADR-0005 define o State Store como store gerido com writer único.
   Interpretei que a regra rege escrita de *arquivos avulsos*; SQLite é store distinto. O
   *backup* do db passa por core.fs. Registro: docstring de `core/state.py` + WORKLOG.
3. **Tabela `operation` populada pela orquestração**, não pelo `core.transaction` (que usa
   o journal como fonte de verdade do recovery, ADR-0005). `state.save_operation` existe;
   o job manager/domínio a chama. Registro: WORKLOG.
4. **Texto de erro fixo (sem interpolação).** ERROR-CATALOG mostra títulos interpolados
   (ex.: "Falta scph1001.bin"). Mantive texto de catálogo FIXO e joguei especificidades em
   `detail`/`autoAction` — honra "texto fixo auditado" (CONTENT-POLICY). Interpolação de
   UX fica para Fase 3. Registro: WORKLOG.
5. **Adições ao ERROR-CATALOG**: `E-CLI-USAGE`, `E-STATE-MIGRATION`, `E-STATE-INTEGRITY`,
   `E-INTERNAL-UNEXPECTED`. Permitido pela governança ("catálogo cresce por PR"). Todas com
   texto pt-BR e cobertas pelo teste de completude.
6. **`pip-tools` removido do lockfile de dev.** Arrastava `setuptools` não-pinado e
   quebrava `pip install --require-hashes`. Registro: commit `build: remove pip-tools do lock`.

Nenhum ADR foi divergido; ADR-0013 foi **fechado** (aceito, GPL-3.0-or-later) conforme o processo.

---

## 4. Dívidas técnicas conhecidas (classificadas)

**Bloqueante:** nenhuma para as Fases 1–2 (no nível verified-dev).

**Alta:**
- **A0. Adapters de hardware da Fase 2 ausentes.** device/mode/storage/session/helper
  usam **portas injetadas** provadas com fakes/dry; falta a camada `adapters.*`
  concreta (ler DMI real, aplicar KMS/DRM, /proc/mounts + /dev/disk/by-uuid, efetor
  sysfs/systemd, transporte pkexec/D-Bus) e a composição que a injeta. Sem isso,
  M4–M6 não funcionam de fato em um Deck. É a maior dívida da Fase 2.
- **A5. Compat Matrix (F-SD-05) só tem a tabela** `compat_fact`; falta o serviço de
  reconciliação SteamOS/Steam-client na subida (FM-10). Perfis de desempenho
  (F-PF-01/03) modelados via helper set-tdp, mas sem o fluxo apply/restore G-STATE
  completo (fica com a Fase 4).
- **A1. FI-06 real (ENOSPC no meio do apply) não testado** — só o *preflight* (via
  monkeypatch de `free_space`). O caso mid-apply exige FS de loopback com quota. FI-01/02/
  03/05/07..14/16..20 também não implementados (Fases 2–3).
- **A2. AC-TX-03 sem verificação por `strace`** — asseguro "sem escrita no alvo" por
  asserção de estado, não por contagem de syscalls como o AC pede. Falta harness de strace no CI.
- **A3. `shellcheck` não executado** — ausente no ambiente; não há shims bash na Fase 1
  (ADR-0001), mas o gate de CI só foi escrito, não exercitado.
- **A4. Matriz Python 3.11/3.12 não exercitada** — rodou só em 3.14.6. `requires-python>=3.11`
  e o workflow declara 3.11/3.12, mas GitHub Actions não foi executado aqui.

**Média:**
- **M1d. Daemon/IPC ausente** — a CLI roda o núcleo in-process (single-shot). O serviço
  local JSON-RPC sobre UNIX socket com SO_PEERCRED/confirmToken (SR-18) não existe ainda.
- **M2d. Stream de eventos `--follow` (NDJSON) não implementado** — `event-v1` tem schema +
  amostra validada, mas não há emissão ao vivo; jobs emitem para `event_log` (State Store).
- **M3d. i18n só pt-BR** — sem catálogo `en`; a infraestrutura de chaves suporta, falta o
  segundo idioma.
- **M4d. Marcador `rt` não aplicado** — os testes de rollback existem (em `test_transaction.py`)
  mas não estão etiquetados `rt`; a suíte RT formal (RT-01..14) é de Fases 3–6.
- **M5d. `core.proc`/`core.net`/`core.crypto` não implementados** — sem consumidores na
  Fase 1; os lints de fronteira já os preveem.

**Baixa:**
- **B1.** Doctor mínimo (sem varredura de lock órfão nem disponibilidade de ferramentas).
- **B2.** Rotação de log com `keep=3` fixo; sem sampling de debug.
- **B3.** Plano guarda conteúdo inline (base64) — adequado a config; inviável para arquivos
  grandes (tratar na Fase 3, staging por streaming).
- **B4.** `_render_human` da CLI é básico (sem cores/tabelas).

---

## 5. Build e execução do zero (máquina limpa)

Pré-requisitos: Python ≥ 3.11 com `venv`, git, acesso ao PyPI.

```bash
git clone <repo-url> Port_Steam && cd Port_Steam
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-dev.lock   # deps pinadas + hash (SR-11)
.venv/bin/pip install --no-deps -e .                              # o pacote steamzero
make check          # ruff + ruff format --check + boundaries + mypy --strict + pytest
.venv/bin/steamzero doctor --json                                 # smoke
```

**Prova de que foi seguido:** um clone limpo (`git clone` local, sem `.venv/` nem
`reference/`) foi construído do zero nesta sessão; `make check` → tudo verde;
`pytest` → **270 passed**; `steamzero doctor --json` → `status: ok`. (Reproduzido no HEAD
atual em clone limpo; registro: WORKLOG.)

`make` alvos: `venv lint format-check typecheck boundaries test cov check`. CI equivalente
em `.github/workflows/ci.yml` (matriz 3.11/3.12 — ver dívida A4).

---

## 6. verified-vm vs verified-hw vs não verificado

- **verified-dev (VM/estação):** toda a suíte (270 testes), lints, tipos e o binário
  `steamzero` — em Linux Manjaro, Python 3.14.6. Inclui SIGKILL real de processo (FI-04)
  e fuzzing do helper (ST-01). A lógica de domínio da Fase 2 (modos, fallback, microSD
  por UUID, sessão, allowlist) roda com **portas fake / efetor dry**.
- **verified-hw:** **nada.** Sem Steam Deck (LCD/OLED), docks ou TVs — G5 do KNOWN-GAPS.
  Nenhuma célula da STEAM-DECK-HARDWARE-MATRIX foi tocada. Nenhuma ação privilegiada
  real (TDP/sysctl/mount) foi executada (efetor dry, sem root).
- **Não verificado (mesmo em VM):**
  - Python 3.11 e 3.12 (rodou só 3.14) — dívida A4.
  - Perda de energia real (poweroff -f / FI-10) — só SIGKILL de processo foi exercitado;
    a durabilidade por fsync é assumida correta, não provada contra corte de energia.
  - Concorrência real de jobs (o executor é síncrono; sem threads/cgroup).
  - GitHub Actions (workflow escrito, não executado).

---

## 7. Autoavaliação honesta — o que NÃO tenho confiança que funciona

1. **Compatibilidade 3.11/3.12.** Usei `datetime.UTC`, uniões `X | Y` (com
   `from __future__ import annotations`), `importlib.resources.files`. *Deve* funcionar em
   3.11+, mas **não rodei** em 3.11/3.12. Risco real de alguma API 3.12+.
2. **Durabilidade sob perda de energia real.** O recovery é sólido contra SIGKILL (testado
   de verdade). Contra corte de energia no meio de um `fsync`/`rename`, confio no modelo
   POSIX (tmp+fsync+rename+fsync-dir) mas **não testei** com VM `poweroff -f`.
3. **Empacotamento dos schemas no wheel.** Os `.json` de `steamzero/schemas/` carregam via
   `importlib.resources` no editable install (testado). Num **wheel real** dependo do
   hatchling incluir dados de pacote — não construí/instalei um wheel para confirmar.
4. **Cross-filesystem (ext4↔exFAT do microSD).** `same_filesystem` e o fallback copy+unlink
   existem, mas o caminho cross-FS é pouco exercitado; colisões case-insensitive (PATH-SAFETY §8)
   não implementadas.
5. **Fronteira "UI não executa shell" na prática.** É garantida por arquitetura e lint, mas
   **não há daemon/IPC** ainda; a garantia real (SO_PEERCRED, allowlist sobre socket) é da Fase 2.
6. **Heurística do lint de fronteira.** `tools/lint_boundaries.py` pega os casos claros
   (open-write, os/shutil, Path.write_*), mas não detecta escrita via `Path.replace` nem
   aliasing dinâmico. É defesa em profundidade, não prova formal.

7. **Fase 2 sem hardware/root (o ponto mais importante).** M4–M6 provam a **lógica** com
   portas fake e efetor dry. NÃO tenho confiança de que funcionem num Deck real: a
   detecção DMI, a aplicação de modos via DRM/KMS, a montagem de microSD, o set-tdp/sysctl
   e o polkit não foram executados nem uma vez contra hardware/root. A allowlist e as
   máquinas de estado são sólidas; a **ponte com o mundo real** (adapters + composição)
   não existe (dívida A0).

8. **Fase 3 sem ferramentas externas reais.** BIOS/saves/sync/library são lógica pura,
   bem coberta. Mas **conversões reais** (chdman, dolphin-tool, maxcso, nsz) usam porta
   **fake** — nenhum binário de conversão foi exercitado. E o M7 é **parcial**: falta o
   pipeline generalizado de organização (scan→plan→apply→rollback de move/rename) sobre
   10k fixtures + o benchmark de desempenho (que o M7 exige explicitamente), além de
   RT-08..11. O que existe (import/scan/safezip/dedupe/convert-fake) está provado.

**Resumo honesto:** as Fases 1 (M1–M3) e 2 (M4–M6) estão sólidas **no nível de lógica de
domínio, verified-dev**; a Fase 3 entrega M8–M9 `done` e M7 `parcial`. O núcleo transacional
kill-proof (SIGKILL real recuperado), o fuzzing do helper e o safezip (bytes reais) são as
peças mais fortes. Ressalvas grandes, todas explícitas: nada tocou hardware, root nem
ferramentas de conversão reais; falta a camada de adapters concretos (dívida A0) e o
pipeline de organização 10k do M7. Fases 4–6 não iniciadas. Nada mascarado — a suíte
(270 testes, 0 falhas/skips) e os `git log` comprovam cada afirmação acima.
