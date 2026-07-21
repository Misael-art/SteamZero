# WORKLOG — PhaseZero Unified (Fase 0: Fundação Documental)

## 2026-07-14 — Sessão 1: Descoberta, auditoria e fundação documental

### Etapa: Descoberta de repositórios

**Repositórios locais encontrados:**

| Projeto | Caminho | Estado |
|---|---|---|
| PhaseZero | `/mnt/sdcard/Projects/PhaseZero/` | Repo git íntegro, HEAD `a0468ba` (pós v1.8.4), remote `github.com/Misael-art/PhaseZero` |
| EmuDeck | **AUSENTE localmente** | Nenhum clone em `/mnt/sdcard/Projects/`; apenas wrapper `PhaseZero/linux/emulation/emudeck.sh` e `~/Downloads/EmuDeck.desktop` |
| LinuxToys | **AUSENTE como repo**; artefatos em `PhaseZero/linuxtoys-bin/` (tarball fonte 6.4.3 + pacote Arch) | Não é clone de desenvolvimento |
| RetroDECK | **AUSENTE localmente** | Apenas wrapper `PhaseZero/linux/emulation/retrodeck.sh`; sem Flatpak instalado (`flatpak list` vazio para RetroDECK) |

**Decisão registrada (não silenciosa):** como não havia fonte local a substituir, os repositórios oficiais foram clonados de forma declarada, **somente leitura**, em `Port_Steam/reference/`:

| Referência | Commit | Data upstream |
|---|---|---|
| `reference/EmuDeck` (dragoonDorise/EmuDeck) | `71d4cdc` | 2026-07-09 |
| `reference/linuxtoys` (psygreg/linuxtoys) | `89856ef` (prep 6.4.4) | 2026-07-14 |
| `reference/RetroDECK` (RetroDECK/RetroDECK) | `d7c02e8` | 2026-05-29 |
| `reference/RetroDECK-components-index/` | árvore via API GitHub (6.799 paths) + 5 arquivos representativos | 2026-07-14 |

**Pendência:** o clone completo de `RetroDECK/components` excedeu o timeout (repo com blobs pesados, `archive_later/` com 5.516 paths). Registrado em KNOWN-GAPS. A análise do modelo de componentes usou a árvore completa via API + `framework/component_manifest.json`, `framework/component_recipe.json`, `duckstation/component_manifest.json`, `duckstation/component_functions.sh` baixados individualmente.

### Etapa: Auditoria

**PhaseZero** — arquivos-chave lidos integralmente ou por trecho: `CLAUDE.md`, `linux/lib/common.sh` (817 linhas, lido integral), `linux/lib/json-envelope.sh` (integral), `linux/pz` (usage completo), `linux/emulation/emudeck.sh`, `linux/emulation/library/{apply,plan}.py` (pipeline scan/plan/apply/verify/rollback com confirmToken). 128 scripts shell em `linux/`, 493 `.ps1` no lado Windows, 122 arquivos de teste Pester (dezenas cobrindo Linux: `linux-admin-bridge.sh`, `linux-boot-recovery.sh`, `linux-controllers.sh`...). Zero usos de `eval` em `linux/`.

**EmuDeck** — 228 scripts `.sh`; **0** com `set -euo pipefail`; 1 uso de `eval`; 31 scripts de emulador em `functions/EmuScripts/` seguindo convenção `<Emu>_install/_init/_update/_uninstall`; downloads via `safeDownload()` (`functions/helperFunctions.sh:743`) com staging `.temp` e SHA256 **opcional** (maioria dos callers não fornece); `getReleaseURLGH()` resolve "latest" da API GitHub sem pin de versão.

**LinuxToys** — app GTK Python (`p3/linuxtoys.py`) + 264 scripts com metadados em cabeçalho (`# name:`, `# version:`, `# description:`, `# icon:`, `# compat:`, `# repo:`); bibliotecas compartilhadas `p3/libs/{linuxtoys.lib,helpers.lib,optimizers.lib}`; detecção de distro (`is_fedora`, `is_arch`, `is_ostree`...); fallback zenity→terminal; 1 script com strict mode.

**RetroDECK** — Flatpak (manifest `net.retrodeck.retrodeck.yml`); framework de configuração (`functions/framework.sh`) com **26 usos de `eval`** para indireção de variáveis; Configurator Godot (`godot-configurator.sh` referenciado no manifest de componentes); modelo de componentes: `component_manifest.json` + `component_recipe.json` + `component_prepare.sh` + `component_update.sh` + `component_functions.sh` + `rd_assets/rd_config/`; menus declarativos do Configurator em JSON; gestão de paths móveis (roms/bios/saves/media por variável).

### Descobertas centrais

1. PhaseZero já implementa o padrão transacional alvo no pipeline de biblioteca (`linux/emulation/library/`): scan→plan (com `confirmToken`)→apply(–confirm)→verify→rollback.
2. O envelope JSON (`json-envelope.sh`) é o embrião do contrato CLI/UI: `{ok, module, status, checks, actions, blockers, logs, generatedAt}`.
3. EmuDeck tem a maior cobertura funcional (31+ emuladores, cloud sync, SRM, ES-DE), mas robustez baixa: sem strict mode, paths hard-coded (`$HOME/.local/share/...`), migrações destrutivas sem backup (ex.: `emuDeckDuckStation.sh` move config flatpak e desinstala sem rollback).
4. LinuxToys demonstra o modelo manifest-driven mínimo viável: metadado em cabeçalho + biblioteca comum + detecção de distro.
5. RetroDECK demonstra isolamento Flatpak, paths móveis, backup de userdata, BIOS checker e componentes com manifest/recipe — mas o framework interno usa `eval` extensivamente (anti-padrão a não copiar).
6. Licenças: EmuDeck GPL-3.0, LinuxToys GPL-3.0, RetroDECK GPL-3.0 (+ `other_licenses.txt`). PhaseZero **sem arquivo LICENSE** (proprietário do usuário). Consequência: qualquer cópia literal de código dos três projetos GPL exige que o novo projeto seja GPL-3.0-compatível.

### Decisões desta sessão

- Codinome mantido: **PhaseZero Unified** (nome final = decisão de produto, ver OPEN-QUESTIONS).
- Fundação documental criada em `docs/` conforme estrutura do prompt mestre (§8), com `docs/11-legal/` absorvendo os artefatos citados em §7 como `docs/legal/`.
- 18 ADRs redigidos (0001–0018).
- Nenhum código de produção foi escrito. Nenhum repositório de origem foi modificado.

### Riscos identificados (top 5 — detalhe em 12-roadmap/RISK-REGISTER.md)

1. Incompatibilidade de licença entre PhaseZero (sem licença) e os projetos GPL, se houver cópia literal bidirecional.
2. Escopo do produto é muito amplo (boot/GRUB, VM, Waydroid, homelab no PhaseZero) — risco de arrastar escopo não-emulação para o Unified.
3. Dependência de comportamento do SteamOS/Decky que muda a cada atualização Valve.
4. Ausência de hardware Steam Deck neste ambiente de análise — nada foi validado em hardware.
5. RetroDECK/components não clonado integralmente — modelo de recipes conhecido por amostragem.

### Próxima ação

Aguardar aprovação (`APPROVED_TO_IMPLEMENT` no diretório do projeto ou autorização textual equivalente). Nenhuma implementação antes disso.

## 2026-07-15 — Sessão 1 (continuação): fundação concluída

- 99 arquivos `.md` em `docs/` (todos os 78 obrigatórios do §8.1 verificados presentes por script) + 18 ADRs + glossário + REUSE-POLICY.
- `FOUNDATION-READINESS-REPORT.md` emitido na raiz do projeto: classificação **READY FOR PROTOTYPE**; bloqueadores para READY FOR IMPLEMENTATION: decisão de licença (Q2/ADR-0013) e aprovação formal; G5 (hardware) bloqueia apenas release stable; G1 bloqueia apenas kickoff da Fase 4.
- `README.md` de índice criado.
- Trabalho da Fase 0 encerrado. **Parado, aguardando `APPROVED_TO_IMPLEMENT`.**

## 2026-07-15 — Sessão 1 (correção): realocação do projeto

- Por decisão do responsável, o projeto é **independente** e passa a ser desenvolvido em `/mnt/sdcard/Projects/Port_Steam/`.
- Todo o conteúdo (docs/, reference/, README.md, FOUNDATION-READINESS-REPORT.md) foi movido de `/mnt/sdcard/Projects/PhaseZero-Unified/` (diretório removido) para `/mnt/sdcard/Projects/Port_Steam/`.
- Referências de caminho na documentação atualizadas (ASSUMPTIONS, WORKLOG, SOURCE-REPOSITORIES). O gate de aprovação passa a ser `/mnt/sdcard/Projects/Port_Steam/APPROVED_TO_IMPLEMENT`.
- O codinome de produto "PhaseZero Unified" permanece até decisão de nome (Q1); "Port_Steam" é o nome do diretório de desenvolvimento, não necessariamente o nome do produto.

## 2026-07-15 — Sessão 1 (decisão de produto): nome definido — SteamZero

- **Q1 resolvida pelo responsável: o produto se chama SteamZero.**
- Aplicado em toda a documentação (exceto entradas históricas deste WORKLOG): "PhaseZero Unified" → "SteamZero"; CLI `pzu` → `steamzero`; daemon `unified-core` → `steamzero-core`; helper `unified-admin` → `steamzero-admin`; placeholders `<produto>` em paths → `steamzero` (ex.: `$XDG_STATE_HOME/steamzero/`, socket `$XDG_RUNTIME_DIR/steamzero/core.sock`).
- OPEN-QUESTIONS Q1 e DEPENDENCY-PLAN atualizados; sub-decisão restante: ID Flatpak (depende da org de hospedagem).
- Novo risco registrado: **R-15** — "Steam" é marca da Valve; mitigação com disclaimer de não-afiliação e validação de diretrizes de marca antes do release público.

## 2026-07-15 — Sessão 1 (metodologia): processo documentado para replicação

- Criado `METODOLOGIA-SINTESE-DE-PROJETOS.md` (raiz): documento autocontido, dirigido a agentes de IA, formalizando o método usado neste projeto — pipeline E1–E8 (descoberta → auditoria com evidência → matrizes de cruzamento → legal → síntese arquitetural → fundação documental → gate de prontidão → handoff com revisão externa), com princípios invariantes (MP-1..5), checklist de replicação e armadilhas observadas nesta execução.
- Criado `IMPLEMENTATION-PROMPT.md` (raiz): prompt de construção (etapa E8) para o agente implementador, com gates de partida, DoD por commit, proibições e exigência de `IMPLEMENTATION-REPORT.md` auditável.
- README atualizado com ponteiros para ambos.

## 2026-07-15 — Sessão 2: início da implementação (Fase 1 / M1)

### Gates de partida (todos verdes)
- **Aprovação formal:** concedida pelo titular nesta conversa ("inicie" + seguir a
  recomendação do FOUNDATION-READINESS-REPORT), confirmada via prompt de decisão.
  Registrada em `APPROVED_TO_IMPLEMENT` (raiz).
- **Q2/ADR-0013 licença:** decidida = **GPL-3.0-or-later**. ADR-0013 → ACEITO;
  REUSE-POLICY atualizada; `LICENSE` = GPLv3 canônica da FSF baixada por HTTPS e
  verificada (marcadores + `sha256 3972dc97…`).
- **git init:** repositório criado (`git init -b main`), `.gitignore` cobrindo
  venv/caches/reference/runtime.
- **Decisões de escopo do titular:** Q4 = v1 estritamente emulação+jogos
  (boot/VM/Waydroid/homelab seguem NON-GOALS); Q7 = pt-BR com chaves i18n.

### Toolchain (evidência)
- Python 3.14.6 (≥3.11 ✓). Venv `.venv`. Lockfile `requirements-dev.lock` gerado
  por `pip-compile --generate-hashes` (SR-11) e instalado com `--require-hashes`.
- `ruff 0.15.21`, `mypy 2.3.0`, `pytest 9.1.1`, `jsonschema 4.26.0`, `hypothesis`.
- `shellcheck` ausente no ambiente; sem shims bash na Fase 1 (ADR-0001) — gate de
  CI de shellcheck já escrito, dispara quando houver `shims/**/*.sh`. Dívida baixa.

### Entregue nesta sessão (M1 parcial — base do núcleo)
- Esqueleto do pacote `src/steamzero/` com fronteiras (MODULE-BOUNDARIES).
- `core.ids` (ULID 128-bit Crockford + slugs) + testes (unit + property).
- Pacote `i18n/` pt-BR com catálogo de mensagens (Q7).
- `core.errors`: registro autoritativo de códigos (ERROR-CATALOG) + objeto
  error-v1 + `SteamZeroError` que recusa código não catalogado.
- **Lint de fronteiras** `tools/lint_boundaries.py` (AST puro): BND-EVAL,
  BND-WRITE-PORT, BND-PROC, BND-SHELL, BND-DOMAIN-ADAPTER — com teste que prova
  detecção real e que o `src` passa limpo. Rodando em CI desde o 1º commit.
- Harness: `pyproject.toml` (ruff/mypy-strict/pytest), `Makefile`, `.github/workflows/ci.yml`.

### Divergências/adições registradas (não silenciosas)
- **Adições ao ERROR-CATALOG** (permitido: catálogo "cresce por PR com revisão"):
  `E-CLI-USAGE`, `E-STATE-MIGRATION`, `E-STATE-INTEGRITY`, `E-INTERNAL-UNEXPECTED`.
  Todas com textos pt-BR e cobertas pelo teste de completude do catálogo.
- **Interpolação de texto de erro:** catálogo mantido com **texto fixo** (sem
  placeholders); especificidades dinâmicas vão em `detail`/`autoAction` do objeto
  de erro — escolha conservadora que honra "texto fixo auditado" da CONTENT-POLICY.
  Interpolação de títulos humanos (ex.: "Falta scph1001.bin") fica para a Fase 3 (UX).

### Evidência de qualidade (saída real)
- `ruff check` → All checks passed! · `ruff format --check` → 10 files already formatted
- `mypy` (--strict) → Success: no issues found · `pytest -q` → 41 passed
- `python tools/lint_boundaries.py --root src` → OK (0 violações)

### Fase 1 concluída nesta sessão — demonstração objetiva dos marcos (MILESTONES.md)

Sequência de commits temáticos (0 mega-commit): baseline fundação → gate legal →
scaffold/toolchain → ids/i18n/errors → lint fronteiras → core.fs → core.log/Secret →
core.lock → journal/transação → FI-04 → State Store → Job Manager → M2 (CLI/schemas)
→ build reproduzível.

**M1 — "Kill-proof core" (FI-04 verde):**
```
$ pytest tests/failure_injection -q
22 passed in 1.44s
```
Cobre kill (SimulatedKill) em cada etapa do pipeline × {alvo existente, ausente},
kept pós-commit, recovery idempotente, e **SIGKILL real** de subprocesso em
apply.intent/activate/done/commit. AC-TX-02 provado (estado byte-idêntico, zero
tmps órfãos, journal terminal).

**M1 — AC-TX-01..04 + rollback (RB-3/RB-4/T-09):**
```
$ pytest tests/integration/test_transaction.py -q -k "ac_tx or rb3 or rb4 or verify_failure or new_file"
7 passed
```

**M2 — "CLI contratada" (`steamzero doctor --json` validado por schema):**
```
$ steamzero doctor --json | (valida contra envelope-v2.schema.json) → ENVELOPE VÁLIDO
status=ok, checks=4 (runtime.python, state.layout, state.db.integrity, recovery.pending)
$ steamzero --contract-version → 2.0
```

