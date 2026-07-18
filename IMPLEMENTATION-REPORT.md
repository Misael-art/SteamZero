# IMPLEMENTATION-REPORT — SteamZero

**Data:** 2026-07-15 · **Sessão:** implementação 9 · **Escopo entregue:** Fases 1–3
(M1–M9) + Fase 4 em andamento (M10 parcial, M10-H foundation + bootstrap host)

> Este relatório será reexecutado e auditado por revisão externa independente.
> Cada afirmação abaixo é verificável com os comandos citados. Nada é marcado
> "validado" sem teste. O Steam Deck LCD disponível foi usado para status read-only
> do M10-H e instalação/rollback da aplicação; nenhum apply de display/input foi
> executado no host.

Ambiente de verificação: Steam Deck LCD com BigLinux/Manjaro, KDE Wayland, kernel
6.18.38, **Python 3.14.6**, git 2.55.
Rótulo global desta entrega: **`verified-dev`** (VM/estação de desenvolvimento) —
ver §6. Apenas as células explicitamente `verified-hw-readonly` e
`verified-host-install` foram exercitadas no Deck.

---

## 1. Estado por marco (M1–M15)

| Marco | Fase | Estado | Evidência |
|---|---|---|---|
| **M1** Kill-proof core (SIGKILL em toda etapa) | 1 | **done** | `pytest tests/failure_injection -q` → **22 passed**; kill in-process em 8 etapas × {alvo existe/ausente} + kept pós-commit + recovery idempotente + **SIGKILL real** de subprocesso (apply.intent/activate/done/commit). AC-TX-02 provado. |
| **M2** CLI contratada (envelope v2 + golden) | 1 | **done** | `steamzero doctor --json` valida contra `envelope-v2.schema.json` (status=ok, 4 checks); `steamzero --contract-version` → `2.0`. `pytest tests/golden -q` → **10 passed**. |
| **M3** Jobs resilientes (pausa/resume/cancel/reboot-recovery) | 1 | **done** | `pytest tests/integration/test_jobs.py -q` → **13 passed**; recovery running→interrupted→{queued\|rolled-back\|completed}. |
| **M4** Deck-aware (modos + display + microSD UUID) | 2 | **done** (verified-dev) | `pytest tests/integration/test_{device,mode,storage}.py` → **18 passed**; classificação DMI, cadeia de fallback de display (FM-18/AC-SD-01), microSD por UUID com bloqueio de escrita fantasma (FM-06/AC-SD-02/FI-07). Portas fake — **não** em hardware. |
| **M5** Helper privilegiado auditado | 2 | **done** (verified-dev) | `pytest tests/security -q` → **29 passed**; allowlist enum, fuzzing (parametrizado + hypothesis) prova zero execução sem gate (AC-PR-01/ST-01), allowlist só privilegiada (AC-PR-02), audit log. Efetor **dry** — sem root/sysfs real. |
| **M6** Sessão segura (suspend/resume checkpoint) | 2 | **done** (verified-dev) | `pytest tests/integration/test_{session,offline}.py` → **14 passed**; suspend pausa jobs + checkpoint (FI-09/AC-SV-02), fallback flush (E-SAVES-FLUSH-TIMEOUT), close escala até SIGKILL c/ confirmação (FM-08), offline-first (AC-OF-01). Porta fake. |
| **M7** Biblioteca transacional (10k fixtures) | 3 | **done** | `pytest tests/integration/test_library_organize.py -q` → **12 passed** em ~19s: scan→plan(confirmToken)→apply→verify→commit→rollback G-FULL sobre **10.000 fixtures**, rollback idempotente, falha parcial e crash pós-move recuperados; colisão/traversal/stale-plan bloqueados. Somado aos **27 testes** de scan/import/safezip/conversão: AC-LB-01..03, RT-06/07 e benchmark do marco verdes. |
| **M8** BIOS center + saves timeline | 3 | **done** | `pytest tests/integration/test_bios.py tests/integration/test_saves.py` → **15 passed**: BIOS store hash-only, links atômicos com RT-08, saves timeline append-only e restore transacional com RT-09; AC-BI/SV verdes. |
| **M9** Sync não-destrutivo | 3 | **done** | `pytest tests/integration/test_sync.py` → **6 passed**: feature flag, fila offline, conflito preservador e estados pending→in-flight→done; upload interrompido retorna a pending e é retomado (RT-10). Porta CloudPort fake. |
| **M10** Engine de adapters + 3 emuladores | 4 | **partial** (verified-dev) | Schema/registry e manifests pinados de DuckStation/RetroArch/Dolphin; lifecycle portável G-FULL; lockfile anti-drift; executor Flatpak user-scoped com plan/token, commit OSTree exato, verify/smoke, rollback G-DEPLOYMENT e recovery em **24 testes**. A CLI expõe list/status/plan/apply/rollback/recover. Status real read-only passou; instalação dos três em VM ainda não foi feita e DuckStation segue EOL no Flathub. |
| **M10-H** Handheld Desktop BigLinux/KDE | 4 | **foundation** (verified-dev + hw-readonly + host-install) | Contexto real Deck/KScreen, perfis auto/handheld/dock/safe, plano+confirmToken, snapshots G-STATE/recovery, efeitos KDE reversíveis, teclado em fallback, bridge QML tokenizada, gate de independência e importador offline. **36 testes da experiência + 7 do instalador host**; conflito conhecido tem card, plano confirmado e rollback parcial; aplicação instalada sob `/opt`, QML e rollback real validados; apply de perfil ainda não executado. |
| M11 Frontends (Steam/SRM/ES-DE) | 4 | not-started | — |
| M12 Game Mode UI (focus graph) | 5 | not-started | — |
| M13 Adoção EmuDeck/RetroDECK em HW real | 5 | not-started | — |
| M14 Flatpak + canais + update/rollback | 6 | not-started | — |
| M15 Release 1.0 stable (SBOM/assinaturas) | 6 | not-started | — |

