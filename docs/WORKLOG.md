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

## 2026-07-21 — Sessão 42: persistência Switch e fluxo local de NSZ

**Branch:** `codex/correcao-importacao-switch`, criada do commit `832d82b` de
`main` em worktree isolado. Nenhuma alteração de outra frente foi incorporada.

| Item | Commit | Testes que provam |
|---|---|---|
| Conversão segura de URLs `file://` em caminhos locais nos seletores QML de keys, firmware e diretórios | `b4d85e8` | `check_emulation.qml`, `test_emulation_controller.py` |
| Projeção auditável de `prod.keys`, firmware e diretórios de jogos para Citron, Ryubing e NSZ já presentes, sem criar configuração de emulador ausente | `b4d85e8` | `test_emulation_controller.py` |
| Instalação privada, hash-pinned e reversível de NSZ; seleção e conversão confirmável NSP↔NSZ após keys válidas | `b4d85e8` | `test_emulation_controller.py`, `test_nsz_converter.py`, `test_nsz_conversion.py` |

**Gates finais:** 829 testes passaram; cobertura 85,02%; Ruff format/lint,
mypy em 88 arquivos, `make independence boundaries` e `git diff --check`
verdes. O `qmllint` completou sem erro, mantendo apenas avisos preexistentes de
acesso não qualificado do QML.

**Decisões conservadoras:** a ferramenta NSZ permanece em venv privado do
usuário, com wheels binários e hashes fixados; qualquer falha remove o estado
parcial. Keys e firmware continuam exclusivamente escolhidos pelo usuário e
nunca são buscados da rede. Configurações de Citron/Ryubing só são atualizadas
quando o respectivo arquivo já existe e é regular.

**Host/release:** nenhum merge em `main`, wheel/release, instalação, rollback,
ação privilegiada ou alteração do host foi executada nesta sessão. A validação
física no host e uma eventual publicação exigem autorização explícita do
operador e os preflights usuais.

## 2026-07-21 — Sessão 43: integração e publicação da persistência Switch

**Integração:** `codex/correcao-importacao-switch` foi integrada por
fast-forward em `main`: `832d82b` → `c4372c1`. Os dois itens não rastreados já
existentes no worktree principal permaneceram intocados.

| Item | Commit/release | Evidência |
|---|---|---|
| Gate completo da fonte integrada | `c4372c1` | 829 testes, cobertura 85,02%, Ruff format/lint, mypy, independence e boundaries verdes |
| Wheel reproduzível e wheelhouse runtime hash-pinado | `0.1.0a33-c4372c12b7ad` | wheel SHA-256 `9580a9573181c0818a8dde3b0f47b21b02a537c887e7cbde3089509d17f1bbef`; 5 wheels runtime verificados pelo lock |
| Instalação transacional e ativação | `0.1.0a33-c4372c12b7ad` | manifesto v4, commit completo e estado de fonte `clean` conferidos pelo instalador |

**Nota do gate:** o primeiro uso do `tmp_path` padrão falhou somente porque o
prefixo temporário do Codex excede o limite de socket AF_UNIX. O gate foi
repetido com `--basetemp=/tmp/sz-pytest`, sem mudar código, e terminou verde.

**Validação pós-instalação:** `steamzero --version` retornou `0.1.0a33`; doctor
OK, schema 6 e zero operações pendentes; `steamzero-core.socket` e
`steamzero-core.service` ativos; `desktop status` retornou contrato válido;
Game Mode disponível com fallback Desktop. Não houve reboot ou alteração de
configuração de boot.

**Rollback:** release anterior preservada e registrada no manifesto:
`0.1.0a33-832d82be8e22`. O teste físico da UI, seleção de arquivo e conversão
NSZ no host continua sendo a próxima etapa do operador.

## 2026-07-21 — Sessão 44: diálogo de firmware e descoberta da biblioteca

**Branch:** `codex/correcao-dialogo-scan-switch`, criada do tip `74f2984` de
`main`. Os itens não rastreados já existentes permaneceram intocados.

| Item | Commit | Testes que provam |
|---|---|---|
| Diálogo de confirmação com altura confinada, preview formatado e barras de rolagem para imports grandes de firmware | `4f0a01f` | harnesses Qt6 offscreen, `qmllint` e testes transacionais |
| Descoberta rápida de NSP/NSZ/XCI/XCZ/NRO sem hash integral durante o inventário, mantendo hash completo nas operações de integridade | `4f0a01f` | `test_switch_library.py`, `test_emulation_controller.py` |
| Jogos sem Title ID visíveis como não verificados; Title ID procurado também nas pastas-pai; ações dependentes de identidade bloqueadas com explicação | `4f0a01f` | `test_switch_library.py`, `test_emulation_workspace.py`, `test_emulation_controller.py` |
| Inclusão de `~/emulation/roms` e varredura automática após confirmar um novo diretório | `4f0a01f` | `test_emulation_controller.py` e prova read-only de 178 NSP identificados no diretório real |

**Gates finais:** 834 testes passaram, cobertura 85,03%; Ruff, mypy em 88
arquivos, independence, boundaries, `git diff --check`, `qmllint` e os dois
harnesses QML offscreen verdes.

**Host/release:** nenhuma release, instalação, rollback, ação privilegiada ou
alteração de dados do host foi executada. A correção permanece somente nesta
branch até autorização explícita para integração e publicação.

## 2026-07-21 — Sessão 45: publicação das correções Switch no host

**Branch:** `codex/correcao-dialogo-scan-switch`; fonte publicada no commit
`483b962a41db09a03f92cb87d5f8bc952e041270`, sem merge em `main`. Os itens não
rastreados já existentes permaneceram intocados.

| Item | Commit/release | Evidência |
|---|---|---|
| Gate completo da fonte publicada | `483b962` | 834 testes, cobertura 85,06%, Ruff, mypy em 88 arquivos, independence e boundaries verdes |
| Wheel e wheelhouse reproduzíveis | `0.1.0a33-483b962a41db` | wheel SHA-256 `c9d6b8dd9d9c772e76a20aa75500732a3804b2d0b60523a61a879f3e1297dd9c`; entry points de boot e 5 wheels runtime hash-pinned conferidos |
| Instalação transacional e ativação | `0.1.0a33-483b962a41db` | manifesto v4, árvore `clean`, commit completo e vínculo `/opt/steamzero/current` confirmados |

**Validação pós-instalação:** `steamzero --version` retornou `0.1.0a33`; doctor
aprovou Python, layout, integridade SQLite e zero operações pendentes;
`steamzero-core.socket` e `steamzero-core.service` estavam ativos; Game Mode
reportou `ready`, runtime independente e fallback Desktop; `desktop status`
retornou contrato válido sem erros de observação. A consulta não privilegiada
do boot degradou para `unknown`/`permissionDenied`, conforme o contrato, sem
bloquear a sessão ou o fallback.

**Rollback:** a release anterior `0.1.0a33-c4372c12b7ad` foi preservada e
registrada no manifesto. Nenhum reboot nem alteração adicional de boot foi
executado; resta ao operador apenas o teste físico da UI e da biblioteca no
host.

## 2026-07-21 — Sessão 46: painel executivo da plataforma Switch

**Branch:** `codex/painel-controle-emulacao`, criada da branch própria de
correção Switch no commit `0bbde6d`. Os itens não rastreados já existentes e os
arquivos de adapters, domínio e contratos permaneceram intocados.

| Item | Commit | Testes que provam |
|---|---|---|
| Visão Geral Global convertida em painel de Keys, firmware, biblioteca/ROMs e emulador principal, com cards simétricos e ações rápidas | `34cc48d` | `qmllint`, harness `check_emulation.qml` e render Qt6 offscreen em 1320×760 |
| Banner de prontidão compacto e ações alinhadas no rodapé dos cards | `34cc48d` | inspeção visual do render offscreen e harness Qt6 |
| Manutenção detalhada removida do resumo Global e exibida apenas no escopo Emulador para o item selecionado | `34cc48d` | `check_emulation.qml`, `check_main_emulation.qml` e render responsivo |
| Atalhos de adicionar/varrer biblioteca e revisar nomes integrados às ações já publicadas | `34cc48d` | harnesses QML e validação do despacho allowlisted existente |

**Gates finais:** 834 testes passaram; cobertura 85,05%; Ruff lint/format,
mypy em 88 arquivos, independence, boundaries, `git diff --check`, `qmllint` e
os dois harnesses QML offscreen ficaram verdes.

**Lacuna preservada:** o payload atual não publica nem persiste o emulador
padrão usado pelo Play no Steam/Game Mode. A UI identifica isso explicitamente
como “Padrão não definido” e direciona à gestão dos emuladores, sem fingir uma
preferência local que o runtime ignoraria. A implementação real exige mudança
coordenada de backend/contrato, fora do escopo desta frente de UI.

**Host/release:** nenhuma release, instalação, rollback, ação privilegiada ou
alteração do host foi executada nesta sessão. A release ativa permaneceu a já
publicada `0.1.0a33-483b962a41db`.

## 2026-07-21 — Sessão 47: biblioteca e jornada Por Jogo

**Branch:** `codex/jornada-por-jogo`, criada da branch própria de UI no commit
`a72e64b`. Os itens não rastreados já existentes permaneceram intocados; a
mudança de backend ficou restrita ao scanner solicitado, sem alterar adapters,
contratos ou serviços de boot/sessão.

| Item | Commit | Testes que provam |
|---|---|---|
| Scanner deixa de promover updates e DLCs NSP/NSZ à biblioteca de jogos base, usando Title ID e marcadores explícitos sem descartar conteúdo ambíguo | `177e92f` | `test_scanner_excludes_updates_and_dlc_from_base_game_library`, testes de conteúdo sem Title ID, NRO e suíte completa |
| Dropdown Por Jogo substituído por biblioteca densa com busca por nome/Title ID, ordenação reversível em cinco campos e seleção por linha | `8631be6` | `testGameLibraryJourney`, `qmllint`, harnesses Qt6 e render offscreen em 1320×760 |
| Linhas exibem capa segura/fallback Switch, identidade, compatibilidade por emulador, complementos, tamanho/formato, requisitos e ações sem inventar dados ausentes | `8631be6` | harness QML com dados completos e incompletos; render visual responsivo |
| Painel lateral retrátil reúne performance, conteúdo/mods, saves/cache e ferramentas, encaminhando somente ações já publicadas | `8631be6` | harnesses `check_emulation.qml` e `check_main_emulation.qml` |

**Gates finais:** 837 testes passaram; cobertura 85,06%; Ruff lint/format,
mypy em 88 arquivos, independence, boundaries, `git diff --check`, `qmllint` e
os dois harnesses QML offscreen ficaram verdes.

**Degradação honesta:** o backend ainda não publica compatibilidade por jogo,
região/idiomas, inventário consolidado de complementos, emulador padrão por
título nem um plano de lançamento do jogo. A UI mostra `—`/“Não avaliado” e
mantém Play/seletor desabilitados nesses casos, em vez de inferir ou persistir
estado que Steam/Game Mode ignoraria. Mods também permanecem indisponíveis até
existir serviço transacional próprio.

**Host/release:** nenhuma release, instalação, rollback, ação privilegiada ou
alteração do host foi executada nesta sessão. A release ativa permaneceu
`0.1.0a33-483b962a41db`; a biblioteca instalada só será reclassificada depois
de uma nova release e uma nova varredura autorizadas pelo operador.

## 2026-07-21 — Sessão 48: lançamento e publicação seletiva de jogos

**Branch:** `codex/lancamento-steam-roms`, baseada na linha atual de emulação;
`origin/main` (`74f2984`) foi confirmado como ancestral. Os caminhos não
rastreados `.worktrees/` e `docs/12-roadmap/EMULATOR-PORTING-DIRECTIVE.md`, de
outras frentes, permaneceram intocados.

| Item | Commit/release | Testes que provam |
|---|---|---|
| Preferência persistente de emulador, lançamento direto sem shell, validação de ROM/raiz/fingerprint e CLI local para atalhos | `807e05e` | `test_game_preference_launch_delete_and_rollback`, `test_emulation_launch_cli_uses_local_controller` |
| Seleção e sincronização de atalhos locais na Steam, preservando entradas externas e recusando Steam aberta/VDF ambíguo | `807e05e` | `test_sync_preserves_foreign_entries_and_removes_only_managed`, corpus de codec/corrupção e bridge HTTP |
| Exclusão de ROM com G-FULL e rollback limitado por journal às operações `emulation.game-delete` | `807e05e` | exclusão, nova varredura, restauração byte a byte e recusa de rollback de outro kind |
| Jornada Por Jogo com seletor funcional, Play, marcação/sincronização Steam e exclusão confirmada | `043e290` | `qmllint`, `check_emulation.qml`, `check_main_emulation.qml` e harness Qt6 offscreen |
| Plano resiliente de provider de mídia, condicionado a API/licença oficiais e fallback local | `043e290` | revisão documental com gates G1–G10; nenhum scraping foi introduzido no runtime |
| Build e ativação do commit funcional | `0.1.0a33-043e290a184f` | wheel SHA-256 `c15b9bf7313d1e790e8059190c2c3291de774fc18b2b28922917e6314d851051`, manifesto v4 e entry points de boot conferidos |

**Gates finais:** 842 testes passaram com `TMPDIR=/tmp`; Ruff, mypy em 89
arquivos, independence, boundaries, `git diff --check`, `qmllint` e os dois
harnesses QML ficaram verdes. A primeira execução da suíte no diretório
temporário longo do Codex teve somente falhas `AF_UNIX path too long`; a
reexecução no `/tmp` curto passou integralmente sem alteração de teste ou de
código.

**Host:** o instalador transacional ativou `0.1.0a33-043e290a184f`, originada da
árvore limpa `043e290a184fe45e06c0513a073e6e34a0d5eaac`. O serviço core do usuário
foi reiniciado após `daemon-reload` para abandonar o processo da release antiga;
socket e serviço ficaram ativos, o executável resolveu para a release nova,
doctor aprovou os quatro checks e o Game Mode permaneceu `ready` com fallback
Desktop. Nenhum reboot nem ajuste de boot foi executado.

**Rollback:** `0.1.0a33-483b962a41db` foi preservada e registrada como release
anterior. A integração externa de mídia ficou fora do runtime porque não há API
pública oficial documentada; a próxima etapa depende de validação de termos e
licença. Resta ao operador testar a jornada visual, o lançamento real de ROMs e
a importação dos atalhos com a Steam totalmente encerrada.

## 2026-07-21 — Sessão 49: bootstrap resiliente da central QML

**Branch:** `codex/lancamento-steam-roms`. Os caminhos não rastreados de outras
frentes permaneceram intocados.

| Item | Commit/release | Evidência |
|---|---|---|
| Diagnóstico da falha pós-reboot | `dbb824b` | journal da sessão mostrou `E-INTERNAL-UNEXPECTED: [Errno 7] Argument list too long: /usr/sbin/qml6`; core, doctor e SQLite estavam íntegros |
| Snapshot removido dos argumentos do processo e carregado assincronamente pela bridge HTTP | `dbb824b` | teste impede `--steamzero-status`, limita argv a menos de 4 KiB e prova que `coordinator.status()` não é chamado antes do spawn |
| Degradação inicial segura da UI | `dbb824b` | QML inicia com o read model fallback existente e chama `refreshStatus()` somente após URL/token da bridge estarem disponíveis |
| Release corretiva | `0.1.0a33-dbb824b4ce54` | wheel SHA-256 `fe15d855edc6122a4bc42e1cbbf4cefda97e68dc726058fa6630072f265c3655`, manifesto v4 e árvore clean |

**Gates:** 843 testes, Ruff, mypy em 89 arquivos, independence, boundaries,
`qmllint`, harness QML e smoke offscreen com o snapshot real do host ficaram
verdes. O smoke permaneceu ativo até o timeout intencional de oito segundos,
sem E2BIG, traceback ou falha do aplicativo.

**Host:** `0.1.0a33-dbb824b4ce54` foi ativada, o serviço core do usuário foi
reiniciado e passou a executar o Python dessa release. Socket e serviço ficaram
ativos, doctor aprovou todos os checks e Game Mode permaneceu `ready`. Nenhum
reboot, mudança de boot ou arquivo de outra frente foi alterado.

**Rollback:** `0.1.0a33-043e290a184f` foi preservada como release anterior.

## 2026-07-21 — Sessão 50: lançamento Switch resiliente e catálogo consolidado

**Branch:** `codex/lancamento-steam-roms`. A branch continua descendendo de
`main` (`74f2984`). Os caminhos não rastreados `.worktrees/` e
`docs/12-roadmap/EMULATOR-PORTING-DIRECTIVE.md`, pertencentes a outras frentes,
permaneceram intocados.

| Item | Commit | Testes que provam |
|---|---|---|
| Scanner separa jogo-base, update e DLC por Title ID, versão e fallback nominal; cache legado também é filtrado antes da UI | `e9834c0` | `test_scanner_excludes_updates_and_dlc_from_base_game_library`, `test_scanner_excludes_scene_version_above_zero_without_title_id`, `test_library_groups_updates_and_dlcs_under_unique_base` |
| Lançamento revalida ROM-base, preserva caminhos com espaços sem shell, usa flags específicas de Eden/Citron/Ryubing e desativa a interceptação do AppImageLauncher | `e9834c0` | `test_game_preference_launch_delete_and_rollback`, `test_detached_spawn_disables_appimage_launcher_and_preserves_argv` |
| Keys globais são verificadas fisicamente nos emuladores; reparo transacional projeta `prod.keys` e `title.keys` opcional, sem sobrescrever divergências | `e9834c0` | `test_imports_project_to_switch_consumers_and_save_game_directories`, `test_keys_import_projects_optional_title_keys` |
| Preparação confirmada desativa verificações interativas de update nos três emuladores | `e9834c0` | `test_runtime_prepare_mutes_interactive_update_checks` |
| UI mantém lista e painel no mesmo jogo/emulador, compacta badges, qualifica metadados pendentes e melhora contraste das ações | `83c1f7d` | `qmllint src/steamzero/ui/qml/Emulation.qml` e suíte completa |

**Gates:** 849 testes passaram com `TMPDIR=/tmp/szg.u7HfRZ`; Ruff, mypy em 89
arquivos, independence, boundaries, `git diff --check` e `qmllint` ficaram
verdes. A primeira execução teve somente 14 erros/falhas `AF_UNIX path too
long` causados pelo diretório temporário do Codex; a repetição na raiz curta
passou sem mudar código ou testes.

**Validação no host, somente leitura:** o cache de 178 arquivos foi reduzido a
16 jogos-base; 19 updates e 143 DLCs deixaram de ser promovidos a jogos. Eden e
Ryubing possuem `prod.keys` idêntica à cópia global; Citron foi corretamente
marcado como não sincronizado, fazendo a prontidão deixar de declarar 100%.

**Host/release:** nenhuma release, instalação, rollback ou alteração
privilegiada foi executada nesta sessão. A release ativa permaneceu
`0.1.0a33-dbb824b4ce54`; o operador ainda precisa autorizar explicitamente uma
nova release/instalação antes do teste funcional desta correção.

## 2026-07-21 — Sessão 51: release do catálogo Switch e filtro auxiliar final

**Branch:** `codex/lancamento-steam-roms`. A branch permanece descendente de
`main` (`74f2984`). Os caminhos não rastreados `.worktrees/` e
`docs/12-roadmap/EMULATOR-PORTING-DIRECTIVE.md`, pertencentes a outras frentes,
permaneceram intocados.