**M3 — "Jobs resilientes" (pausa/resume/cancel/reboot-recovery):**
```
$ pytest tests/integration/test_jobs.py -q -k "recover or pause or cancel"
5 passed
```
recover: running→interrupted→{queued | rolled-back | completed(roll-forward)}.

**Qualidade (build limpo reproduzido do zero — clone + venv do lockfile):**
```
ruff OK · ruff format OK · boundaries OK (0 violações) · mypy --strict OK
pytest → 168 passed ; cobertura núcleo: fs 95% journal 97% state 96%
transaction 93% lock 94% (meta ≥90% no núcleo/core.fs: atingida)
```

### Divergências/notas adicionais (não silenciosas)
- **`interrupted -> completed`** adicionado à máquina de estados de job (roll-forward),
  conforme o TEXTO do JOB-LIFECYCLE §Recuperação; o diagrama não o desenha.
- **State Store como porta de persistência distinta de core.fs**: escrita SQLite não
  passa por core.fs (ADR-0005: writer único no daemon); backup do db passa por core.fs.
- **`operation` table populada pela orquestração** (job manager/domínio), não pelo
  core.transaction (que usa o journal como fonte de verdade do recovery).
- **Adições ao ERROR-CATALOG**: E-CLI-USAGE, E-STATE-MIGRATION, E-STATE-INTEGRITY,
  E-INTERNAL-UNEXPECTED (permitido; catálogo cresce por PR).

## 2026-07-15 — Sessão 2 (continuação): Fase 2 (M4–M6)

Entregue na mesma sessão, após a Fase 1. **Nível verified-dev** (portas fake /
efetor dry — nada tocou hardware nem root).

**M4 — Deck-aware:**
```
$ pytest tests/integration/test_device.py tests/integration/test_mode.py tests/integration/test_storage.py -q
18 passed
```
- `domain.device`: DMI → deck-lcd/oled/desktop; quirks (faixa TDP).
- `domain.mode`: cadeia de fallback de display (FM-18) sempre até imagem válida (AC-SD-01).
- `domain.storage`: microSD por UUID; remoção → missing + `resolve_write_path` recusa
  (E-STORAGE-MISSING, zero escrita fantasma); reinserção restaura (FM-06/AC-SD-02/FI-07).

**M5 — Helper privilegiado:**
```
$ pytest -m security -q
29 passed
```
- `privileged.protocol`: allowlist fechada (6 ações), validadores explícitos, tabelas embutidas.
- `privileged.helper`: valida protocolo→allowlist→chaves→params→authorizer ANTES de executar;
  audit append-only. Fuzzing (parametrizado + hypothesis) prova zero execução sem gate
  (ST-01/AC-PR-01); allowlist só privilegiada (AC-PR-02).

**M6 — Sessão + offline:**
```
$ pytest tests/integration/test_session.py tests/integration/test_offline.py -q
14 passed
```
- `domain.session`: suspend pausa jobs + checkpoint (FI-09/AC-SV-02), fallback flush
  (E-SAVES-FLUSH-TIMEOUT), close escala até SIGKILL c/ confirmação (FM-08).
- `jobs.manager`: `requiresNetwork` → blocked (E-SUPPLY-OFFLINE); local/doctor offline (AC-OF-01).

**Fronteira crítica mantida:** `domain.*` nunca importa `adapters.*` (portas Protocol
injetadas) — verificado por `lint_boundaries` (BND-DOMAIN-ADAPTER), 0 violações.

**Qualidade:** ruff/format/boundaries/mypy verdes; `pytest` → 229 passed; cobertura
93% (domínio 91–98%, privileged 90–100%). Build limpo reproduzido no HEAD → 229 passed.

**Divergência registrada:** máquina de estados de sessão própria (idle→…→closed) — o
diagrama do DATA-FLOW/§11.1 descreve o comportamento, não os estados nominais; adotados
estados explícitos (P6).

### Dívida principal da Fase 2 (ver IMPLEMENTATION-REPORT §4-A0)
Camada `adapters.*` concreta (DMI real, DRM/KMS, /proc/mounts+by-uuid, efetor sysfs/
systemd, transporte pkexec/D-Bus) + composição que injeta as portas. Sem ela, M4–M6
não funcionam num Deck real. Compat Matrix (F-SD-05) tem só a tabela.

## 2026-07-15 — Sessão 2 (continuação): Fase 3 (M7 parcial, M8–M9 done)

**M7 — Library (parcial):**
```
$ pytest tests/integration/test_library.py tests/integration/test_convert.py tests/failure_injection/test_safezip.py -q
27 passed
```
- `core.safezip`: extração confinada por bytes reais — traversal/symlink/NUL/bomb/
  contagem/profundidade/razão (FI-16/17/18, AC-LB-03, FM-14).
- `domain.library`: scan read-only (AC-LB-01), import por cópia com origem intocada
  (RT-07/AC-LB-02), dedupe por hash, multidisco "(Disc N)", archive via safezip com
  staging limpo em inseguro.
- `domain.convert`: conversão para staging via porta fake; original-até-commit,
  preflight de espaço (E-STORAGE-SPACE), timeout/falha limpam staging e preservam o
  original (RT-06, marcador `rt`).
- **Falta (M7 não fecha):** pipeline generalizado scan→plan→apply→rollback de
  organização (move/rename) sobre 10k fixtures + benchmark; RT-08..11; conversores reais.

**M8 — BIOS store + Saves timeline (done):**
```
$ pytest tests/integration/test_bios.py tests/integration/test_saves.py -q
13 passed
```
- `domain.bios`: banco bios-db-v1 só-hashes (schema `additionalProperties:false` rejeita
  conteúdo — CONTENT-POLICY); ausente sem link (AC-BI-02); hash/key nunca em log, só
  truncado (AC-BI-01/SR-14).
- `domain.saves`: timeline append-only, blobs por conteúdo (dedupe), restauração
  byte-idêntica verificada (AC-SV-03), conflito preserva ambos (AC-SV-01/P12).

**M9 — Sync não-destrutivo (done):**
```
$ pytest tests/integration/test_sync.py -q
5 passed
```
- `domain.sync`: feature flag; fila offline em sync_queue (DF-4); conflito remoto≠local
  baixa remoto como versão paralela e marca conflicted — ambos preservados (J6/AC-SV-01).

**Divergências registradas:**
- `E-CONVERT-TIMEOUT`/`E-CONVERT-FAILED` adicionados ao catálogo (Fase 3, textos pt-BR).
- "Quarentena" no import de archive externo = staging limpo + evento (a fonte do usuário
  NÃO é movida; escolha conservadora que preserva dados — a origem é read-only externa).

**Qualidade:** ruff/format/boundaries/mypy verdes; `pytest` → **270 passed** (0 falhas/skips);
cobertura **94%**. Build limpo reproduzido no HEAD → 270 passed.

### Próxima ação
Fechar M7 (pipeline de organização 10k + RT-08..11) OU Fase 4 (engine de adapters +
adapters de emuladores/frontends) OU fechar o gap verified-dev→verified-hw (adapters de
hardware reais + Deck). Ver IMPLEMENTATION-REPORT §4 (dívidas) e §7 (autoavaliação).

## 2026-07-15 — Sessão 3: M7 concluído (organização transacional 10k)

**Entregue:**
- `core.transaction` ganhou ações de move/rename sem conteúdo inline, com precondições
  de origem+destino, confirmToken, containment, rejeição de colisões/ciclos, backup
  verificado, journal intent→done, verify e rollback G-FULL idempotente.
- Falha comum no meio do apply agora dispara rollback automático; crash abrupto continua
  sendo recuperado pelo journal. Rollback se recusa a destruir origem/destino recriado
  ou alterado depois da operação (`E-TX-ROLLBACK-FAILED`).
- `core.fs.copy_file_atomic` copia em streaming com fsync+replace; backups/restores de
  ROMs não carregam mais o arquivo inteiro em memória.
- `domain.library.LibraryOrganizer`: scan→plan→apply→rollback por paths relativos, com
  plano validado pelo schema `plan-v1`.

**Demonstração objetiva M7:**
```text
$ pytest tests/integration/test_library_organize.py::test_10k_fixture_apply_and_rollback_benchmark -q -vv
1 passed in 18.97s
```
O teste cria 10.000 fixtures sintéticas, planeja e aplica 10.000 movimentos, verifica o
layout e executa rollback de todos os itens, restaurando as origens e limpando staging.

**Gate completo:**
```text
$ make check
ruff format/check OK · boundaries OK · mypy strict OK · pytest: 284 passed
$ pytest --cov=steamzero -q -m 'not slow'
283 passed, 1 deselected · core.fs 94% · core.transaction 91% · pacote 92%
```
O total do pacote inclui `src/steamzero/ports.py` (trabalho não rastreado preexistente,
preservado nesta sessão) com 0% de cobertura. Falhas/skips/xfails: zero.

**Estado:** M7 `done`; M7–M9 concluídos. O gate amplo da Fase 3 continua parcial por
RT-08..11 e por conversores externos reais ainda não exercitados. Próxima ação normativa:
fechar esses RTs ou iniciar M10; a dívida A0 (adapters concretos de hardware) permanece.

## 2026-07-15 — Sessão 4: gate da Fase 3 fechado (RT-08..11)

**RT-08 — links de BIOS:** `core.transaction` ganhou ação `symlink` e `core.fs`
publicação atômica com fsync. `BiosStore.plan_link` verifica a BIOS central antes de
planejar. Link deliberadamente quebrado falha no verify, é removido e não toca a fonte;
apply/rollback normal é idempotente.

**RT-09 — restore de save:** restauração para o arquivo ativo agora usa plan+confirmToken,
backup e verify/smoke. Falha de validação restaura byte-idêntico o save atual.

**RT-10 — sync interrompido:** fila explicita `pending→in-flight→done|conflicted`;
exceção remota devolve o item a pending com `E-SUPPLY-REMOTE-FAILED`. Um drain posterior
retoma; entradas deixadas in-flight por crash também são recuperadas.

**RT-11/ST-06 — mídia:** novo `domain.media` local canonicaliza por gameId/kind e magic
bytes; órfãos, tamanho excessivo, magic inválido e nomes bidi vão para quarentena lógica
com nomes seguros. Falha ou rollback devolve canonicalizados e órfãos aos paths originais.

**Evidência:**
```text
$ make check
ruff format/check OK · boundaries OK · mypy strict OK · pytest: 295 passed in 21.83s
$ pytest --cov=steamzero -q -m 'not slow'
294 passed, 1 deselected · core.fs 93% · core.transaction 90% · pacote 92%
$ pytest --collect-only -q -m rt
17/295 testes RT coletados
```
Falhas/skips/xfails: zero. `src/steamzero/ports.py` permaneceu intacto e não rastreado.

**Estado:** o critério explícito de saída da Fase 3 (AC-LB/BI/SV + RT-06..11) está
atingido em `verified-dev`. Limitações restantes: conversores/provedores reais,
scraper-cache-rate-limit e migração SSD↔microSD (A6). Próximo marco: M10, começando pela
engine de manifests e três adapters núcleo; A0 continua sendo a principal dívida de HW.

## 2026-07-15 — Sessão 5: M10 iniciado (engine e três manifests)

**Entregue:**
- `adapter-v1.schema.json` estrito, loader com validações semânticas e registry fechado;
- manifests pinados para DuckStation, RetroArch e Dolphin, com IDs/commits consultados
  nos remotos Flathub user e system;
- `AdapterEngine` com porta de aquisição injetável, checksum SHA-256 antes de qualquer
  escrita no componente, plan/confirmToken/apply/verify e persistência no State Store;
- releases portáveis imutáveis, ativação por `current.json`, install idempotente sem novo
  fetch, update e rollback G-FULL manual ou automático em falha de smoke test;
- métodos `save/get/list_component` no State Store e contrato empacotado no wheel.

**Risco descoberto:** `org.duckstation.DuckStation` responde no catálogo remoto, porém
está marcado end-of-life/sem manutenção desde 2025-08-13 e já não aparece como disponível
na página do Flathub. O manifesto registra `endOfLife: true`; não será promovido a fonte
instalável. É necessário pin oficial alternativo com checksum antes de fechar M10.

**Evidência:**
```text
$ make check
ruff format/check OK · boundaries OK · mypy strict OK · pytest: 302 passed in 21.73s
$ pytest --cov=steamzero -q -m 'not slow'
301 passed, 1 deselected · adapters.engine 86% · adapters.registry 88% · pacote 91%
$ pytest --collect-only -q -m rt
19/302 testes RT coletados (RT-01/02 agora marcados no lifecycle de componentes)
$ steamzero doctor --json
status: ok · state.db integrity: pass · pending operations: 0
```

**Estado:** M10 `partial` em `verified-dev`. Não houve instalação dos emuladores no host.
Faltam executor Flatpak transacional, lockfile e demo install/update/rollback dos três em
VM; DuckStation também precisa de uma nova fonte oficial. `src/steamzero/ports.py` segue
intacto, não rastreado e fora deste incremento.

## 2026-07-15 — Sessão 6: M10-H Handheld Desktop foundation

**Regra arquitetural fechada:** SteamZero não depende do PhaseZero em build, instalação,
runtime, recuperação ou testes. ADR-0019 e `tools/check_independence.py` tornam a regra
um gate de CI. A antiga coexistência em runtime foi removida; o único caminho legado é
um conversor de snapshot offline, separado, read-only e não empacotado.

**Backend e host adapter:**
- novo `domain.desktop` com `DesktopContext`, `ExperienceProfile`, ownership válido por
  fingerprint, planos v1, confirmação, override e perfis handheld/dock/safe;
- snapshot persistente antes do primeiro efeito, verify por efeito, rollback reverso e
  recovery pós-crash; conflito genérico bloqueia antes de qualquer mutação;
- detector Linux/KDE real (DMI, KScreen, `/proc` input, USB dock, capabilities) e efeitos
  reversíveis de escala KScreen/política KWin;
- InputPlumber só é elegível com marker SteamZero de validação; instalação isolada não
  muda ownership; teclado tenta KWin/Maliit e só depois Steam;
- State Store migração 0002 amplia perfis sem perder linhas da v1.

**CLI e UI:** `desktop status|plan|apply|reset|recover|keyboard|ui`. A central QML tem
layout de uma coluna no Deck, alvos de 48 px, labels acessíveis e grafo de foco. A bridge
é efêmera em 127.0.0.1, usa token aleatório, allowlist e os mesmos confirmTokens; Qt não
entrou na dependência do núcleo. `qmllint` verde e smoke offscreen abriu sem erros.

**Hardware read-only:** em Steam Deck LCD/BigLinux/KDE Wayland, `desktop status --json`
detectou Valve Jupiter, eDP-1 800×1280@60, escala 1,35, KDE/KScreen, Maliit, Steam,
KDE Connect e TTS BigLinux. InputPlumber estava ausente. Nenhum apply, hotplug, captura
de input ou ação privilegiada foi executado. O preflight genérico encontrou um serviço
externo `*-mode-watcher`, retornou `blocked` e permaneceu observador, sem identificá-lo
por integração nem tentar controlá-lo. O rótulo é `verified-hw-readonly`.

O wheel real foi construído e inspecionado: domínio/adapters/schemas/QML estão presentes;
o arquivo local não rastreado `src/steamzero/ports.py` foi excluído explicitamente pelo
Hatch e o gate de independência verifica essa configuração. Instalação do wheel em venv
novo passou em `doctor` e `desktop status` após instalar o runtime declarado `jsonschema`.

