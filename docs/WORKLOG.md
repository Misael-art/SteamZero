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

### Próxima ação
`core.fs` (atomic write / staging / containment / path-safety) + `core.log`
(JSONL + masking de segredos), depois locks, journal, transação, state store.