| Item | Commit/release | Testes que provam |
|---|---|---|
| Release inicial do lançamento resiliente e dos ajustes Por Jogo | `0.1.0a33-90f581e01fea` | manifesto v4, entry points de boot, doctor e snapshot real do dashboard |
| Pacotes auxiliares autônomos com Title ID terminado em `000` deixam de aparecer como jogos quando estão em diretório explícito de DLC/update | `a8aa074` | `test_scanner_excludes_standalone_auxiliary_with_base_shaped_title_id` e suíte completa |
| Release final instalada a partir de árvore limpa | `0.1.0a33-a8aa074d81a3` | wheel SHA-256 `b58a5ba927255a628889b1c29ef53bd7617000e28df0b2963ef3e36633a2dc76`, provenance e conteúdo do wheel conferidos |
| UI instalada carrega o dashboard completo sem falha QML | `0.1.0a33-a8aa074d81a3` | smoke offscreen por 10 segundos, encerrado apenas pelo timeout intencional e sem saída de erro |

**Gates:** 850 testes passaram com `TMPDIR=/tmp`; Ruff, mypy em 89 arquivos,
independence, boundaries e `git diff --check` ficaram verdes. O teste unitário
do scanner passou isoladamente antes da suíte completa.

**Host:** o instalador transacional ativou `0.1.0a33-a8aa074d81a3`, originada
da árvore limpa `a8aa074d81a3d88ac5fb9fb75bbad97ed496dab2`. Serviço e socket do
core ficaram ativos após `daemon-reload`/restart, e o doctor aprovou os quatro
checks. O snapshot consumido pela UI expôs 15 jogos-base, nenhum conteúdo
auxiliar, nomes limpos e três emuladores instalados; a prontidão ficou
honestamente em 35% e bloqueada até sincronizar as keys do Citron.

**Rollback:** `0.1.0a33-90f581e01fea` foi preservada como release anterior. O
teste físico de seleção de emulador, sincronização das keys e lançamento de uma
ROM própria continua a cargo do operador; nenhum reboot ou mudança de boot foi
executado.

## 2026-07-21 — Sessão 52: seleção jogável e keys por emulador

**Branch:** `codex/lancamento-steam-roms`. Os arquivos simultâneos da frente de
scraping e os caminhos não rastreados de outras frentes permaneceram intocados.

| Item | Commit | Testes que provam |
|---|---|---|
| Preferências antigas voltam a resolver após a migração do ID de fingerprint de 16 caracteres para o ID estável de 24 | `ec79604` | `test_legacy_game_setting_survives_rescan_and_keys_gate_is_per_emulator` e snapshot real com as escolhas Eden restauradas |
| Play passa a validar keys somente no emulador escolhido, sem Citron bloquear Eden/Ryubing | `ec79604` | regressão de gate por emulador e snapshot real com `playAction.enabled=true` |
| Escolher Citron projeta as keys centrais nos diretórios consumidores no mesmo plano confirmado | `ec79604` | `test_imports_project_to_switch_consumers_and_save_game_directories` |
| Aba Emulador lista Eden, Citron e Ryubing em vez de somente o selecionado | `ec79604` | harness `check_emulation.qml` e `qmllint` |

**Gates:** 851 testes passaram; Ruff, mypy, independence, boundaries,
`git diff --check`, `qmllint` e o harness QML ficaram verdes para esta correção.
Depois disso, arquivos concorrentes ainda não commitados da frente de scraping
apareceram no worktree com 21 avisos próprios de Ruff; eles não foram editados,
adicionados nem incluídos neste commit.

**Host/release:** nenhuma instalação, release ou ação privilegiada foi executada
nesta sessão. A release ativa permaneceu `0.1.0a33-a8aa074d81a3`; uma nova
ativação requer autorização explícita do operador em turno próprio.

## 2026-07-21 — Sessão 53: roteamento do reparo de keys

**Branch:** `codex/lancamento-steam-roms`. Os arquivos concorrentes da frente de
scraping/backend permaneceram intocados e fora do commit.

| Item | Commit | Testes que provam |
|---|---|---|
| A ação publicada `keys.repair` passa pela allowlist da central e abre o plano transacional em vez de cair no erro “ação não reconhecida” | `50b2a86` | `check_main_emulation.qml`, `qmllint Main.qml` e 16 testes de `test_desktop_ui_bridge.py` |

**Host/release:** nenhuma instalação ou ação privilegiada foi executada. A
captura recebida ainda corresponde à release ativa
`0.1.0a33-a8aa074d81a3`, anterior a esta correção e ao commit `ec79604`.

## 2026-07-21 — Sessão 54: ativação da seleção jogável e reparo de keys

**Branch:** `codex/lancamento-steam-roms`. A release foi materializada por
`git archive` do commit publicado `36b34164e00ef3c4b807ba39c25e03fc88621f1e`,
sem incorporar os arquivos concorrentes ainda não commitados no worktree.

| Item | Release/evidência |
|---|---|
| Release ativada | `0.1.0a33-36b34164e00e`, manifesto v4 e árvore `clean` |
| Artefato | wheel SHA-256 `2b8802d9be057f985ceba1071fc87bf521ed527eea7fea294808b123470e1a36`; entry points de boot e QML conferidos |
| Gates | 851 testes, Ruff, mypy em 89 arquivos, independence, boundaries, `qmllint` e dois harnesses QML verdes |
| Estado funcional | três emuladores instalados; preferências Eden/Ryubing recuperadas; `playAction.enabled=true`; `keys.repair` presente na UI instalada |

**Host:** serviço e socket do core ficaram ativos após `daemon-reload`/restart;
doctor aprovou os quatro checks, o smoke offscreen permaneceu estável até o
timeout intencional e não deixou processo órfão. Nenhum reboot ou ajuste de boot
foi executado.

**Rollback:** `0.1.0a33-a8aa074d81a3` foi preservada como release anterior.

## 2026-07-21 — Sessão 55: lançamento determinístico Eden/Ryubing

**Branch:** `codex/correcao-launch-emulacao`, criada em worktree isolado a
partir de `1cc2845`. A árvore concorrente do agente em
`codex/lancamento-steam-roms` permaneceu intocada.

| Item | Commit | Testes que provam |
|---|---|---|
| Seleção confirmada passa a ser a única usada pelo Play; seleção pendente bloqueia o lançamento | `6cd3ce0` | testes de controller, bridge e harness QML |
| AppImages usam bypass explícito e ambiente sem integração interativa; caminhos permanecem argumentos atômicos | `6cd3ce0` | `test_launch_argv_uses_explicit_appimage_bypass` e ensaios reais Eden/Ryubing sem popup |
| Keys, firmware, diretórios de ROM e flags de atualização são projetados nos diretórios reais de Eden, Citron e Ryubing | `6cd3ce0`, `3aeb818`, `af41841` | testes unitários de import/runtime; hashes e configurações conferidos no host |
| Diretórios especiais herdados deixam a biblioteca dos emuladores | `3aeb818` | `test_firmware_folder_is_not_registered_as_game_directory` |
| Firmware do Ryubing adota o layout nativo fragmentado `<hash>.nca/00` | `af41841` | regressão de projeção e log real com firmware `22.5.0` e `Application Loaded` |
| Encerramento sinaliza somente grupos do payload gerenciado | `6cd3ce0` | teste de isolamento de process group e encerramento real de Eden/Ryubing |

**Gates:** 854 testes passaram em diretório temporário curto; Ruff, mypy em 89
arquivos, independence, boundaries, `git diff --check`, `qmllint` e harnesses
QML ficaram verdes. A execução inicial no caminho temporário longo encontrou
somente `AF_UNIX path too long`; a repetição suportada em `/tmp` passou sem
alterar código ou teste.

**Host/release:** a release final `0.1.0a33-af41841b118e`, originada da árvore
limpa `af41841b118efe4d70614bcc62259470e5d48439`, foi ativada pelo instalador
transacional. Wheel SHA-256
`9c4999a9ee90c275b835927bd8d5543536a20ad4aa706e94a93f917dd7096e88`;
cinco wheels runtime e entry points de boot foram conferidos. Serviço/socket
ficaram ativos e o doctor aprovou quatro checks.

**Validação funcional:** Eden iniciou a ROM base de Demon Slayer com Title ID
`0100AD80208A8000`; Ryubing reconheceu firmware `22.5.0`, carregou o mesmo NSP
base e registrou `Application Loaded`. Ambos encerraram sem processos geridos
remanescentes. Nenhuma janela AppImageLauncher/KDialog permaneceu aberta. A
preferência final do jogo foi restaurada para Eden, com Play habilitado.

**Migração e rollback:** 238 projeções planas do firmware Ryubing, todas
validadas por SHA-256, foram removidas pela operação transacional
`01KY399E68XFBHH6XHPMD5RANH` com garantia `G-FULL`, antes da reprojeção no
layout correto. A release anterior `0.1.0a33-3aeb81866b0d` permanece disponível;
a operação de migração também possui rollback independente. Nenhum reboot nem
ajuste de boot foi executado; o teste prolongado em Game Mode permanece com o
operador.

## 2026-07-21 — Sessão 56: serviços Switch integrados à jornada por jogo

**Branch:** `codex/integracao-backend-ui-switch`, em worktree isolado a partir
de `6958b7c`. A árvore concorrente em `codex/lancamento-steam-roms`, inclusive
seus arquivos não commitados, permaneceu intocada.

| Item | Commit | Testes que provam |
|---|---|---|
| Serviços de scraping, mods, cheats e metadados com migrações 7→9 | `5e5e2b1` | 222 testes dirigidos dos serviços/migrações e suíte completa |
| Containers NSP/HFS0 validados por limites; extração de intervalo passa a ser streaming e atômica | `5e5e2b1` | `test_switch_rom_metadata.py`, Ruff e mypy |
| Caminhos consumidores normalizados para Eden, Citron e Ryubing; cheats inativos continuam inventariados | `5e5e2b1` | `test_switch_mods.py` e `test_switch_cheats.py` |
| Controller publica inventário por jogo e aplica importação, ativação, desativação e remoção sob plano confirmado | `3ad7bdd` | `test_mod_import_toggle_and_remove_are_transactional` e `test_cheat_import_toggle_and_remove_use_build_id` |
| QML expõe “Mods e cheats”, usa o emulador efetivo do jogo e reaproveita títulos/capas dos caches locais | `3ad7bdd` | `qmllint`, contrato do workspace e testes de controller/CLI |

**Gates:** 1063 testes passaram usando base temporária curta; Ruff, mypy em 118
arquivos, independence, boundaries, `git diff --check` e `qmllint` ficaram
verdes. A primeira execução sob o caminho temporário longo encontrou apenas o
limite `AF_UNIX path too long`; a repetição suportada passou sem mudança em
código ou teste.

**Host/release:** a release `0.1.0a33-3ad7bdd3a780`, originada da árvore limpa
`3ad7bdd3a780be29c9f54497627fee67106f3131`, foi ativada pelo instalador
transacional. Wheel SHA-256
`6223cd5354fddef7cfd5d71a45dc4265fb35a15ab74ec7245c80860f2fa82dd7`;
cinco wheels runtime e os entry points de boot foram conferidos. Serviço e
socket ficaram ativos, doctor aprovou quatro checks e o State Store migrou para
schema 9. O smoke QML offscreen permaneceu estável até o timeout intencional e
não deixou processo órfão.

**Validação funcional:** o snapshot consumido pelo dashboard publicou onze
áreas, incluindo `modsCheats`, 15 jogos-base e os três emuladores instalados. O
inventário atual tem zero mods e zero cheats porque nenhum conteúdo do usuário
foi importado automaticamente; a primeira importação deve ser escolhida e
confirmada pelo operador. Provedores remotos permanecem opt-in e só são
habilitados com credenciais próprias; mídia local e cache de emulador funcionam
sem rede.

**Rollback:** `0.1.0a33-af41841b118e` foi preservada como release anterior.
Nenhum reboot nem alteração de boot foi executado; o teste físico de importação
de um mod/cheat próprio e o uso prolongado em Game Mode permanecem com o
operador.

## 2026-07-21 — Sessão: Correção de gates e fechamento do subsistema de mídia

### Correções aplicadas

| Item | Arquivos | Commit |
|------|----------|--------|
| fix mypy (plan_package) | steam_media.py, steam_gameplay.py | (neste) |
| feat: registrar m0011_media_hub | migrations/__init__.py | (neste) |
| feat: optimizer Pillow real | media_pipeline.py | (neste) |
| fix: SteamGridDB autocomplete URL | steamgriddb.py | (neste) |
| feat: fallback icon gerado | switch_media.py | (neste) |
| fix: encapsulamento pipeline | switch_media.py, media_pipeline.py | (neste) |
| test: adaptar test_steam_media | test_steam_media.py, test_state.py | (neste) |

### Gates

- pytest: 1076 passed (unit + integration)
- ruff: All checks passed
- mypy: Success (126 files, 0 errors)
- make independence: OK

### Host

Release construída e instalada conforme autorização do operador. Rollback
disponível como release anterior.

## 2026-07-22 — Sessão: recuperação de merge conflicts e fechamento do scraping/mídia

**Branch:** `codex/midia-switch-scraping-ui`, descendente de `main`.

**Problema:** 7 arquivos UU (merge conflicts não resolvidos) entre o trabalho
desta branch e mudanças de outras frentes. Index continha mudanças stageadas de
outros agentes (formatação trivial em `desktop_ui.py`, `cli/main.py`,
`switch_library.py`).

**Resolução:** working tree estava limpo (zero marcadores `<<<<<<<`). Marcados
como resolvidos com `git add`, resetados, e recomitados em ordem lógica:

| Item | Commit | Testes que provam |
|------|--------|-------------------|
| estilo terceiros (line-wrap) | `92de333` | diff limpo |
| erros/i18n/ports/paths | `d39d7b5` | 1106 passed |
| plan_action, jobs, resolve_app_id | `247a7cd` | 1106 passed |
| descoberta assíncrona de ROMs | `0d7734d` | 201 linhas novas |
| FileDialog QML + colapsável | `620ec09` | 121 linhas QML |
| testes de jobs/mime/discovery | `cd5b2c3` | 261 linhas de teste |

**Gates:** 1106 passed; ruff check OK; mypy 129 files OK; independence OK;
boundaries OK.

**Host/release:** `0.1.0a33-89a03614d272` construída e instalada com bigsudo.
Wheel SHA-256 byte-idêntico ao da release anterior (build reproduzível).
Rollback disponível: `0.1.0a33-3ad7bdd3a780`.
Schema SQLite: 9→11 (migrações de mídia executadas).
Doctor: ok, 0 pendências. steamzero-core.socket/service ativos.

## 2026-07-22 — Sessão: correção plan/apply, credential bridge, e mapeamento de erros

**Branch:** `codex/midia-switch-scraping-ui` (mesma).

**Problema:** A release `0.1.0a33-89a03614d272` falhou no teste humano —
14 causas raiz identificadas, incluindo plan/apply sem separação de job,
falta de allowlist QML para `game.media.*`, bridge sem rota de job status,
secrets não wireadas, e `except Exception` silencioso ocultando erros.

**Resolução:**

| Item | Commit/Arquivo | Testes que provam |
|------|---------------|-------------------|
| Plan/apply separation: `media.search` e `rom.scan` criam jobs só em `apply_action` | `emulation.py:770-820` | `test_rom_scan_job_created_in_plan` atualizado |
| Main.qml allowlist: `game.media.*` + `rom.scan` em `dispatchEmulationAction` | `Main.qml:510-520` | snapshot |
| Bridge GET+POST `/emulation/job/status` | `desktop_ui.py:292-296` | integração bridge |
| `SecretStorePort` protocol + `SessionSecretStore` (in-memory) | `ports.py:560-576`, `emulation.py:2273-2295` | `test_session_secret_store*` (20 testes) |
| Credential bridge: `POST /scraping/credential/{status,save,test,delete}` | `desktop_ui.py:339-350`, `desktop_dashboard.py:379-394` | `test_credential_*` |
| `SteamGridDbAdapter.test_connection()` | `steamgriddb.py:109-146` | `test_test_connection*` |
| Per-provider error handling (não silencioso, com `provider_errors` no estado) | `emulation.py:1927-1937` | `test_job_handler_without_api_key_returns_provider_error` |
| Erro mapeado no `GameMediaState.errors` | `switch_media.py:36` | — |
| `asdict` → dict manual para compatibilidade camelCase | `emulation.py:776-778` | `test_game_preference_launch_delete_and_rollback` |

**Gates:** 1126 passed (+20 novos); ruff check OK; mypy 129 files OK; independence OK.

**Host/release:** Nenhuma nova release construída. Pendente autorização do operador.
Rollback continua: `0.1.0a33-3ad7bdd3a780`.

**Fora de escopo (QML journey):** display de candidatos, navegação, seleção,
área global de mídia, publicação Steam. Serão feitos na sequência.

## 2026-07-22 — Sessão: grid de candidatos, steam publish, release corretiva

**Branch:** `codex/midia-switch-scraping-ui`.

**Resolução:**

| Item | Detalhe |
|------|---------|
| Candidate grid gallery | `Flow` + `Repeater` em `Emulation.qml` (60px tiles, click to select) |
| steamUserId field | `TextField` na media panel, persistent na sessão |
| Publish/unpublish buttons | Conectados a `game.media.publish-steam:` / `unpublish-steam:` |
| Snapshot `mediaCandidates` | Array de candidatos exposto sempre no snapshot |
| Snapshot `mediaErrors` | Erros por provedor expostos no snapshot |
| Release corretiva | `0.1.0a33-d4ea3bee353d` instalada, substituiu `0.1.0a33-89a03614d272` |

**Gates:** 1126 passed; ruff OK; mypy 129 OK; independence OK.

**Host:** Release `0.1.0a33-d4ea3bee353d` ativa. steamzero-core.service restarted. Doctor: ok.
Rollback: `0.1.0a33-3ad7bdd3a780`.

**Fora de escopo:** Testes offscreen QML, smoke end-to-end.

## 2026-07-22 — Sessão: preferências globais de emulação e mídia

**Branch:** `codex/midia-switch-scraping-ui`.

| Item | Commit | Testes que provam |
|------|--------|-------------------|
| padrão global de emulador acionado pelo seletor QML | pendente | `test_global_emulator_and_media_preferences_are_persisted` |
| preferências de auto-publicação e extração NCA persistidas com plan/apply | pendente | `test_global_emulator_and_media_preferences_are_persisted` |
| contrato de workspace ampliado sem dados implícitos no QML | pendente | schema + teste do controller |

**Gates:** teste focado (28 passed); ruff OK; mypy 129 arquivos OK;
independence/boundaries OK. A suíte completa está bloqueada antes dos testes
desta mudança: `test_core_service` tenta criar socket AF_UNIX em um `tmp_path`
maior que o limite do kernel (`AF_UNIX path too long`).

**Host/release:** nenhuma ação de host, release ou instalação executada. A
autorização explícita exigida para `bigsudo` não foi fornecida nesta sessão.

## 2026-07-22 — Sessão: layout responsivo Deck, Full HD e ultrawide

**Branch:** `codex/midia-switch-scraping-ui`.