**Gate:**
```text
$ make check
format/lint/boundaries/independence/mypy OK · pytest: 333 passed em 23.86s
$ steamzero doctor --json
status: ok · schemaVersion: 2 · pending operations: 0
```

Falhas/skips/xfails: zero. `src/steamzero/ports.py` permaneceu intacto, não rastreado e
deve continuar fora do commit. M10-H fica `foundation`: o próximo gate é o apply
assistido em hardware com rollback, dock/hotplug real e spike do InputPlumber.

## 2026-07-15 — Sessão 7: M10 Flatpak pinado e recuperável

**Entregue:**
- `component-lock.json` empacotado e schema `component-lock-v1`; o registry recusa
  manifesto sem lock, órfão ou hash/origem/commit divergente;
- `FlatpakExecutor` user-scoped com plan/confirmToken/TTL, commit OSTree de 64 caracteres,
  preflight remoto do alvo e do commit anterior, revalidação de deployment e bloqueio EOL;
- intent durável antes do efeito, verify do commit, smoke, rollback G-DEPLOYMENT e recovery
  pós-crash; app data nunca recebe `--delete-data` e runtimes órfãos ficam para GC;
- CLI `component list|status|plan|apply|rollback|recover`, sem shell e com argv fixo;
- FI-25/26 cobrem queda após deploy e falha dupla smoke+rollback.

**Hardware/host:** somente `component list --json` read-only foi executado no host e
detectou os três adapters como ausentes. Nenhum `flatpak install/update/uninstall/run`
foi disparado fora das portas fake. O wheel final foi construído, inspecionado (inclui
executor/lock/schemas e exclui `ports.py`), instalado isoladamente em `/tmp` e repetiu o
status read-only com sucesso.

**Gate:**
```text
$ make check
format/lint/boundaries/independence/mypy OK · pytest: 350 passed
$ pytest --cov=steamzero -q -m 'not slow'
349 passed, 1 deselected · flatpak 75% · lockfile 88% · pacote 86%
```

M10 continua `partial`: falta a demonstração install/update/rollback dos três em VM e
uma fonte oficial ativa para DuckStation. O arquivo local `src/steamzero/ports.py`
permaneceu intacto, fora do wheel e fora deste incremento.

## 2026-07-15 — Sessão 8: bootstrap host BigLinux resiliente

**Instalação reproduzível:** foi adicionado um lock mínimo de runtime com hashes e um
instalador stdlib-only para `bigsudo`. Cada release fica imutável em
`/opt/steamzero/releases/<id>`, com wheel, lock, manifesto, venv próprio e instalador
auditável. A ativação acontece por troca atômica de `/opt/steamzero/current`; comando e
Desktop entry são integrações gerenciadas, e arquivos preexistentes alheios são recusados.

O instalador valida release/hash/tamanho/tipo dos artefatos, instala offline com
`--require-hashes`, executa `pip check`, versão e doctor antes de publicar, fsynca toda a
árvore e recupera instalação interrompida por `.installing.json`. Estado XDG do usuário
não é alterado por install/rollback. O plano de gerenciamento
`/usr/local/sbin/steamzero-host` permanece na versão mais nova durante rollback.

**Falhas descobertas e corrigidas durante adversidade:**
- pip rejeitou um wheel renomeado; o nome original agora é preservado;
- mover um venv pronto invalidava shebangs absolutos; ele agora nasce no path final e só
  fica visível depois dos smokes;
- o `PATH` seguro do `bigsudo` não inclui `/usr/local/sbin`; documentação usa caminho
  absoluto;
- duas categorias principais duplicavam o atalho KDE; ficou apenas `Game`;
- rollback da aplicação também regredia o gerenciador e podia recriar integração antiga;
  o plano de gerenciamento foi separado e ganhou ownership marker.

**Evidência real no Steam Deck LCD/BigLinux:** release final
`0.1.0.dev0-1bb00d7-host3`, wheel SHA-256
`c5771ea08b0f643384a5244f461b57a1ea435850f70bc5b4f31df9c2c56bd407`.
`steamzero doctor --json` retornou `ok`, schema 2 e zero operações pendentes; `pip check`,
manifesto/hashes/permissões root, Desktop entry, `qmllint`, QML offscreen e cache KDE
passaram. Reinstalação foi idempotente (mesmo `installedAt`). Rollback real
`host3 → host1 → host3` manteve o gerenciador regular root-owned com hash idêntico e
restaurou o lançador correto.

`desktop status --json` detectou Deck LCD + monitor DP e retornou `independentRuntime:
true`; o watcher externo `phasezero-steamdeck-mode-watcher.service` foi apenas detectado
como conflito e bloqueou mutação (`E-DESKTOP-OWNER-CONFLICT`). Nenhum serviço PhaseZero,
perfil de display/input ou componente Flatpak foi alterado. O wheel instalado não contém
`steamzero.ports`.

**Gate final:** `make check` com **357 testes**, zero falhas/skips/xfails. O
arquivo local `src/steamzero/ports.py` permaneceu intacto, não rastreado e fora do wheel.

## 2026-07-15 — Sessão 9: feedback e liberação segura de ownership Desktop

**Problema reproduzido:** o bloqueio FM-22 funcionava, mas a central apenas desabilitava
Apply. Não havia card persistente, explicação acionável nem caminho confirmado para liberar
o owner, e uma exceção inesperada na bridge podia fechar a conexão sem resposta.

**Escopo real corrigido:** no Deck/BigLinux, `phasezero-steamdeck-mode-watcher.service`
está carregado de `~/.config/systemd/user`, `active` e `enabled`; não existe unidade de
sistema com esse nome. Assim, `sudo systemctl stop|disable` atuaria no escopo errado. A
ação allowlisted usa exatamente `systemctl --user stop` e `systemctl --user disable`.

**Fluxo entregue:** `desktop status` expõe `conflictActions` estruturado; a UI mostra card
âmbar com causa/impacto/unidade e botão **Revisar desativação do watcher antigo**. O diálogo
exibe argv exato e só aplica com `planId` + `confirmToken`. Se stop passar e disable falhar,
o adapter tenta `enable` + `start` para restaurar o owner anterior. O Apply permanece
bloqueado até um novo status confirmar que o watcher saiu. Falhas esperadas e inesperadas
viram resposta HTTP estruturada e mensagem visível, não silêncio.

**Evidência sem mutação do watcher:** plano real validado por
`desktop-conflict-plan-v1`, QML real carregado offscreen com uma conflictAction, e o serviço
permaneceu `active/enabled` porque a confirmação não foi acionada automaticamente. Testes
novos cobrem token incorreto sem efeito, bridge+refresh, erro HTTP estruturado, argv
user-scoped e rollback da falha parcial. `make check`: **362 passed**,
independência/lint/mypy verdes.

**Host atualizado:** release `0.1.0.dev0-635429c-conflict-ui2`, wheel SHA-256
`3a0cfd9106df739fdbc05c0afae941d3b4e1be9f838242a6c2f90587dd19f21a`. Doctor,
`pip check`, schema empacotado, `qmllint` e QML instalado offscreen passaram; o status
instalado expôs uma conflictAction. O watcher permaneceu `active/enabled`, deixando a
decisão de desativação para o usuário no diálogo novo.

## 2026-07-16 — Sessão 10: System Studio, Steam e recuperação de emergência

**Redesenho funcional:** a central QML foi reconstruída conforme a direção visual System
Studio selecionada. A navegação agora organiza Visão geral, Emuladores, Steam, Perfis,
Saves e Sync e Sistema; o cabeçalho informa o contexto do Deck e um banner âmbar mantém
conflitos de ownership visíveis. Em telas largas há lista/detalhe simultâneos; no painel
interno do Deck a lista ocupa a largura útil sem perder foco, rolagem ou footer de controle.

**Dados e ações reais:** `DesktopDashboard` agrega registry/lock Flatpak, Steam, fila de
sync e doctor. Dolphin, DuckStation e RetroArch mostram a verdade do deployment; a fonte
EOL do DuckStation continua indisponível. A área Steam usa a mesma estrutura visual e
expõe cliente, biblioteca, Steam Input e teclado. Launches usam refs/URIs allowlisted;
install/update abre plano com confirmação e revalida o conflito no backend antes da
mutação. Falha, timeout ou bridge ausente sempre retorna feedback na UI.

**FM-23:** quando o journal exige recovery, a inicialização abre o modal **Alteração
incompleta detectada** com uma ação única para restaurar o último estado seguro. A UI só
libera o fluxo normal depois que um novo status confirma a recuperação.

**Design QA:** comparação conjunta e normalizada contra o terceiro conceito, incluindo
recorte focado de banner/lista/detalhe. Logos reais licenciados substituem placeholders;
marca própria, botões escuros, estados disabled e seção Steam foram validados. O relatório
`design-qa.md` encerrou sem P0/P1/P2.

**Gate e host:** `make check` passou com **367 testes**, além de `qmllint`. O wheel
`ce1c74bf22fb1b14da4de3b732c6b3741104751147807ee1a970778f9f3f6886` inclui QML,
assets e dashboard e exclui `steamzero.ports`. A release imutável
`0.1.0.dev0-20260716-systemstudio1` foi instalada com `bigsudo`; `steamzero-host status`
e `steamzero doctor --json` retornaram `ok`, schema 2 e zero operações pendentes. A cópia
instalada foi aberta no KDE/Wayland real. O watcher legado permaneceu inativo e não
registrado no systemd; instalação e runtime não exigem sua presença nem dependem dele.

## 2026-07-15 — Sessão de pesquisa: quadro de funções e proveniência

- Criado `docs/02-research/FUNCTION-PROVENANCE-MATRIX.md`: **262 funções** (camada de usuário + internas do núcleo) em 15 seções, cada uma classificada por proveniência com evidência.
- Taxonomia de 4 níveis (decidida com o responsável): **INSP** (conceito, implementação independente) · **ADAP** (deriva de artefato concreto — sujeito à licença) · **APRI** (existe no original com falha documentada que corrigimos, citando `arquivo:linha`) · **NOVO** (nenhum dos quatro entrega, citando `GA-xx`).
- Contagens apuradas por script (não estimadas): NOVO 117 (44,7%) · INSP 104 (39,7%) · APRI 37 (14,1%) · **ADAP 4 (1,5%)**. Citações de origem nas 145 linhas rastreáveis: PhaseZero 93 · RetroDECK 47 · EmuDeck 41 · LinuxToys 11 — confirmando quantitativamente a tese da ROBUSTNESS-SCORE (PZ=execução, RD=plataforma, ED=domínio, LT=forma).
- **Achado com impacto legal:** apenas 4 funções (templates de config do ED, estrutura `roms/`, banco de hashes de BIOS, perfis Steam Input) são ADAP. **258 das 262 (98,5%) independem da decisão de licença (Q2/ADR-0013)** e todas as 4 têm alternativa documentada — a licença deixa de ser bloqueador de implementação e passa a ser decisão de custo sobre 4 artefatos.
- Escopo Handheld Desktop (F-HD-01..05, ADR-0019/M10-H), acrescentado durante a implementação, teve a proveniência apurada e entrou como seção 13.5 (SZ-HD-01..12).
- Verificações de consistência executadas e verdes: cobertura de todos os `F-xx` do FEATURE-CATALOG; zero `GA-xx` órfão; zero ID `SZ-*` duplicado.

## 2026-07-18 — Sessão 31: robustez e resiliência do boot Game Mode

**Evidência física incorporada:** o responsável confirmou que a entrada SteamZero chegou
diretamente ao Big Picture após o GRUB. Esse caminho funcional foi preservado como baseline;
nenhuma instalação, regeneração de GRUB ou mutação de `/etc`, `/boot` ou `/usr` foi executada
nesta sessão.

**Boot e sessão endurecidos:** o script `/etc/grub.d` agora resolve o par kernel/initramfs
quando o `grub-mkconfig` o executa, acompanhando atualizações sem congelar o nome observado no
momento do `enable`. O preflight reproduz a precedência efetiva do SDDM, exige que a sessão
esteja no `SessionDir` visível, valida Steam/Gamescope/fallback Desktop antes de efeitos e
confirma a presença/ausência da entrada no `grub.cfg`; falha pós-geração restaura os bytes
anteriores. Symlinks quebrados ou artefatos sem marcador de ownership são recusados.

**Detecção pós-boot e backoff:** cada boot solicitado recebe marcador por `boot_id`; a sessão
registra início em estado do usuário. Três solicitações consecutivas sem início suspendem o
autologin e devolvem o host ao greeter. Selecionar a sessão manualmente ou executar `recover`
zera o backoff. Reexecução do oneshot no mesmo boot é idempotente, e falha ao gravar telemetria
é registrada sem impedir Gamescope ou o fallback Plasma.

**Instalação e apresentação:** a sessão é publicada em
`/usr/share/wayland-sessions/steamzero-gamemode.desktop`; uma cópia antiga em `/usr/local` só
é removida quando possui ownership SteamZero. Links estáveis e Desktop entry participam do
rollback do instalador. As duas strings BigLinux-específicas do dashboard foram neutralizadas
em commit próprio, mantendo a decisão por capacidade da ADR-0020.

**Provas:** teste renomeia kernel+initramfs e reexecuta o mesmo script GRUB; cenário completo
de três falhas→backoff→sessão manual→recuperação; precedência SDDM; EACCES distinto de não
configurado; rollback por `grub.cfg` inválido; ownership de symlink quebrado; falha de marcador
sem tela preta; instalação/rollback da sessão. Gate completo: Ruff, formato, fronteiras,
independência e mypy verdes; **401 passed**. Cobertura integral: **85%**, com `steam_boot` 83%
e `steam_session` 79%. Wheel `steamzero-0.1.0.dev0` construído e instalado em venv descartável,
SHA-256 `9b03b2702458a280525329d7f781696e94e81a830c3c6c0956ac092c756e8f03`; entrypoints e
`status` passaram. Probes read-only no host confirmaram `/usr/share/wayland-sessions` e a
entrada para `vmlinuz-6.18-x86_64`/UUID real.

**Commits:** `eee14ab` (backend/testes), `28e432e` (instalador/SessionDir) e `e535f3d`
(P1-1, strings isoladas). Instalação root e novo reboot físico permanecem gates externos.

## 2026-07-18 — Sessão 32: validação física Game Mode → Desktop

**Boot real concluído:** o kernel iniciou com `root=UUID=307f0ecc-3ad9-4619-893d-28454cad339a`
e `steamzero.gamemode=1`; o oneshot selecionou a sessão gerenciada no `SessionDir` efetivo do
SDDM. `gamescope-session-plus@steam.service` iniciou Gamescope e o Steam com
`-gamepadui -steamos3`. O cliente concluiu atualização/verificação e apresentou o Big Picture
no Steam Deck LCD.

**Handoff real para o Desktop:** o botão nativo registrou `target: plasma` às 20:59:41,
encerrou Steam e Gamescope de forma ordenada e iniciou os serviços Plasma às 20:59:49. O
Codex Desktop voltou na sessão KDE às 21:00:43. Para eliminar dependência indireta do seletor
da distribuição, o instalador publica `/usr/local/bin/steamos-session-select` como link estável
para o entrypoint SteamZero, sem alterar `/usr/bin` nem `/usr/lib/os-session-select`.

**Falha encontrada no teste físico:** o BigLinux manteve
`next_entry=steamzero-gamemode` no `grubenv` mesmo após consumir o boot único, por causa da
combinação com `env_block`. O preparador agora remove exclusivamente esse identificador após
observar o marcador SteamZero, recusa bloco inseguro ou limpeza ineficaz e deixa seleções
alheias intactas. A release `0.1.0a33-b075ead` foi instalada mantendo a a32 para rollback;
`prepare` removeu o valor persistente e `status` confirmou estado `ready`, zero backoff e zero
falhas consecutivas.