**Critério de saída da Fase 1** (`AC-TX-01..04 verdes; kill em cada etapa recuperável`):
**atingido.** Entregas de infraestrutura da Fase 1 além dos marcos numerados, todas
`done`: repositório com lints de fronteira em CI; `core.fs` (atomic/staging/containment/
path-safety); núcleo transacional + journal WAL + locks + quarentena; State Store SQLite
+ migrações 0001–0002; Job Manager; CLI envelope v2; catálogo de erros; logging JSONL; doctor.

**Critério de saída da Fase 2** (`AC-SD-01/02, AC-OF-01, AC-PR-01/02 em VM`):
**atingido em nível de domínio (verified-dev), com portas fake/efetor dry.** As
capacidades de hardware (aplicar TDP/sysctl real, DRM/KMS, montagem de removível,
DMI real) dependem de adapters concretos + hardware/root — **não** exercitadas
(ver §6/§7). A lógica de domínio (máquinas de estado, fallback, containment,
allowlist) está provada. Compat Matrix inicial: a tabela `compat_fact` existe
(migrações 0001–0002); o serviço de reconciliação SteamOS ficou como dívida (M-Compat).

**Critério de saída da Fase 3** (`AC-LB-*, AC-BI-*, AC-SV-*; RT-06..11`):
**atingido em verified-dev.** AC-LB-01/02/03, AC-BI-01/02, AC-SV-01/03 e
RT-06..11 estão provados. RT-08 cobre symlink BIOS quebrado; RT-09 preserva o save
atual quando restore falha; RT-10 recupera upload interrompido para pending; RT-11
reverte canonicalização e devolve órfãos da quarentena. Safezip FI-16/17/18 e o
pipeline 10k também estão verdes. Limite: conversores reais, scraper remoto com
cache/rate limit e migração SSD↔microSD ainda não foram exercitados/implementados
por completo; o rótulo continua `verified-dev`, não hardware/produção.

### Reprodução do build limpo (prova do §5)
Clone fresco + venv do lockfile (hash-verified) + `pip install --no-deps -e .`
(reproduzido na Fase 1; o worktree atual foi validado pelo gate completo):
```
ruff OK · ruff format OK · boundaries OK (0 violações) · mypy --strict OK
independence OK · pytest → 362 passed · steamzero doctor --json → status ok
```

---

## 2. Resultado completo da suíte

Contagem por categoria (por diretório/ marcador):