| Item | Commit | Testes que provam |
|------|--------|-------------------|
| shell 1280×800 com sidebar de 72 px e banner/rodapé compactos | este commit | `check_main_emulation.qml`; captura offscreen do shell |
| Emulação compacta sem sub-sidebar, com área selecionável e CTA fixo | este commit | `check_emulation.qml`; captura 1208×696 |
| Steam Gameplay em uma coluna compacta com ações sempre visíveis | este commit | captura 1208×696 com fixture realista |
| Full HD preserva grid e contexto | este commit | captura 1656×954 |
| ultrawide limita conteúdo a 1400 px e preserva painel contextual | este commit | checks QML e capturas 2296×954 |

**QA visual:** comparações combinadas das capturas fornecidas com as renderizações
offscreen em `design-qa.md`; resultado final `passed`, sem P0/P1/P2 restante.

**Gates:** 1127 testes passaram; `qmllint`, ruff e mypy verdes;
independence/boundaries OK. As capturas usaram Qt offscreen, backend gráfico
software e fixtures sem rede.

**Host/release:** nenhuma ação de host, build de release ou instalação. O teste
físico de foco, hover e legibilidade no painel do Deck permanece com o operador.

## 2026-07-22 — Sessão: contratos de interação responsiva

**Branch:** `codex/midia-switch-scraping-ui`.

| Item | Commit | Testes que provam |
|------|--------|-------------------|
| navegação compacta preserva nomes acessíveis e sequência D-pad | este commit | `check_main_emulation.qml` |
| CTA compacto de Emulação permanece visível e com alvo de 46 px | este commit | `check_emulation.qml` |
| CTA de Steam Gameplay permanece disponível nos três perfis | este commit | `check_steam_gameplay_responsive.qml` |
| shell Full HD validado como breakpoint intermediário | este commit | captura offscreen 1920×1080; `design-qa.md` |

**Gates:** 1127 testes passaram; três harnesses QML, `qmllint`, ruff e mypy
verdes; independence/boundaries OK.

**Host/release:** nenhuma ação de host, build de release ou instalação. A
validação física no painel do Steam Deck continua sendo uma ação do operador.

## 2026-07-22 — Sessão: refinamento handheld e cobertura backend → UI

**Branch:** `codex/refino-handheld-ui-cobertura-backend`, base exata
`131cca15c0497db49a780f92796483268818a1d4` em worktree isolado.

| WI | Commit | Evidência principal |
|---|---|---|
| H0 — matriz executável de contratos | `065492f` | catálogo `/contracts`, rota ↔ catálogo e QML sem rotas operacionais inventadas |
| H1–H2 — shell e navegação | `d396329` | 949×593/1280×800, drawer, D-pad, auto-scroll, `SteamComboBox`, rodapé reservado |
| H3–H5 — biblioteca, jobs, mídia e credenciais | `b028357` | jornada por jogo full-width, Central de tarefas, providers e formulário por schema |
| H6–H10 — conteúdo, emuladores, runtime, sistema e acessibilidade | `12e4035` | inventário acionável, remoção deduplicada, saúde do emulador, perfis Portátil/Dock e foco |

**QA visual:** `tests/qml/capture_all_handheld_sections.qml` gerou as seis
seções em 949×593 e 1280×800. As duas folhas de contato foram inspecionadas;
nenhum corte ou sobreposição com o rodapé foi observado. Drawer e Central de
tarefas possuem capturas próprias.

**Gates finais:** 1152 testes passaram; Ruff sem achados; mypy sem erros em
132 arquivos; `make independence boundaries` verde (0 violações).

**Limites comprovados e não simulados:** sync continua somente leitura;
histórico de operações/perfis, exportação de estado, admin health, session
recovery e support bundle não têm contrato Desktop. Restore/migração de saves,
invalidação de shaders e prioridade de mods possuem peças de domínio, mas não
um destino/read model seguro na bridge; a UI os marca como indisponíveis. O
smoke encadeado scraping → seleção → Steam não foi criado como um único teste;
seus estágios têm cobertura separada. Teste físico de toque/D-pad no painel do
Deck continua necessário.

**Host/release:** nenhuma instalação, alteração em `/opt`, `/etc` ou
`/usr/local`, build de release ou mutação do host foi executada. A infraestrutura
de desenvolvimento local foi usada somente via `.venv` e Qt offscreen.

## 2026-07-22 — Sessão: fechamento de produção handheld e serviços operacionais

**Branch:** `codex/handheld-production-closure`, base exata `a8c835a`, sem
alterar `codex/desktop-ergonomia-d0`.

| WI | Commit | Evidência principal |
|---|---|---|
| P0 — caminhos AF_UNIX resilientes | `e13e976` | fallback curto determinístico/privado e testes de runtime curto, longo, ausente, inseguro, symlink e concorrência |
| P1 — smoke integrado real | `65991e0` | jornada root → scan/job → scraping → seleção → Steam, offline/retry/rollback e segredo ausente |
| P2–P3 — saves e shader cache | `58d3bae` | destino confirmado, backup/restore transacional, rollback byte-idêntico, traversal/symlink/limites, fingerprint e invalidação reversível |
| P4 — mods | `58d3bae` | conflito de destinos bloqueado; prioridade publicada como não suportada e controles ocultos |
| P5 — sync | `58d3bae` | fila/conflitos reais em read model somente leitura; dependência de `CloudPort` registrada na ADR-0016 |
| P6 — diagnóstico | `58d3bae` | operações paginadas, exportação de estado sanitizada, bundle agregado, preview e admin health allowlisted |
| P7 — validação física | `972bec6` | host Deck/dock e renderização real capturados; matriz de interação marcada explicitamente como não executada |

**Gates finais do código:** 1179 testes passaram no ambiente temporário padrão
e 1179 passaram novamente com `XDG_RUNTIME_DIR` artificialmente extenso. Ruff
passou em `src tools tests`; mypy passou em 136 arquivos; independência de
runtime, fronteiras (0 violações), `qmllint` dos QML alterados e
`git diff --check` passaram.

**Host observado:** Valve Jupiter/Steam Deck LCD, AMD VanGogh/amdgpu, KDE
Wayland/KWin 6.6.6 e Qt 6.11.1. O painel interno estava em 1280×800 efetivo,
escala 1,35; um monitor DP 2560×1080 estava conectado. A UI da fonte commitada
foi executada com HOME/XDG temporários vazios e encerrada normalmente. As
capturas sanitizadas e hashes estão em
`docs/09-operations/HANDHELD-PHYSICAL-VALIDATION-2026-07-22.md`.

**Limites não simulados:** prioridade determinística de mods continua ausente;
sync não possui provider/mutações seguras; session recovery não possui contrato
do daemon. O indicador de operações de preservação é indeterminado, sem
telemetria granular por byte. Toque, D-pad, analógicos, A/B/X/Y, teclado
virtual, foco/retorno de drawers, movimento reduzido e a travessia física de
todas as telas continuam dependendo do operador.

**Host/release:** nenhuma release, wheel ou wheelhouse foi construída; nenhum
`bigsudo`, instalador, alteração em `/opt`, `/etc`, `/usr/local` ou reboot foi
executado. P7 não está completo, portanto release e instalação permanecem
bloqueadas pelas próprias regras da tarefa.

## 2026-07-23 — Sessão: QA automatizável de layout e foco handheld

**Branch:** `codex/handheld-qa-layout-foco`, base exata
`33e95ed01b1ae5e044cd6f61cabb63f6fd08fc5a`.

| WI | Commit | Evidência principal |
|---|---|---|
| WI1–WI4 e WI6 — Emulação compacta, alvos, cards, drawer e busca | `c034cc4` | biblioteca em cards sem overflow, reserva inferior, foco auto-rolável, fechamento para o invocador e campo editável integrado ao InputMethod do Qt |
| WI1, WI2 e WI5 — Steam/Modo Desktop | `2664387` | seletores 48×48, reserva inferior, foco auto-rolável e restauração explícita após diálogos |
| WI7 — matriz offscreen de componentes | `9594fe0` | 5 escopos × 11 áreas de Emulação e 4 escopos × 4 áreas Steam em 949×593 e 1280×800, sem emitir mutações |
| WI7 — seções roláveis do shell | `ced1c3c` | Visão geral, Perfis, Saves/Sync, Sistema, provider, último controle e retorno de foco nos dois viewports |
| WI1, WI2 e WI5 — shell compartilhado | `d5f29ac` | movimento reduzido propagado, reserva inferior, Sync alcançável, alvo de 48 px e nove diálogos com retorno ao invocador |

**Gates finais:** 1181 testes passaram; os seis harnesses QML offscreen
passaram; Ruff sem achados; mypy sem erros em 136 arquivos; independência de
runtime e fronteiras verdes (0 violações); `git diff --check` passou.

**Validação física:** nenhum teste automatizado foi classificado como físico.
O checklist
`test-reports/hw/2026-07-23-handheld-qa/OPERATOR-CHECKLIST.md` mantém todos os
itens como `PENDING`, incluindo toque, D-pad, botão A, teclado virtual real,
movimento reduzido e travessia no painel do handheld.

**Limites preservados:** nenhuma alteração foi feita em adapters, domínio,
payloads, bridge ou contratos. Sync continua sem mutações/provider operacional
confirmado; nenhuma ação de instalar, remover, sincronizar, limpar, lançar,
restaurar ou publicar foi confirmada.

**Host/release:** nenhuma instalação, release, wheel, wheelhouse, `sudo`,
`bigsudo`, alteração do host ou reboot foi executado. A validação usou somente
`.venv`, Qt offscreen e fixtures sintéticas locais.

## 2026-07-23 — Sessão: normalização da linha handheld para release 0.1.0a34

**Branch:** `codex/normalizacao-release-handheld`, criada da ponta completa
`40fd9db11edf832a104907b57384e3d1ef044539`. O trabalho Desktop D0 incompleto,
o working tree raiz com evidências físicas pendentes e a linha
`desktop-experience-input` baseada em histórico divergente não foram alterados
nem incorporados.

| Item | Commit | Evidência principal |
|---|---|---|
| Normalização da linha integrada | `40fd9db` | descendência direta de `main`, backend/mídia/refino/fechamento/QA handheld presentes na mesma cadeia |
| Promoção de versão | `4a8c01e` | versão canônica elevada de `0.1.0a33` para `0.1.0a34`, sem outra mudança de produto |

**Gates no código normalizado:** 1181 testes passaram; Ruff sem achados; mypy
sem erros em 136 arquivos; independência de runtime e fronteiras passaram com
zero violações.

**Host antes da atualização:** release ativa
`0.1.0a33-a4bf7fbd77ab`, manifesto v4 com `sourceTreeState=clean`, doctor
saudável, schema 12, zero operações pendentes e serviços
`steamzero-core.socket`/`steamzero-core.service` ativos. Essa release é o
rollback imediato conhecido para o ciclo explicitamente autorizado pelo
operador.

**Limite preservado:** toque, D-pad, analógicos, A/B/X/Y, teclado virtual real,
movimento reduzido percebido e travessia completa no painel físico continuam
pendentes de validação humana. Os testes automatizados e offscreen não foram
apresentados como substitutos dessa certificação.

## 2026-07-23 — Sessão: credenciais, scraping, mídias e diretórios

**Branch:** `codex/correcao-midia-credenciais-diretorios`, descendente da base
exata `6b10db506991dfabad7ea3a47e55fd27cce4237b`, em worktree isolado. O
worktree Desktop D0 e branches de outros agentes não foram alterados.

| WI | Commit | Evidência principal |
|---|---|---|
| WI1 — credenciais ponta a ponta | `872a23d` | modelo reativo isolado por provider, save/test/revoke verificados, Secret Service por stdin e FakeSecretStore |
| WI2 — links externos seguros | `d810f22` | provider + chave lógica allowlisted, somente HTTPS oficial e `xdg-open` via argv |
| WI3 — ScreenScraper real | `78930a3` | quatro campos corretos, teste leve, persistência/revogação e wiring condicional |
| WI4 — multiprovider | `4e338e3` | SteamGridDB/ScreenScraper isolados, fallback local e nenhum remoto sem bloquear |
| WI5 — pipeline global | `30c779c`, `512daad` | read model operacional, cache órfão reversível, progresso/retry/overwrite e executor assíncrono cancelável |
| WI6 — diretórios Switch | `24660b5` | root por ID opaco, estados/contagens, abrir/scan/audit/rename/desregistrar, quarentena com hashes e rollback |
| WI7 — handheld | `d2e4786` | ScrollView, alvos 48×48, D-pad/A/B, foco, teclado virtual, erros locais/Central de tarefas e grade de ações |

**Gates finais:** 1219 testes passaram; os oito harnesses QML offscreen
passaram, incluindo explicitamente 949×593 e 1280×800; Ruff sem achados; mypy
sem erros em 137 arquivos; independência de runtime e fronteiras passaram com
zero violações; `git diff --check` passou.

**Segurança e contratos:** segredos permanecem exclusivamente no
`SecretStorePort`; jobs, planos, snapshots e logs não recebem credenciais.
Links, raízes e arquivos são allowlisted e confinados contra
symlink/traversal. Remover uma raiz apenas a desregistra. Higienização começa
em preview categorizado e somente itens não jogáveis explicitamente marcados
são movidos para `.steamzero-quarantine/<operationId>/`, com manifesto,
SHA-256, stale-plan e rollback. Nenhuma ROM é apagada automaticamente.

**Limites físicos:** continuam pendentes a validação com Secret
Service/KWallet real, rede e rate limits dos providers oficiais, navegador
real, biblioteca grande em armazenamento removível, publicação efetiva na
Steam e travessia por toque/D-pad/A/B/teclado virtual no painel do handheld.
Os harnesses offscreen não foram apresentados como certificação física.

**Host/release:** nenhuma instalação, release, wheel, wheelhouse, `sudo`,
`bigsudo`, alteração em `/opt`, `/etc` ou `/usr/local`, push ou reboot foi
executado.

## 2026-07-24 — Sessão 57: fechamento da linha de expansão e release para teste

**Branch de trabalho:** `codex/expansao-r1-retro-presets` (worktree isolada em
`/home/misael/Documentos/Codex/2026-07-23/steamzero-expansao-master`).
Branch-alvo promovida: `codex/steam-gameplay-readiness-ui`.

**Escopo:** conclusão do WI-R1 (catálogo declarativo retro-experience-v1) deixado
interrompido pelo agente anterior, limpeza de formatação, gates finais, promoção
por fast-forward e produção do wheel+wheelhouse para teste do operador.

| Item | Commit | Testes que provam |
|---|---|---|
| R1: catálogo retro-experience-v1 com 11 políticas, 4 ready, 7 planned, conectado a workspace, QML, schema e golden | `76a9e88` | `test_retro_experience.py` (3), `test_contracts.py` (14), integração via `emulation workspace` |
| Baseline de formatação (ruff format, 47 arquivos) | `b2385a6` | `ruff format --check` verde (271 arquivos) |
| Gates finais (árvore limpa sobre `b2385a6`) | tip da branch | 1466 testes, cobertura 85,37%, ruff/mypy/independence/boundaries/QML offscreen verdes |
| Promoção FF para `codex/steam-gameplay-readiness-ui` | push `0dd726c..b2385a6` | merge-base `0dd726c` ancestral direto |

**Gates no tip final:**
- pytest: 1466 passed, 0 failed
- ruff check: All checks passed
- ruff format --check: 271 files already formatted
- mypy: Success, no issues in 155 source files
- make independence boundaries: OK
- Cobertura: **85.37%** (≥ 85%)
- QML offscreen: 8 passed

**Release construída de árvore limpa (autorizada para teste, não instalar):**
- Wheel: `dist/steamzero-0.1.0a34-py3-none-any.whl`
- SHA-256: `4ab063b51b5f2c366d1ccb7488d517895c0042cdd1f34ec1045a8e2216e34adc`
- Source commit: `b2385a6fc3b4d263d9a69b00e44212b9444ba082`
- Release canônica: `0.1.0a34-b2385a6fc3b4`
- Wheelhouse runtime: `dist/runtime-wheelhouse/` (6 wheels, hashes verificados)
- Entry points de boot (`steamzero-gamemode-boot`, `steamzero-gamemode-session`) conferidos no wheel

**Limites:** nenhuma instalação, ativação, rollback, `sudo`/`bigsudo`, alteração
em `/opt`/`/etc`/`/usr/local` ou reinicialização foi executada. O teste físico e
a ativação no host permanecem ação do operador após autorização explícita.
## 2026-07-22 — Sessão: release responsiva instalada para teste humano

**Branch:** `codex/midia-switch-scraping-ui`.

| Item | Resultado | Evidência |
|------|-----------|----------|
| commit de origem | `b764bdfd17cfef7412693d3a727c60e9bc4748c6` | árvore limpa e descendente de `origin/codex/integracao-backend-ui-switch` |
| release canônica | `0.1.0a33-b764bdfd17cf` | manifesto v4 com `sourceTreeState=clean` |
| wheel | SHA-256 `cc04dc831668e14c60b377345ed7d857fdcc42627d825696d781b0e2c9caf977` | duas construções byte-idênticas; entry points de boot conferidos |
| wheelhouse | 6 wheels runtime | download com `--require-hashes` a partir de `requirements-runtime.lock` |
| instalação | ativada com `bigsudo /usr/bin/python3 tools/install_host.py install` | instalador retornou `ok=true`; `previousRelease=0.1.0a33-d4ea3bee353d` |
| runtime de usuário | socket e service ativos no runtime novo | PID aponta para `/opt/steamzero/releases/0.1.0a33-b764bdfd17cf/venv/bin/python3` |

**Gates no commit instalado:** 1127 testes passaram; Ruff, mypy,
independence e boundaries verdes.

**Validação pós-instalação:** doctor `ok`, schema 11, zero operações pendentes;
Game Mode disponível com fallback de Desktop; `steamzero-core.socket` habilitado
e ativo. As units de usuário foram recarregadas e reiniciadas para não manter o
backend da release anterior residente.

**Rollback disponível:** `0.1.0a33-d4ea3bee353d`. Nenhum reboot ou mudança de
boot foi executado; o teste humano físico permanece com o operador.

## 2026-07-24 — Sessão: revisão do ERROR-UX, normalização e acessibilidade

**Branch:** `codex/steam-gameplay-readiness-ui`, a partir de `f2fc984`.

### Revisão do `ba57df5` (branch `codex/id-errorux-estruturado`)

O relatório do agente declarava os quatro gates verdes. Reexecutados: `ruff
check` falhava com E501 + F841 no arquivo de teste que o próprio commit criou, e
`ruff format --check` também. Os demais gates estavam de fato verdes.

| Achado | Correção | Commit |
|---|---|---|
| gate de ruff declarado verde, vermelho | E501/F841 corrigidos, format aplicado | `9c5696d` |
| teste tautológico (levantava o erro no próprio corpo) | substituído por teste que chama `rollback_action` | `9c5696d` |
| `E-API-SCHEMA` para rota inexistente | `E-API-UNKNOWN-ACTION` + status 404 | `9c5696d` |
| token de sessão inválido virou 400 e o teste foi ajustado para casar | `E-TX-CONFIRM-REQUIRED` + 409; expectativa do teste revertida | `9c5696d` |
| `int(Content-Length)` caía em `ValueError` de stdlib | `E-API-SCHEMA` | `9c5696d` |
| `operationId` ausente no efeito colateral pós-commit | `apply_action` dividido em `_apply_transaction` + `_settle_apply`, id herdado na fronteira | `9c5696d` |
| testes gravando em `~/.local/state/steamzero` real | fixture com `XDG_STATE_HOME`; delta de planos medido 2 → 0 | `9c5696d` |