**Provas finais:** testes novos cobrem o seletor nativo `plasma`, publicação/ownership do link,
limpeza do `next_entry` e recusa quando a variável permanece. Ruff, formato, fronteiras,
independência e mypy verdes; **407 passed**. Commits desta validação: `d015a40` e `b075ead`.

## 2026-07-18 — Sessão 33: fechamento conservador de rollback e sessão

**Rollback completo:** uma falha durante `disable` agora restaura, além dos arquivos e do
`grub.cfg`, o estado anterior de habilitação da unidade systemd e recarrega sua definição.
O teste de regressão injeta uma saída GRUB inválida após o `disable` e prova a recuperação
dos bytes e do `systemctl enable` original.

**Contenção de sessão:** o launcher verifica `WAYLAND_DISPLAY`/`DISPLAY` antes do fallback
por dependência. Assim, Steam ou Gamescope ausente nunca provoca um segundo Plasma dentro de
uma sessão gráfica existente; o override explícito de desenvolvimento permanece disponível.

**Provas desta sessão:** `make check` verde (formato, Ruff, fronteiras, independência, mypy
estrito e **409 passed**); cobertura **85%** global, `steam_boot` **85%** e `steam_session`
**81%**. Wheel final instalado com dependências travadas, SHA-256
`91d440609762925e33577cb292a895c1cca4ab4d18c555dbde3874ed4f56c099`; CLI e os três
entrypoints de Game Mode passaram no smoke read-only. Commit: `60edfa0`. Nenhuma mutação
privilegiada, reinstalação host ou reboot físico foi executado nesta sessão.
## 2026-07-16 — Sessão 11: baseline de confiança e congelamento de features

**Preservação:** o checkout completo foi copiado do microSD para
`/home/misael/Projects/Port_Steam`, no Btrfs interno, mantendo `.git` e o `ports.py`
local. Hash do arquivo, `HEAD` e `git fsck --full --strict` foram conferidos; a cópia
do microSD permaneceu intacta como fallback. O remoto privado/off-host continua
bloqueado porque não há remoto configurado e o `gh` não está autenticado.

**Baseline histórica corrigida:** antes desta remediação, a execução real foi
**367 passed / 85%** (4251 statements, 528 misses, 938 branches). O State Store do host
também prova que não foi apenas read-only: a operação Desktop
`01KXMDC05NTYS88F5WC8XS8V3T` aplicou `docked-desktop`, capturou KScreen/KWin e chegou
a `committed`; os eventos `desktop.conflict-released` e `desktop.profile-applied`
foram persistidos. O relatório deixou de afirmar que nenhum apply ocorreu.

**Arquitetura e verdade Desktop:** `steamzero.ports` passou a ser a única definição de
seis contratos/DTOs, é empacotado e mantém os imports antigos por reexportação. O status
Desktop agora separa `recommendedProfile`, `desiredProfile`, `appliedProfile` e
`observedProfile`; `effectiveProfile` é somente alias temporário do observado. Contexto
ou desejo divergente retorna `stale`, falha/indisponibilidade de observação retorna
`degraded`, e um teste reproduz dock→undock após apply real do domínio.

**Versão e proveniência:** a baseline passou de `0.1.0.dev0` para `0.1.0a1`, com uma
única fonte de versão no pacote. Novas instalações exigem manifesto v2, SHA completo e
ID canônico `<versão>-<commit[0:12]>`. A auditoria byte a byte das releases antigas foi
registrada em `RELEASE-LEDGER.md`; releases intermediárias sem árvore Git coincidente
foram classificadas como não reproduzíveis em vez de receberem um commit inventado.

**CI/supply chain:** backend Hatchling e todas as Actions foram pinados; a matriz cobre
Python 3.11/3.12/3.14, wheel sem editable, smoke em Ubuntu/Arch/Manjaro por digest,
cobertura publicada, auditoria `pip-audit` pelo feed OSV, SBOM CycloneDX, checksums e
proveniência do wheel. A proveniência recusa árvore rastreada suja e commit diferente do
`HEAD`. Localmente, o wheel `0.1.0a1` foi construído, contém `steamzero.ports`, instalou
em venv vazio, passou `pip check`/versão/doctor e a auditoria OSV não encontrou
vulnerabilidades conhecidas. A execução no provedor continua pendente do remoto.

**Gate pós-remediação local:** **372 passed / 85%**, zero falhas/skips/xfails; Ruff,
fronteiras, independência e mypy verdes. M10 em VM, daemon/reconciliador, transporte
polkit e matriz física do Deck não foram executados e permanecem bloqueando UI/release
em `OPERATIONAL-TRUST-GATES.md`.

## 2026-07-16 — Sessão 12: Steam Gameplay no padrão Prontidão do jogo

**Direção visual escolhida:** o terceiro mockup passou a ser a referência da central
Desktop. A primeira cobertura foi aplicada à área Steam com hierarquia jogo → prontidão
→ ajustes essenciais → impacto → confirmação, preservando tema azul-preto, foco ciano,
estados semânticos, sidebar e footer por controle.

**Contrato real e honesto:** `SteamGameplayController` descobre manifests e capas locais,
observa Steam/Gamescope/Feral GameMode/MangoHud/vkBasalt, memória, tela e limites do Deck.
Perfis usam token, expiração e fingerprint do ambiente; mudança da biblioteca gera
`E-TX-STALE-PLAN`, owner concorrente é rechecado no apply e dependência ausente bloqueia
em vez de simular sucesso. A persistência permanece `desired`, sem afirmar que TDP/GPU
foram aplicados antes do executor M11.

**UI e gate:** perfis/FPS/MangoHud usam escolhas segmentadas, TDP usa slider contínuo e
upscaling usa listbox. A revisão mostra alterações, bloqueios e rollback; drivers ausentes
encaminham apenas a **Abrir Sistema**. A suíte chegou a **377 testes**; Ruff, mypy,
`qmllint`, fronteiras e independência passaram. A captura Qt/QML em 1600×1000 foi
comparada ao mockup selecionado.

**Versão:** a árvore passa a `0.1.0a2`; nenhum artefato desta mudança reutiliza a versão
`0.1.0a1` da baseline.

## 2026-07-17 — Sessão 13: LSFG e Steam Input por jogo

**Perfis por jogo:** o contrato de gameplay passou a aceitar geração de quadros
Desligada/LSFG 2×/3×/4× e layouts Steam Input allowlisted. A camada LSFG é observada pelo
manifesto Vulkan em escopos user/local/system; ausência bloqueia o plano e encaminha para Sistema, sem
download ou aplicação fictícia. Layouts abrem somente `steam://controllerconfig/<appid>`
com AppID numérico validado.

**Persistência e resiliência:** desempenho continua em `kind=performance`; controles são
gravados em `kind=controls`, com owner `steam-input`. Os dois perfis usam a nova operação
atômica `StateStore.save_profiles`: falha em qualquer linha reverte o conjunto inteiro.
O estado permanece honestamente `desired` até o launcher/reconciliador M11 aplicar e observar.

**Experiência:** a tela escolhida ganhou áreas Desempenho e LSFG/Controles sem mudar a
hierarquia jogo → escopo → prontidão → revisão. No breakpoint compacto, Ambiente e capacidade
ficam disponíveis em diálogo em vez de esmagar os ajustes; a ação de revisão permanece fixa.

**Gate:** **382 passed / 85%** (4646 statements, 560 misses, 1092 branches); Ruff,
mypy estrito, fronteiras, independência, `qmllint` e comparação visual passaram.

**Versão:** a árvore passa a `0.1.0a3`; a instalação automática pinada do LSFG-VK permanece
como próxima entrega de Sistema porque exige aquisição verificada, staging em streaming e
rollback de arquivos sob `~/.local`, sem embutir um artefato de ~74 MB no plano transacional.

## 2026-07-17 — Sessão 14: instalação pinada e reversível do LSFG-VK

**Supply chain:** Sistema passou a adquirir exclusivamente `lsfg-vk_noui.zip` da release
oficial 1.0.0, fixada por URL e SHA-256
`af5ee1626d9543349245520689da107c3ebc5ef3755086441fbb854173b8e096`. A biblioteca
extraída também é validada pelo hash
`de4954bcce6904b62b6c48f1525c7fd78b4c2d7f9a959edf621528d9363ebbfd`. O ZIP aceita
somente as duas entradas esperadas, rejeita symlinks/excesso de tamanho e normaliza o
manifesto Vulkan para o caminho user-scoped absoluto.

**Propriedade e transação:** o SteamZero exige a instalação real do Lossless Scaling
(App 993090 e `Lossless.dll`) antes de preparar a camada; não baixa nem redistribui o
componente proprietário. Biblioteca e manifesto são gravados sob `~/.local` pelo núcleo
transacional com plano, confirmToken, verificação pós-apply e rollback G-FULL. Nenhuma
escrita global, `sudo`, `pacman` ou dependência PhaseZero foi introduzida.

**Experiência e verdade:** Sistema mostra ausente/verificado/reparo necessário, a fonte,
a dependência proprietária e as ações Preparar/Reparar/Desfazer. Sem a dependência, abre
somente a biblioteca Steam. A detecção no host real retornou `missing`, dependência ausente
e `installable=false`; portanto nenhuma mutação foi tentada. A aplicação por jogo continua
honestamente `desired` até o launcher/reconciliador M11.

**Gate:** **387 passed / 85%** (4839 statements, 601 misses, 1150 branches); Ruff,
mypy estrito, fronteiras, independência e `qmllint` verdes. A captura
`/tmp/steamzero-system-lsfg.png` não apresentou diferenças P0/P1/P2.

**Versão:** a árvore passa a `0.1.0a4`; nenhum artefato reutiliza a versão anterior.

## 2026-07-17 — Sessão 15: launcher Steam aplicado e observável

**Execução real:** entrou o entry point `steamzero-launch`, destinado às Launch Options
`steamzero-launch --appid <id> -- %command%`. A linha é interpretada sem shell e o comando
recebido da Steam permanece uma lista de argumentos. A política é resolvida por prioridade
por jogo → contexto portátil/dock → global. Gamescope limita FPS e aplica FSR quando pedido;
GameMode usa `gamemoderun`; MangoHud usa `mangohud` fora do Gamescope e `--mangoapp` dentro
dele; LSFG usa somente as variáveis oficiais, a camada observada e o `Lossless.dll` possuído.

**Verdade e lifecycle:** cada execução registra launching→active→exited/failed no State
Store. `observed` exige PID vivo, marcadores de ambiente do SteamZero e digest do perfil
atual; PID reutilizado não produz falso positivo. Mudança de perfil durante a execução vira
`stale` sem matar o jogo. Wrapper interrompido com PID morto exige recuperação explícita.
Sinais TERM/INT são encaminhados ao filho e nenhuma linha de comando ou ambiente é gravada
no estado. TDP, clock de GPU e FSR2 interno aparecem como adiados, nunca aplicados.

**Schema:** a migração v3 corrige uma inconformidade anterior: a UI aceitava os escopos
Global/Portátil/Dock, mas o CHECK SQLite v2 os rejeitava. A migração preserva perfis antigos,
adiciona os três escopos e o tipo `performance-runtime`.

**Experiência:** a página Prontidão do jogo mostra estado do lançamento, Launch Option
selecionável e recuperação contextual. A captura `/tmp/steamzero-launcher-runtime.png`
confirma hierarquia e legibilidade no viewport lógico 1600×1000. A edição automática do
`localconfig.vdf` permanece bloqueada até existir parser preservador, Steam parada, plano
confirmado e rollback byte-idêntico.

**Gate:** **411 passed / 85%**; launcher a 94%; Ruff, mypy estrito, fronteiras,
independência e `qmllint` verdes. Nenhum jogo comercial foi iniciado no host nesta sessão.

**Versão:** a árvore passa a `0.1.0a5`; nenhum artefato reutiliza `0.1.0a4`.

## 2026-07-17 — Sessão 16: Launch Options automáticas e reversíveis

**Edição preservadora:** entrou um parser estrutural de Valve KeyValues que trabalha com
offsets dos bytes, preserva comentários, ordem, espaçamento e conteúdo não relacionado.
Ele altera somente `apps/<appid>/LaunchOptions`, rejeita AppID/folha duplicados, blocos
ambíguos, symlinks e arquivos acima de 16 MiB. Com múltiplas contas, `MostRecent=1`
seleciona uma única conta sem expor identificadores na API ou na UI.

**Transação e concorrência:** Steam aberta bloqueia plan/apply/rollback. O plano vincula
AppID, conta, raiz, alvo único, fingerprint e conteúdo esperado; mudança concorrente ou
plano de outro arquivo falha antes da mutação. A aplicação exige `confirmToken`, verifica
o valor observado e registra rollback G-FULL byte-idêntico. A configuração é uma ação
explícita separada do perfil e a substituição de Launch Options existente é revisada.

**Experiência e host:** a faixa Lançamento gerenciado ganhou status e ações Configurar/
Desfazer. O diálogo informa Steam fechada, substituição e garantia. O QA 1280×800 com
escala KDE 1,35 encontrou e corrigiu truncamento do rótulo; a captura final é
`/tmp/steamzero-launch-options-auto.png`. O host retornou `missing`, Steam fechada e
nenhuma mutação foi realizada.

**Gate:** **426 passed / 85%** (5527 statements, 673 misses, 1386 branches); módulo de
Launch Options a 80%. Ruff, mypy estrito, fronteiras, independência e `qmllint` verdes.

**Versão:** a árvore passa a `0.1.0a6`; nenhum artefato reutiliza `0.1.0a5`.

## 2026-07-17 — Sessão 17: lifecycle Steam com fonte de verdade única

**Persistência:** a migração v4 adiciona `game_session` com os estados canônicos F-SD-01,
PID, digest, timestamps, terminal e metadados públicos mínimos. Um índice parcial único
por owner impede atomicamente dois jogos gerenciados em estados ativos. O domínio de
sessão e `steamzero-launch` agora compartilham vocabulário, transições e owner.

**Resiliência:** o wrapper registra launching antes do spawn, running com o PID observado,
closing quando recebeu TERM/INT e closed/failed como terminal. Wrapper morto deixa sessão
ativa recuperável; outro launch recebe E-TX-LOCKED. Recovery explícito usa
E-SESSION-INTERRUPTED. Falha de spawn/runtime usa E-SESSION-LAUNCH-FAILED, nunca nome cru
de exceção. Estados legados active/exited/interrupted continuam legíveis.

**Contrato:** eventos de sessão passaram de `job.state` indevido para `session.state`,
com `sessionId`/`gameId` no schema. `steamzero session status|recover --game-id APPID`
expõe o lifecycle sem ampliar a UI Game Mode, preservando o congelamento de G8. Comando e
ambiente do jogo não entram na tabela, evento ou envelope.

**Host:** inspeção SQLite em `mode=ro` encontrou schema v3, sem `game_session` e sem
runtime legado ativo. A migração v4 não foi aplicada ao host nesta sessão.

**Gate:** **434 passed / 85%** (5688 statements, 691 misses, 1430 branches); conjunto
state/session/launcher a 93%. Ruff, mypy estrito, fronteiras e independência verdes.

**Versão:** a árvore passa a `0.1.0a7`; nenhum artefato reutiliza `0.1.0a6`.

## 2026-07-17 — Sessão 18: plano de controle e gestão Steam resiliente