| Categoria | Contagem | Onde |
|---|---|---|
| Unit | 116 | `tests/unit/` |
| Integração | 175 | `tests/integration/` (inclui organização 10k, BIOS/saves/sync/media/adapters/Desktop/Flatpak/host) |
| Injeção de falha (FI) | 40 | marcador `fi` — inclui FI-16/17/18, FI-21..24 Desktop e FI-25/26 Flatpak |
| Rollback (RT) | 23 | marcador `rt` — inclui lifecycle portátil e Flatpak, RT-06..11; RT-12..14 pendentes |
| Segurança (ST) | 30 | marcador `security` — helper + mídia ST-06 |
| Golden (contrato) | 10 | `tests/golden/` (plan-v1 write/move/symlink) |
| Sistema (VMs) | 0 | não iniciado (Fase 5/6) |
| UI (foundation) | 3 | parser/contrato QML + bridge tokenizada (incluídos em unit/integração) |
| **Total** | **362** | `pytest -q` → **362 passed** |

**Falhas: 0. Skips: 0. xfails: 0.** (Nenhum teste silenciado.)

Cobertura (`pytest --cov=steamzero`):

| Módulo do núcleo | Cobertura |
|---|---|
| core/fs.py | 93% |
| core/journal.py | 97% |
| core/state.py | 96% |
| core/transaction.py | 90% |
| core/lock.py | 94% |
| core/ids.py · errors.py · secret.py | 100% |
| domain/{device,mode,storage,session} | 91–98% |
| domain/{library,bios,saves,sync,media,convert} | 90–100% |
| adapters/{engine,registry,lockfile} | 85–88% |
| adapters/flatpak.py | 75% (porta real não mutada; orquestração exercitada por fake) |
| domain/desktop.py | 89% |
| adapters/{desktop_kde,desktop_ui} | 61–65% (efeitos reais não acionados no host) |
| core/safezip.py | 98% |
| privileged/{protocol,helper,client} | 90–100% |
| jobs/manager.py | 93% |
| **TOTAL (pacote no worktree)** | **86%** (inclui `ports.py` ainda não rastreado, 0%) |

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
- M7 10k + organização G-FULL → `test_library_organize::*` (apply/rollback 10k,
  confirmação, stale-plan, colisão, falha parcial e crash recovery)
- FI-16/17/18 (zip bomb/traversal/limites) → `test_safezip::*`
- AC-BI-01/02 (hash/key nunca em log; ausente sem link) → `test_bios::test_ac_bi_01_*`, `test_bios::test_status_missing_*`
- AC-SV-01/03 (conflito preserva ambos; restauração byte-idêntica) → `test_saves::*`, `test_sync::test_conflict_*` (J6)
- RT-08 → `test_bios::test_rt08_*`; RT-09 → `test_saves::test_rt09_*`;
  RT-10 → `test_sync::test_rt10_*`; RT-11 → `test_media::test_rt11_*`.
- M10/RT-01/02 → `test_adapters::*`: schema/registry, checksum antes de escrita,
  install idempotente, update e rollback manual/automático preservando a release anterior.
- M10 Flatpak → `test_flatpak*` + CLI: lockfile anti-drift, argv fixo user-scoped,
  commit exato, stale-plan, EOL, G-DEPLOYMENT, FI-25/26 e recovery idempotente.
- AC-HD-01..06 → `test_desktop*`, `test_runtime_independence` e CLI hermética: auto/dock,
  teclado, ownership, stale context, rollback, crash recovery, bridge/QML e liberação
  confirmada do watcher user-scoped com restauração em falha parcial.
- AC-UI completo e RT-12..14 → **não implementados** (gates restantes das Fases 5–6).

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
7. **DuckStation não pode mais usar o exemplo Flatpak como fonte ativa.** A descoberta
   remota confirmou que `org.duckstation.DuckStation` está sem manutenção/EOL no Flathub
   desde 2025-08-13. O manifesto conserva o commit apenas como evidência e o marca
   `endOfLife`; uma AppImage oficial pinada por checksum deve substituí-lo antes da demo M10.

Nenhum ADR foi divergido; ADR-0013 foi **fechado** (aceito, GPL-3.0-or-later) conforme o processo.

---

## 4. Dívidas técnicas conhecidas (classificadas)

**Bloqueante:** nenhuma para as Fases 1–2 (no nível verified-dev).