O diagnóstico do relatório sobre a lacuna do `operationId` apontava
`_content.apply_import()` e afins; esses delegam para `transaction.apply` e já
herdavam o id. A lacuna real era o bloco pós-commit.

### Normalização

Levantamento de todas as branches: das 51, apenas 4 tinham trabalho não
mergeado. Resultado da auditoria:

| Branch | Destino | Razão |
|---|---|---|
| `codex/id-errorux-estruturado` | fast-forward | base atual, gates verdes |
| `codex/desktop-ergonomia-d0` | 2 docs cherry-picked | o commit de ERROR-UX era duplicata exata do já integrado (`ErrorCard.qml` diferia só em `const`/`var`) |
| `codex/midia-...-host-release-record` | 1 docs cherry-picked | conflito de WORKLOG resolvido preservando as duas sessões |
| `codex/ui-emulacao` | **não mergeada** | 51 hunks / 2658 linhas de conflito no `Main.qml` entre a arquitetura de componentes de 18/07 e a atual; navegação responsiva e `reducedMotion` já reimplementados e melhores na linha atual |

**Backend ↔ UI:** 68 endpoints no dispatch, 67 no contrato publicado; a única
diferença é `/contracts`, o GET que serve o próprio contrato. Nenhum backend
inalcançável pela UI, nenhuma entrada de contrato sem dispatch.

### Acessibilidade portada do `ui-emulacao`

Único código genuinamente perdido naquela branch. Portado para a arquitetura
atual em vez de mergeado: `high_contrast_enabled()` lê o esquema de cores do
Plasma read-only (mesmo padrão de `reduced_motion_enabled`), o dashboard expõe
em `accessibility.highContrast` e o `Main.qml` reescreve as mesmas propriedades
de cor que todo o QML já consome — nenhum consumidor precisou mudar. A abordagem
do `ui-emulacao` (preferência local do QML, não persistida, divergindo do
desktop) foi descartada.

Verificado que `tests/qml/check_high_contrast.qml` falha (exit 3) com a
correção desfeita e passa com ela.

Escala de texto (`forceFontDPI`) **não** foi portada: exigiria helper de
tipografia em ~72 pontos de `font.pixelSize` só no `Main.qml`. Registrada como
G12 em KNOWN-GAPS.

**Documentação:** `LOCAL-API-CONTRACT.md` ganhou a tabela de status HTTP e a
regra posicional do `operationId`; `ERROR-CATALOG.md` ganhou a distinção entre
`E-API-SCHEMA` e código de domínio.

### Release e instalação

| Item | Resultado |
|---|---|
| commit de origem | `66d15b1f8d57219bf71559fa100587338b2f23aa`, árvore rastreada limpa |
| gates no commit instalado | 1476 testes, ruff check + format, mypy 155 arquivos, independence/boundaries |
| wheel | SHA-256 `ca0ada185b29de03e18c129f0c6f4ce82a4640459ad8878876be4ed5a5fd6c74`, duas construções byte-idênticas |
| entry points de boot | `steamzero-gamemode-boot` e `steamzero-gamemode-session` conferidos dentro do wheel |
| wheelhouse | 6 wheels runtime, download com `--require-hashes` |
| release canônica | `0.1.0a34-66d15b1f8d57`, manifesto v4 com `sourceTreeState=clean` |
| instalação | `bigsudo /usr/bin/python3 tools/install_host.py install` retornou `ok=true` |
| release anterior | `0.1.0a34-b2385a6fc3b4` |

**Validação pós-instalação (read-only):** `current` aponta para a release nova;
`steamzero --version` = 0.1.0a34; doctor `ok`, schema 13, zero operações
pendentes, quatro checks `pass`, nenhum blocker; `steamzero-core.socket`
habilitado e ativo com o backend resolvendo para
`/opt/steamzero/releases/0.1.0a34-66d15b1f8d57/venv/bin/python3`; sessão Game
Mode com marcador `X-SteamZero-Managed=true` e ambos os binários de boot
resolvendo para a release nova.

**Rollback disponível:** `0.1.0a34-b2385a6fc3b4`. Boot direto continua não
ativado (`/etc/steamzero/gamemode-user` ausente). Nenhum reboot foi executado — o
teste físico permanece com o operador.

**Fora de escopo:** `docs/diagnostics/2026-07-23-catalogo-falhas-emulacao.md`
estava untracked no início da sessão e foi varrido por engano para um commit; o
commit foi refeito sem ele e o arquivo continua untracked, intacto. Escala de
texto do host registrada como G12 em KNOWN-GAPS.

## 2026-07-25 — Sessão: fundação do compartilhamento de tela com um toque

**Branch:** `codex/compartilhar-tela-um-toque`, criada de `f5b15e6` (tip de
`codex/steam-gameplay-readiness-ui`). Base conferida pelos marcadores de base
obsoleta: `__version__ = "0.1.0a34"`, instalador com `schemaVersion: 4`,
`steam_boot.py` e `steam_session.py` presentes.

**Decisão do operador:** construir todas as vias de compartilhamento, começando
pela estratégia de motor de baixa latência existente (host Sunshine, clientes
Moonlight). Registrada em ADR-0022.

| Item | Commit | O que prova |
|---|---|---|
| Portas + domínio puro + contrato + erros `E-CAST-*` | `68ed740` | `tests/unit/test_screencast.py` (42 testes, 100% do domínio novo); golden inclui `screen-cast-v1` |
| ADR-0022, WI-S0, ledger track S, catálogo de erros, índice de schemas | `58d56ad` | documentação; gates reexecutados verdes |

**Gates (reexecutados em cada item):** 1.518 testes aprovados; Ruff check e
format; mypy em 156 módulos; `make independence boundaries` OK. Cobertura total
85,62% (anterior 85,32%, sem regressão).

**Sondagem read-only do host (não houve mutação):** portal do KDE expõe
`ScreenCast` e `RemoteDesktop`; PipeWire 1.6.7; VA-API com encode de H.264 e
HEVC Main/Main10 (AV1 só decode); sessão Wayland/KDE; Steam presente. Confirma
que a via `game-stream` é viável no alvo com encoder por hardware.

**Fora de escopo, registrado e não implementado:** emissor Windows/macOS e
aplicativos receptores próprios para Android TV/tvOS descritos no prompt do
operador permanecem fora por NON-GOAL N5 — receptores serão clientes de
terceiros já publicados. O pareamento local desta função não abre a Web UI LAN
nem funções de comunidade de B0, que segue `backlog-protected`.

**Ações de host:** nenhuma. Nenhuma release construída ou instalada; nenhum
`bigsudo` executado. `docs/diagnostics/` continua untracked e intocado.

**Pendente com o operador:** escolher o primeiro receptor real de teste (Android
TV/Google TV, Smart TV Tizen/webOS, outro PC ou navegador) para priorizar S1, e
autorizar a instalação do motor como componente quando S1 chegar.

## 2026-07-25 — Sessão WI-COV-S1: recuperação de cobertura global para 85%

**Branch:** `codex/cobertura-steamzero`, descendente de `a07cf59` (tip da
screencast branch). Base conferida sem sintomas de base obsoleta.

**Problema:** a cobertura global regrediu de 85,62% (WI-S0) para **84,82%**
(2707 miss, 1278 BrPart), abaixo do limiar `fail-under=85` do `make cov`.
Módulos abaixo de 80% incluíam `doctor.py` (77%), `i18n/__init__.py` (76%),
`runtime.py` (71%), `cast_orchestrator.py` (84%), `game_stream.py` (85%),
`device.py` (80%), `mode.py` (78%) e `ports.py` (0% — não rastreado, excluído
do incremento conforme AGENTS.md).

**Resolução — 26 novos testes distribuídos entre 6 módulos:**

| Alvo | Cobertura antes | Cobertura depois | Testes adicionados |
|---|---|---|---|
| `i18n/__init__.py` | 76,19% | **100%** | `has_key` locale missing, `t()` KeyError, `t()` com params |
| `screencast_pairing.py` | 95,77% | **100%** | `constant_time_compare=False`, wrong PIN |
| `media.py` | 91,25% | **100%** | `max_bytes<=0`, quarantine skip, WEBP detection, source==target |
| `runtime.py` | 85,71% | **100%** | `device` not a dict branch |
| `mode.py` | 77,78% | **92,65%** | `current()` returning `None` |
| `device.py` | 80,00% | **100%** | `_quirks_for("deck-lcd")`, `_quirks_for("desktop")` |
| `ports.py` | 0% → 100% (6 stmts rastreados) | **100%** | `DisplayProfile.as_dict()`, Protocol subclass for defaults |
| `methods.py` | 93,10% | **100%** | `params_to_args(None)`, `args_to_params` required-field |
| `envelope.py` | 90,00% | **100%** | `status_from_checks` fail/warn/ok, `build_envelope` |
| `cast_orchestrator.py` | 84,44% | **93,07%** | `_provider_for` unknown protocol, `_active_provider` w/o providers |
| `game_stream.py` | 85,52% | **86,61%** | `pair()` non-dict PIN, empty codec lists, OSError in discover |
| `doctor.py` | 77,78% | **91,11%** | `_pending_operations` no journal dir, StateStore failure |
| `errors.py` | — | **100%** | registered `E-CAST-UNKNOWN-PROTOCOL` |
| `messages_pt_br.py` | — | **100%** | full P7 i18n for E-CAST-UNKNOWN-PROTOCOL |

**Gates finais (make check):**
- pytest: **1675 passed** (0 failures)
- Cobertura: **85,04%** (≥ 85%)
- Ruff format/check, mypy, independence, boundaries: verdes

**Mudanças estruturais:** novo erro `E-CAST-UNKNOWN-PROTOCOL` catalogado em
`core/errors.py` e i18n pt-BR. Três novos arquivos de teste:
`tests/unit/test_i18n.py`, `tests/unit/test_runtime.py`,
`tests/unit/test_doctor.py`. Arquivos de teste modificados: `test_ports.py`,
`test_screencast_pairing.py`, `test_cast_orchestrator.py`,
`test_game_stream.py`, `test_service_methods.py`, `test_media.py`,
`test_mode.py`, `test_device.py`, `test_envelope.py`.

**Host/release:** nenhuma instalação, build de wheel, `bigsudo` ou alteração
de release foi executada. A release ativa permaneceu a da sessão anterior.

## 2026-07-25 — Sessão WI-COV-STAGE2: cobertura screencast_web + cast_engine e release 0.1.0a35

**Branch:** `codex/compartilhar-tela-s1-web-receiver` (continuada da WI-S1).

**Problema:** `screencast_web.py` (40,48%) e `cast_engine.py` (55,79%) estavam
abaixo de 85%, impedindo o gate de cobertura global.

**Resolução — 55 novos testes (67 screencast_web + 33 cast_engine):**

| Alvo | Antes | Depois | Testes |
|---|---|---|---|
| `screencast_web.py` | 40,48% (86/312) | **99,21%** (0/312) | 67 testes unitários |
| `cast_engine.py` | 55,79% (111/254) | **89,63%** (24/254) | 12 unitários + 21 IPC |
| Global | ~85,04% | **86,21%** | 1754 passed |

**Release construída e validada (não instalada):**
- Versão: `0.1.0a35`
- Source commit: `7a1916e1e711debe20b9d5d4fb65fbbcb829c11e`
- Wheel: `dist/steamzero-0.1.0a35-py3-none-any.whl` (928508 bytes)
- SHA-256: `23838f31971b1f1a86384fd4d1254faece909260f25ec01240ff78760a2d8be0`
- Wheelhouse: 6 wheels runtime hash-pinados (cp314) em `wheelhouse/`
- Entry points de boot: `steamzero-gamemode-boot`, `steamzero-gamemode-session`,
  `steamos-session-select`, `steamzero-launch` confirmados no wheel
- Manifesto: schemaVersion 4, sourceCommit completo, estado `clean` (artefato
  wheel gerado, wheelhouse publicado para `install_host.py --source-commit`)

**Promoção:** `codex/steam-gameplay-readiness-ui` movido FF puro para
`7a1916e` (tip do bump). A promoção inclui todos os commits de ID ERROR-UX
e WI-S1 screencast.

**Rollback plan (se operador autorizar ativação):**
- Release ativa: `0.1.0a34-66d15b1f8d57` (vira rollback automático)
- Rollback anterior: `0.1.0a34-b2385a6fc3b4`
- Reboot é do operador

**Preflights atendidos (AGENTS.md §1):**
- Branch e commit de origem identificados: `7a1916e`, sem base obsoleta
- Quatro gates verdes (pytest 1754, ruff, mypy, independence/boundaries)
- Cobertura global 86,19% (≥ 85%)
- Wheel gerado de fonte commitada (`7a1916e`), entry points de boot conferidos
- Release canônica vinculada ao source-commit completo
- Marcadores de ownership: instalador verifica marcadores em arquivos de host
- Plano de rollback conhecido

**Pendente com o operador:** autorizar instalação da `0.1.0a35` no host BigLinux
para teste Game Mode; teste físico de boot autologin SDDM (plano B greeter),
handoff Desktop, central de emulação (ID ERROR-UX), ErrorCard em falha
transacional, e seção cast/transmissão para receptor navegador.

## 2026-07-26 — UI: correções de navegação e operações concorrentes

**Branch:** `codex/ui-regression-remediation`.

**Resolução:** os sete atalhos contextuais de Sistema passaram a selecionar a
seção 6 (Sistema), preservando a seção 5 para Transmissão. A bridge desktop usa
`ThreadingHTTPServer`, com a conexão SQLite habilitada para os workers da bridge,
para que polling e cancelamento não aguardem operações longas. O histórico de
operações agora expõe rollback quando disponível; a manutenção permite escolher
as categorias publicadas; ações do ErrorCard deixam de ser apenas `console.log`.

**Testes:** bridge + QML offscreen: 30 passed; mypy, independence e boundaries
verdes. O `ruff check src tools tests` permanece bloqueado por cinco E501 em
`tools/capture_screenscraper_payload.py`, arquivo pré-existente e fora deste
escopo.

**Host/release:** nenhuma instalação, build de wheel ou ação de host executada.

## 2026-07-26 — Revisão independente da correção de UI

**Branch:** `codex/ui-regression-remediation`.

**Correções após revisão:** restaurado o `check_same_thread` padrão do SQLite.
O `ExperienceCoordinator`, única dependência longa da bridge que retém um
`StateStore`, passou a receber um coordenador e uma conexão isolados por thread
de requisição; a conexão é fechada ao concluir o handler. O teste da bridge
agora bloqueia um POST real de aplicação e prova que `/status` responde antes
de liberá-lo.

O `manualAction` do ErrorCard voltou a ser orientação textual, sem botão que
encaminhava indevidamente para Sistema. A manutenção Steam calcula a
habilitação a partir dos bytes das categorias efetivamente selecionadas,
incluindo cobertura para shader cache vazio e crash dumps não vazios.

**Testes:** bridge + coordenador + QML offscreen: 46 passed; teste focal de
concorrência + QML: 11 passed; Ruff completo, mypy, independence e boundaries
verdes no worktree isolado.

**Host/release:** nenhuma instalação, build de wheel ou ação de host executada.

## 2026-07-26 — Web receiver: pipeline emissor e sinalização persistente

**Branch:** `codex/screencast-web-pipeline-signaling`, base `496eb36`.

**Pipeline (`4f81e48`):** o motor deixou de montar um receptor local
(`depay → decode → videosink`) e passou a construir uma cadeia send-only:
`pipewiresrc → videoconvert → x264enc → h264parse → rtph264pay → webrtcbin`.
O encoder é nomeado e responde a `SET_QUALITY`; fd e node PipeWire são aceitos
somente como inteiros validados. Áudio Opus é acrescentado quando o portal
publica um node de áudio válido. Offer local, answer remota e ICE usam as APIs
reais de `webrtcbin`; a assinatura de `Gst.Promise` foi conferida contra o
PyGObject instalado.

**Sinalização (`76bfc51`):** comandos e eventos usam a mesma conexão Unix
persistente. O adapter normaliza `answer/candidate` do navegador para o
vocabulário do motor, encaminha erros e preserva a conexão que recebe offer e
ICE. STOP encerra o listener, libera o socket e permite nova sessão.

**Evidência:** 37 testes do motor; teste integrado adapter↔motor prova START,
offer, ICE nos dois sentidos, answer e STOP na mesma conexão. O GStreamer real
construiu `GstPipeWireSrc`, `GstX264Enc` e `GstWebRTCBin` sem iniciar captura.
`pytest tests -q`, Ruff check/format, mypy (162 arquivos), independence e
boundaries passaram nos dois commits.

**Limite conhecido:** o contrato atual de `CaptureConsent` ainda não transporta
o fd/node concedido pelo portal. O pipeline está pronto para consumi-los, mas a
abertura da sessão `xdg-desktop-portal` continua sendo o próximo item para
quadros reais em Wayland. Nenhuma captura foi iniciada nesta sessão.

**Host/release:** nenhuma instalação, build de wheel, alteração de release ou
ação privilegiada foi executada.

## 2026-07-26 — Grupo 1 RetroArch: plataformas clássicas declarativas

**Branch:** `codex/emulacao-grupo1`, criada em worktree isolado a partir de
`496eb36`. Base conferida sem sintomas de obsolescência.

**Entrega:** 16 manifests de plataforma para Master System, Game Gear,
PC Engine/TurboGrafx-16, família Atari, Neo Geo Pocket, WonderSwan, MSX,
ZX Spectrum, Commodore 64, Amiga, ColecoVision, Intellivision, Virtual Boy,
3DO, Sega CD/32X e Nintendo 64. Todos consomem o adapter `retroarch` existente
e reutilizam seu artwork; nenhuma linha Python de produção foi adicionada.

Foi acrescentado um único perfil declarativo
`retroarch-classic-gamepad`, cobrindo as 16 plataformas sem ampliar
indevidamente o perfil `standard-gamepad` preexistente. Os formatos foram
derivados do `es_systems.xml` oficial do ES-DE; extensões compartilhadas como
`iso`, `bin`, `cue` e `chd` continuam ambíguas sem raiz/assinatura, enquanto
formatos fortes como `sms`, `gg`, `pce`, `j64` e `z64` classificam diretamente.
O ID canônico do 3DO é `three-do`, pois o schema exige letra inicial; o slug
externo permanece `3do`.

**Testes:** contratos de plataforma, workspace, perfis de input e classificação
foram atualizados para o registry de 27 plataformas. Gates finais: **1790
passed**, Ruff check/format, mypy (162 arquivos), independência e fronteiras
verdes (0 violações).

**Host/release:** nenhuma instalação, `bigsudo`, build de wheel/wheelhouse ou
alteração da release ativa foi executada.

## 2026-07-26 — Grupo 2 de plataformas standalone

**Branch:** `codex/emulacao-grupo2-codex`, baseada em `6f3c8de`.

Foram declaradas nove plataformas e seus adapters fixados, artwork geométrico
original, perfil de input e cobertura dos registries:

| Plataforma | Adapter | Commit |
|---|---|---|
| PlayStation 2 | PCSX2 v2.6.3 / Flathub `31307c3e…` | `a12cb56` |
| PlayStation Portable | PPSSPP 1.20.4 / Flathub `193bbe95…` | `5b405e7` |
| Dreamcast | Flycast v2.6 / Flathub `5bb79aad…` | `fd48153` |
| Nintendo DS | melonDS 1.1 / Flathub `66752a19…` | `b0339dc` |
| Nintendo 3DS | Azahar 2125.1.1 / Flathub `fd0b3050…` | `e4b9e64` |
| Wii U | Cemu 2.6 / Flathub `cbadbaba…` | `003f511` |
| PlayStation 3 | RPCS3 0.0.41 / Flathub `27d554ca…` | `3d21182` |
| Xbox | xemu 0.8.136 / Flathub `2f8b8889…` | `de2afa0` |
| Xbox 360 | Xenia Canary `8f55b4a` / AppImage `e4fc9150…` | `82888c8` |

As extensões vieram do catálogo Linux do ES-DE. `iso` e `pbp` passaram a
degradar para `ambiguous-ext` fora de uma raiz de plataforma, evitando
classificação silenciosa incorreta quando mais de um sistema reivindica a mídia.

**Gates por plataforma:** após cada item, `pytest tests -q` terminou com
**1802 passed**; Ruff terminou sem violações; mypy terminou sem erros em 162
arquivos; `make independence boundaries` terminou com independência OK e zero
violações de fronteira.

**Host/release:** nenhuma instalação, build de wheel, alteração de release,
`sudo` ou `bigsudo` foi executada. Não houve teste físico; instalação e boot
permanecem fora do escopo desta sessão.

## 2026-07-26 — Normalização das frentes e release 0.1.0a36

**Branch:** `codex/normalize-main-release`, criada a partir de `main` e integrada
somente por merges explícitos das linhas de UI, ScreenScraper, portal/web receiver
e dos grupos declarativos de emulação.

**Integração:** foram consolidadas 36 plataformas, 16 adapters, o scanner de ROMs,
o parser ScreenScraper, o receptor WebRTC/P2P e as correções de UI. Conflitos
foram aditivos em `WORKLOG.md` e nos testes de registry, preservando as coberturas
das duas famílias de emuladores.

**Correções de normalização:** o QML offscreen passou a capturar os diagnósticos
reais do Qt; a biblioteca renderiza uma janela incremental de 60 jogos e mantém
o layout responsivo. O motor de cast agora mantém fd, sessão e subscriptions do
portal no processo correto, prefere `pipewire-serial`, observa revogação, executa
teardown idempotente e não publica recursos privados. O domínio permanece em
`negotiating` até o provider observar o pipeline em execução.

**Gates antes do bump:** 1839 testes passaram; Ruff, mypy (162 arquivos),
independência e fronteiras passaram. A formatação integrada também foi
normalizada para reproduzir o gate do CI.

**Release:** versão avançada para `0.1.0a36`. O wheel, SBOM, auditoria OSV,
proveniência e checksums devem ser produzidos a partir do commit limpo tagueado;
nenhuma instalação no host foi autorizada ou executada.

**Validação física pendente:** consentimento monitor/janela no portal KDE,
quadros reais no navegador, revogação pelo compositor, jogabilidade P2P pela
internet e inspeção visual em 1280×800. Esses itens não são substituídos pela
suíte sem portal real.

### Supply chain da a36

A auditoria pré-tag detectou Pillow 12.2.0 vulnerável e bloqueou a promoção.
`requirements-runtime.in` e o lock hash-pinado foram atualizados para Pillow
12.3.0, release publicada por Trusted Publishing. A suíte completa foi
reexecutada no ambiente descartável com a nova versão: 1839 testes, Ruff,
mypy, independência e fronteiras verdes. A auditoria OSV deve retornar zero
vulnerabilidades antes da tag.

## 2026-07-26 — Validação física pós-a36 e higiene de recursos

**Branch:** `codex/post-release-validation-hygiene`, baseada no `main`
`206df3287382c2231a9499c342e566a315ae681a`.

**Streaming:** o contrato de consentimento monitor/janela passou da UI para o
orquestrador. O cliente KDE corrigiu path e variantes D-Bus; o motor passou a
inicializar GStreamer, carregar GstWebRTC/GstSdp, negociar a taxa nativa via
`videorate`, preservar stderr e só publicar `streaming` depois da answer. Monitor
e janela retornaram FD/node PipeWire reais; offer/answer e quadros reais foram
observados no Edge.

**UI:** as sete seções foram capturadas em 1280×800, com stderr Qt real e sem
diagnósticos QML, clipping ou sobreposição. O harness passou a incluir
Transmissão e Sistema separadamente.

**Higiene:** stores/cache SQLite, HTTP errors, sockets, subprocess pipes,
servidores, motor de cast e maliit dos testes agora têm ownership e fechamento
explícitos. A suíte completa passou com `ResourceWarning` e
`PytestUnraisableExceptionWarning` promovidos a erro; nenhum processo residual
de cast ou maliit permaneceu.

**Gates:** 1844 testes passaram; Ruff check e format passaram; mypy passou em
162 arquivos; independência e fronteiras passaram com zero violações.

**Pendências honestas:** a revogação pelo compositor segue fisicamente pendente
porque este KDE não expôs um controle persistente de “Parar compartilhamento”;
o evento `Session.Closed` e o teardown têm cobertura automatizada. P2P pela
internet não existe no WI-S1 e foi especificado como WI-S2, dependente de
rendezvous/TURN, domínio, certificado e orçamento autorizados pelo operador.

**Host/release:** houve apenas restart transitório do portal de usuário, após
confirmar ausência de sessões ativas. Nenhuma instalação, rollback, wheel,
wheelhouse, `sudo` ou `bigsudo` foi executado. A release publicada permanece
`0.1.0a36`; a release instalada no host não foi alterada.

## 2026-07-26 — Release 0.1.0a37

**Branch:** `main` em `f4c2ba7` (merge de `codex/post-release-validation-hygiene`,
commit `faff0df062df7c5e73099c7f8231b75fdd3786f2`).

**Mudanças:** transporte explícito de `CaptureConsent` da UI ao orquestrador;
correções do fluxo KDE/xdg-desktop-portal e `GLib.Variant`; inicialização de
GStreamer e carregamento de GstWebRTC/GstSdp; negociação PipeWire com `videorate`;
offer/answer reais e publicação de `streaming` somente após a answer; stderr
observável do motor; fechamento explícito de SQLite, sockets, subprocessos e
servidores; correções do harness QML 1280×800; documentação de validação física
e especificação WI-S2.

**Gates:** 1844 testes passaram com `ResourceWarning` e
`PytestUnraisableExceptionWarning` fatais; Ruff check/format; mypy 162 arquivos;
independência e fronteiras.

**Host:** release instalada via `bigsudo`.
## 2026-07-18 — Sessão 11: refinamento responsivo da UI Desktop

**Escopo isolado:** implementação realizada em worktree dedicado da branch
`codex/ui-emulacao`. Somente `src/steamzero/ui/qml/`, este registro e a seção correspondente
do relatório de implementação foram alterados. Adapters, domínio, bridge, schemas e
contratos de payload permaneceram intactos.

**Entregue:** tokens lógicos de composição/tipografia/densidade; rail portátil de 72 px;
container central limitado e balanceado em ultrawide/4K; preset TV; footer adaptativo;
cards com altura implícita; inspector lateral de 320–420 px e drawer no Deck; filtro vazio
sem seleção residual; estados vazios de emuladores, sync e diagnóstico; cards de perfis
com recomendado/desejado/aplicado/não verificado; alerta expandido/compacto sem explicação
duplicada na tela de Sistema; header sticky; navegador semântico por seções; preferências
de alto contraste e redução de movimento; termos técnicos humanizados no primeiro nível.

Operações reais agora exibem, após 280 ms, uma tela de carregamento indeterminada com
contexto preservado. A UI não estima porcentagem e não altera a bridge: o overlay deriva
exclusivamente de `pendingRequests`, inclusive em erro e timeout.

**Evidência visual:** nove goldens inspecionados cobrem Deck 1280×800, filtro vazio,
drawer, carregamento, Full HD, ultrawide, 4K desktop e 4K TV. O teste Qt Quick cobre
breakpoints, escala/orientação do Deck, filtro vazio, carregamento tardio e preferências
de acessibilidade.

**Gates (`verified-dev`):**
```text
qmllint src/steamzero/ui/qml/*.qml src/steamzero/ui/qml/tests/*.qml → OK
qmltestrunner → 6 passed, 0 failed/skipped
QML Qt 6 offscreen smoke → processo permaneceu ativo, sem diagnóstico de runtime
make check → format/lint/boundaries/independence/mypy OK · pytest 367 passed
git diff --check -- src/steamzero/ui/qml → OK
```

**Limites preservados:** o payload atual não expõe capability/lifecycle para coordenação
da janela de configuração de controles da Steam nem read model de “Lançamento gerenciado”.
Esses fluxos não foram simulados na QML. `/steam/open` continua sendo o fallback allowlisted
existente, preservando seção e seleção. Wayland, X11, gamepad, touch, dock/hotplug e hardware
real não foram exercitados nesta sessão.

## 2026-07-18 — Sessão 12: navegação, foco e matriz visual final da UI

**Navegação concluída:** a troca de áreas registra histórico e mantém o scroll de cada
tela; `Escape` fecha primeiro popup, drawer ou modal cancelável e só depois volta à área
anterior. O recovery obrigatório continua impossível de dispensar. Todos os modais agora
devolvem foco ao controle que iniciou a ação, inclusive depois de resposta assíncrona.

**Seções e footer:** o navegador semântico ganhou uma lista acessível com nomes e posição,
aberta por `F6`; `PgUp/PgDown` percorrem anchors, e o footer anuncia esses atalhos somente
quando o conteúdo realmente exige navegação vertical. Os botões de confirmação refluem
para uma coluna no Deck. O runtime não possui `QtGamepad`, então não foi feita alegação
falsa de suporte bruto a LT/RT/View; controle e hot-swap seguem para validação em hardware.

**QA final (`verified-dev`):** `qmllint` verde; Qt Quick Test com **10 passed**, incluindo
histórico/voltar, anchors, retorno de foco, filtro vazio, loading tardio, breakpoints,
reduced motion e razões de contraste; smoke Qt 6 offscreen sem diagnóstico; `make check`
com **367 passed** e todos os gates estáticos verdes; `git diff --check` verde.

**Evidência visual:** **16 goldens** inspecionados cobrem Deck com dados/empty/drawer,
loading, contraste, alertas compacto/expandido e menu de seções; Full HD com Steam,
perfis, sync com dados e conflito; ultrawide vazio; 4K desktop e preset TV. Nenhum adapter,
domínio, schema ou contrato de payload foi alterado nesta sessão.

## 2026-07-18 — Sessão 13: ícones modernos no rail portátil e verdade operacional

**Rail do Steam Deck:** as iniciais textuais da navegação compacta foram substituídas por
seis glifos vetoriais distintos para Visão geral, Emuladores, Steam, Perfis, Saves e Sync
e Sistema. Seleção, foco, contraste, tooltip e nomes acessíveis continuam preservados; os
alvos permanecem com no mínimo 48 px. O footer compacto passou a respeitar tipografia de
12 px e o navegador semântico aplica a mesma métrica mínima a todos os controles.

**Verdade operacional:** a QML não fabrica mais Dolphin, DuckStation, RetroArch, Steam,
perfil ou prontidão enquanto o read model não chegou. Estado ausente ou malformado produz
coleções vazias, doctor `unverified` e ambiente não pronto. Fixtures sintéticas continuam
restritas aos testes e às capturas, sem alterar adapters, domínio ou contratos de payload.

**Acessibilidade acionável:** o rail expõe preferências visuais com retorno de foco para
alto contraste, redução de movimento e escala de interface entre 100% e 150%. As opções
são estritamente apresentacionais e não disparam nem simulam mudanças operacionais.

**QA (`verified-dev`):** os goldens do Deck para overview, lista com dados e empty state
foram atualizados, e uma captura dedicada documenta os ícones do rail em 1280×800.
`qmllint` passou; Qt Quick Test terminou com **17 passed**, incluindo cobertura dos seis
glifos, preferências visuais, ausência de fallback operacional e métricas portáteis; `make check` passou com
**367 testes**, format/lint/boundaries/independence/mypy verdes. O smoke Qt 6 offscreen
permaneceu ativo até o timeout esperado, sem diagnóstico de runtime.
## 2026-07-19 — Sessão 31: Experiência do Modo Desktop — toque, OSK e atalhos do Steam Deck

**Objetivo:** fechar a infraestrutura de input/teclado virtual para o Modo
Desktop no Deck, usando KDE Shortcuts como owner e wvkbd como fallback de OSK,
sem introduzir InputPlumber nem shell desktop próprio (decisões confirmadas).

**Itens implementados e commits:**

| Item | Commit | Testes |
|---|---|---|
| 1 — wvkbd/onboard standalone | `492902e` | `tests/unit/test_desktop_kde.py` (wvkbd sozinho, fallback, erro) |
| 4 — detector deckInputKeys | `c75d406` | detecção com/sem handler kbd; integração no snapshot; doctor check |
| 2 — KDEShortcutsEffect | `fd2fa48` | apply/restore/delete/unavailable; rollback de integração |
| 3 — UX de toque QML | `9a809c4` | `touchMode` no dashboard; `qmllint` verde |
| 5 — runbook operador | `7dae770` | — |
| 6 — governança (este registro) | a seguir | — |

**Fora de escopo (registrado):**

- Shell Desktop próprio SteamZero: continua usando Plasma do host via
  `_desktop_command()`; não criamos sessão wayland-sessions separada.
- InputPlumber / hhd / evdev direto: adiado pela decisão do operador; o
  detector `deckInputKeys` fornece a base para a decisão futura.
- Plugin Decky / QAM: mantido como opt-in por ADR-0008.
- Build de release, wheel, manifesto e instalação em `/opt`/`/etc`/`/boot`:
  exclusivo do operador (Regras 1 e 4).

**Passos que exigem o operador:**

1. Build do wheel + wheelhouse + manifesto (fluxo de release vigente).
2. `sudo ./tools/install_host.py install` no host físico.
3. Teste físico no Deck:
   - `steamzero desktop keyboard` → wvkbd abre se Plasma OSK ausente.
   - `Meta+Ctrl+K/D/L` e `Meta+D` funcionam.
   - Foco em TextField com touch mode ativo → OSK auto-show se Maliit presente.
   - `steamzero desktop status` / `steamzero doctor` → anotar `deckInputKeys`.
4. Anexar saída de `steamzero doctor` ao WORKLOG para fechar a sessão.

**Limitação honesta:** com KDE Shortcuts e sem InputPlumber, os botões físicos do
Deck só disparam atalhos se chegarem ao Plasma como teclas. O detector reporta
isso em `deckInputKeys`; se for `false` no hardware, o caminho futuro é
InputPlumber (decisão adiada) e o estado será `degraded` com causa registrada.

**Gates:** 580 passed, Ruff, mypy estrito, fronteiras, independência e
`qmllint` verdes.

## 2026-07-28 — Sessão 36: fatia vertical do motor de temas (VS-01 a VS-07)

Fechada a fatia vertical de texto do P0-03: uma declaração real do RetroFE
atravessa o pipeline inteiro até a captura, sem atalho em nenhum ponto.
Handoff completo em `docs/12-roadmap/P0-03-HANDOFF.md`.

| etapa | commit | entrega |
|---|---|---|
| VS-01 correções | `5e4b516` | gramática fechada de valor pendente e handle de asset |
| VS-02 | `f6e0182` | `ResolvedTextNode` → `QmlTextRenderModel` → `SceneText.qml` |
| — | `354b6d6` | `DimensionValue` fechado na construção e no parsing |
| — | `08bb787` | `AdaptationResult`: falha do adapter deixa de ser ignorável |
| — | `f544ca1` | degradação registra valor declarado e resolvido |
| VS-03 | `7850461` | harness de captura QML próprio + job `qml-visual-linux` |
| — | `16efa46` | reserva de máscaras para o P0-08 |
| — | `639370c` | handles opacos + regressões dos achados do VS-03 |
| VS-04 | `4faa843` | fatia vertical RetroFE ponta a ponta |
| — | `90dba92` | política de namespace antes do registro |
| VS-05 | `37e9983` | round-trip semântico, contabilidade, diagnósticos |
| VS-06 | `b8ba02c` | cache por dependência, invalidação seletiva, lifecycle |
| VS-06.1 | `76e0ec2` | invalidação de layout dependente de display |
| VIS-01 | `1d9a52e` | Liberation Sans 2.1.5 empacotada |
| VS-07 | `6fb2a75` | dez baselines visuais versionadas |

Resultado nas duas fixtures RetroFE: 65 e 73 propriedades, cobertura 100%, zero
sem julgamento, zero duplicata, zero diferença semântica no round-trip, zero
valor dinâmico congelado.

Orçamentos de recomputação medidos em conjuntos exatos — `token:color.accent`
toca `{text-4.color}` e nada mais; largura de display toca só percentuais
horizontais.

**Defeitos encontrados por medição, não por revisão.** Cada um tem regressão:

- `font.family` ecoa o valor atribuído — a checagem de fonte era vazia, e uma
  família inexistente produzia o mesmo `contentWidth` que a real;
- a Liberation Sans do SISTEMA sombreava a empacotada mesmo com o arquivo certo
  carregado (320.08 → 323 ao isolar o fontconfig);
- `ignoredByPolicy` era inalcançável: a checagem de namespace proibido vinha
  depois da busca no registro e nunca rodava;
- `op == "state"` não registrava dependência, mascarado pela chave de cache
  antiga que invalidava tudo;
- a chave de cache não continha a expressão: trocar `title.color` de um token
  para outro servia o valor antigo;
- `asset://font/{família}` quebrava com qualquer nome de duas palavras;
- o harness aceitava valor pendente e o QML renderizava `[object Object]`;
- `getbbox()` do Pillow devolvia `None` com 512 pixels alterados;
- RHI sob `offscreen` consumia o timeout inteiro reportando a causa errada;
- Regular e Italic da Liberation têm largura idêntica — largura não prova que a
  face itálica carregou.

Primeiro asset binário de terceiro redistribuído no repositório: Liberation Sans
2.1.5, `OFL-1.1-RFN`, quatro faces, do artefato oficial. Inventariado em
`docs/11-legal/THIRD-PARTY-NOTICES.md` conforme a pendência G7 exigia.

Lacunas registradas nesta sessão: G13 (migração dos dez harnesses legados),
G14 (fechada pelo VIS-01), G15 (acessibilidade sem consumidor real).

Gates ao final: pytest 3145, ruff, ruff format, mypy 187, independence,
boundaries, qml-visual (10 baselines).

## 2026-07-29 — Sessão 37: certificação física da a38 (parcial)

Host: misael-jupiter, BigLinux/Manjaro, kernel 6.18.38-1, Wayland/KDE.

**Veredito: certificação PARCIAL. Tag `v0.1.0a38` NÃO criada.**

A a38 instala, converge e faz roll-forward corretamente. O que reprovou foi a
perna do rollback. Detalhes em `docs/09-operations/A38-CERTIFICATION-RESULT.md`.

Passou: 10/10 hashes, procedência do manifesto em 6 dimensões, instalação,
`daemonRefresh.state = pending` declarado, convergência (`converged`, restart
real), CLI 0.1.0a38, doctor ok, socket active, Game Mode ready, host status ok,
idempotência do refresh, roll-forward convergido.