**Daemon/IPC:** entrou `steamzero-core`, user-scoped e socket-activated, com JSON-RPC 2.0
em socket UNIX 0600, diretório 0700, `SO_PEERCRED`, limite de mensagem/conexão/mutações e
dispatch por allowlist. A CLI prefere IPC e só cai para in-process antes de conectar; uma
resposta ambígua nunca repete mutação. O instalador publica units systemd user e valida os
novos entry points sem abrir TCP ou depender de PhaseZero.

**Gestão Steam:** a área Biblioteca ganhou limpeza real de shader cache com frase
destrutiva, fingerprint, rename atômico e recovery pós-crash. Compatdata, saves, jogos,
Workshop e downloads são exclusões invariantes. Pacotes locais de grid/portrait/hero/logo
passam por magic bytes, conta explícita, transação G-FULL e rollback byte-idêntico.

**Sessão:** `steamzero-gamemode-session` fornece uma entrada SDDM própria, argv fechado de
Gamescope/Steam e fallback automático para Plasma. O host revelou que a única sessão
console existente apontava para `/usr/local/lib/phasezero`; a nova sessão não usa esse
arquivo. Boot direto continua protegido porque GRUB não seleciona sessões gráficas e o
protocolo snapshot+TTY+console remoto ainda não foi cumprido.

**Versão:** a árvore passa a `0.1.0a8`; manifesto host v3 associa daemon e Session Manager
ao mesmo wheel/commit.

**Gate local:** **475 passed / 85%** (6582 statements, 806 misses, 1734 branches);
Ruff, formato, mypy estrito, fronteiras, independência e `qmllint` verdes. A evidência da
instalação no host é associada ao commit exato no fechamento operacional desta sessão.

## 2026-07-17 — Sessão 19: fechamento Steam no host real

**Releases honestas:** `0.1.0a8` foi instalada a partir de
`d2bf3819d12d16f5b5a682db06af3e63c091efcd`, mas o smoke encontrou o entry point da
sessão somente dentro da release. O instalador passou a publicar e restaurar
atomicamente `/usr/local/bin/steamzero-gamemode-session`, recusando arquivo alheio; a
correção foi instalada como `0.1.0a9-e38b3762f144`. Ela não reempacotou `a8`.

**Falha adversa corrigida:** o smoke Qt offscreen do `a9` reproduziu timeout de
`kscreen-doctor -o` e a exceção derrubava a UI. O runner KDE agora converte timeout em
`CommandResult(124)` e falha de execução em estado degradável, preservando saída parcial.
O teste de regressão e o smoke pela fonte passaram; a correção foi lançada como
`0.1.0a10-1c4527ae3961`, commit
`1c4527ae39612062742b318b102c33c8b311d918`, wheel SHA-256
`a8a77ab25fcd3267d9fc2f756a56d63ae3600c9d68e857daf84d462d2b465d91`.

**Host real:** `steamzero doctor` retornou `ok`, schema SQLite v4, integridade `ok` e
zero operações pendentes. Socket e diretório IPC ficaram `0600/0700`; daemon e socket
user-scoped estão ativos. O Session Manager observou Steam, Gamescope e fallback Plasma,
declarou runtime independente e `legacyRuntimeRequired=false`. Nenhum arquivo da sessão
contém PhaseZero; o watcher legado está `inactive/disabled`. O smoke da UI instalada
permaneceu ativo por 8 segundos e encerrou somente pelo timeout externo esperado (124).

**Steam e limites reais:** a Steam estava aberta. Inventários de manutenção e mídia
funcionaram em leitura; a tentativa de planejar limpeza foi corretamente recusada com
`E-TX-LOCKED`. Nenhum cache, arte, jogo, display, TDP, sessão atual ou GRUB foi mutado.
Boot direto permanece `gated` até snapshot restaurável, TTY e console remoto comprovados;
isso é uma garantia de recuperação, não uma função simulada.

**Gate final:** **477 passed**; cobertura combinada exata **84,84%**, exibida como
**85%** (6594 statements, 805 misses, 1736 branches). Ruff, formato, mypy estrito,
fronteiras, independência, `qmllint`, wheel provenance, manifesto host v3,
`systemd-analyze --user verify` e status administrativo passaram.

## 2026-07-17 — Sessão 20: roadmap Steam R1 e observação Linux real

**Roadmap normativo:** `STEAM-SESSION-ROADMAP.md` filtra o catálogo para lifecycle,
suspend, dock/display, microSD, offline, compatibilidade, desempenho, privilégio,
Steam Input, frontends, Game Mode UI e validação física. A ordem R1–R10 impede que UI
ou boot automático avancem antes de estado aplicado/observado e recovery comprovado.

**R1:** entrou `session environment`, disponível por CLI e JSON-RPC allowlisted. O adapter
combina DMI com painel interno, observa sessão gráfica, bateria/AC, rede, conectores DRM e
volumes de mountinfo associados a `/dev/disk/by-uuid`. Toda a superfície é read-only e
tolera fontes ausentes. O contrato `session-environment-v1` congela a saída v1.

**Correção descoberta no host:** o leitor microSD do Deck expõe `mmcblk0` com
`removable=0`; a primeira sonda classificou `/mnt/sdcard` como interno. A regra passou a
usar a identidade MMC, mantendo NVMe interno e USB separados. A repetição observou o UUID
`58D14C064972BE55` como `microsd`, sem montar ou escrever no volume.

**Host:** release `0.1.0a11-11e57d269fb2`, commit
`11e57d269fb205f5c0258888e1afd56b826ca96c`, wheel SHA-256
`a8caada99aa4049f56ae05a680d67f698aae94fd4f30898797e8a709f7f64641`.
O daemon instalado observou Deck LCD com quatro evidências, KDE/Wayland, bateria real,
rede, eDP-1, estado vivo do DP-1, Btrfs interno, EFI e microSD. Doctor, manifesto v3,
systemd user e permissões IPC continuaram saudáveis.

**Gate:** **482 passed / 85%** (6845 statements, 845 misses, 1804 branches); Ruff,
formato, mypy, fronteiras, independência, `qmllint`, provenance e smokes host verdes.

## 2026-07-17 — Sessão 21: reconciliador persistente R2 no host

**R2 incremental:** o daemon user-scoped passou a amostrar o ambiente real a cada cinco
segundos. Um digest material considera dispositivo, sessão, AC, conectividade, topologia
de displays e volumes; timestamp, percentual de bateria e espaço livre não criam ruído.
Snapshot e evento `session.environment` são gravados atomicamente no SQLite v5. A CLI e
o daemon usam a mesma composição Linux, sem importar ou executar PhaseZero.

**Host:** release `0.1.0a12-105cce61a9a3`, commit
`105cce61a9a3d471429f3af520537f29f8025f72`, wheel SHA-256
`72130dd966690ec1e87c1863d9ed1b2a9b35119df0c451d2c7ac9221cdf0a1cd`. O doctor
instalado retornou schema v5, integridade `ok` e zero operações pendentes. Daemon e
socket systemd user ficaram ativos; o snapshot persistido observou Deck LCD, KDE
Wayland, eDP, DP desconectado, Btrfs, EFI e microSD. Após múltiplos ciclos estáveis, a
contagem permaneceu em um único evento, comprovando a deduplicação no processo real.

**Gate:** **484 passed**. O valor local de cobertura então reportado como 82,88% foi
posteriormente invalidado: `make check` não renovava `.coverage` e podia ler dados de
outro processo. Ruff, formato, mypy, fronteiras, independência, `qmllint`, wheel
provenance, manifesto host e smokes instalados passaram.

## 2026-07-17 — Sessão 22: retomada R2 e fronteira Polkit R3 mínima

**Suspend/resume honesto:** `0.1.0a13-3730f7322c80` adicionou a detecção pós-resume
pela diferença `CLOCK_BOOTTIME`−`CLOCK_MONOTONIC`, sem alegar um hook pré-suspend.
O host confirmou ambos os relógios e nenhum falso `session.resume` apareceu em ciclos
estáveis. Dock→undock e microSD remove→reinsert ganharam cenários determinísticos; a
execução mutável em VM e o flush pré-suspend continuam pendentes pelos gates R2/R3.

**Polkit mínimo real:** `0.1.0a14-60712ad3972c`, commit
`60712ad3972cca6b23ecfb19233f7de1076bd471`, wheel SHA-256
`1231695893f075be48f8d7b70c0424d58ae61b12f1dd14a570b7f06fd20d60fe`. O instalador
publicou atomicamente `/usr/local/libexec/steamzero-admin` e a policy
`io.github.misael-art.steamzero.admin`; rollback para release sem a capability remove
ambos. `pkexec ... --health` executou como UID 0 e retornou protocolo 1,
`mutationsEnabled=false`. Execução direta sem Polkit retornou `E-PRIV-DENIED`.

**Auditoria e host:** `/var/log/steamzero-admin.log` ficou `root:root 0600` e registrou
somente action, caller UID, resultado e timestamp. Doctor instalado permaneceu `ok`,
SQLite v5 íntegro e sem operações pendentes. Nenhum TDP, clock, sysctl, mount, unit,
display, sessão padrão ou GRUB foi alterado.

**Gate:** **488 passed**. O valor local de 82,14% também pertencia à medição não renovada
descrita na sessão seguinte e não é uma baseline válida. Ruff, formato, mypy, fronteiras,
independência, `qmllint` e proveniência do wheel passaram.

## 2026-07-17 — Sessão 23: transporte Polkit, baseline honesta e capabilities AMDGPU

**Baseline corrigida:** `make check` agora apaga dados anteriores, executa a suíte com
`pytest-cov` e impõe `fail_under=85`. A medição autoritativa de `0.1.0a17` é **503
passed / 85,09%** (7139 statements, 859 misses, 1874 branches). O cliente Polkit ficou
com 93%. CI e gate local passam a usar a mesma origem de verdade.

**Falha host e release sucessiva:** `0.1.0a15-ba87f9ee5c44` conectou `admin.health` à
CLI/RPC, mas o smoke mostrou que `pkexec` originado pelo daemon user-scoped era recusado,
embora o mesmo fluxo interativo funcionasse no terminal. Nenhuma mutação ocorreu. A
correção saiu como `0.1.0a16-592dba1628a4`: a ação interativa não é anunciada nas 17
capabilities RPC e a CLI fala diretamente com o Polkit. Daemon ativo e CLI normal então
retornaram health `ok` como UID 0.

**Hardware observado:** `0.1.0a17-76d764ad773e`, commit
`76d764ad773e95c2485d5a88d853513b723c4caa`, wheel SHA-256
`b511b02df87e75bfb66f04b2d47b99c8e102dbded23a5ab6b6510891071a8376`. O helper leu
as interfaces reais AMDGPU: `slowPPT` e `fastPPT` convergidos em 15 W, default 15 W,
range seguro observado 3–29 W e SCLK 200–1600 MHz. `mutationsEnabled=false` e
`manualWriteEnabled=false`; nenhum valor sysfs foi escrito.

**Host final:** doctor `ok`, SQLite v5 íntegro, zero operações pendentes, daemon ativo,
manifesto associado ao commit exato e audit root preservado. TDP, GPU, display, mounts,
sessão padrão e GRUB permaneceram inalterados.

## 2026-07-17 — Sessão 24: motor TDP G-STATE atrás do gate

**Transação privilegiada interna:** `set-tdp` agora possui um motor fechado que descobre
somente `amdgpu slowPPT/fastPPT`, restringe o pedido ao máximo observado, grava journal
0600 antes da primeira escrita, aplica as duas rails, verifica e restaura os valores
anteriores em falha. `rollback-tdp` aceita somente ULID associado; `recover-tdp` restaura
journals `pending`/`rollback-failed`. O transporte público continua health-only e declara
`mutationsEnabled=false`.

**Failure injection:** uma prova interrompe o processo imediatamente após escrever
`slowPPT`. O novo apply foi bloqueado por `E-TX-LOCKED`; recovery restaurou ambas as rails
e uma segunda recuperação foi `noop`. Também foram cobertos verify divergente, rollback
idempotente, journal inválido, interface ausente e valor acima da capability.

**Wheel e host:** release `0.1.0a18-1d76d7986330`, commit
`1d76d7986330053240c9001d64468d112303be88`, wheel SHA-256
`618718da9c919471a9c5583ba4c449e67acaf6eb35001045d3719d7256dd98b0`. O motor do wheel
instalado foi executado numa cópia descartável das interfaces reais: 15 W→10 W nas duas
rails→rollback para 15 W; diretório 0700 e journal 0600. `/sys` real não foi escrito.
Doctor continuou `ok`, SQLite v5 íntegro, zero pendências e daemon ativo.

**Gate:** **510 passed / 85,03%** (7320 statements, 886 misses, 1924 branches), Ruff,
formato, mypy, fronteiras, independência, `qmllint` e proveniência verdes. O agente
Polkit permanece ativo a pedido do responsável; a duração da autorização já concedida
continua controlada pela policy do sistema e não é ampliada artificialmente.

## 2026-07-17 — Sessão 25: motor GPU SCLK G-STATE atrás do gate

**Transação AMDGPU interna:** `set-gpu-clock` ganhou motor fechado que descobre somente
`cardN/device/pp_od_clk_voltage` com `OD_SCLK`/`OD_RANGE` válido e o performance level
associado. O snapshot persiste min/max SCLK e modo anterior em journal root `0600` antes
da primeira escrita. O apply usa a sequência documentada pelo kernel — `manual`, `s 0`,
`s 1`, `c` —, verifica os dois clocks e o modo, e restaura tudo em falha. As ações
`rollback-gpu-clock` e `recover-gpu-clock` aceitam somente ULID/nenhum parâmetro.

**Failure injection e host seguro:** as provas interrompem o motor logo após entrar em
modo manual, bloqueiam novo apply com `E-TX-LOCKED` e recuperam o snapshot. Também cobrem
commit recusado, verify divergente, rollback idempotente, journal/snapshot inválidos,
capability malformada e clock fora do range observado. O wheel instalado foi executado
somente numa interface descartável: 200–1600 MHz/auto → 800–800 MHz/manual → rollback
200–1600 MHz/auto; diretório 0700, journal 0600. O `/sys` real não foi escrito.

**Release e operação:** `0.1.0a19-364185ac7d87`, commit
`364185ac7d8750a1a7a8f920baccb8893205f94c`, wheel SHA-256
`e58bded9177b60ae20cd453220275008a80cbf2f8dcdbca38140ba6c94a6596c`.
O primeiro smoke revelou o daemon antigo ainda carregado; `systemctl --user daemon-reload`
e a reativação do socket fizeram doctor/daemon convergir para `a19`. Doctor ficou `ok`,
SQLite v5 íntegro, zero pendências, helper UID 0 observou SCLK real 200–1600 MHz e TDP
15 W, mas declarou `mutationsEnabled=false` e `manualWriteEnabled=false`. O agente Polkit
oficial permanece ativo conforme solicitado.

**Gate:** **520 passed / 85,08%**, Ruff, formato, mypy estrito, fronteiras,
independência, `qmllint`, wheel e manifesto host verdes. A certificação mutável em VM
AMDGPU continua pendente; este incremento não autoriza clock real no host principal.

## 2026-07-17 — Sessão 26: lock interprocesso e motor sysctl gated

**Concorrência real:** os motores TDP, GPU e sysctl passaram a adquirir um lock
não bloqueante antes de consultar/criar journals. O arquivo fica fora do diretório de
journals, usa modo 0600, `O_NOFOLLOW` e `flock`; tentativa simultânea ou lock symlink
é recusado com `E-TX-LOCKED`. Isso fecha a janela em que dois processos poderiam ver
ausência de pending ao mesmo tempo.