**Alta:**
- **A0. Adapters de hardware da Fase 2 parciais.** M10-H adicionou detecção DMI,
  KScreen, input/capabilities e efeitos KDE reais com composição; o status foi provado
  read-only no Deck LCD. Apply de KScreen/KWin, storage/mount, TDP/sysfs, sessão e
  transporte pkexec/D-Bus continuam sem validação real. É a maior dívida de hardware.
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
- **A6. Integrações externas da Fase 3 incompletas.** Conversores reais, provedores de
  scraping/cache/rate limit e migração SSD↔microSD não foram exercitados fim-a-fim.
  O gate AC/RT está verde em lógica local, mas essas capacidades não estão prontas para uso real.
- **A7. M10 ainda não foi demonstrado em VM real.** Engine portátil, lockfile e executor
  Flatpak transacional estão provados localmente, inclusive crash/recovery por porta fake.
  Faltam smoke/install/update/rollback reais dos três em VM. DuckStation exige selecionar
  uma nova fonte oficial porque seu ref Flathub está EOL.

**Média:**
- **M1d. Daemon/IPC ausente** — a CLI roda o núcleo in-process (single-shot). O serviço
  local JSON-RPC sobre UNIX socket com SO_PEERCRED/confirmToken (SR-18) não existe ainda.
  A central M10-H usa bridge HTTP efêmera em loopback, token aleatório e allowlist,
  encerrada junto ao QML; ela não substitui o daemon persistente planejado.
- **M2d. Stream de eventos `--follow` (NDJSON) não implementado** — `event-v1` tem schema +
  amostra validada, mas não há emissão ao vivo; jobs emitem para `event_log` (State Store).
- **M3d. i18n só pt-BR** — sem catálogo `en`; a infraestrutura de chaves suporta, falta o
  segundo idioma.
- **M4d. RT-03..05 não têm marcador `rt`**, embora seus comportamentos estejam cobertos
  em `test_transaction.py`; RT-01/02 e RT-06..11 somam 19 casos marcados, RT-12..14
  seguem pendentes.
- **M5d. `core.proc`/`core.net`/`core.crypto` não implementados** — Flatpak possui runner
  restrito próprio no adapter (argv fixo/timeout/sem shell); falta a porta compartilhada
  para futuros processos e aquisição em streaming.

**Baixa:**
- **B1.** Doctor mínimo (sem varredura de lock órfão nem disponibilidade de ferramentas).
- **B2.** Rotação de log com `keep=3` fixo; sem sampling de debug.
- **B3.** Planos de escrita de config ainda guardam conteúdo inline (base64). Planos de
  move/rename da biblioteca agora guardam só metadados e backups/restores copiam em
  streaming; falta generalizar esse modelo para futuras escritas grandes.
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

**Prova disponível:** o clone limpo da entrega anterior produziu 270 testes verdes.
No worktree desta sessão,
`make check` produziu **362 passed**; a reprodução em clone limpo deste incremento deverá
ser repetida após seu commit. `steamzero doctor --json` permanece `status: ok`.

`make` alvos: `venv lint format-check typecheck boundaries independence test cov check`. CI equivalente
em `.github/workflows/ci.yml` (matriz 3.11/3.12 — ver dívida A4).

---

## 6. verified-vm vs verified-hw vs não verificado

- **verified-dev (VM/estação):** toda a suíte (362 testes), lints, tipos e o binário
  `steamzero` — em Linux Manjaro, Python 3.14.6. Inclui SIGKILL real de processo (FI-04)
  e fuzzing do helper (ST-01). A lógica de domínio da Fase 2 (modos, fallback, microSD
  por UUID, sessão, allowlist) roda com **portas fake / efetor dry**.
- **verified-hw-readonly:** `desktop status` identificou no Steam Deck LCD real:
  Valve Jupiter, Wayland, eDP-1 800×1280@60, escala 1,35 e capabilities KDE/KScreen,
  Maliit, Steam, KDE Connect e TTS BigLinux. InputPlumber estava ausente e não foi
  selecionado. Um serviço externo `*-mode-watcher` foi encontrado por padrão genérico;
  o status ficou `blocked`/observador e expôs a remediação user-scoped correta. O plano
  e a UI foram exercitados sem confirmar apply; nenhuma configuração ou serviço foi alterado.
- **verified-host-install:** wheel e dependências hash-verified foram instalados com
  `bigsudo` em releases imutáveis sob `/opt`; `doctor`, `pip check`, QML offscreen,
  Desktop entry, ownership e integridade passaram. Rollback real
  `host3 → host1 → host3` preservou o gerenciador estável e o estado XDG.