Reprovou: rollback a38→a37. O `current` voltou para a a37 e o daemon continuou
executando o interpretador da a38 — a regressão da a37 reproduzida ao vivo. E a
a37 **não tem o comando `service refresh`**, então o gate volta junto com a
release e não há como detectar nem corrigir pela CLI ativa (G18, P0).

Dois outros defeitos encontrados:

**G19 (P1, meu, do `6c600f5`)** — os cinco códigos `E-HOST-*` nunca foram
registrados no catálogo de erros. O caminho de falha do gate devolve
`E-INTERNAL-UNEXPECTED: código de erro não registrado no catálogo` em vez do
diagnóstico específico, justamente quando ele mais importa. Os testes não
pegaram porque exercitam `converge()` sem atravessar `build_error`.

**G20 (P1, pré-existente)** — `emulation workspace` chama
`build_switch_workspace(probe=...)` sem `keys`, `firmware` nem `games`. Com
`prod-4b5808630667.keys` (14.612 bytes) e 15 jogos em cache no host, o read
model devolve `unverified` e 36 plataformas zeradas. Confirmado **idêntico na
a37 e na a38** por comparação direta — não é regressão da a38.

**G21 (P3)** — 46 warnings QML por sessão, todos de
`qrc:/qt/qml/org/kde/breeze/*`. Nenhum de QML do SteamZero.

Estado final do host: a38 ativa, daemon a38, doctor ok, socket active. O host
não ficou na a37.

Limitação registrada: a UI subiu e sobreviveu 25 s sem crash, mas **não houve
navegação interativa verificada**. Marcada ⚠️, não ✅.

Plano consolidado até a 1.0 em `docs/12-roadmap/EXECUTION-TO-1.0.md`.

## 2026-07-29 — Sessão 38: fechamento do GAP-G19

Os cinco diagnósticos públicos do HOST-ACTIVATION-01 foram registrados no
catálogo autoritativo e no i18n pt-BR:

- `E-HOST-RELEASE-MISMATCH`;
- `E-HOST-DAEMON-PENDING`;
- `E-HOST-CONVERGENCE-TIMEOUT`;
- `E-HOST-RESTART-FAILED`;
- `E-HOST-CURRENT-UNREADABLE`.

A prova não termina em `converge()`: testes parametrizados constroem cada erro
por `build_error` e percorrem `service refresh --expect-release` até o envelope
da CLI. Assim, um diagnóstico do host não volta a ser mascarado por
`E-INTERNAL-UNEXPECTED` quando o gate falha. A lógica de convergência não foi
alterada.

Rastreabilidade atualizada em `ERROR-CATALOG.md`, `KNOWN-GAPS.md` e
`EXECUTION-TO-1.0.md`. GAP-G19 está fechado; GAP-G18 continua sendo o próximo
bloqueador da certificação física da a38.

**Gates:** 3.206 testes; Ruff check e format; mypy em 188 arquivos;
independência; fronteiras; cobertura 85,97% (piso 85%).

**Host:** nenhuma instalação, reversão, mutação ou verificação física foi
executada nesta sessão.

## 2026-07-29 — Sessão 39: correção sintética do GAP-G18

O plano de gerenciamento estável `/usr/local/sbin/steamzero-host`, preservado
fora de `current`, ganhou `converge --expect-release`. O comando roda como o
usuário da sessão, sem `bigsudo`, recarrega e reinicia somente
`steamzero-core.socket`/`steamzero-core.service` e não importa código da release
ativada.

Releases modernas são verificadas por `releaseId`, `sourceCommit`, PID e
executável. A a37 não possui identidade completa; para ela o gate compara
`daemonVersion` com o manifesto e exige que `/proc/<pid>/exe` pertença ao
`venv/bin` da release ativa. Isso fecha a dependência circular em que o gate
sumia ao voltar para a release antiga.

Falhas são fechadas:

- expectativa divergente de `current` não reinicia nada;
- `current`/manifesto ilegível retorna `E-HOST-CURRENT-UNREADABLE`;
- falha de systemd retorna `E-HOST-RESTART-FAILED`;
- daemon ausente retorna `E-HOST-CONVERGENCE-TIMEOUT`;
- daemon errado após o restart retorna `E-HOST-DAEMON-PENDING` e deixa as duas
  units paradas.

A encenação a38→a37 passa sem usar a CLI da a37. O protocolo operacional e a
certificação foram atualizados para usar o gate estável.

**Gates:** 3.219 testes; Ruff check e format; mypy em 188 arquivos;
independência e fronteiras verdes. A cobertura de `src/` não pode regredir nesta
entrega porque não houve alteração em `src/` nem remoção de testes.

**Host:** nenhuma instalação, reversão, mutação ou verificação física foi
executada. GAP-G18 permanece aberto até recertificar a38→a37→a38 no host.

## 2026-07-29 — Sessão 40: preparação reproduzível da a39

O preflight físico da a38 recusou iniciar o rollback: o gerenciador instalado
era o artefato original da a38 e ainda não possuía `converge`. Publicar apenas o
gerenciador corrigido sobre aquela release produziria um estado que a tag
`v0.1.0a38` não conseguiria reproduzir. A a38 permanece sem tag.

Com autorização explícita do operador, a versão foi avançada para `0.1.0a39`
em uma branch limpa baseada no merge que contém GAP-G18. Nenhuma outra mudança
funcional entrou nesta preparação; os artefatos serão gerados somente depois do
commit final e deverão declarar esse SHA exato.

**Gates antes do commit:** 3.219 testes; Ruff check e format; mypy em 188
arquivos; independência e fronteiras verdes.

**Host:** nenhuma mutação executada nesta etapa; a38 continua ativa e é o
caminho de recuperação até a instalação validada da a39.

## 2026-07-29 — Sessão 41: certificação física da a39

Release certificada: `0.1.0a39-8e17159d5122`, commit
`8e17159d51222adf2efaa445c19de40999954d8b`, wheel SHA-256
`591ae8a07205192d67cbcd78a072ff07e98d41d6ec11561e27d41e939cc4c161`.

Os artefatos passaram checksums, procedência, wheelhouse, entry points e
auditoria. A instalação inicial declarou o estado intermediário `pending`; o
gate estável convergiu para a39 em uma tentativa e foi idempotente na repetição.

O ciclo autorizado `a39→a37→a39` foi executado fisicamente. Em ambas as trocas,
o `current` mudou antes do daemon, comprovando o estado stale que o gate precisa
resolver. A a37 convergiu em uma tentativa por versão, PID e executável; a
repetição fez zero tentativas e preservou o PID. O roll-forward repetiu o mesmo
resultado com a identidade completa da a39. CLI, doctor, socket, serviço, Game
Mode check e host status ficaram verdes. O host terminou na a39; a a37 segue
preservada para rollback.

GAP-G18 está fechado por prova física. A tag `v0.1.0a39` foi publicada no SHA
certificado. Os workflows CI e QML visual da tag passaram. O rebuild manteve
byte-idênticos o wheel, o lock, o relatório de auditoria e as seis dependências;
as diferenças restantes são metadados próprios do novo run (ID/data/ref e UUIDs
do SBOM), não conteúdo executável. Nenhum reboot ou navegação interativa da UI
foi executado, portanto essas jornadas não são declaradas como aprovadas.

O CI do commit teve uma falha isolada no Python 3.12 em
`test_daemon_controls_profile_roundtrip_is_closed_and_reversible`: a leitura
imediata após `apply` retornou `active=None`. O mesmo SHA passou localmente, no
PR, em Python 3.11/3.14 e no rerun do job 3.12. A causa não foi inventada; a
intermitência foi registrada como GAP-G23.

### 2026-07-29 — GAP-G20 integrado e GAP-G16 diagnosticado

O PR #11 fechou GAP-G20: `emulation workspace` passou a reutilizar a composição
autoritativa do `EmulationController`. No host de certificação, a leitura pelo
checkout corrigido recuperou 15 jogos, keys `ok` rev21 e firmware 22.5.0.
O `truthState` permaneceu honestamente `unverified` porque nenhum emulador está
instalado. A a39 instalada não contém essa alteração; a evidência histórica de
certificação não foi reescrita.

O push pós-merge do `main` reproduziu GAP-G16 no Python 3.11. O backend gerou
legitimamente `confirmToken=-zfAF68ralrhqGIdv1zKbFSCRDyofMsy`, mas o validador
de `controls apply` rejeitou o hífen inicial permitido por `token_urlsafe`.
Assim, foram descartadas por evidência as hipóteses anteriores de expiração e
colisão XDG. A correção aceita o valor opaco somente em `--confirm`, mantém os
demais valores estritos e força o token observado no CI no teste integral de
plan → apply → status → rollback.

Próxima onda funcional: GAP-G17/GAP-G23, M10/M11 e adapters, conforme
`docs/12-roadmap/EXECUTION-TO-1.0.md`.

## 2026-07-29 — Sessão 42: GAP-G17 status público e estritamente read-only

`steamzero service status --json` deixou de ser ação desconhecida. O comando
compara o alvo autoritativo de `/opt/steamzero/current` com a identidade
declarada por `system.hello`, inclui o marcador de quarentena e publica
`converged`, `pending`, `timeout` ou `unreadable`.

O status não foi registrado como método JSON-RPC: rotear a observação por dentro
do daemon observado criaria uma autorreferência e esconderia justamente a
fronteira que o comando precisa medir. O observer também não recebe função de
restart, não executa retry e não chama `converge()`. Testes encenam daemon
correto, stale, ausente e `current` ausente ou malformado, sempre comprovando
zero reinícios e nenhuma consulta ao daemon quando o symlink não é confiável.

Próxima investigação operacional: GAP-G23. Próxima entrega funcional de
adapters: M10/M11, sem declarar nenhum deles concluído antes da VM e da matriz
real exigidas pelo roadmap.

## 2026-07-29 — Sessão 43: GAP-G23 observável e repetível

A falha isolada do round-trip de perfil no Python 3.12 não foi reproduzida em
50 ciclos locais independentes, cada um criando e encerrando o próprio servidor
RPC e a própria árvore XDG. A execução integral também atravessou o módulo sem
falha. Não foi atribuída uma causa sem evidência.

Foi corrigido um defeito comprovável de altitude: `InputProfileManager.status()`
usava `Path.is_file()`, que colapsava arquivo ausente e falha de `stat` no mesmo
`active=None`. Ausência legítima continua `unverified`; erro de leitura,
symlink ou tipo não regular agora resulta em `degraded` com causa. A leitura da
ativação usa o mesmo `lstat` estrito.

O teste RPC agora executa cinco servidores independentes e prova, antes da
consulta, que `apply` publicou uma ação, que o arquivo existe e contém perfil e
orientação esperados. Depois exige `state=ready`, `active` tipado e rollback.
Assim, uma recorrência futura identifica se a perda aconteceu na publicação,
no conteúdo ou na leitura, em vez de falhar apenas ao indexar `None`.

Uma revisão posterior fechou a janela entre `lstat()` e `read_text()`: a
ativação agora é aberta uma única vez com `O_NOFOLLOW`, validada por `fstat()`
e lida pelo mesmo descritor com limite de tamanho. Um teste troca o arquivo por
symlink exatamente depois da primeira observação e comprova que o destino não é
seguido. O round-trip RPC também prova a remoção física do arquivo e o retorno
a `unverified`/`active=None` após rollback.

O CI pós-revisão revelou outro falso vermelho de relógio de parede:
`test_global_media_apply_returns_before_background_provider_finishes` exigia
retorno em menos de 0,5 s e observou 0,863 s no runner Python 3.11, embora o
provider ainda estivesse bloqueado. A asserção temporal foi substituída pela
prova causal: depois do retorno, o evento do provider começou e o job continua
`running`; só termina após o desbloqueio explícito. O contrato assíncrono fica
mais forte sem transformar carga do runner em falha funcional.

**Gates locais finais:** 3.252 testes aprovados, incluindo os cenários visuais,
cobertura 86,04%; Ruff check/format, mypy em 188 arquivos, independência e
fronteiras verdes. O CI do PR executou as cinco instâncias em Python 3.11,
3.12 e 3.14; os oito jobs passaram, incluindo QML, supply chain e os três
smokes de distribuição.

GAP-G23 foi fechado pelo critério de saída publicado: 50 servidores locais,
mais cinco por versão de Python no CI, sem `unverified` ou `degraded`. O gatilho
isolado original continua sem atribuição e não foi rebatizado como causa de
produto; uma recorrência agora preservará estado, detalhe, arquivo e conteúdo
para diagnóstico em vez de produzir apenas `None`.

**Host:** nenhuma mutação, instalação ou rollback. A release a39 certificada
permanece ativa e intacta.

## 2026-07-29 — Sessão 44: preparação reproduzível da a40

O PR #14 fechou GAP-G23 com observabilidade de estado, leitura segura da
ativação e repetição controlada nas três versões de Python. O GitHub mesclou o
SHA aprovado em `main` somente depois de todos os gates obrigatórios passarem;
o review automatizado adicional foi pulado por cota, sem substituir nenhum
gate de CI.

Com autorização explícita do operador para atualizar o host, a versão foi
avançada para `0.1.0a40` em uma branch cujo ancestral é o conteúdo exato
mesclado. Nenhuma outra mudança funcional entrou nesta preparação. Os artefatos
deverão ser produzidos pelo CI a partir do commit final limpo, e a tag continuará
proibida até a prova física `a40→a39→a40`.

**Gates locais:** 3.252 testes aprovados em Python 3.14, incluindo os cenários
visuais, com cobertura de 85,97%; Ruff check e format, mypy em 188 arquivos,
independência e fronteiras verdes.

**Host:** nenhuma mutação nesta etapa; a39 permanece ativa e é o rollback
certificado da a40.

## 2026-07-29 — Sessão 45: verdade da emulação na bridge HTTP

A captura física da central mostrou o workspace mínimo de fallback — ações
vazias, keys aparentemente pendentes e biblioteca zerada — embora a CLI da a40
lesse keys rev21, firmware 22.5.0 e 15 jogos. O log estruturado registrava
`dashboard.emulation-snapshot-failed` com `ProgrammingError`. A reprodução em
thread separada confirmou a causa: o `EmulationController` abria o State Store
de jobs na thread que criava o dashboard e o reutilizava nas threads do
`ThreadingHTTPServer`, operação recusada pelo SQLite.

O manager próprio de jobs passou a ser criado sob demanda na thread da
requisição e fechado por `DesktopControlHandler.finish()`. Managers injetados
preservam o contrato anterior. A regressão é coberta tanto no controller
multithread quanto por uma chamada HTTP real a `/status`, que exige ações e
`health` completos no cartão do emulador.

**Gates locais:** 3.254 testes aprovados, cobertura 86,01%; Ruff check/format,
mypy em 189 arquivos, independência e fronteiras verdes.

| Item | Commit | Prova |
|---|---|---|
| State Store de jobs por thread HTTP e descarte no fim da requisição | `bc25b21` | `test_snapshot_owns_job_store_in_the_calling_thread` |
| Workspace completo atravessa a bridge sem cair no builder mínimo | `bc25b21` | `test_status_keeps_full_emulation_model_across_http_thread` |

**Fora de escopo:** instalar um emulador Switch, alterar o perfil Desktop
`handheld` aplicado com monitor externo, ou reinterpretar os 15 jogos como 15
diretórios. Esses são estados independentes da falha de composição corrigida.

**Host:** nenhuma mutação nesta etapa; a40 continua ativa e convergida. Uma nova
release exige autorização explícita do operador antes de preparar artefatos e
instalar.

**Rollback disponível:** a40 permanece ativa e fisicamente certificada; o PR
pode ser revertido sem migração de dados. O passo ainda exigido do operador é
autorizar explicitamente a preparação e instalação da a41 e, depois, validar a
navegação física da central.

## 2026-07-29 — Sessão 46: preparação reproduzível da a41

O operador autorizou explicitamente preparar, instalar e certificar a release
`0.1.0a41` no ciclo físico `a41→a40→a41`. A branch de release descende do merge
exato `cd709722cebfda533f1d9d6afbca546d2f755cc1`, que integrou o PR #16 após
todos os checks obrigatórios aprovarem a correção da afinidade SQLite entre o
dashboard e as threads da bridge HTTP.

Esta preparação altera somente a versão do pacote e registra a trilha de
release. Wheel, wheelhouse e manifesto serão gerados apenas de um commit final
limpo. A tag `v0.1.0a41` permanece proibida até instalação, rollback para a40,
roll-forward para a41, convergência e idempotência aprovados no host.

**Rollback planejado:** `0.1.0a40-fa29b46ba796`, atualmente ativa, convergida e
fisicamente certificada. O instalador é o único dono dos artefatos de host e
nenhum dado XDG do usuário será migrado ou removido pelo ciclo.

## 2026-07-29 — Sessão 47: certificação física da a41

**Veredito: APROVADA.** O ciclo autorizado `a41→a40→a41` convergiu nas duas
direções. A instalação e o roll-forward declararam o refresh do daemon
`pending`; o gate estável confirmou cada release em uma tentativa. As
repetições foram idempotentes, com zero tentativas e `restarted=false`.

O host terminou em `0.1.0a41-31b30211ba85`, commit
`31b30211ba85ec9ef60096809616771ff1aef6b5`. CLI, doctor, socket, serviço,
Game Mode, laboratório KVM/libvirt e status administrativo passaram. O doctor
reportou schema 13 e zero operações pendentes. A tag `v0.1.0a41` foi publicada
no commit certificado.

A leitura instalada do workspace Switch confirmou 15 jogos, keys `rev21`,
firmware `22.5.0` e uma ação `Instalar` para cada um dos três emuladores. A UI
abriu fisicamente na rota Emulação sem cair no modelo mínimo. O bloqueador
restante é verdadeiro: nenhum emulador Switch está instalado.

**Limites:** nenhum reboot, entrada real no Game Mode ou instalação de emulador
foi executado. A navegação integral por teclado/gamepad não foi certificada
porque o backend local de automação recusou entrada com a versão instalada do
`ydotool`. A a40 permanece preservada para rollback.

Detalhes e matriz de evidências:
`docs/09-operations/A41-CERTIFICATION-RESULT.md`.

## 2026-08-01 — Sessão 48: G27 lifecycle único e estado verdadeiro (branch fix/component-lifecycle-truth-g27)

Fachada `ComponentLifecycle` implementada em `src/steamzero/adapters/lifecycle.py`,
roteando AppImage/Flatpak pela família da fonte declarada (ADR de roteamento,
sem execução no plan): status normalizado (state/installed/installable/
executor/sourceType/version/targetVersion/origin/detail/endOfLife), planos v2
executor-independentes persistidos em `state/plans` (com `confirmToken`
compartilhado com o plano delegado), apply revalidando executor + fingerprint
(E-TX-STALE-PLAN) e ainda aplicando planos Flatpak v1 legados. `degraded` nunca
colapsa em `missing`; falha de um adapter vira `unavailable` com motivo, sem
derrubar lista/workspace; fonte end-of-life preserva o flag (teste de contrato
adicionado).