**Sysctl transacional:** `write-sysctl` agora resolve somente paths compilados para
`vm.swappiness` e `vm.compaction_proactiveness`, valida os ranges já allowlisted,
persiste snapshot antes da escrita, verifica o valor observado e restaura em falha.
`rollback-sysctl` aceita ULID e `recover-sysctl` nenhum parâmetro. Failure injection
cobre queda após escrita, verify divergente, rollback-failed, recovery, interface ausente,
snapshot inválido, path fora da allowlist e contenção.

**Wheel e host:** release `0.1.0a20-ced9e2157548`, commit
`ced9e21575485afd337eb70f5ffae9dbcb08b11f`, wheel SHA-256
`68344159cc2258151c6d6e74e691445cd5f22f1741c89e2cc2b87fb9be1704f0`.
O wheel instalado executou `swappiness` 60→10→60 numa árvore `/proc/sys` descartável,
confirmou lock concorrente `E-TX-LOCKED`, state 0700 e journal 0600. O host real foi
somente lido e permaneceu em `swappiness=30` e `compaction_proactiveness=20`.

Doctor/daemon convergiram para `a20`, SQLite v5 ficou íntegro e sem pendências. O agente
Polkit oficial permaneceu ativo; a autorização temporária expirou antes do último health
administrativo e foi honestamente registrada como `E-PRIV-DENIED`. Isso não desativa o
agente nem implica falha do helper, e nenhuma mutação ocorreu.

**Gate:** **530 passed / 85,14%** (7666 statements, 918 misses, 2016 branches), Ruff,
formato, mypy estrito, fronteiras, independência, `qmllint`, wheel e manifesto v3 verdes.
O transporte mutável continua fechado até a certificação em VM descartável.

## 2026-07-17 — Sessão 27: identidade de processo no lifecycle Steam

**Falha corrigida:** um PID ativo, porém reutilizado por processo alheio, fazia a sessão
ficar `stale` sem oferecer recovery e mantinha o índice exclusivo do owner bloqueado.
O launcher agora confirma `steamzero-launch --appid <jogo>` durante `launching` e exige
`STEAMZERO_GAME_ID` + digest exatos no ambiente do filho em `running`, `suspending`,
`suspended`, `resuming` e `closing`. Divergência produz `recoveryRequired=true`; recovery
altera somente o State Store e nunca sinaliza o PID não reconhecido.

**Wheel e host:** release `0.1.0a21-7e1136cc80ae`, commit
`7e1136cc80aecf2d5e5c1e5be4c931c25f9c5218`, wheel SHA-256
`8f53b5429726f99231f197ff35c0a6286ec454322e923c6eb850ab54c7a6f2b4`.
O wheel instalado lançou `/usr/bin/true` pelo adapter real e observou
`launching→running→closed`, exit 0 e PID final nulo. Uma sessão sintética apontando para
o PID vivo do smoke foi reconhecida como reutilização, recuperada, e o processo continuou
vivo. Um wrapper executável real nomeado `steamzero-launch --appid 10` foi identificado.

Doctor/daemon convergiram para `a21`, SQLite v5 permaneceu íntegro, zero pendências,
socket, service e agente Polkit ficaram ativos. A tentativa posterior de repetir status
root não recebeu nova autorização; o manifesto v3 instalado foi verificado em leitura e
nenhuma mutação privilegiada foi executada nessa etapa.

**Gate:** **541 passed / 85,21%** (7681 statements, 917 misses, 2020 branches), Ruff,
formato, mypy estrito, fronteiras, independência, `qmllint`, wheel e manifesto verdes.

## 2026-07-17 — Sessão 28: boot Game Mode próprio e Área Modo Desktop

**Causa reproduzida:** a entrada GRUB legada entregava corretamente
`phasezero.steamos=1` ao kernel e o SDDM selecionava `phasezero-steamos.desktop`, mas o
launcher exigia `gamescope-session-plus`, ausente no host, e executava
`startkde-biglinux wayland`. O desvio ocorria depois do GRUB/SDDM e explicava o retorno
silencioso ao KDE.

**Session Manager independente:** `steamzero-gamemode-boot` passou a gerar entrada
**SteamZero Game Mode**, reconciliar o SDDM antes do display manager e selecionar somente
`steamzero-gamemode.desktop`. `Relogin=false`, sessão ausente remove o autologin e retorna
ao greeter; Steam/Gamescope falhos retornam ao Plasma. A ativação é root-only, atômica,
regenera o GRUB, preserva o `grub.cfg` durante a transação e possui `disable` reversível.
O marcador antigo é aceito apenas para migração; não há import, binário ou serviço
PhaseZero requerido.

**Host agnóstico:** o novo `steamzero-host-prepare` detecta pacman, apt ou dnf, publica
plano fixo e exige confirmação literal antes de instalar QEMU/libvirt/virt-install,
UEFI, TPM e rede. A verdade distingue laboratório VM com `virtio-gpu` de hardware Valve:
clean install/update/rollback pertencem à VM; AMDGPU, TDP, clock, KScreen, dock e suspend
pertencem ao Deck físico com snapshot e recuperação.

**UI:** a área Steam agora inclui **Modo Desktop** no mesmo seletor contextual de
Desempenho, Controles e Biblioteca. A tela conserva a direção visual Prontidão e agrupa
perfil recomendado/desejado/aplicado/observado, entrada/touch/teclado, tela/dock/hotplug,
sessão/boot, conflito e recovery. Ações chamam os endpoints reais de plano, apply, reset,
conflito, recuperação e teclado; componentes de Sistema direcionam para Sistema.

**Gate pré-host:** **564 passed / 85,34%** (8025 statements, 945 misses, 2134 branches),
Ruff, formato, mypy estrito, fronteiras, independência, `qmllint` e documentação verdes.
Instalação, ativação e evidência pós-reboot permanecem fora deste registro até a release
imutável ser construída a partir do commit limpo.

## 2026-07-17 — Sessão 29: instalação real, KVM/libvirt e boot Game Mode ativado

**Releases sucessivas e honestas:** o primeiro wheel instalável foi
`0.1.0a22-7c1084e35707`. O smoke standalone mostrou que a classificação do Deck dependia
do contexto fornecido pela UI; `a23-f24b59e2c860` passou a ler DMI diretamente. A
instalação real dos pacotes revelou uma corrida entre a consulta e a ativação da rede
libvirt; `a24-e5dc9b35e9d4` adicionou rechecagem. O host então expôs alinhamento/localização
do texto do `virsh`; `a25-2b9f65e54a4b` substituiu o parser por `net-list --name`. Nenhum
wheel foi republicado sob a mesma versão; commits e hashes completos estão no release
ledger.

**Laboratório agnóstico no Deck real:** a release `a25` instalou e verificou
QEMU 11.0.2, libvirt 12.5, virt-install 5.1.0, OVMF, swtpm 0.10.1, dnsmasq e backend nft.
`libvirtd.service` ficou ativo/habilitado, a rede `default` ativa, persistente e em
autostart, `misael` pertence ao grupo `libvirt` e `domcapabilities --virttype kvm`
confirmou KVM x86_64, EFI/OVMF, virtio, TPM emulado e CPU AMD host-passthrough. O snapshot
classificou `officialDeck=true`, `/dev/kvm` acessível, laboratório VM `ready` e laboratório
físico AMDGPU/TDP/KScreen `ready`, sem alegar que virtio-gpu equivale ao hardware Valve.

**Boot independente ativado:** `steamzero-gamemode-boot enable` gerou a entrada
**SteamZero Game Mode** com `steamzero.gamemode=1`, publicou o unit oneshot antes do
display manager e selecionou `steamzero-gamemode.desktop` no SDDM com `Relogin=false`.
O unit `phasezero-steamos-boot-prepare.service` ficou desabilitado e a configuração SDDM
legada foi removida. O launcher instalado confirmou Steam, Gamescope, runtime independente
e fallback Plasma. O host não foi reiniciado automaticamente; observar Big Picture após
o próximo reboot continua um gate físico explícito.

**Estado operacional:** o manifesto v4 ativo vincula `0.1.0a25` ao commit
`2b9f65e54a4b2314cc293c4a20e389f37c40a6f5` e wheel SHA-256
`fc88b41a9d08996321da8ada10c48f0a694dc6cd52e807ab00fdecb6d21aff47`.
Doctor retornou `ok`, SQLite v5 íntegro, zero operações pendentes, socket/core ativos e
agente Polkit oficial ativo. O Desktop reportou honestamente `degraded`: recomendado,
desejado e aplicado estão em `docked-desktop`, enquanto a observação atual ainda é
`handheld-desktop`; nenhuma aplicação destrutiva foi feita para mascarar essa divergência.

**Gate final:** **567 passed / 85,27%** (8041 statements, 955 misses, 2138 branches),
Ruff, formato, mypy estrito, fronteiras, independência e `qmllint` verdes. A UI recebeu a
Área **Modo Desktop** usando os componentes e tokens existentes; a revisão visual e o
focus graph completos permanecem, conforme decisão do responsável, para quando todas as
funções estiverem coesas.

## 2026-07-18 — Sessão 30: incidente de boot diagnosticado, correções e desacoplamento PhaseZero

**Incidente real diagnosticado:** as duas entradas GRUB ("PhaseZero SteamOS Console" e
"SteamZero Game Mode") falhavam em chegar ao Big Picture. Journal comprovou a causa
primária: `sddm: Unable to find autologin session entry "steamzero-gamemode.desktop"` —
a sessão vivia em `/usr/local/share/wayland-sessions`, mas o `/etc/sddm.conf` do
BigLinux (lido por último na precedência) restringe `SessionDir=/usr/share/wayland-sessions`.
O boot caía no greeter; o login manual entrava na sessão legada, que degradava para
Plasma por falta de `gamescope-session-plus`. Causa secundária: `status()` sem
privilégio engolia `EACCES` e reportava "ativação não executada" com boot direto
instalado — telemetria falsa durante todo o incidente.

**ADR-0020 (proposto):** arquitetura multi-distro para Arch e derivadas —
`DisplayManagerPort` (SessionDir efetivo como pré-condição de autologin) e
`BootEntryPort` (GRUB/systemd-boot/rEFInd/Limine + one-shot), preflight no `enable`,
verificação pós-boot com backoff e matriz de VMs no laboratório KVM. Capacidade
detectada, nunca nome de distro; artefato próprio muda de lugar, config alheia
não é editada.

**Correções (release `a26`, commit `ca88ada`):** sessão movida para
`/usr/share/wayland-sessions` (instalador remove a cópia legada gerenciada ao
sincronizar) e `status()` com estado `unknown` + `permissionDenied=true` sob EACCES.
Verificado no host: sem privilégio `state=unknown/permissionDenied=true`; com
privilégio `state=ready/configured=true`.

**Desacoplamento PhaseZero (release `a27`, commit `1dc331c`):** decisão do responsável —
PhaseZero foi somente referência de pesquisa e não faz parte do produto. `prepare()`
reage apenas a `steamzero.gamemode=1` (marcador alheio = boot normal); `BootLayout`
perdeu `legacy_sddm_config`/`legacy_unit`; payloads perderam
`legacyMarker`/`legacyMarkerAccepted`/`legacyRuntimeRequired`; a UI não menciona o
projeto pesquisado e o contrato de independência passou a exigir a ausência da
referência. Limpeza externa e explícita do host executada com `bigsudo`: entrada GRUB,
sessão wayland, unit de boot, scripts `/usr/local/lib/phasezero`, sudoers, drop-in de
suspend, units de usuário, autostart e tray — `find` em `/etc`, `/usr/local` e
`~/.config` retorna zero referências; grub.cfg regenerado só com a entrada SteamZero.

**Gates:** 569 passed, Ruff, mypy estrito, fronteiras e independência verdes nas duas
releases. Manifesto v4 ativo vincula `0.1.0a27` a
`1dc331c9eea9e61736541b8d0822f0831918561b`. Gate físico pendente: observar Big Picture
no próximo reboot pela entrada "SteamZero Game Mode".

## 2026-07-19 — Sessão 31: diagnóstico e correção do teclado virtual no Desktop

**Problema reportado:** serviços de experiência Desktop implementados por agente anterior
não funcionavam; teste real no host mostrou que o teclado virtual não abria.

**Diagnóstico:**
- A instalação ativa no host é `0.1.0a34-4c495cf92fbe`, enquanto a árvore de trabalho
  atual (`codex/robustez-boot-resiliencia`) está em `0.1.0a33` (`9fe5213`). A instalação
  contém uma `KDEShortcutsEffect` que não existe no código fonte atual, evidenciando
  divergência entre build publicada e branch de desenvolvimento.
- O comando `qdbus6 org.kde.KWin /VirtualKeyboard forceActivate` retornava sucesso
  (exit 0), mas a propriedade `available` do KWin era `false` e `visible` permanecia
  `false`; o `maliit-server` não estava rodando e não se registrava como input method.
- O código antigo considerava o `forceActivate` com exit 0 como sucesso, mascarando
  a falha real.

**Correção (commit `b025bb3`):**
- `VirtualKeyboardController` agora verifica `available` antes de ativar e `visible`
  depois de ativar via KWin DBus.
- Se o teclado KWin não estiver disponível, tenta iniciar `maliit-server` (com guarda
  contra duplicatas via `/proc/<pid>/comm`).
- Adicionados fallbacks documentados: `steam` (tenta abrir o cliente se não estiver
  rodando), `wvkbd-mobintl` e `onboard`.
- Erro final alterado de "aceitou a ativação" para "ficou visível", refletindo a
  verificação real.

**Gates:** 597 passed, Ruff, mypy estrito, fronteiras e independência verdes.

**Pendência operador:** para que a correção entre em vigor no host, é necessário
construir e instalar uma nova release a partir desta branch (`0.1.0a33+`). Nenhum
agente deve executar `install_host.py install` — esta ação é exclusiva do operador
humano com privilégio, conforme AGENTS.md §1.

## 2026-07-19 — Sessão 31 (continuação): release 0.1.0a33 preparada para instalação

**Artefatos construídos (não commitados — `dist/` está em `.gitignore`):**
- Wheel: `dist/steamzero-0.1.0a33-py3-none-any.whl`
- SHA-256: `b207f1022f329fce0bfb07c55cd23d0443496bf2680507a0a3feeb14f7ec0503`
- Source commit: `8e7f55fef9acc02a552c389c3037f98d0d5b8eb8`
- Release canônica: `0.1.0a33-8e7f55fef9ac`
- Wheelhouse runtime: `dist/runtime-wheelhouse/` com 5 dependências verificadas por hash
- Verificação: `tools/release_provenance.py verify-wheel` identificou projeto, versão e hash corretamente.

**Comando de instalação para o operador humano (requer `bigsudo`):**

```bash
cd /mnt/sdcard/Projects/Port_Steam
SOURCE_COMMIT=8e7f55fef9acc02a552c389c3037f98d0d5b8eb8
bigsudo /usr/bin/python3 tools/install_host.py install \
  --release "0.1.0a33-${SOURCE_COMMIT:0:12}" \
  --wheel dist/steamzero-0.1.0a33-py3-none-any.whl \
  --wheel-sha256 b207f1022f329fce0bfb07c55cd23d0443496bf2680507a0a3feeb14f7ec0503 \
  --requirements requirements-runtime.lock \
  --wheelhouse dist/runtime-wheelhouse \
  --source-commit "$SOURCE_COMMIT"
```

**Após a instalação:**

```bash
systemctl --user daemon-reload
systemctl --user restart steamzero-core.socket steamzero-core.service
steamzero --version
steamzero doctor --json
```

Nenhum agente executou `install_host.py install`; a instalação no host permanece como ação exclusiva do operador, conforme AGENTS.md §1.