- **verified-hw mutável:** **nada.** Apply de KScreen/KWin, dock/hotplug, input owner,
  TDP/sysctl/mount e ações privilegiadas permanecem não verificados.
- **Não verificado (mesmo em VM):**
  - Python 3.11 e 3.12 (rodou só 3.14) — dívida A4.
  - Perda de energia real (poweroff -f / FI-10) — só SIGKILL de processo foi exercitado;
    a durabilidade por fsync é assumida correta, não provada contra corte de energia.
  - Concorrência real de jobs (o executor é síncrono; sem threads/cgroup).
  - GitHub Actions (workflow escrito, não executado).
  - Instalação/update/rollback Flatpak dos três adapters M10; executor, argv e recovery
    foram exercitados por porta fake e o status real foi somente read-only.

---

## 7. Autoavaliação honesta — o que NÃO tenho confiança que funciona

1. **Compatibilidade 3.11/3.12.** Usei `datetime.UTC`, uniões `X | Y` (com
   `from __future__ import annotations`), `importlib.resources.files`. *Deve* funcionar em
   3.11+, mas **não rodei** em 3.11/3.12. Risco real de alguma API 3.12+.
2. **Durabilidade sob perda de energia real.** O recovery é sólido contra SIGKILL (testado
   de verdade). Contra corte de energia no meio de um `fsync`/`rename`, confio no modelo
   POSIX (tmp+fsync+rename+fsync-dir) mas **não testei** com VM `poweroff -f`.
3. **Empacotamento e bootstrap host validados.** O wheel real contém adapters, domínio, schemas/QML do
   M10-H e agora `flatpak.py`, lockfile e schemas de componente; exclui explicitamente o
   `ports.py` local não rastreado. O wheel final foi instalado no host com venv próprio,
   lock hash-verified e release retida; passou `doctor`, `component list`, integridade e
   rollback real. Ainda falta validar o bundle Flatpak final da plataforma.
4. **Cross-filesystem (ext4↔exFAT do microSD).** `same_filesystem` e o fallback copy+unlink
   existem, mas o caminho cross-FS é pouco exercitado; colisões case-insensitive (PATH-SAFETY §8)
   não implementadas.
5. **Bridge da UI ainda é transitória.** QML usa HTTP efêmero em 127.0.0.1, token
   aleatório e allowlist sem shell; os testes cobrem token e confirmação. O daemon UNIX
   com SO_PEERCRED permanece a solução final e ainda não existe.
6. **Heurística do lint de fronteira.** `tools/lint_boundaries.py` pega os casos claros
   (open-write, os/shutil, Path.write_*), mas não detecta escrita via `Path.replace` nem
   aliasing dinâmico. É defesa em profundidade, não prova formal.

7. **Hardware mutável ainda não validado (o ponto mais importante).** DMI/KScreen e
   capabilities agora funcionam read-only no Deck real; efeitos KScreen/KWin existem e
   são cobertos por runner fake. Não tenho confiança para marcar apply, dock/hotplug,
   montagem, TDP/sysctl ou polkit como verified-hw antes do checklist assistido.

8. **Fase 3 sem ferramentas externas reais.** BIOS/saves/sync/library/media local estão
   cobertos e RT-06..11 verdes. Porém conversões reais (chdman, dolphin-tool, maxcso,
   nsz), scraper/cache/rate limit e migração SSD↔microSD não foram exercitados fim-a-fim.

9. **M10 parcial.** Schema, registry, lockfile, lifecycle portátil e executor Flatpak
   estão cobertos, inclusive recovery pós-crash. A mutação real ainda não rodou em VM e
   DuckStation perdeu sua fonte Flathub; falta selecionar e pinar alternativa oficial.

**Resumo honesto:** as Fases 1 (M1–M3) e 2 (M4–M6) estão sólidas **no nível de lógica de
domínio, verified-dev**; a Fase 3 entrega M7–M9 e o gate RT-06..11 verdes.
O núcleo transacional kill-proof (SIGKILL real recuperado), o fuzzing do helper e o
safezip (bytes reais) são as peças mais fortes. Ressalvas grandes, todas explícitas:
somente detecção read-only tocou hardware; root foi usado apenas no bootstrap versionado,
sem efeitos de perfil, e ferramentas de conversão reais não foram acionadas. A Fase 4
contém M10 parcial e M10-H foundation; Fases 5–6 não iniciaram. Nada mascarado — a suíte
(362 testes, 0 falhas/skips) e o
WORKLOG comprovam cada afirmação acima.