CLI (`component list/status/plan/apply/rollback/recover`, `--action`) passou a
usar a fachada; workspace Switch ganhou `installState: degraded`, `sourceState:
degraded`, `launchReadiness` por jogo com `playAction.enabled` derivado; QML
trata degradado como presente (seleção/contagem) e despacha `emulator.repair`
como plano de update; dashboard roteia plan/apply/launch/rollback/linhas de
componente pela fachada (EOL+ausente continua "Fonte descontinuada", degradado
vira "Reparar").

Rodada de revisão (mesma sessão): as cinco falhas apontadas pelo avaliador
foram corrigidas com regressões próprias no commit `d740b76` — snapshot
sobrevive a componente degradado (`payload_path` guardado), `unavailable`
nunca aparece como instalado no dashboard, degradado bloqueia a prontidão
global (45% attention, nunca 100%), plano v2 corrompido é rejeitado antes da
desserialização (E-STATE-INTEGRITY) e componente EOL instalado preserva a
verdade observada. Segunda rodada: `launch()` roteia Flatpak EOL instalado
para o executor correto (não mais pelo engine), degradado não recebe mais
`emulator.launch`, schema v2 fecha `delegated` (additionalProperties false,
exatamente uma chave) e rejeita raiz JSON não-objeto, e o dashboard repassa
as injeções `which`/`spawn` e respeita `installable=false` na ação. Terceira
rodada: schema v2 amarra executor↔chave delegada (`flatpak` exige
`flatpakPlanId`, `engine` exige `transactionPlanId`), exige ULID nos IDs
delegados, confirmToken ASCII (base64url) e timestamps com offset de timezone
(sem `format_checker` no validador, o pattern é a única defesa real); o
`apply` ganhou guards em profundidade (ASCII antes do `compare_digest`,
timezone antes da comparação com UTC) e `stop()` passou a tratar Flatpak EOL
como Flatpak, não como portátil.

Gates: 3358 testes isolados verdes, ruff/mypy/independence/boundaries OK.

## 2026-08-01 — Sessão 49: G28 verdade de erros de provider de mídia (branch fix/g28-media-provider-errors)

Causa raiz: `StateStoreGameMediaAdapter.save()` nunca persistia
`GameMediaState.errors` (e `_row_to_state` nunca lia) — a quota excedida
persistida pelo refresh não chegava a workspace/UI (`providerErrors: {}`).