## 2026-07-19 — Sessão 32: resiliência do teclado virtual — input method KWin, UI e fallback Steam

**Motivação:** após instalar a release `0.1.0a33`, o teclado virtual ainda não aparecia
porque o KWin não tinha input method configurado e o fallback Steam não iniciava o
cliente de forma confiável.

**Implementação (commit `6bcf03d`):**

1. **Gerenciamento do input method do KWin (Passo 1):**
   - Novo `KDEInputMethodEffect` em `desktop_kde.py`.
   - Verifica se o teclado virtual do KWin está `available` via DBus.
   - Se não estiver e o Maliit estiver instalado, configura
     `kwinrc -> Wayland -> InputMethod` para o arquivo `.desktop` do Maliit e
     reconfigura o KWin.
   - Captura o valor anterior para rollback seguro.
   - Adicionado à cadeia de efeitos do coordenador Desktop.

2. **Monitoramento e ações na UI (Passo 2):**
   - `input_method_status()` retorna `available`, `configured-restart-needed`,
     `unconfigured` ou `missing`.
   - Dashboard expõe `inputMethod` no snapshot.
   - `SteamDesktop.qml` mostra o estado do teclado virtual e botão contextual:
     - "Abrir teclado" quando disponível
     - "Reiniciar sessão" quando configurado mas o KWin precisa reiniciar
     - "Configurar" quando não configurado (dispara plano Desktop auto)
     - "Ver detalhes" quando indisponível

3. **Fallback Steam mais robusto (Ponto 3):**
   - Verifica se o processo `steam` está rodando via `/proc`.
   - Se não estiver, tenta `steam -silent` e aguarda até 5s pelo processo.
   - Só considera sucesso se o cliente realmente estiver no ar.

4. **Outras melhorias:**
   - Extração de helpers `_kwin_vk_property`, `_kwin_vk_available`,
     `_kwin_vk_visible`, `_process_running` e `_maliit_desktop_file`.
   - Adicionados fallbacks `wvkbd-mobintl` e `onboard`.

**Gates:** 601 passed, Ruff, mypy estrito, fronteiras, independência e `qmllint` verdes.

**Próximo passo operador:** reconstruir e instalar release a partir do commit
`6bcf03d` para que o `KDEInputMethodEffect` e a UI atualizada entrem em vigor no
host. A configuração do input method é aplicada automaticamente no próximo
`desktop apply`; dependendo do KWin, pode ser necessário reiniciar a sessão Plasma
para o teclado virtual ficar disponível.

## 2026-07-20 — Sessão EM-01: refino resiliente do lifecycle e da conversão

**Isolamento e base:** trabalho realizado exclusivamente na branch
`codex/refino-emulacao`, criada em `5bdd995` e atualizada sem conflito sobre `b7d4c55`.
O worktree concorrente de robustez e
seu `docs/WORKLOG.md` não commitado permaneceram intactos. A base confirmou
`0.1.0a33`, schema de instalação 4, `--source-commit` e a cadeia `steam_boot` /
`steam_session`; nenhum artefato de release ou efeito no host foi criado.

**Flatpak concorrente e recuperável (`c79206e`):** apply, rollback e recovery agora
recarregam plano, operação e deployment depois de adquirir o lock. Isso impede que um
segundo apply use snapshot/token consumido ou que rollback sobrescreva um deployment
alterado enquanto aguardava. Snapshots persistidos recusam booleanos ambíguos,
origin/commit inconsistentes, IDs, refs, timestamps e commits inválidos antes de tocar o
Flatpak. Testes injetam mudança exatamente na aquisição do lock e comprovam zero mutação.

**Conversão confinada (`bff665c`):** o conversor recebe somente cópia verificada em
staging, nunca o dump original. Formato/traversal, symlink, destino igual ao original,
colisão e mudança concorrente são recusados; espaço é checado no staging e no destino;
publicação usa streaming atômico e hash pós-cópia. Timeout, EIO e ENOSPC limpam staging e
preservam o original byte-idêntico.

**Capabilities e proveniência (`e211795`):** novas instalações ignoram fontes EOL sem
alterar a leitura honesta do dashboard; prioridades duplicadas e campos de origens
misturados são inválidos. Engine portátil e Flatpak recusam install/update não declarado
antes de fetch/remote/mutação. Metadata portátil divergente do adapter, manifesto ou raiz
é `degraded`, com versão observada preservada quando segura. O gate completo detectou e
evitou uma regressão de estado do DuckStation no dashboard compartilhado.

**Gates por item:** baseline bruto teve 587 passes, 9 failures e 5 setup errors, todos
causados pelo path temporário do Codex exceder o limite AF_UNIX. A repetição controlada
com `--basetemp` curto passou com **601 testes**. Após cada commit: **608**, **614** e
**620 passed**; Ruff check, mypy (78 arquivos), independence e boundaries passaram em
todas as rodadas. Após atualizar a base para `b7d4c55`, o gate final passou com **623
testes**. O `ruff format --check` dos arquivos alterados passou. A verificação
global extra aponta três arquivos preexistentes fora do escopo que seriam reformatados:
`desktop_kde.py`, `steam_boot.py` e `tools/install_host.py`; eles não foram editados.

**Limites explícitos:** instalação dos emuladores em VM/hardware não foi executada;
DuckStation continua EOL e nenhum manifesto foi promovido sem fonte validada. A aquisição
do `ResourceLock` central ainda usa read+write sem criação exclusiva entre processos e a
persistência composta do import de biblioteca ainda não possui transação pública única no
State Store; ambos exigem mudança fora deste escopo antes de alegar segurança
cross-process/import plenamente atômica.

## 2026-07-20 — Sessão 33: normalização de branches, instalação e testes no host

**Branches normalizadas na main:** merge de `codex/refino-emulacao` (que já continha
`codex/robustez-boot-resiliencia`) para `main`. O merge adicionou 71 commits de
robustez de boot, sessão Steam, emulação/Flatpak transacional e Desktop.

**Branch mantida em aberto:** `codex/ui-emulacao` não foi mergeada nesta sessão porque
apresentou 21 conflitos de conteúdo em `src/steamzero/ui/qml/Main.qml`. A versão da
branch de UI remove as rotas e componentes Steam (`/steam/gameplay/*`, LSFG, etc.) que
os testes de runtime (`test_runtime_independence.py`) e o contrato da central exigem.
A integração desta branch requer reconciliação manual entre o refinamento responsivo da
UI e as telas `SteamGameplay`/`SteamDesktop` introduzidas pela frente de emulação/boot.

**Formatação prévia:** três arquivos preexistentes fora do escopo imediato
(`desktop_kde.py`, `steam_boot.py`, `tools/install_host.py`) estavam fora do padrão
Ruff. Foram formatados em commit dedicado para satisfazer o gate `make check`, sem
mudança de lógica.

**Gates executados:** `make check` passou com **623 testes passed**, lint/format/mypy
verdes, fronteiras e independência OK, cobertura **85.17%**.

**Release construída:**
- Wheel: `dist/steamzero-0.1.0a33-py3-none-any.whl`
- SHA-256: `d6e434a2965e66cd23ecc4461e159ba97cb27368493565dbd9296f6174a8ff86`
- Source commit: `69fb7db4dea299c6a4c107bf6c99d3952c2e22a2`
- Release canônica: `0.1.0a33-69fb7db4dea2`
- Wheelhouse runtime: `dist/runtime-wheelhouse/` (5 wheels, hashes verificados)

**Instalação no host:** executada com `bigsudo /usr/bin/python3 tools/install_host.py install`
usando os parâmetros canônicos acima. Release anterior: `0.1.0a33-5bdd99539c2d`.
Instalação idempotente/preservadora; serviços recarregados.

**Testes no host real:**
- `steamzero --version` → `0.1.0a33`
- `steamzero doctor --json` → ok, schema 5, 0 operações pendentes
- `steamzero desktop status --json` → ok, detectou `deck-lcd`, sessão Wayland, perfil
  `docked-desktop` aplicado
- `systemctl --user status steamzero-core.service/socket` → ativos e ouvindo
  `/run/user/1000/steamzero/core.sock`
- `bigsudo /usr/local/sbin/steamzero-host status` → instalado, manifesto schema 4,
  source tree clean

**Próximos passos pendentes:** integrar manualmente `codex/ui-emulacao` preservando o
contrato de rotas Steam da central; teste físico de boot Game Mode e handoff Desktop
permanecem como gates externos do operador.

## 2026-07-20 — Sessão 34: teclado com toggle e idioma do host, painel auto-oculto e Terminal Ashy

**Contexto:** continuação de sessão interrompida. O trabalho anterior estava não
commitado na branch `feat/keyboard-panel-ashy`; esta sessão avaliou o diff, corrigiu
três defeitos reais antes de commitar e atualizou o host com autorização do operador.

**Defeitos corrigidos na avaliação:**
- Idioma do maliit era "configurado" via `MALIIT_KEYBOARD_LAYOUT`, variável que não
  existe no binário. O mecanismo real é `gsettings org.maliit.keyboard.maliit
  active-language`/`enabled-languages` com códigos ISO (`pt`, não `br`); a
  sincronização agora acontece na ativação/toggle e vale com o servidor já em
  execução (caso do provider persistente).
- O script de captura do `KDEPanelEffect` atribuía `p.hiding = 'null'` durante a
  LEITURA — todo apply corromperia a configuração dos painéis. Leitura e escrita
  foram separadas em scripts distintos; a leitura é observação pura.
- `wvkbd` era iniciado com `--hidden` sem SIGUSR2 (ativação "bem-sucedida" com
  teclado invisível) e com `-l <xkb>` — layer inexistente encerra o processo. Agora
  só layers conhecidas são passadas (cyrillic/arabic/greek/persian/georgian) e o
  spawn nasce visível; Onboard não recebe mais `-l` (espera arquivo .onboard, não
  idioma).

**Itens entregues (item → commit):**
- Toggle suave de teclado (show/hide via `forceActivate`/`forceDeactivate` do KWin,
  fallback por sinais), geometria proporcional ao display interno, idioma do host
  com override manual, `panelAutoHide` por perfil com efeito KDE (capture/apply/
  verify/restore), endpoints `/keyboard action=toggle`, `/panel/autohide`,
  `/ashyterm` e CLI `desktop keyboard --toggle --language` → `2ca8fdf`
- Controles na central QML (alternar teclado, seletor de idioma, switch de painel,
  botão Terminal Ashy), arquivos compartilhados isolados → `5b61183`

**Gates:** `make check` completo verde no commit instalado — 658 testes, cobertura
**85.17%** (sem regressão sobre a sessão 33), ruff/format/mypy/boundaries/
independence OK.

**Release e instalação no host (autorizada pelo operador nesta thread):**
- Wheel: `dist/steamzero-0.1.0a33-py3-none-any.whl` construído de árvore limpa
- SHA-256: `d42b5bc11290635401304f6c1fa828d1d55d80dbc2a8b0d46ef7b3209e698e37`
- Source commit: `5b611834c52b59d3be9edaab2e2119b916d3df25`
- Release ativa: `0.1.0a33-5b611834c52b`; rollback disponível:
  `0.1.0a33-69fb7db4dea2` (via `install_host.py rollback`)
- Preflights: base descende do tip da main, gates verdes, entry points de boot
  conferidos no wheel, proveniência verificada, estado anterior inspecionado.

**Testes no host real após instalação:**
- `steamzero --version` → `0.1.0a33`; `doctor --json` ok, 0 operações pendentes
- `steamzero-core.socket/service` ativos após reload
- `steamzero desktop keyboard --toggle` alternou o teclado real: `show` →
  `hide` via kwin-maliit
- `gsettings … active-language` mudou de `'en'` para `'pt'` (locale pt_BR do
  host), corrigindo o teclado em inglês observado nas fotos do teste anterior

**Pendências do operador (teste físico):** teclado no Big Picture e no desktop com
toque, troca manual de idioma pela central, switch de auto-ocultar painel no perfil
handheld e digitação no Terminal Ashy com o teclado virtual.

### Sessão 34 (continuação): normalização na main e release oficial

- Merge `feat/keyboard-panel-ashy` → `main` (`dbd4b60`, sem conflitos); `make check`
  verde na main (658 testes, cobertura 85.17%). Push de `main` e da branch feita.
- Release oficial instalada no host: `0.1.0a33-dbd4b6010ff6` (source commit
  `dbd4b6010ff64c487ad9580a91e8e12e8cfb9790`; wheel byte-idêntico ao da release
  anterior — build reproduzível). Rollback: `0.1.0a33-5b611834c52b`.
- Pós-instalação: versão, doctor (0 pendências, 0 checks falhando) e units OK.
- `codex/ui-emulacao` permanece aberta: exige reconciliação manual do Main.qml
  preservando as rotas Steam (registrado na sessão 33); fora do escopo desta
  normalização.

## 2026-07-20 — Sessão 35: teclado onipresente, conforto do Maliit e retorno ao Game Mode

**Branch:** `feat/keyboard-ux-gamemode` a partir de `a41a5a6` (main).

| Item | Commit | Testes que provam |
|---|---|---|
| Conforto do Maliit (som/háptica/tema) via gsettings | `ea9bf54` | `test_maliit_comfort_*` (4), `test_bridge_keyboard_settings_*` (2) |
| Atalho global Meta+K com efeito e rollback | `1c664b1` | `test_shortcut_effect_*` (5), coordenador inclui efeito |
| Gesto de borda inferior (spike, KWin script) | `b48db0d` | `test_edge_gesture_*` (4) |
| Retorno confirmado ao Game Mode (`/session/select`) | `e36832a` | `test_bridge_session_select_*` (3) |
| QML: switches de conforto + botão Game Mode | `d79e086` | contrato de sinais preservado; gates verdes |

**Detalhes técnicos:**
- `apply_maliit_comfort` escreve apenas chaves divergentes, confirma por readback,
  reverte em divergência e retorna valores anteriores. Testado ao vivo no host:
  `SuruDark` aplicado e revertido para `Ambiance` com sucesso.
- `KDEShortcutEffect` publica `steamzero-keyboard-toggle.desktop` (marcado,
  `X-KDE-GlobalAccel-CommandShortcut=true`) e binding `Meta+K` em
  `kglobalshortcutsrc`; o kglobalaccel carrega na próxima sessão. Escrita FS
  pelo port `core.fs` (exigência do gate de fronteiras).
- Existe no host um artefato manual PRÉ-EXISTENTE sem marcador
  (`~/.local/share/applications/steamzero-desktop-keyboard.desktop`, Meta+Ctrl+K,
  sem toggle). Não foi tocado (regra de ownership); operador pode remover.
- `KDEEdgeGestureEffect` (spike): KWin script marcado com
  `registerTouchScreenEdge(ElectricBottom)` alternando o teclado via DBus;
  habilitado em `kwinrc [Plugins]` + reconfigure. Validação física decide
  permanência.
- `/session/select`: dois passos com plano efêmero em memória da bridge,
  allowlist `steam|gamepadui`, readiness degradada responde 409 com causa;
  execução usa `request_target` + logout Plasma via `org.kde.Shutdown`.

**Gates:** `make check` verde após cada item; final com **677 testes passed**,
cobertura **85.33%**, ruff/mypy/independence/boundaries OK.

**Limites explícitos:** atalho e gesto exigem nova sessão para o kglobalaccel/KWin
carregarem; validação física (Meta+K, gesto de borda, som, tema, retorno ao Game
Mode) é gate do operador após instalação.