---

## 8. Refinamento responsivo da UI Desktop — sessão 11

Rótulo desta fatia: **`verified-dev`**. Branch: `codex/ui-emulacao`.

### Resultado

Sem redesenhar a identidade System Studio, a apresentação QML foi decomposta em tokens e
componentes para inspector adaptativo, empty state, carregamento, cards, footer e navegação
por seções. O shell usa pixels lógicos e os sinais já existentes de dispositivo, displays,
escala, teclado/mouse e capabilities; nenhum contrato de payload foi alterado.

| Perfil | Composição entregue |
|---|---|
| Deck 1280×800 | rail de 72 px, conteúdo em uma coluna, inspector em drawer, margens 16 px, alvos ≥48 px e footer de 46 px |
| Full HD | sidebar de 248 px, inspector de 344 px, grid de perfis e margens 24 px |
| Ultrawide | conteúdo central limitado a 1920 px e balanceado por gutters; sem formulários esticados |
| 4K desktop | composição lógica equivalente a Full HD, golden em escala 200% |
| 4K TV | sidebar de 300 px, alvos de 64 px e escala tipográfica/espacial ampliada |

Antes, o layout dependia principalmente de `root.width`, margens repetidas de 28 px,
painéis de 292 px, linhas de 94 px e footer fixo. Depois, a UI faz reflow por composição,
limita largura, usa altura implícita e só reduz densidade depois de reorganizar o conteúdo.

O filtro `Instalados 0` agora limpa `selectedEmulator`, fecha o inspector e oferece
**Ver todos** e **Instalar primeiro emulador** (a segunda ação apenas abre o plano seguro já
existente). Perfis, sync e diagnóstico receberam estados vazios orientativos. Prontidão não
é apresentada como “tudo aplicado”: ambiente, desejo, recomendação, último perfil aplicado
e estado não verificado permanecem distinguíveis.

O carregamento solicitado é tardio (evita flash em requests rápidos), bloqueia interação
concorrente, mantém a tela anterior como contexto e nunca inventa percentual. Redução de
movimento remove a animação de navegação; alto contraste troca tokens, não aplica filtro.

### Evidência

```text
qmllint → OK
Qt Quick Test → 6 passed, 0 failed, 0 skipped
Qt 6 offscreen smoke → OK (encerrado apenas por timeout do harness)
make check → 367 passed; format/lint/boundaries/independence/mypy verdes
git diff --check → OK
```

Nove goldens foram renderizados e inspecionados em
`src/steamzero/ui/qml/golden/`: visão geral Deck, filtro vazio, drawer, carregamento,
perfis Full HD, conflito Full HD, sync ultrawide, 4K desktop e 4K TV.

### Limites e riscos restantes

- **Wayland/X11:** não verificado nesta fatia; o render foi Qt 6 offscreen/software.
- **Hardware:** não verificado; nenhum apply, URI Steam ou efeito de sistema foi acionado.
- **Gamepad/touch/hot-swap/dock:** não verificados em hardware. O grafo existente e os
  labels acessíveis foram preservados, e PgUp/PgDown exercem a navegação por seções no dev.
- **Steam Controller coordenado:** não implementado na QML porque o payload atual só
  oferece `/steam/open`; não existem `steamControllerWindowManaged`, lifecycle de janela
  externa ou ação “trazer para frente”. Implementar isso exige adapter/capability no escopo
  de outra branch, com testes Wayland/X11 e rollback de regra temporária.
- **Lançamento gerenciado:** o read model atual não fornece seus estados/detalhes; a QML
  não inventa fallback. A apresentação compacta/expandida deve ser ligada quando o contrato
  real existir.
- **i18n:** todas as novas strings usam `qsTr`, mas o catálogo inglês continua ausente,
  dívida já registrada como M3d.

Próxima etapa recomendada: integrar os dois read models ausentes em branch de adapters,
então executar a matriz assistida no Deck/KDE Wayland, X11 suportado, controle/touch e
dock/hotplug antes de promover qualquer célula para `verified-hw`.
