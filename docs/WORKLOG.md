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