**Adendo (mesma sessão):** correção da ambiguidade docked/safe na observação
(`fix(desktop)`): perfis observacionalmente idênticos não degradam mais o status
quando o aplicado está entre os candidatos consistentes — resolução registrada
em `observation.resolvedBy` (campo aditivo no schema de status). Ambiguidade que
exclui o aplicado permanece degradada (teste dedicado). Artefato manual sem
marcador `steamzero-desktop-keyboard.desktop` (Meta+Ctrl+K) removido do host
pelo agente com autorização explícita do operador nesta thread.

## 2026-07-20 — Sessão 36: central de emulação Switch orientada por capacidades

**Branch:** `codex/ui-emulacao-switch`, criada do tip `af69698` da main. Escopo
restrito a `src/steamzero/ui/qml/`, apresentação e harnesses QML; nenhum adapter,
domínio, contrato de payload, artefato de host ou release foi alterado.

| Item | Commit | Testes que provam |
|---|---|---|
| Central por plataforma com escopos Global/Emulador/Por jogo/Portátil/Dock e áreas especializadas | `a0808f7` | `check_emulation.qml`, `qmllint` e carregamento Qt6 offscreen |
| Integração da central à navegação e ao snapshot `dashboard.emulation` | `a0e340e` | `check_main_emulation.qml` e carregamento integral de `Main.qml` |
| Responsividade dos seletores em telas compactas | `2ddfe69` | harnesses em 1440×900 e 980×900; inspeção visual offscreen |
| Alinhamento ao contrato versionado Switch v1 | `219bf0f` | fixture/fallback do contrato e ambos os harnesses Qt6 |
| Allowlist conservadora: somente `emulation.refresh`; mutações sem rota ficam desabilitadas com causa | `24c05bb` | teste QML de ação permitida, desconhecida e indisponível |
| Alvos interativos mínimos de 48 px e ícones vetoriais modernos | `8808d5d` | `qmllint`, harnesses e inspeção visual nas duas larguras |
| Preservação de plataforma/escopo/área durante refresh do mesmo payload | `c20f0e9` | regressão dedicada em `check_emulation.qml` |

**Resultado funcional:** a antiga lista rasa de emuladores tornou-se uma central
de emulação guiada por plataforma. Nintendo Switch possui marca visual própria,
readiness, contexto de emulador/jogo, especialidades por emulador e as áreas
Keys & Firmware, Updates & DLC, Gráficos, Controles, Saves, Shader cache, Mídia,
Armazenamento e Avançado. Estados `blocked`, `attention`, `unverified`, `planned`
e `ready` são apresentados sem fabricar disponibilidade; o fallback mantém a UI
navegável se o provider estiver ausente ou incompleto.

**Gates finais da branch UI:** 679 testes Python passaram (330 unitários, 236 de
integração, 103 de segurança/failure injection e 10 golden), Ruff verde, mypy
verde em 78 arquivos, independence/boundaries verdes, `qmllint` verde e os
harnesses Qt6 `check_emulation.qml`/`check_main_emulation.qml` com exit 0. A
branch backend independente foi revisada em separado com 822 testes e os quatro
gates verdes; seus commits e entregáveis constam exclusivamente na Sessão 37
daquela branch.

**Ações de host/release:** nenhuma. Não houve build de wheel, instalação,
rollback, `bigsudo`, reinício de serviço ou push durante a implementação.

**Limites e próximos passos:** importações, instalação e demais mutações seguem
desabilitadas na UI até existirem rotas completas de plan/apply/rollback. Fontes
Eden/Citron/Ryujinx permanecem `unverified`; DAT é somente local do usuário.
Após integração das branches, ainda cabe ao operador validar navegação por
gamepad e legibilidade no Deck físico em modo portátil e dock.

## 2026-07-20 — Sessão 37: backend Switch e contrato multiplaforma de emulação

**Branch:** `codex/backend-emulacao-switch` a partir de `af69698` (main).

| Item | Commit(s) | Testes que provam |
|---|---|---|
| WI-0 schema keys/firmware/tool/DAT e ADR de domínios dedicados | `26f6fdf` | `test_switch_schemas.py` |
| WI-1 import local auditado, linking e compatibilidade por jogo | `eb3252d`, `02cc290` | `test_keys_firmware.py` |
| WI-2 catálogo Eden/Citron/Ryujinx com disponibilidade honesta | `fa8286f` | `test_switch_emulators.py` |
| WI-3 perfis conhecidos bons, diff/plan/apply/rollback e INI endurecido | `5951401`, `02cc290` | `test_emulator_config.py` |
| WI-4 NSZ com smoke/version, confirmação, cleanup e rollback por hash | `5b1ff2f`, `4d7e290`, `89d7a75` | `test_nsz_converter.py`, `test_nsz_conversion.py` |
| WI-5 DAT local, matching e rename transacional sem colisão | `383a851`, `4d7e290`, `89d7a75` | `test_switch_library.py` |
| WI-6 blobs compartilhados, updates/DLC persistentes, shader e saves | `24d6914`, `52dea7a`, `c0ecb83` | `test_switch_content.py`, `test_transaction_copy.py` |
| WI-7 dock/portátil e até quatro jogadores sem controles fantasmas | `fe7c285`, `c0ecb83` | `test_switch_runtime.py` |
| WI-8 recomendação LSFG 30→60 somente com opt-in e evidência estável | `fe7c285` | `test_switch_runtime.py` |
| WI-9 read model v1, golden, CLI/RPC e `dashboard.emulation` | `45387a8`, `e97529c`, `e2959ae` | `test_emulation_workspace.py`, `test_cli_emulation.py`, `test_desktop_dashboard.py` |

**Gates finais:** 822 testes passaram; Ruff, mypy, independence e boundaries
verdes. O pytest completo foi executado fora do sandbox porque a suíte de
integração exige sockets locais; nenhuma permissão de host ou privilégio foi
usada pelo produto testado.

**Decisões e limites:** nenhuma fonte de instalação de emulador foi inventada;
Eden/Citron/Ryujinx permanecem `unverified` até pin verificável. DAT é somente
import local do usuário e não é redistribuído. A UI habilita apenas
`emulation.refresh` (GET `/status`); import, verify, conversão e rename continuam
desabilitados na bridge até existirem rotas mutáveis allowlisted completas.
Templates específicos por emulador ainda precisam de validação com os binários
reais; o domínio entrega perfil genérico sem inventar chaves de configuração.

**Host/release:** nenhuma instalação, build de wheel, alteração de serviço ou
ação privilegiada foi executada; release ativa e rollback do host não foram
alterados. Teste físico com dumps próprios, ferramentas pinadas e dock/controladores
reais permanece ação do operador após integração da branch.

## 2026-07-20 — Sessão 38: integração, release e instalação da central de emulação

**Integração:** branch `codex/integracao-emulacao-switch` criada do tip
`af69698` de `origin/main`. Backend e UI foram mesclados em commits explícitos;
o único conflito foi o apêndice concorrente de `docs/WORKLOG.md`, resolvido
preservando integralmente e em ordem as Sessões 36 e 37. O gate de formatação
apontou 13 arquivos do backend e a normalização determinística foi isolada em
`5c8c33d`. O mesmo commit foi promovido por fast-forward para `main`, sem force
push.

| Item | Commit | Testes que provam |
|---|---|---|
| Merge do backend Switch WI-0..WI-9 | merge pai de `21ceb27` | suíte integrada e contratos golden |
| Merge da UI e resolução preservadora do WORKLOG | `21ceb27` | harnesses `check_emulation.qml` e `check_main_emulation.qml` |
| Normalização requerida pelo format gate | `5c8c33d` | Ruff format/check, Ruff lint, mypy, independence e boundaries |

**Gates do commit instalado:** 822 testes passaram; cobertura consolidada
**85.72%** (limiar 85%); Ruff lint/format, mypy em 87 arquivos, independence e
boundaries verdes; `qmllint` e os dois harnesses Qt6 com exit 0. O `make check`
foi também executado: a ferramenta encerrou sua emissão longa durante o pytest,
então a mesma coleta de cobertura foi concluída em grupos sequenciais com
`--cov-append` e relatório único acima do limiar.

**Release construída de árvore limpa:**
- Source commit: `5c8c33ddb0dd6f869cdbeca93c46656446cc9dc4`
- Release canônica: `0.1.0a33-5c8c33ddb0dd`
- Wheel: `steamzero-0.1.0a33-py3-none-any.whl`
- SHA-256: `eb4cdce1ff7f86803670db1b3e4364e927d3e17db6b51aeafac50245884ce2d7`
- Wheelhouse: 5 wheels binários verificados por hash; entry points de CLI,
  core, sessão, launcher e boot conferidos antes da ativação.

**Instalação autorizada pelo operador nesta thread:** executada exclusivamente
com `bigsudo /usr/bin/python3 tools/install_host.py install` e argumentos
canônicos. Release anterior e rollback disponível:
`0.1.0a33-af69698d58b0`. Nenhuma configuração de terceiro, reboot ou ativação de
boot foi realizada.

**Validação pós-instalação:** manifesto v4 íntegro e source tree `clean`;
`steamzero --version` retornou `0.1.0a33`; doctor OK, schema 6 e zero operações
pendentes; `steamzero-core.socket/service` ativos após daemon-reload/restart;
`desktop status` OK no host real; Game Mode disponível com fallback Desktop;
workspace Switch v1 exposto com estado honesto `unverified`; QML empacotado
carregou offscreen por seis segundos sem erro. O teste visual/físico final da
central, navegação por gamepad, portátil e dock permanece com o operador.

## 2026-07-20 — Sessão 39: correções funcionais da central Switch

**Branch:** `codex/correcao-instalacao-emuladores`, criada do tip `5890bb7` de
`origin/main`. O trabalho permaneceu no worktree isolado desta branch; arquivos
não rastreados e worktrees das outras frentes não foram tocados.

| Item | Commit | Testes que provam |
|---|---|---|
| Instalação, atualização, abertura e desinstalação de Eden/Citron com fonte HTTPS pinada, checksum, smoke test, confirmação e rollback | `d4044d1` | `test_adapters.py`, `test_desktop_ui_bridge.py` |
| Diretórios adicionais de ROMs, descoberta de caminhos locais compatíveis, varredura e identificação de Title ID | `d4044d1` | `test_emulation_controller.py`, `test_switch_library.py` |
| Importação local de keys e firmware por arquivo, pasta ou ZIP seguro, com versão e estado persistidos | `d4044d1` | `test_emulation_controller.py` e validações de archive/transação existentes |
| Importação e ativação/desativação de updates e DLC; backups de save, shader cache e reconciliação de storage | `d4044d1` | `test_emulation_controller.py`, `test_switch_content.py` |
| Seletores QML, ações por emulador, preview e confirmação das operações | `6927858` | `qmllint`, `check_emulation.qml`, `check_main_emulation.qml` |

**Gates finais:** 825 testes passaram; Ruff lint e format-check verdes; mypy em
88 arquivos; independence e boundaries verdes. Os dois harnesses QML passaram
com Qt6 offscreen. Os AppImages pinados de Eden e Citron tiveram hash conferido
e o smoke `--appimage-version` retornou código zero com a integração automática
do host explicitamente desabilitada durante a verificação.

**Decisões conservadoras:** Ryujinx permanece sem instalação gerenciada porque
a origem original está descontinuada; uma instalação externa pode ser detectada,
mas nenhuma fonte substituta não verificada é promovida. Keys, firmware, ROMs,
updates, DLC, saves e caches são exclusivamente conteúdo local selecionado pelo
usuário. A descoberta padrão usa diretórios genéricos existentes e caminhos
adicionais explícitos, preservando a independência de runtime.

**Host/release:** nenhuma instalação, build de wheel, alteração de serviço,
rollback ou ação privilegiada no host foi executada nesta sessão. A release
ativa continuou `0.1.0a33-5c8c33ddb0dd`; a instalação desta correção exige um
novo fluxo de release autorizado e os preflights obrigatórios do repositório.

## 2026-07-21 — Sessão 40: Ryubing gerenciado e identidade visual dos emuladores

**Branch:** `codex/correcao-instalacao-emuladores`, mantendo o worktree isolado
da Sessão 39. Nenhum arquivo ou commit das outras frentes foi alterado.

| Item | Commit | Testes que provam |
|---|---|---|
| Substituição do Ryujinx descontinuado pelo Ryubing 1.3.3 com AppImage oficial x86-64, versão e SHA-256 fixados, lockfile, smoke, instalação, atualização, abertura, desinstalação e rollback | `bb85481` | `test_adapters.py`, `test_emulation_controller.py`, `test_switch_emulators.py`, `test_switch_schemas.py` |
| Logos oficiais de Eden, Citron e Ryubing nas linhas de instalação/manutenção, com fallback seguro para o ícone do sistema e atribuição | `bb85481` | `check_emulation.qml`, `qmllint` e inspeção renderizada dos ativos |

**Gates finais:** 826 testes passaram; Ruff verde; mypy sem erros em 88
arquivos; independence e boundaries verdes; `qmllint` terminou com código zero.
A suíte completa foi executada fora do sandbox somente porque os testes de
integração exigem sockets Unix/HTTP locais efêmeros.

**Verificação de fornecimento:** o AppImage oficial foi obtido de
`git.ryujinx.app`, teve SHA-256
`b4511f46612276bb8490d7c30a017622854be75a06c1ca7a9728b71862d4822a`
conferido e o smoke `--appimage-version` terminou com código zero, mantendo a
integração automática do AppImageLauncher desabilitada durante a validação.

**Decisões conservadoras:** `ryubing.net` não foi usado como fonte. A identidade
e os artefatos foram vinculados ao domínio `ryujinx.app` controlado pela
organização oficial verificada do projeto. Keys, firmware e conteúdo do Switch
continuam exclusivamente locais e fornecidos pelo usuário.

**Host/release:** nenhuma instalação, build de wheel, alteração de serviço,
rollback ou ação privilegiada foi executada. A release ativa e o rollback do
host não foram modificados; publicação no host exige um novo fluxo de release
explicitamente autorizado e todos os preflights do repositório.

## 2026-07-21 — Sessão 41: integração e release do Ryubing no host

**Branch de origem:** `codex/correcao-instalacao-emuladores`; integração
fast-forward em `main` no commit `e8acfd8ffa13a4f8e13ff739bf7c924addca067b`.
Os dois itens não rastreados já existentes no worktree de `main` não foram
alterados.

| Item | Commit/release | Evidência |
|---|---|---|
| Gate completo da fonte integrada | `e8acfd8` | 826 testes, cobertura 85,11%, Ruff format/lint, mypy, independence e boundaries verdes |
| Wheel reproduzível e wheelhouse runtime pinado | `0.1.0a33-e8acfd8ffa13` | wheel SHA-256 `6ff8a13b3b90399579524fd91bd31ab07a2ad9854fadf847406fc3a2a454bca7`; 5 wheels runtime verificados por lock/hash |
| Instalação transacional e ativação | `0.1.0a33-e8acfd8ffa13` | manifesto v4 íntegro, source commit completo e estado `clean` |

**Validação pós-instalação:** `steamzero --version` retornou `0.1.0a33`;
doctor aprovou Python, layout, integridade SQLite e zero operações pendentes;
`steamzero-core.socket` e `steamzero-core.service` estavam ativos; Game Mode
reportou `ready` com fallback Desktop; `steamzero desktop status --json` retornou
contrato válido.

**Rollback:** release anterior preservada:
`0.1.0a33-5c8c33ddb0dd`. A consulta privilegiada de status do boot não pôde ser
repetida no fim porque a política local recusou nova autorização; nenhuma
alteração de boot, reinício ou recuperação foi feita nesta sessão.