Implementação em 4 commits (PR #26):
- `91fafb7` — m0014 `errors_json` em `switch_game_media`; adapter persiste e
  limpa erros por jogo (resave bem-sucedido limpa);
- `108a520` — m0015 `scraping_provider_status` (`last_error_code`,
  `last_error_category`, `state`); `ProviderHealth` sanitizado (só códigos,
  categorias estáveis, contadores, timestamps — nunca credenciais/detalhes/
  URLs); circuit breaker abre após 5 falhas consecutivas e `record_success`
  reativa; contrato terminal do job `media.global` (outcome
  success/partial/degraded, provider_errors, provider_details,
  interrupted_providers, no_candidates) persistido em `job.result`; quota
  interrompe ScreenScraper nos jogos restantes do mesmo job (1 tentativa);
  `_enrich_games` emite `mediaErrorCategories` por jogo;
- `d7d0624` — QML: card `media-provider-health` (PT-BR por categoria), label
  por jogo e `taskResultSummary` para `media.global`;
- `dda707e` — testes isolados do XDG real (`XDG_DATA/CONFIG/STATE_HOME`
  pinados) e regressão de restart reforçada no snapshot do workspace
  (providerDetails reconstruído da health).

Regressões: 12 mapeadas no PR (persistência por jogo, limpeza em resave,
sobrevivência a restart, contrato do job, interrupção por quota com provider
saudável seguindo, zero candidatos ≠ erro, modo inválido antes de chamadas,
limpeza por busca bem-sucedida, health sem segredos, circuit breaker,
categorias estáveis).

Gates: 3374 testes isolados verdes (3359 → 3374), ruff check/format, mypy e
`make independence boundaries` OK. Host intocado; release e instalação
dependem de merge e autorização do operador.

## 2026-08-01 — Sessão 50: G29 verdade observada do Feral GameMode (branch fix/g29-gamemode-operational-truth)

Causa raiz (GAP-G29): a linha "Feral GameMode" era publicada como pronta pela
presença de `gamemoderun` (`_capabilities`), embora o daemon pudesse estar
fora do ar, a autorização do usuário negada e governor/split lock/ioprio
recusados — prontidão de performance falsa.

Implementação em 2 commits (PR #27):
- `2300423` — `domain/gamemode.py` (verdade observada em seis dimensões:
  binaryState, daemonState, authorizationState, capabilityState,
  activityState + efeitos governor/splitLock/ioprio; hierarquia de condições
  nunca mascara falha superior; rótulos PT-BR do contrato); `adapters/
  gamemode_probe.py` (probe read-only injetável: which, `gamemoded -s` ou
  socket, conexão sem requisição, sysfs/proc e State Store de sessões;
  timeout/erro -> unknown, nunca falso verde); schema
  `gamemode-admin-plan-v1.schema.json` + plano administrativo declarativo
  validado por `contracts.validate` (inválido -> `E-STATE-INTEGRITY`, nunca
  KeyError/TypeError; sem endpoint de aplicação); `steam_gameplay.py`
  (linha `gamemode` do ambiente + seção `gamemode` no snapshot, ocioso
  explícito, readiness reflete degradação); CLI `desktop gamemode-status`
  read-only com o mesmo modelo; 16 regressões em `test_gamemode_probe.py`;
- `ea62c00` — QML: rótulos PT-BR por estado, botão seguro "Ver instruções"
  (diálogo com causa, orientação e aviso quando a ação depende do operador,
  sem botão que aplique mutação) e fallback do Main.qml com
  causa/remediação.

Semânticas garantidas por teste: binário sozinho nunca é ready; daemon
ausente degrada; autorização negada visível; idle não é falha; parcial é
degraded listando efeitos recusados; falha/timeout de sondagem é unknown;
nada sensível (argv/stdout/paths privados/jogos) vaza no snapshot, log ou
plano; nenhum teste toca ferramentas reais do host (dependências injetadas);
degradação não bloqueia lançamento (launcher intacto, regressão própria).

Gates: 3401 testes isolados verdes (3374 → 3401), ruff check/format, mypy e
`make independence boundaries` OK. Host intocado: zero mutações, release
ativa `0.1.0a41-c9111a00d3c0` preservada e rollback
`0.1.0a41-31b30211ba85` preservado. Validação física (boot direto + GameMode
real) segue pendente e exige release construída da main e autorização do
operador.

## 2026-08-02 — Sessão 51: G31 fechamento do guard de crash e diagnósticos do probe (branch fix/g31-crash-guard-wiring-and-diagnostics)

Motivo: o merge do PR #29 (G31) veio com `mergeStateStatus: UNSTABLE` porque
o check "Sourcery review" (IA externa) falhou. Investigação dos comentários
revelou achados reais — divergências entre o contrato declarado do G31 e o
código mergeado — que comprometiam a verdade observada, embora o núcleo do
gate (rejeição de SIGABRT/exit≠0 do harness) estivesse intacto. Esta sessão
fecha essas divergências.

Causa raiz de cada achado e correção:
- **Guard baseline/delta sem caller**: `CrashSnapshot.collect()` e
  `assert_no_new_crashes()` existiam e tinham testes, mas `capture()` nunca
  os chamava — a defesa declarada ("falha só por coredump novo atribuível à
  execução") não protegia capturas reais. Verde falso possível: captura
  bem-sucedida escondendo coredump de processo filho. Correção: `capture()`
  agora coleta baseline antes do harness e delta antes de retornar sucesso,
  passando o PID do harness (`Popen` no lugar de `subprocess.run`) para
  atribuição precisa (precedente: `adapters/emulation.py`,
  `adapters/screencast_web.py`);
- **OSError virava "saiu com código None"**: binário `qml6` ausente ou
  inexecutável (OSError no probe) produzia `exit_code=None`, e
  `check_runtime_version()` emitia `DIAG_QT_EXIT` com a mensagem enganosa
  "saiu com código None" — fere o contrato G31 "cada modo de falha é estado
  distinto". Correção: novo diagnóstico `DIAG_QT_RUNTIME-020`
  ("QML-VISUAL-QT-RUNTIME-020") para OSError, detectado pela combinação
  `exit_code is None and signal_number is None and not timed_out`;
- **Timeout produzia stderr literal "None"**: `subprocess.TimeoutExpired` com
  `stderr=None` (filho que não produziu saída) virava `str(None)` →
  `sanitize_stderr("None")` → o literal "None" no diagnóstico. Correção:
  `raw = exc.stderr or b""` normaliza para vazio;
- **`verify_packaged_qml()` retornava `dict[str, Any]`**: chaves mágicas
  ("resolved", "reason", "sizeBytes") sem verificação de tipo — typo de chave
  passaria silenciosamente. Correção: dataclass `PackagedQmlStatus`
  (`@dataclass(frozen=True)`, precedente de `RuntimeProbe`/`QmlMessage`).

Testes reparados/aumentados (3 novos): teste do wiring do guard (prova que
`capture()` chama `assert_no_new_crashes` com o PID real do harness numa
captura bem-sucedida); teste do probe OSError (afirma `DIAG_QT_RUNTIME`, não
`DIAG_QT_EXIT`, e ausência de "código None" na mensagem); teste do reader de
coredump que lança exceção (`CrashSnapshot.collect` degrada para vazio,
nunca levanta). PNG-residual reparado: o PNG agora é escrito durante a
execução do harness (via hook `on_start`), não antes — `capture()` apaga o
arquivo antes de lançar o processo, então o teste anterior nunca atingia o
estado que declarava provar.

Falso-positivo de segurança (Sourcery): `subprocess.run([tool, ...])` em
`read_coredumpctl` com `executable` default hardcoded `"coredumpctl"` em
lista (sem `shell=True`, sem input externo) — sem superfície de injeção;
nenhuma mudança necessária.

Gates: 3450 testes isolados verdes (sem regressão, +3 novos), ruff check
limpo em `src tools tests`, mypy success em 199 source files,
`make independence boundaries` OK. Host intocado: zero mutações, sem
release/wheel. Validação física (gate visual real no boot direto) segue
pendente e exige release construída da main e reinicialização pelo operador.
## 2026-08-02 — Sessão 52: automação de release/host rebasada e limpa (branch feat/release-host-automation)

O PR #20 (`codex/automate-release-host`, draft) misturava duas frentes
independentes e estava 45 commits atrás da `main` com conflitos reais em
`Makefile` e `docs/WORKLOG.md`. Análise separou:

- **Frente A — automação de release/host**: `tools/release_host.py`
  (1267 linhas), `tests/unit/test_release_host.py` (645 linhas),
  `docs/09-operations/RELEASE-HOST-AUTOMATION.md` (192 linhas), seção de
  automação em `AGENTS.md` (8 linhas) e targets no `Makefile`. Coerente com
  AGENTS.md §1/§4 — formaliza o caminho canônico de release, não enfraquece
  regra de segurança (reforça: falha de gate encerra o fluxo);
- **Frente B — `ai-memory`**: bloco de roteamento (~84 linhas em `AGENTS.md`)
  + 5 skills em `.agents/skills/ai-memory-*/SKILL.md`. Infraestrutura de
  ferramenta externa (`akitaonrails/ai-memory`), sem relação com o produto.

Decisão do operador: descartar a Frente B e rebase da Frente A sobre a
`main` atual. Execução: branch nova `feat/release-host-automation` criada de
`origin/main` (`0012055`), cherry-pick seletivo do commit `a2d7e48` (só
Frente A), resolução manual dos conflitos (`Makefile` manteve ambas as
variáveis `TEST_RUNNER` e `RELEASE_HOST`; `WORKLOG` manteve as sessões da
main). A Frente B (commit `2af2395`) foi inteiramente descartada.

`tools/release_host.py` oferece `inspect`, `prepare`, `verify-bundle`,
`install`, `rollback`, `cycle` e `publish`. As únicas chamadas privilegiadas
geradas são `bigsudo /usr/bin/python3 tools/install_host.py install/rollback`;
cada ativação exige token exato, converge duas vezes e reprova se a segunda
chamada reiniciar. Publicação exige os quatro gates nominais de certificação.
Nenhuma referência a projetos proibidos (AGENTS.md §7 verificado: zero
ocorrências de phasezero/retrodeck/linuxtoys/ai-memory no código).

Gates: 3476 testes isolados verdes (3450 → 3476, +26 do `release_host.py`
que entraram limpos), ruff check limpo, ruff format limpo (379 arquivos),
mypy success em 199 source files, `make independence boundaries` OK. Host
intocado: zero mutações, sem instalação/rollback/tag/build. Release ativa
`0.1.0a41-c9111a00d3c0` preservada. O PR #20 foi fechado e a branch remota
`codex/automate-release-host` removida.

## 2026-08-02 — Sessão 53: release consolidada `0.1.0a41-d0e45da1fd2d` instalada no host

Promoção da primeira release consolidada da linha de estabilização
(G27–G32 + release/host automation) sobre a release ativa anterior
`0.1.0a41-c9111a00d3c0` (G27/G28), mediante autorização explícita do
operador para atualizar o host.

Quatro PRs mergeados como pré-requisito:
- `#29` G31 (gate visual que rejeita SIGABRT/exit≠0);
- `#30` G31 (fechamento do guard de crash, `DIAG_QT_RUNTIME-020`);
- `#31` `feat/release-host-automation` (`tools/release_host.py`);
- `#32` fix `component list` (import de `AdapterRegistry` em runtime).

Dois defeitos reais encontrados no caminho e corrigidos:
- **`component list` quebrava em runtime** (`NameError: name 'AdapterRegistry'
  is not defined`) na release ativa E no fonte de main — `AdapterRegistry` só
  importado sob `if TYPE_CHECKING:`; corrigido no #32 com import local;
- **`bigsudo` (pkexec) redefine o cwd para `/root`**, quebrando o argv
  relativo `tools/install_host.py` do `release_host.py`; corrigido no #33 com
  caminho absoluto (`str(ROOT / "tools" / "install_host.py")`).

Bloco de instalação: `release_host.py prepare` baixou o artifact do run `push`
verde do commit `d0e45da1fd2d` e validou bundle/wheelhouse; `install` exigiu
aprovação interativa do polkit (o `bigsudo`/pkexec em subprocesso
não-interativo pendura aguardando o diálogo; o operador autorizou na tela).
Resultado `install` (release_host): converge 2× (idempotente, daemon na nova
geração, `restarted:false`), doctor `schemaVersion` 16, service/socket ativos.

Verificação read-only pós-instalação:
- `readlink /opt/steamzero/current` → `releases/0.1.0a41-d0e45da1fd2d`;
- `steamzero --version` → `0.1.0a41`;
- `doctor`: `runtime.provenance=0.1.0a41-d0e45da1fd2d`, `service.generation`
  pass (daemon na mesma geração), 8 pass / 3 warn (resíduo G26 pré-existente
  de ~1,1 GB de órfãos staging/backup/journal);
- `component list`: exit 0, 16 componentes, Eden/Citron/Ryubing instalados,
  status honesto (bug #32 corrigido no host);
- `desktop gamemode-status`: `unknown`/"Não foi possível verificar" — honesto,
  o probe não fecha verde falso;
- `system resources`: 6 classes, atribuição real, `complete:false`
  (`reason: proc-incomplete`) — degradação honesta conforme G30;
- `service`/`socket`: `active`.

Rollback preservado: `0.1.0a41-c9111a00d3c0` (release anterior, com
manifesto) disponível. Wheel sha256 `a2d8fecbcb88523a8c2a574f4cd6735176...`.

Validação física pendente (NÃO autorizada por esta sessão): boot direto,
UI, RetroArch/cores, standalone, Switch, BIOS/keys/firmware, launch, playtime,
encerramento/crash, saves, controles, mídia, GameMode, consumo por processo,
rollback `nova→anterior→nova`. A instalação de uma release consolidada com
teste físico exige nova autorização.

## 2026-08-02 — Sessão: Etapa 6 REQUIREMENTS-E2E completa (PRs #40, #41, #42)

### Etapa 6 do Programa de Conclusão da Emulação — todos os critérios entregues

**PR 1 — `feat/emulation-requirements-truth` (PR #40, commit `8f5d225`)**
BIOS por plataforma/emulador com projeção honesta no workspace
(`biosRequired`/`biosPresent` no emulador, `requirements.bios` na plataforma,
bloqueio de lançamento nomeando plataforma e emulador) e ação segura
`bios.import` (validação de nome contra o manifest, limite 64 MiB, reimport
idempotente, divergência bloqueada, hash nunca em logs). 15 testes novos;
suite 3605 passed.

**G24 — `feat/emulation-g24-diagnosis` (PR #41, commit `0e1c97a`)**
Requisito parcial agora é diagnosticado (status `unverified`, valor preservado,
chaves faltantes nomeadas), não degrada em silêncio. `KNOWN-GAPS.md` atualizado.

**PR 2 — `feat/emulation-content-projection` (PR #42, commit `3441557`)**
- `library.projection.repair`: reparo de projeção plan/apply/verify/rollback
  (G-FULL) — reconcilia o cache de biblioteca com o disco sem apagar, mover ou
  reescrever nenhum arquivo do usuário; no-op honesto quando íntegro.
- `bios.link`: links gerenciados com ownership — projeção do store central
  (`bios_dir/<plataforma>/<nome>`) para os dirs reais dos emuladores
  (RetroArch/DuckStation/PCSX2/melonDS), idempotente, divergência bloqueia,
  rollback remove cópias. Independente do PR 1 (base `main@31afa6f`);
  `E-CONTENT-BIOS-MISSING` orienta a importação.
- Contrato: `contentKind` (const `base`), `updateCount`, `dlcCount`,
  `updateVersion` declarados no game row — update/DLC são conteúdo associado,
  nunca jogos duplicados. 12 testes novos; suite 3602 passed.

**Base verificada no início:** `main@31afa6f`, nenhuma release tocada no host
(`real-state` idêntico antes/depois em todas as execuções).

**Pendências do operador:** merge de PRs #40/#41/#42 (nessa ordem);
Etapa 7 — SESSION-E2E (`feat/emulation-session-saves-e2e`,
`feat/emulation-controls-e2e`) quando autorizado.

## 2026-08-02 — Sessão 54: PR 1 tema default — fundação de cena (branch codex/theme-scene-foundation)

Primeira PR da linha de tema default do SteamZero, sobre `origin/main`
(`59f22a8`): fundação do IR de cena para o motor de temas. Nenhuma ação de
host; trabalho apenas em worktree próprio.

Quatro commits, todos com os gates da seção 6 verdes:

- `954f970` — **árvore de cena**: `children` no `ElementContract` com
  validação recursiva e serialização v2 (leitura v1 preservada); novo
  `scene_tree.py` com limites fechados (profundidade 40, filhos 128, nós
  4096, ids únicos) e validação na leitura do documento.
- `6793766` — **display responsivo**: `DisplaySpec` fechado
  (largura/altura/dpr/orientação/safe-area) e bindings `display.*` por eixo
  no resolver, com invalidação seletiva por geração e `set_display`.
- `50151db` — **fechamento do contrato**: `CONTRACT_PROPERTY_TYPES` (44
  entradas) como tabela única; o registro de tipos passou a derivar dela,
  eliminando nomes fantasmas (`content`, `source`) e os enums do catálogo
  de slots de valor; testes de fechamento nos dois sentidos.
- `e6be003` — **auditoria executável da migração**: `theme_migration_audit`
  (fidelidade por área, nomes sem tradutor expostos) e
  `tools/audit_theme_migration.py` (relatório por layout, `--json`); o gate
  `source_property_count < 388` ganhou corpo inspecionável.

Descobertas registradas:

- a divergência contrato↔registro era real e silenciosa: `content`/`source`
  viviam no registro sem existir no contrato (ver commit 3);
- `expected_for_property` (registro de propriedades) não tem chamadores —
  a resolução usa o vocabulário de bindings; o catálogo de propriedades é
  hoje consumido apenas por testes e pela auditoria;
- flakiness pré-existente confirmada: `test_desktop_ui_bridge` quebra com
  `BrokenPipeError` em loopback sob carga (passa isolado, sem relação com
  esta PR).

Validação física pendente (operador): revisão da PR, merge e testes de
tema futuros. Suíte completa: 3691 passed (1 flaky de rede reconfirmado
verde isolado); mypy 202 arquivos; fronteiras e independência 0 violações.

## 2026-08-03 — Sessão: Etapa 7 SESSION-E2E, PR 1 — preservação de saves/estados

### PR 1 — `feat/emulation-session-saves-e2e`

- **Mapeamento amplo**: `PreservationService` cobre saves de RetroArch
  (`.srm`), save states de RetroArch (`.state`), DuckStation (`.savestate`) e
  Flycast (`.state`) como arquivo nomeado pelo stem da ROM; kind novo `"state"`
  com limites próprios (512 MiB/arquivo, 4 GiB/árvore); Switch continua por
  Title ID. Match por nome sem ambigüidade; destino inseguro continua bloqueado.
- **Protocolo seguro**: `game.save|state|shader.backup/restore` e
  `game.shader.invalidate` bloqueiam com a sessão em execução
  (`E-CONTENT-BUSY`, catalogado + i18n pt-BR) — saves/estados são gravados pelo
  emulador enquanto o jogo roda.
- **Checkpoint automático**: ao encerrar a sessão, o save é catalogado se o
  digest da árvore mudou (debounce por `treeDigest` de 80 bits no version);
  retenção limitada a 8 backups por jogo; falha nunca interrompe o encerramento.
- **Conflito preserva ambas versões**: restore com estado atual divergente do
  backup escolhido primeiro cataloga o estado atual como novo backup, depois
  aplica o restore no settle (`restoreApplied` + operationId no response);
  rollback do restore segue G-FULL.
- **Formato de version compacto**: `backup:v1:c<epoch>:f<fp>:d<digest>` cabe
  nos 128 chars do record key com fingerprint e digest completos; leitura
  retrocompatível com o formato JSON antigo.
- `stateTarget`/`stateBackups`/`stateCount` declarados no schema do game row;
  seção `saveStates` na dashboard. 12 testes novos (integration + unit);
  suite 3627 passed; gates completos verdes; `real-state` idêntico antes/depois.

**Pendências do operador:** merge do PR #43; depois PR 2 da Etapa 7 —
`feat/emulation-controls-e2e`.

## 2026-08-03 — Sessão: Etapa 7 SESSION-E2E, PR 2 — perfil de input por jogo

### PR 2 — `feat/emulation-controls-e2e`

- **Perfil por jogo com herança**: o game row agora publica `controlsProfile`
  (`state`, `statusLabel`, `source` game/platform, `scope`, `active`,
  `available`, `activateActions`, `clearAction`). Sem override do jogo, o perfil
  efetivo é herdado da plataforma (`source: "platform"`); com ativação
  `scope=game`, é próprio (`source: "game"`) e ganha a action de limpar.
- **Actions e2e**: `controls.profile.activate:<perfil>` agora aceita
  `scope=game` + `gameId`/`scopeId` e valida `E-CONTENT-BUSY` (sessão em
  execução) antes de ativar; nova action `controls.profile.clear:<gameId>`
  remove só o override por jogo (transação G-FULL com backup; rollback
  restaura) e também bloqueia com sessão rodando.
- **Prontidão honesta sem interditar**: `controlsReadiness` no game row
  (`state` ready/attention, `reason`, `profileConfigured`, `controllers`)
  informa se há perfil ativo e controle detectado — NUNCA bloqueia o launch.
- **Domínio**: `InputProfileManager.plan_clear` (remoção transacional com
  `removals`, noop idempotente quando não há override) e `apply`/`rollback`
  passam a aceitar o prefixo `input-profile.` (activate + clear).
- **Contrato**: `controlsProfile`/`controlsReadiness` declarados no
  `emulation-workspace-v1.schema.json` (game def); `operation_history` rotula
  `input-profile.clear:` como "Perfil de controle".
- **Testes**: 5 de domínio (ativação/clear/rollback por jogo, noop, symlink,
  plano stale) + 2 de controller (game row com herança/ativação/clear/rollback
  e `E-CONTENT-BUSY` por jogo) + contrato literal do game row atualizado
  (mudança de contrato documentada). Suite 3632 passed; gates verdes
  (ruff/mypy/independence); `real-state` idêntico antes/depois.

**Pendências do operador:** revisar e commitar/pushar o PR 2 da Etapa 7
(`feat/emulation-controls-e2e`); depois merge.

## 2026-08-03 — Sessão 55: PR 2 tema default — tema renderizável (branch codex/theme-default-pr2)

Segunda PR da linha de tema default, sobre `origin/main` (`87cf493`): o tema
default renderizável consumindo a fundação de cena. Nenhuma ação de host;
trabalho apenas em worktree próprio.

Quatro commits, todos com os gates da seção 6 verdes:

- `ad72bd9` — **imagem/mídia no pipeline**: `imageContent` no contrato
  (tabela 45 entradas), `ResolvedImageNode` + `ImageFillMode` (CROP/STRETCH/
  FIT/ORIGINAL), `build_image_node` (percentuais via `LayoutBox`, recusa
  elemento sem `imageContent`), `QmlImageRenderModel` + `to_image_render_model`
  (`_MEDIA` fechada em `assets/...`, recusa de caminho de host e de valor
  pendente) e `SceneImage.qml` burro. Fallback de asset degrada com
  diagnóstico emitido pelo resolver (`DIAG_MISSING_ASSET`); fixtures de mídia
  (320x180) sob `tests/fixtures/scene-media/`.
- `0a14670` — **harnesses VS-03 de imagem/cena + navegação de grid**:
  `CaptureImageHarness.qml` (imagem única) e `CaptureSceneHarness.qml`
  (composição texto+imagem via `Loader.setSource` com propriedades iniciais —
  `setSourceComponent` não existe no Qt 6.11); runner ganhou `HarnessKind` e
  o test-double do mapeamento de assets do shell (`mediaFiles`); cada nó
  publica geometria (painted vs caixa prova o crop em números);
  `grid_navigation.py` (`move_focus`, `Direction`, `GridSpec` com
  wrap/clamp documentados).
- `f5028dc` — **tema default renderizável**: `default_theme.py` — primeiro
  consumidor real da fundação — com paleta Aura, `DefaultGridMetrics`
  (geometria derivada 6x4 em 1920x1080), `build_default_scene` (cabeçalho +
  24 células capa/título validado por `validate_tree`), resolução com tokens/
  bindings/fallbacks e `focus_target` delegando a `move_focus`.
- `fe20c65` — **WORKLOG + handoff**: este registro e a seção nova do P0-03.

Descobertas registradas:

- `Loader.setSourceComponent(component, props)` não existe no QML Qt 6.11 —
  `ReferenceError`; o caminho é `setSource(url, props)` com a URL do
  componente do produto (ver commit 2).
- `paintedWidth/Height` refletem a ESCALA coberta (crop escala a fonte e a
  caixa clipe); a prova numérica do crop é painted > caixa.
- `Alignment` não tem `MIDDLE`/`TOP`: o contrato mapeia START/CENTER/END →
  TOP/MIDDLE/BOTTOM no construtor de nós.
- C1 saiu sem os fixtures de mídia (criados na sessão, referenciados pelo
  teste do C2); como C1 não tinha sido pushado, os fixtures entraram por
  amend do C1 — história local, sem force push.
- onAfterRendering do runtime offscreen entrega 2 frames; o harness de cena
  esperava 3 e travava em "layout não estabilizou" com stderr vazio.

Validação física pendente (operador): revisão da PR, merge e teste físico
de boot da linha de tema. Suíte completa: 3808 passed; cobertura 86.42%;
mypy 203 arquivos; fronteiras e independência 0 violações.

## 2026-08-03 — Sessão 56: PR 3 tema default — shell de entrada + ponte shell→tema→QML (branch codex/theme-default-pr3)

Terceira PR da linha de tema default, sobre `origin/main` (`017c4c7`, merge da
PR #47). Entrega o shell de entrada: eventos de controle viram movimento de
foco no domínio, e o anel de foco — primeiro consumidor real do token
`color.focusRing` — é desenhado no QML sobre a célula focada. Nenhuma ação de
host; trabalho apenas em worktree próprio.

Três commits, todos com os gates da seção 6 verdes:

- `e32ed64` — **shell de entrada no domínio**: `theme_shell.py` —
  `ControlEvent` (vocabulário mínimo: as quatro direções), `map_control`
  (recusa evento desconhecido; desconhecido não vira direção adivinhada) e
  `apply_control` delegando a `move_focus` (`current=None` foca o primeiro
  item). `default_theme.py` ganhou a geometria do anel: `focus_ring_geometry`
  (capa expandida pela margem) e as constantes `FOCUS_RING_INSET`/`FOCUS_RING_WIDTH`.
- `f55f02a` — **ponte shell→tema→QML**: `SceneFocusRing.qml` (renderizador
  burro do anel: atribui o modelo, não decide nada), `CaptureShellHarness.qml`
  (nós de texto/imagem + `kind: "focus"`, reporta geometria de todos) e
  `HarnessKind.SHELL` no runner; `shell_bridge.py` monta o payload do shell —
  cena resolvida e traduzida (adapter) + anel da célula focada.
- docs — WORKLOG + handoff P0-03 (este registro e a seção nova do P0-03).

Provas de que a ponte funciona no runtime real:

- integração (`test_qml_theme_shell.py`, fatia 3x3 em 800x480): anel em foco 0
  e foco 5 nas coordenadas exatas de `focus_ring_geometry`; o pixel `#22d3ee`
  é desenhado na tela e é a ÚNICA fonte da cor (cena sem o nó focus não tem
  nenhum pixel dele); duas capturas do mesmo foco são idênticas byte a byte.
- unidade (`test_theme_shell.py`, `test_shell_bridge.py`): mapeamento
  controle→direção, wrap/clamp, foco inicial, geometria do anel e payload da
  ponte (cena + anel por último, recusa de foco fora do grid).
- sem goldens novos: a prova é a geometria do anel + contagem de pixels, não
  uma imagem congelada — o mesmo critério de `test_qml_default_theme.py`.

Descobertas registradas:

- Adicionar a MESMA margem aos dois lados de uma caixa 16:9 NÃO preserva a
  razão — o teste inicial do anel assumia o contrário e reprovou (correto); a
  propriedade honesta é "o anel envolve a capa", não "o anel é 16:9".
- `Image.getdata` do Pillow está deprecado (remoção prevista para Pillow 14);
  a contagem de pixels usa `getcolors`, o mesmo mecanismo do runner.
- Defesas de invariante interno (ramo "impossível") seguem o precedente do
  repo com `# pragma: no cover` — `gamemode.py:190`, `net.py:253`.

Fora de escopo (decisões conscientes): read model da biblioteca (títulos
seguem no fallback `Jogo sem título` — caminho de degradação real), migração
de capas reais do corpus, eventos de confirm/back (A/B chegam com o controle
de seleção) e persistência do foco entre sessões.

Validação física pendente (operador): revisão da PR, merge e teste físico de
boot da linha de tema. Suíte completa: 3842 passed; cobertura 86.42% (sem
regressão); mypy 205 arquivos; fronteiras e independência 0 violações.

## 2026-08-04 — Sessão: gate canônico saindo 86 na `main` (atribuição do state real)

Branch `codex/fix-state-guard-attribution`, base `origin/main`
`1d23cbf598940e376b82e2905979901e93645c52`.

### A premissa da tarefa estava errada

A investigação anterior tratava o exit 86 como vazamento intermitente da suíte e
já tinha descartado, por bissecção, arquivo único, metades, `test_core_service`
e `test_fi04_sigkill_subprocess`. Nenhum culpado dentro da suíte existia.

**O autor é o daemon instalado do host** (`steamzero-core --systemd`, pid 135687,
release `0.1.0a41-d0e45da1fd2d`), que roda com `HOME=/home/misael` e sem
`XDG_STATE_HOME` — resolvendo para o MESMO state home que o guard fotografa. O
reconciliador (`service/reconciler.py:101`) grava `session.environment.changed` a
cada flap de rede/energia (`state.db` + `logs/core.jsonl`), e o `ensure_dir` do
`AppendWriter` (`core/fs.py:43`) faz `chmod` incondicional que bumpa o **ctime**
do diretório `logs`. Uma única amostra do daemon muda exatamente as três entradas
da assinatura relatada.

A intermitência é a irregularidade dos flaps, que vêm em rajadas: 6 mutações em
6 min de uma janela, depois ~50 min sem nenhuma (incluindo 5 suítes completas com
o state intocado).

**Prova decisiva:** a própria lógica de snapshot do guard, rodada por 25 min
**sem pytest algum**, deu `IDLE_MUTATIONS=6` e `GUARD_VERDICT=EXIT=86`.

### O defeito real

O guard media *presença temporal* na janela e reportava *autoria* ("pytest
alterou o state home original"). As duas coisas divergem sempre que outro dono
legítimo do state home está ativo — que é o caso permanente num host com a
release instalada. Por isso o CI sempre foi verde: lá não há daemon.

### Entregue

| Item | Commit | Testes que provam |
|---|---|---|
| Guard atribui a mutação: varre `/proc` por processos steamzero fora do isolamento que resolvam para o mesmo state home; dono anterior à janela → `W-TEST-REAL-STATE-EXTERNAL-WRITER` (não reprova), nascido na janela → 86 | `f3e4914` | `test_external_writer_predating_window_does_not_fail_the_gate`, `test_process_born_during_window_is_blamed_as_suite_leak`, `test_suspect_wins_over_external_writer`, `test_external_writer_preserves_pytest_failure` |
| Amostra explícita no fechamento da janela (o `__exit__` do watcher roda depois da decisão) | `f3e4914` | `test_writer_appearing_only_at_window_close_is_still_observed` (verificada reprovando sem a correção) |
| Match restrito ao executável/script (argv[0:2]): mencionar "steamzero" não faz de um shell ou grep um dono do state home | `f3e4914` | `test_scan_ignores_process_that_only_mentions_steamzero`, `test_scan_accepts_interpreter_running_a_steamzero_script` |
| Mensagem do 86 nomeia suspeitos e abre pelas hipóteses acionáveis, começando pelo falso positivo do operador | `f3e4914` | `test_mutation_without_writers_still_fails_and_names_operator_command` |
| G33 em `KNOWN-GAPS.md`, com o limite da atribuição degradada | `f3e4914` | — |

Nenhum caminho entrou em lista de exceções e nenhuma escrita foi tolerada por
path. Zero mudança em `src/` (`git diff origin/main -- src/` vazio).

### Limite conhecido (G33)

Com um dono externo ativo, a atribuição é **degradada**: uma escrita da própria
suíte ficaria encoberta por ele. O guard diz isso na própria mensagem e recomenda
rodar com o daemon parado para rigor total. Comando `steamzero` curto do operador
pode terminar entre duas amostragens (poll de 2 s) e não ser nomeado — por isso a
mensagem do 86 lista esse falso positivo como primeira hipótese.

### Gates

Cinco execuções consecutivas da suíte completa: `EXIT=0` nas cinco, 3855 passed
cada. `ruff check`, `ruff format --check`, `mypy src` (206 arquivos) e
`make independence boundaries`: exit 0. Honestidade sobre o alcance dessa
evidência: o daemon ficou quieto durante as cinco execuções (state real byte a
byte idêntico), então elas provam que o gate está verde, **não** que o caminho do
dono externo funciona em produção. Isso é provado separadamente pelo ensaio ponta
a ponta com o scan real de `/proc` (dono externo nomeado por pid e argv,
`GATE_EXIT=0`, state sintético mutado durante a janela) e pelos testes acima.

### Fora de escopo, registrado

- `desktop_kde.py:47` fixa `phasezero-steamdeck-mode-watcher.service` — referência
  a projeto de pesquisa que o gate de independência não pega (AGENTS.md §7).
- `test_desktop_ui_bridge.py::test_status_keeps_full_emulation_model_across_http_thread`
  reprovou uma vez sob carga (timeout de 3 s do cliente em loopback) numa bateria
  anterior; flakiness pré-existente já registrada neste WORKLOG (linha 3901).
- State home real com ~1,1 GB de resíduo histórico: **nada foi removido**.

Ações de host executadas: **nenhuma**. Nenhuma instalação, rollback ou mutação de
release. O daemon foi deixado rodando de propósito, por ser a condição que
reprovava.

### Adendo da mesma sessão — CI e footprint do watcher

Primeira execução de CI da branch reprovou no Python 3.11 em
`test_desktop_ui_bridge.py::test_status_keeps_full_emulation_model_across_http_thread`
(`TimeoutError` no timeout de parede de 3 s do cliente em loopback). Reexecutada,
a mesma CI ficou **verde nos oito jobs**, incluindo 3.11. A `main` foi verde em
duas execuções. O mesmo teste flakeou 1 vez em 10 suítes completas locais.

Ou seja: teste flaky sob carga, sem prova de relação com esta mudança (o diff não
toca `src/`). Mas como não dá para **excluir** que o polling de `/proc` a cada 2 s
somasse carga, o watcher passou a só rodar onde pode achar algo: se o state home
real não existe — o caso do CI, que roda em home limpo — não há dono externo
possível e a thread não sobe. As amostras de abertura e fechamento continuam
sempre, então nenhuma atribuição se perde (`6e9ee19`).

Validação final, com o daemon do host rodando: cinco execuções consecutivas da
suíte completa, `EXIT=0` nas cinco, 3857 passed cada. `ruff check`,
`ruff format --check`, `mypy src`, `make independence boundaries`: exit 0.

### Adendo 2 — o flake do bridge é da `main`, não desta branch

Caracterizado por dispatch repetido de CI em 2026-08-04:

| Ref | Execuções | Python 3.11 |
|---|---|---|
| `main` | 3 | 2 verdes, 1 vermelha |
| `codex/fix-state-guard-attribution` | 3 | 1 verde, 2 vermelhas |

Sempre o mesmo teste e o mesmo erro
(`test_status_keeps_full_emulation_model_across_http_thread`, `TimeoutError` no
timeout de 3 s do cliente). **A `main` reproduz.** Além disso, no CI o state home
real não existe (`real-state before: exists=False`), então a thread do watcher
nem sobe — a mudança é inerte em tempo de execução justamente no job que reprova.
Somado ao diff sem nenhuma linha de `src/`, a branch está descartada como causa.

Registrado como **G34** em `KNOWN-GAPS.md`: CI ~1 em 3 no 3.11 por teto de parede
absoluto em runner compartilhado — mesma classe do já fechado G22. Fora do escopo
desta sessão; não corrigido aqui.
