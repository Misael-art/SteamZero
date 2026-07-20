# FUNCTION-PROVENANCE-MATRIX — quadro técnico de funções e proveniência

Catálogo técnico de **todas as funções do SteamZero** (camada de usuário + internas do núcleo), com a origem de cada uma e o **tipo de relação** com o projeto de origem.

Visão complementar: [FEATURE-CATALOG](../01-product/FEATURE-CATALOG.md) traz a visão de produto por fase; este quadro traz a visão técnica por proveniência. Gaps citados: [GAP-ANALYSIS](GAP-ANALYSIS.md). Política que rege o reuso: [REUSE-POLICY](../11-legal/REUSE-POLICY.md).

## Legenda da proveniência (normativa)

| Marca | Significado | Consequência prática |
|---|---|---|
| **INSP** | Inspiração: o conceito vem do projeto X; implementação independente (sem código lado a lado) | Livre de licença; registrar "inspired by, implemented independently" no PR |
| **ADAP** | Adaptação: deriva de artefato concreto de X (template, estrutura, lista de referência) | **Sujeito à REUSE-POLICY**; bloqueado até ADR-0013 (Q2) definir a licença; exige SPDX + atribuição |
| **APRI** | Aprimoramento: existe em X, mas com falha conhecida; reimplementamos corrigindo | Nota cita a falha (`arquivo:linha`) e o requisito que a corrige |
| **NOVO** | Nenhum dos quatro projetos entrega | Nota cita o gap `GA-xx` |

Proveniência mista usa a marca mais forte na ordem `APRI > ADAP > INSP`; a nota detalha a composição.

**Colunas:** `ID` (namespace `SZ-*`, estável) · `Função` · `Camada` (usuário/interna) · `Prov.` · `Origem + evidência` · `Nota` · `Ref` (IDs cruzados) · `Fase` (roadmap).

**Abreviações de origem:** PZ = PhaseZero · ED = EmuDeck · LT = LinuxToys · RD = RetroDECK.

---

## 1. Núcleo transacional

### 1.1 Pipeline de mutação

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-TX-01 | `scan` — leitura do estado real, sem escrita fora do state | interna | INSP | PZ `library/scan.py` | Generalizado de biblioteca para toda mutação | F-LB-01, AC-LB-01 | 1 |
| SZ-TX-02 | `plan` — diff estado→alvo, ações ordenadas, requisitos, riscos | interna | INSP | PZ `library/plan.py:120` | Acrescenta requisitos (espaço/rede/privilégio) e classe de garantia de rollback | F-PL-01, RB-7 | 1 |
| SZ-TX-03 | `confirmToken` single-use vinculado ao plano | interna | INSP | PZ `library/apply.py:76` | Token expira e é single-use (original não expira) | AC-TX-04 | 1 |
| SZ-TX-04 | Precondições congeladas (fingerprint) revalidadas no apply | interna | NOVO | — | Nenhum dos quatro protege contra TOCTOU entre plan e apply | GA-07, T-11, AC-TX-01 | 1 |
| SZ-TX-05 | `preview` humano/JSON do plano | interna | INSP | PZ envelope + RD dialogs | Preview é obrigatório, não opcional | U2 | 1 |
| SZ-TX-06 | `backup` pré-apply com manifesto de hashes | interna | APRI | PZ boot backup bundle (`common.sh:260-282`) | Original: bundle só para GRUB, sem manifesto verificável. Aqui: toda operação, com hash por entrada | RB-4 | 1 |
| SZ-TX-07 | `stage` no mesmo filesystem do destino | interna | APRI | ED `safeDownload` (`helperFunctions.sh:760`) | Original: staging só no download (`.temp`), configs vão por rsync direto. Aqui: universal, garante rename atômico | SR-05, FM-05 | 1 |
| SZ-TX-08 | `apply` com journaling write-ahead por ação | interna | NOVO | — | — | GA-07, FM-04 | 1 |
| SZ-TX-09 | `verify` de pós-condições (hash, versão, parse, executável) | interna | APRI | PZ `-Audit`; ED `checkInstalledEmus.sh` | Original: audit é etapa separada e opcional. Aqui: verify é gate do pipeline; status "ok" só existe com verify | P10, AC-IN-03 | 1 |
| SZ-TX-10 | `activate` — troca atômica (rename/symlink flip) | interna | INSP | PZ `pz_boot_atomic_install` (`common.sh:425-434`) | Estado antigo permanece ativo até este ponto | FM-05 | 1 |
| SZ-TX-11 | `test` — smoke test declarado no manifesto | interna | NOVO | — | Nenhum dos quatro testa o componente após instalar | GA-09 | 1 |
| SZ-TX-12 | `commit` — selo do journal, GC do staging | interna | NOVO | — | — | GA-07 | 1 |
| SZ-TX-13 | `dry-run` universal (scan→plan→preview sem tocar disco) | interna | APRI | PZ `PZ_DRY_RUN` (`common.sh:638`) | Original: dry-run existe no profile runner, ausente em RD/ED. Aqui: obrigatório em toda operação, verificado por strace no CI | AC-TX-03 | 1 |

### 1.2 Journal e recuperação

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-TX-14 | Journal WAL por operação (intent→done, JSONL fora do SQLite) | interna | NOVO | — | PZ registra mudanças (`pz_rollback_register`, `common.sh:516`) mas sem intents nem recovery determinístico | GA-07, FM-04, ADR-0005 | 1 |
| SZ-TX-15 | Recovery determinístico na subida (undo de intents abertos) | interna | NOVO | — | — | FM-04, R3 | 1 |
| SZ-TX-16 | Roll-forward pós-`activate` quando idempotente | interna | NOVO | — | — | FM-04 | 1 |
| SZ-TX-17 | Rollback verificado por hash contra o manifesto de backup | interna | APRI | PZ `pz_rollback` (`common.sh:532-556`) | Corrige duas falhas: restaura com `cp` sem verificar (`:545`) e apaga o manifesto inteiro mesmo em falha parcial (`:554`) | RB-4, RB-5, RT-01 | 1 |
| SZ-TX-18 | Rollback idempotente e sem rede | interna | NOVO | — | — | RB-1, RB-2, RB-3 | 1 |
| SZ-TX-19 | Estado `rollback-failed`: congela recurso, alerta crítico | interna | NOVO | — | Nenhum projeto tem o conceito de falha de reversão | FM-17, R1 | 1 |
| SZ-TX-20 | Classe de garantia declarada no plano (G-FULL/G-STATE/G-TIMELINE) | interna | NOVO | — | — | RB-7 | 1 |

### 1.3 Locks

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-TX-21 | Lock por recurso com lease + dono (pid/jobId) + heartbeat | interna | NOVO | — | — | GA-01 | 1 |
| SZ-TX-22 | Detecção e quebra registrada de lock órfão | interna | NOVO | — | — | FM-15, FI-15 | 1 |

### 1.4 Quarentena e sagas

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-TX-23 | Quarentena com manifesto e restauração (nunca deleta) | interna | INSP | PZ `media clean` (move p/ backup) | Generalizado: qualquer conteúdo suspeito/deslocado | FM-13, FM-14 | 1 |
| SZ-TX-24 | Sagas: operação composta com compensação reversa | interna | NOVO | — | — | GA-07 | 3 |
| SZ-TX-25 | GC de backups com política, teto de disco e preview | interna | APRI | PZ `pz_write_managed_file` (`common.sh:63,78`) | Corrige "backups infinitos": original cria `.bak.<ts>` sem limite nem GC | RB §GC, R4 | 1 |

## 2. core.fs e path safety

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-FS-01 | Escrita atômica única (tmp+fsync+rename) — porta exclusiva de escrita | interna | APRI | PZ `pz_write_managed_file` (`common.sh:54-82`) | Original: função existe mas convive com escritas diretas noutros módulos. Aqui: lint de CI proíbe escrita fora de `core.fs` | SR-05, MODULE-BOUNDARIES | 1 |
| SZ-FS-02 | Canonicalização + containment por componentes de path | interna | INSP | PZ guard de profile scripts (`common.sh:748-764`) | Generalizado a toda operação com raízes declaradas | SR-06, PATH-SAFETY §1 | 1 |
| SZ-FS-03 | `O_NOFOLLOW` / `openat2(RESOLVE_BENEATH)` em escrita | interna | NOVO | — | — | SR-06, FM-13 | 1 |
| SZ-FS-04 | Symlink fora da raiz: ignorado + relatado (nunca seguido) | interna | NOVO | — | — | FM-13, FI-13 | 1 |
| SZ-FS-05 | safezip: limites de razão de expansão, entradas, profundidade | interna | INSP | PZ `library/safezip.py` | — | F-LB-06, FM-14, FI-16..18 | 1 |
| SZ-FS-06 | Validação por entrada de archive antes de materializar | interna | INSP | PZ `library/safezip.py` | — | F-LB-06, PATH-SAFETY §3, FI-17 | 1 |
| SZ-FS-07 | Sanitização de nomes gerados (NFC, sem bidi/NUL, limites) | interna | NOVO | — | — | PATH-SAFETY §4, T-03 | 3 |
| SZ-FS-08 | Expansão de variáveis de path por tabela fechada | interna | APRI | RD `eval config_file=` (`framework.sh:564+`) | Corrige: original expande path por `eval` (26 ocorrências em framework.sh) | SR-02, PATH-SAFETY §6 | 1 |
| SZ-FS-09 | Mount awareness: confirmar UUID montado antes de escrever | interna | NOVO | — | Impede escrita em mountpoint vazio | FM-06, PATH-SAFETY §7 | 2 |
| SZ-FS-10 | Detecção de colisão case-insensitive entre filesystems | interna | NOVO | — | ext4→exFAT (microSD) | PATH-SAFETY §8 | 3 |
| SZ-FS-11 | Preflight de espaço com margem | interna | INSP | PZ `Assert-BootstrapDiskSpace` (JIT disk guard) | — | FM-03, E-STORAGE-SPACE | 1 |

## 3. State Store

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-ST-01 | SQLite WAL com writer único no daemon | interna | NOVO | — | PZ/RD/ED usam JSON/cfg soltos; consultas do dashboard são relacionais | GA-02, ADR-0005 | 1 |
| SZ-ST-02 | Schema de entidades (device, volume, component, game, bios, save…) | interna | NOVO | — | — | GA-02, STATE-MODEL | 1 |
| SZ-ST-03 | Referência por `volume_id + relpath` (nunca path absoluto gravado) | interna | APRI | ED/RD paths hard-coded (`$HOME/.local/share/...`) | Corrige: sobrevive a troca de mountpoint e remoção de microSD | FM-06, STATE-MODEL §2 | 1 |
| SZ-ST-04 | `verified_at` obrigatório para status "ok" | interna | NOVO | — | — | P10, STATE-MODEL §4 | 1 |
| SZ-ST-05 | Migrações versionadas (`user_version`) com backup pré-migração | interna | APRI | RD `post_update.sh` | Corrige: original encadeia migrações por versão sem dry-run nem backup | MIGRATION-VERSIONING, RT-14 | 1 |
| SZ-ST-06 | Export/import JSON canônico | interna | INSP | PZ profiles JSON | Estado legível/auditável como contrato de 1ª classe | ADR-0005, F-PL-03 | 1 |
| SZ-ST-07 | Integrity check + reconstrução por rescan (state é derivável) | interna | NOVO | — | — | R2 | 1 |
| SZ-ST-08 | `event_log` append-only como fonte dos eventos da UI | interna | NOVO | — | — | GA-02, EVENTS | 1 |

## 4. Job Manager

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-JB-01 | Fila persistente com prioridade (interativo > manutenção > background) | interna | NOVO | — | — | GA-01, F-PL-02 | 1 |
| SZ-JB-02 | Máquina de estados do job (created…rolled-back) | interna | NOVO | — | — | GA-01, JOB-LIFECYCLE | 1 |
| SZ-JB-03 | Pausa/retomada em pontos de segurança | interna | INSP | PZ checkpoint/resume (`Save/Load-BootstrapCheckpoint`) | Original: por pipeline; aqui: fila genérica | GA-01 | 1 |
| SZ-JB-04 | Cancelamento seguro (unwind da etapa, nunca kill) | interna | NOVO | — | — | PROGRESS §Cancelamento | 1 |
| SZ-JB-05 | Recovery pós-reboot (interrupted → rollback ou roll-forward) | interna | INSP | PZ `-Resume` | Original: resume; aqui: decisão rollback/roll-forward pelo journal | FM-04, M3 | 1 |
| SZ-JB-06 | Limites de CPU/IO (nice/ionice/cgroup slice) | interna | NOVO | — | — | GA-01, ADR-0010 | 1 |
| SZ-JB-07 | Política de bateria (`requiresAC` bloqueia < limiar) | interna | NOVO | — | — | FM-19, E-JOBS-BLOCKED-BATTERY | 2 |
| SZ-JB-08 | Bloqueio de jobs pesados durante gameplay | interna | INSP | ED cloud sync "pause during gameplay" | Original: só no sync; aqui: política central por constraint | E-JOBS-BLOCKED-GAMEPLAY | 2 |
| SZ-JB-09 | Checkpoints de progresso persistidos | interna | INSP | PZ checkpoint | — | GA-01 | 1 |
| SZ-JB-10 | Histórico de jobs com retenção e export | interna | NOVO | — | — | GA-01 | 1 |

## 5. Contratos CLI/API

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-API-01 | Envelope JSON v2 (`ok/status/data/checks/blockers/error`) | mista | APRI | PZ `json-envelope.sh:52-66` | Evolui o envelope v1: acrescenta operationId/jobId/correlationId, `data` schemado e `error` com código estável | F-PL-06, CLI-CONTRACT | 1 |
| SZ-API-02 | CLI `steamzero` com gramática domínio-ação-alvo | usuário | INSP | PZ `pz` (`linux/pz` usage 96-100) | Gramática consagrada do `pz emulation library scan/plan/apply` | F-PL-06 | 1 |
| SZ-API-03 | `--json` puro em stdout (avisos em stderr) | mista | INSP | PZ `-UiContractJson` ("JSON only, no stderr") | — | CLI-CONTRACT | 1 |
| SZ-API-04 | Exit codes estáveis (0/1/2/3/4/69/77) | mista | INSP | PZ códigos 69/77 (`common.sh:49,107,565`) | Formalizados e documentados | CLI-CONTRACT | 1 |
| SZ-API-05 | Daemon JSON-RPC 2.0 sobre UNIX socket | interna | INSP | RD `api_server.sh` | Conceito de API local; protocolo e segurança novos | ADR-0004, F-PL-04 | 1 |
| SZ-API-06 | Allowlist de métodos registrados em código (sem reflexão) | interna | APRI | RD `component_manifest.json` (`"zenity": "configurator_*_dialog"`); ED `RunFunc.sh` (`"$emuName"_install`) | Corrige: ambos despacham nome de função vindo de dados. Aqui: dados nunca escolhem o símbolo executado | P4, SR-19, T-05 | 1 |
| SZ-API-07 | Validação de parâmetros por JSON Schema | interna | NOVO | — | — | SR-04, ADR-0012 | 1 |
| SZ-API-08 | Mutação em duas fases (`plan.create` → `job.submit`) | interna | INSP | PZ library pipeline | Não existe método "faça X agora" mutável | LOCAL-API §3 | 1 |
| SZ-API-09 | Peer credentials (SO_PEERCRED) + socket 0700 | interna | NOVO | — | — | SR-18, T-05, ST-02 | 1 |
| SZ-API-10 | Classes de autorização (read/mutate-safe/confirm/destructive/privileged) | interna | NOVO | — | — | AUTHORIZATION-MODEL | 1 |
| SZ-API-11 | Confirmação tipada para ações destrutivas | usuário | NOVO | — | — | AUTHORIZATION-MODEL, U4 | 1 |
| SZ-API-12 | Event bus com `seq` monotônico e re-hidratação na reconexão | interna | NOVO | — | — | GA-08, EVENTS | 1 |
| SZ-API-13 | Progresso medido (total real ou `null`; proibido sintético) | usuário | APRI | ED zenity progress (`helperFunctions.sh:760`) | Corrige: original mostra barra do curl como se fosse a operação inteira (termina antes de config/verify) | P11, AC-UI-03 | 1 |
| SZ-API-14 | Catálogo de erros com códigos estáveis + gate de CI | mista | NOVO | — | Nenhum dos quatro tem código de erro estável | GA-08, ERROR-CATALOG | 1 |
| SZ-API-15 | Versionamento de contrato (`system.hello`, semver) | interna | NOVO | — | — | E-API-CONTRACT | 1 |
| SZ-API-16 | Correlation ID fim-a-fim (UI→API→job→transação→helper) | interna | NOVO | — | — | SR-20, LOGGING §2 | 1 |

## 6. Privilégio

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-PR-01 | Helper `steamzero-admin` separado, ativado por polkit | interna | APRI | PZ `pz_admin_run` (`common.sh:39-52`) | Corrige: bridge original aceita comando arbitrário de quem chama. Aqui: allowlist enum, sem string de comando | ADR-0009, F-PL-05 | 2 |
| SZ-PR-02 | Allowlist enum de ações (set-tdp, udev, unit, mount, sysctl) | interna | NOVO | — | Nenhum dos quatro formaliza allowlist com parâmetros schemados | GA-11, PRIVILEGE-BOUNDARIES, ST-01 | 2 |
| SZ-PR-03 | Parâmetros schemados com range por modelo (LCD/OLED) | interna | NOVO | — | — | AC-PR-01 | 2 |
| SZ-PR-04 | Conteúdos privilegiados embutidos no helper (nunca do chamador) | interna | APRI | LT `sudo flatpak override` em scripts (`game/faugus.sh`) | Corrige: original passa conteúdo/comando arbitrário sob sudo | SR-12 | 2 |
| SZ-PR-05 | Audit log próprio append-only (root, 0600) | interna | NOVO | — | — | SR-20 | 2 |
| SZ-PR-06 | Registro do valor anterior para rollback G-STATE | interna | NOVO | — | — | RB §G-STATE, RT-12 | 2 |
| SZ-PR-07 | Escalada por comando individual (nunca bloco sob sudo) | interna | INSP | PZ `pz_admin_run` | Espírito preservado, fronteira endurecida | SR-12, AC-PR-02 | 2 |
| SZ-PR-08 | Degradação explícita sem helper (nunca fallback silencioso p/ sudo) | usuário | NOVO | — | — | FM-20, E-PRIV-HELPER-MISSING | 2 |

## 7. Ciclo de vida de componentes

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-LC-01 | Engine única manifest-driven (1 engine + N manifestos) | interna | APRI | ED 31 EmuScripts quase-clones (`functions/EmuScripts/`) | Corrige duplicação O(n): `emuDeckDuckStation.sh` e pares compartilham ~80% do esqueleto | GA §Duplicações, ADR-0006 | 4 |
| SZ-LC-02 | `adapter.json` (identidade, capacidades, fontes, compat, licença) | interna | INSP | RD `component_manifest.json` + LT headers (`# name/version/compat`) | Schema próprio; capacidades declaradas viram UI | F-LC-01, MANIFEST-SCHEMAS §1 | 4 |
| SZ-LC-03 | `detect` — existe? versão? origem (flatpak/appimage/nativo)? | usuário | INSP | ED `checkInstalledEmus.sh`; PZ status | Obrigatório em todo adapter | F-LC-01 | 4 |
| SZ-LC-04 | `status` — saúde detalhada (config, BIOS, paths) | usuário | INSP | RD checks.sh; PZ envelope checks | — | F-LC-01 | 4 |
| SZ-LC-05 | `install` via núcleo transacional | usuário | APRI | ED `installEmuAI.sh` | Corrige: original baixa e move sem transação; SHA256 é o 10º parâmetro **opcional**, raramente usado | AC-IN-01, F-LC-01 | 4 |
| SZ-LC-06 | `update` com pin de versão e canal | usuário | APRI | ED `getReleaseURLGH` (`helperFunctions.sh:413`) | Corrige: original resolve "latest" da API GitHub sem pin — instalação irreproduzível | ADR-0014, F-LC-02 | 4 |
| SZ-LC-07 | `uninstall` com inventário e preservação de dados do usuário | usuário | APRI | ED `uninstallEmuAI/FP/uninstallGeneric.sh` | Corrige: remoção ampla sem inventário nem preservação declarada | F-LC-03, RB-6 | 4 |
| SZ-LC-08 | `repair` dirigido pelo verify (só a camada quebrada) | usuário | APRI | PZ `-Audit -Repair`; ED `autofix.sh`; RD `repair_retrodeck_paths` | Corrige: repair "cego" reaplica config e apaga customização | F-LC-04 | 4 |
| SZ-LC-09 | `verify` com smoke test declarado | usuário | NOVO | — | — | GA-09, F-LC-01 | 4 |
| SZ-LC-10 | Rollback de qualquer operação de ciclo de vida | usuário | NOVO | — | Nenhum dos quatro reverte instalação/atualização de componente | GA §rollback, F-LC-05, RT-01/02 | 1 |
| SZ-LC-11 | Lockfile de componentes por canal (versão+hash testados juntos) | interna | INSP | RD recipe + canais main/cooker | Formaliza: conjunto testado em bloco | SUPPLY-CHAIN §2, ADR-0014 | 4 |
| SZ-LC-12 | Checksum obrigatório (falha, não warning) | interna | APRI | ED `safeDownload` (`helperFunctions.sh:743-772`) | Corrige: checksum opcional vira requisito bloqueante | SR-09, AC-IN-01 | 1 |
| SZ-LC-13 | Detecção de distro/família e seleção de source | interna | INSP | LT `helpers.lib` (`is_arch/is_fedora/is_ostree/...`) | Reimplementado em Python (formato diverge por natureza) | F-LC-06, ADR-0001 | 4 |
| SZ-LC-14 | Adapter Flatpak (`--user`, remotes, overrides) | interna | APRI | LT `pkg_flat`; PZ `lib/flatpak.sh`; RD manifest | Consolida 3 implementações; overrides do usuário sem root | F-LC-06, ADR-0003 | 4 |
| SZ-LC-15 | Adapter AppImage (`~/Applications`, launcher, desktop entry) | interna | INSP | ED `installEmuAI`; PZ `emudeck.sh`/`eden.sh`/`citron.sh` | — | F-LC-01 | 4 |
| SZ-LC-16 | Adapter de pacote nativo (pacman/dnf/apt/rpm-ostree) | interna | INSP | LT `pkg_install`; PZ `lib/pacman.sh` | PZ é Arch-first; aqui multi-família | F-LC-06 | 4 |
| SZ-LC-17 | Idempotência: reinstalar = `no-op` verificado | usuário | APRI | ED `configEmuAI` com overwrite | Corrige: reexecução recopia templates sobre config do usuário | AC-IN-02, RNF-04 | 4 |
| SZ-LC-18 | Hooks Python restritos (sem subprocess/rede livres) | interna | NOVO | — | Alternativa segura ao `component_functions.sh` do RD | ADR-0006 | 4 |

## 8. Configuração

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-CF-01 | Parsers estruturados INI/JSON/XML/YAML com round-trip | interna | APRI | RD `framework.sh:515-592` (get/set via `eval`); ED `configEmuAI` (rsync bruto) | Corrige as duas classes: eval-indireção e sobrescrita bruta. Campos não geridos preservados | F-CF-01, SR-02/03 | 1 |
| SZ-CF-02 | Escrita de config atômica com backup e verify de parse | interna | INSP | PZ `pz_write_managed_file` | — | F-CF-01, FM-12 | 1 |
| SZ-CF-03 | Diff antes de aplicar (origem por campo) | usuário | NOVO | — | — | F-CF-01, CONFIGURATION-SCHEMAS | 1 |
| SZ-CF-04 | Templates de configuração por emulador | usuário | **ADAP** | ED `configs/` (por emulador) | **Sujeito à licença (Q2/ADR-0013)**: maior valor de reuso direto do ED; até a decisão, bloqueado | F-CF-02, REUSE-POLICY | 4 |
| SZ-CF-05 | Presets em camadas (default < platform < device/mode < game) | usuário | INSP | RD `presets.sh` | Resolução determinística e visualização da origem do valor | F-CF-02 | 4 |
| SZ-CF-06 | Config por jogo (nativa do emulador quando suportada) | usuário | INSP | ED per-game configs | Nunca editar config global para um jogo | F-CF-02 | 4 |
| SZ-CF-07 | Restore defaults por seção (preserva custom em backup) | usuário | INSP | RD Configurator | — | F-CF-04 | 4 |
| SZ-CF-08 | Migrações versionadas de config com preservação de comentários | usuário | NOVO | — | Lacuna nos quatro | GA-C, F-CF-03 | 3 |
| SZ-CF-09 | Config da plataforma em TOML + drop-ins + schema | interna | NOVO | — | — | ADR-0012, CONFIGURATION-SCHEMAS | 1 |
| SZ-CF-10 | Config corrompida: backup + restaurar último válido/defaults | usuário | NOVO | — | — | FM-12, FI-14 | 1 |

## 9. Biblioteca e ROMs

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-LB-01 | Scan incremental read-only (hash BLAKE2b, mtime+size) | usuário | INSP | PZ `library/scan.py` | Incremental performático é acréscimo (gap de performance) | F-LB-01, M7 | 3 |
| SZ-LB-02 | Classificação (plataforma, região, disco N de M) | usuário | INSP | PZ `library/registry.py`, `sfo.py`, `vita.py` | — | F-LB-01 | 3 |
| SZ-LB-03 | Plan/apply/verify/rollback de organização | usuário | INSP | PZ `library/{plan,apply}.py` | — | F-LB-02 | 3 |
| SZ-LB-04 | Estrutura de pastas por sistema (layout ES-DE) | usuário | **ADAP** | ED `roms/` (layout ES-DE) | **Sujeito à licença**; alternativa: derivar do formato público do ES-DE | F-LB-01, REUSE-POLICY | 3 |
| SZ-LB-05 | Renomeação e organização com preview | usuário | INSP | PZ library apply | — | F-LB-02 | 3 |
| SZ-LB-06 | Deduplicação por hash | usuário | INSP | PZ media clean (conceito) | — | F-LB-04 | 3 |
| SZ-LB-07 | Multi-disco (M3U) e validação de estrutura | usuário | INSP | RD `m3u_multi_file_validator` | — | F-LB-04 | 3 |
| SZ-LB-08 | Detecção de arquivos incompletos/corrompidos | usuário | INSP | ED checkBIOS (hash); RD checks | Estendido a ROMs | F-LB-04, E-CONTENT-INCOMPLETE | 3 |
| SZ-LB-09 | Conversões CHD/RVZ/CSO/NSZ | usuário | INSP | PZ `romopt/`, `nsz.sh`; RD `compression.sh` | Cobertura de formatos vem do ED | F-LB-03 | 3 |
| SZ-LB-10 | Conversão: staging + espaço com margem + timeout + original até commit | usuário | APRI | RD `compression.sh`; PZ rom-optimize | Corrige: originais convertem sem reserva de espaço nem rollback | AC-LB-02, FI-19, RT-06 | 3 |
| SZ-LB-11 | Import de dumps por cópia (fonte nunca alterada) | usuário | NOVO | — | — | J2, RT-07, USER-DATA §1 | 3 |
| SZ-LB-12 | Órfãos e quarentena de biblioteca | usuário | INSP | PZ `media clean` | — | F-LB-04 | 3 |
| SZ-LB-13 | Migração SSD↔microSD (copy-verify-switch-delete) | usuário | APRI | RD `move_folder_dialog`; PZ removable | Corrige: original move sem transação nem verificação | F-LB-05, USER-DATA §3 | 3 |
| SZ-LB-14 | Verificação de dump por hash contra dat | usuário | INSP | ED checkBIOS (padrão de hash-db) | — | F-LB-01 | 3 |
| SZ-LB-15 | Limpeza de sistemas vazios / rebuild de pastas | usuário | INSP | RD `clean_empty_systems`, `rebuild_esde_systems` | Como operação transacional com preview | F-LB-04 | 3 |

## 10. Conteúdo: BIOS, firmware e keys

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-BI-01 | Store central único (0700) como fonte de verdade | usuário | INSP | RD `retrodeck/bios`; ED `Emulation/bios`; PZ shared-content | — | F-BI-01, ADR-0015 | 3 |
| SZ-BI-02 | Banco de hashes/metadados (sem conteúdo) | interna | **ADAP** | ED `checkBIOS.sh`; RD `config/retrodeck/reference_lists/` | **Sujeito à licença**; alternativa: gerar de fonte com termos claros (G7) | F-BI-01, MANIFEST-SCHEMAS §5 | 3 |
| SZ-BI-03 | Verificação de presença/ausência por plataforma | usuário | INSP | RD BIOS checker; ED checkBIOS | — | F-BI-01, W3 | 3 |
| SZ-BI-04 | Compatibilidade por emulador/versão/região | usuário | NOVO | — | Consolidação inexistente nos quatro | F-BI-01, E-CONTENT-FW-INCOMPAT | 3 |
| SZ-BI-05 | Links seguros para emuladores consumidores | usuário | INSP | PZ `shared-content.sh` | — | F-BI-02, ADR-0015 | 3 |
| SZ-BI-06 | Materialização por cópia gerida quando symlink não serve (FAT/exFAT) | usuário | NOVO | — | — | ADR-0015 §Riscos | 3 |
| SZ-BI-07 | Import local auditado de firmware/keys | usuário | INSP | PZ `ps3.sh import-pkg/import-rap`; `sony.sh` | — | F-BI-03, CONTENT-POLICY | 3 |
| SZ-BI-08 | Keys nunca em logs/relatórios/bundles | interna | NOVO | — | — | SR-14, AC-BI-01, ST-03 | 3 |
| SZ-BI-09 | Ação "importar arquivo local" (nunca link de download) | usuário | NOVO | — | Texto de erro auditado, sem interpolação de sugestão | CONTENT-POLICY, AC-BI-02 | 3 |
| SZ-BI-10 | Auditoria de acesso ao store | interna | NOVO | — | — | F-BI-01 | 3 |

## 11. Saves e sincronização

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-SV-01 | Store central de saves/states | usuário | INSP | RD layout `saves/`+`states/`; ED setupSaves por emu | Layout central vem do RD | F-SV-01 | 3 |
| SZ-SV-02 | Timeline append-only por jogo | usuário | NOVO | — | Nenhum dos quatro versiona saves localmente | GA-04, F-SV-01 | 3 |
| SZ-SV-03 | Backups incrementais com dedupe por hash de blob | interna | NOVO | — | — | GA-04, BACKUP-FORMAT §3 | 3 |
| SZ-SV-04 | Restauração por entrada da timeline (verificada) | usuário | NOVO | — | — | AC-SV-03, RT-09 | 3 |
| SZ-SV-05 | Checkpoint pré-suspensão | usuário | NOVO | — | — | GA-03, F-SV-02 | 2 |
| SZ-SV-06 | Flush pré-desligamento (ação semântica ao emulador) | usuário | NOVO | — | — | F-SV-02, E-SAVES-FLUSH-TIMEOUT | 2 |
| SZ-SV-07 | Cloud sync com fila offline | usuário | APRI | ED `cloudServicesManager.sh`, `cloudSyncHealth.sh` (rclone) | Corrige: original exige rede e espelha direto; aqui fila + pendências visíveis | F-SV-03, GA-06 | 3 |
| SZ-SV-08 | Conflito não-destrutivo (ambos preservados por padrão) | usuário | APRI | ED sync (heurística de timestamp) | Corrige a pior falha possível: last-writer-wins destrói progresso | GA-05, AC-SV-01, J6, ADR-0016 | 3 |
| SZ-SV-09 | Identidade de dispositivo no vetor de conflito | interna | NOVO | — | — | ADR-0016, W4 | 3 |
| SZ-SV-10 | Criptografia opcional antes do upload | usuário | NOVO | — | — | F-SV-03 | 3 |
| SZ-SV-11 | Rollback nunca destrói saves criados após a operação | interna | NOVO | — | — | RB-6 | 1 |

## 12. Mídia e metadados

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-MD-01 | Índice incremental de mídia | usuário | INSP | PZ `media-index.py` | — | F-MD-02 | 3 |
| SZ-MD-02 | Gamelist/boxart/screenshots/vídeos | usuário | INSP | ED `generateGameLists.sh`; PZ `media-gamelist.py`; RD (delega ES-DE) | — | F-MD-01 | 3 |
| SZ-MD-03 | Scraping multi-provedor com cache e retry | usuário | INSP | ED store/scraper; RD ES-DE scraper | — | F-MD-01 | 3 |
| SZ-MD-04 | Rate limit por provedor | interna | NOVO | — | — | F-MD-01, CONFIGURATION §network | 3 |
| SZ-MD-05 | Associação por hash e por identificador | usuário | INSP | PZ media-index | — | F-MD-01 | 3 |
| SZ-MD-06 | Mídia órfã → quarentena (nunca delete direto) | usuário | INSP | PZ `media clean --apply` (move p/ backup) | — | F-MD-02, RT-11 | 3 |
| SZ-MD-07 | Registro de origem e licença da mídia | interna | NOVO | — | — | F-MD-01, THIRD-PARTY | 3 |
| SZ-MD-08 | Validação de payload (magic bytes, tamanho máximo, nome) | interna | NOVO | — | — | T-03, ST-06 | 3 |

## 13. Steam Deck: sessão, modos, hardware

### 13.1 Sessão e modos

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-SD-01 | Session Manager (launching→…→failed) | usuário | NOVO | — | PZ `display-session.sh`/mode-watcher cobrem display/modo, não sessão de jogo | GA-03, F-SD-01 | 2 |
| SZ-SD-02 | Hooks pre-suspend (pausar jobs, flush, checkpoint, snapshot de devices) | interna | NOVO | — | — | GA-03, DF-3 | 2 |
| SZ-SD-03 | Retomada com validação camada a camada (processo/input/áudio/display/microSD/saves) | usuário | NOVO | — | Só a camada defeituosa é reparada; jogo não reinicia | GA-03, J3 | 2 |
| SZ-SD-04 | Máquina de modos (handheld/docked-tv/docked-monitor/desktop/unknown) | usuário | INSP | PZ `detect-mode.sh`, `apply-handheld/docked-tv/docked-monitor.sh`, `mode-watcher.service` | Melhor base isolada: só o PZ tem | F-SD-02 | 2 |
| SZ-SD-05 | Perfil por modo (resolução/Hz/HDR/VRR/escala/áudio/controle/TDP/FPS/UI) | usuário | INSP | PZ modos | — | F-SD-02 | 2 |
| SZ-SD-06 | Cadeia de fallback de display (perfil→sem HDR→sem VRR→menos Hz→menos res→interna) | usuário | NOVO | — | Formalização inexistente em qualquer projeto | FM-18, F-SD-02 | 2 |
| SZ-SD-07 | Detecção LCD/OLED por múltiplos sinais (não só DMI) | interna | APRI | PZ `steamdeck/common.sh` | Corrige a fragilidade de strings DMI | §11.3, HW-matrix | 2 |
| SZ-SD-08 | Dual-screen (Deck+TV) para emuladores de duas telas | usuário | INSP | PZ `dualscreen.sh` | — | F-SD-02 | 4 |

### 13.2 Armazenamento e offline

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-SD-09 | Identificação de volume por UUID | interna | INSP | PZ `install-removable-mount.sh` | — | F-SD-03 | 2 |
| SZ-SD-10 | Monitor de montagem/remoção | interna | INSP | PZ removable mount | — | F-SD-03, FM-06 | 2 |
| SZ-SD-11 | Estado `unavailable(storage-missing)` (nunca "deletado") | usuário | NOVO | — | — | FM-06, J7, AC-SD-02 | 2 |
| SZ-SD-12 | Bloqueio de escrita quando o volume some | interna | NOVO | — | — | FM-06, FI-07 | 2 |
| SZ-SD-13 | Detecção de erro de I/O + relatório de integridade | usuário | NOVO | — | — | FM-07, R7 | 2 |
| SZ-SD-14 | Modo offline: operações locais nunca bloqueiam | usuário | APRI | RD (roda offline pós-install); ED (setup exige rede) | Garantia formal + teste (AC-OF-01) | GA-06, F-SD-04 | 2 |
| SZ-SD-15 | Fila de operações remotas com retomada | interna | NOVO | — | — | GA-06, E-SUPPLY-OFFLINE | 2 |
| SZ-SD-16 | Compat Matrix {SteamOS, Steam Client, Decky, componentes} | interna | NOVO | — | Todos os quatro consertam reativamente | GA-13, F-SD-05, FM-10 | 2 |

### 13.3 Desempenho

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-PF-01 | Perfis de desempenho por escopo (jogo/plataforma/device/modo/energia) | usuário | INSP | PZ `performance.sh`, `optimizers/`, `tuning/` | — | F-PF-01 | 2 |
| SZ-PF-02 | GameMode | usuário | INSP | LT `game/gamemode.sh`; PZ tuning | — | F-PF-01 | 4 |
| SZ-PF-03 | Gamescope (resolução, upscaling, FSR) | usuário | INSP | PZ performance-launch | — | F-PF-01 | 4 |
| SZ-PF-04 | MangoHUD | usuário | INSP | PZ tuning; ED advanced settings | — | F-PF-01 | 4 |
| SZ-PF-05 | TDP/clock via helper | usuário | INSP | PZ `install-privileged-controls.sh` | Agora atrás da allowlist enum | F-PF-01, SZ-PR-02 | 2 |
| SZ-PF-06 | Meta de FPS / frame pacing / limite | usuário | INSP | PZ performance | — | F-PF-02 | 4 |
| SZ-PF-07 | Frame generation (LSFG) verificado | usuário | INSP | PZ `performance prepare-lsfg` | Instalação verificada por manifesto | F-PF-02 | 4 |
| SZ-PF-08 | Restauração do estado ao sair | usuário | INSP | PZ `windows-vm optimize` (padrão apply/restore) | — | F-PF-03, RT-12 | 2 |
| SZ-PF-09 | Perfis LCD/OLED e portátil/dock/bateria | usuário | INSP | PZ modos + tuning | — | F-PF-02 | 2 |

### 13.4 Controles

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-CT-01 | Vocabulário de ações semânticas universais | usuário | NOVO | — | ED/RD entregam hotkeys por emulador; o vocabulário único é novo | ADR-0017, F-CT-02 | 4 |
| SZ-CT-02 | Mapeamento ação semântica → mecanismo do emulador | interna | INSP | PZ `hotkey-actions.sh`, `input-actions.sh`; RD hotkeys | Declarado em `semanticActions` do adapter | ADR-0017 | 4 |
| SZ-CT-03 | Perfis Steam Input por emulador/plataforma/jogo | usuário | **ADAP** | ED templates de perfil; RD controller layouts | **Sujeito à licença** se os templates forem derivados | F-CT-01, REUSE-POLICY | 4 |
| SZ-CT-04 | Instalação de layouts no Steam | usuário | INSP | RD `install_retrodeck_controller_layouts` | — | F-CT-01 | 4 |
| SZ-CT-05 | Hot-swap de controle sem perder foco/modal | usuário | INSP | PZ `controllers.sh` | — | F-CT-03, FI-11 | 2 |
| SZ-CT-06 | Recuperação de controle pós-suspensão | usuário | INSP | PZ controllers | — | F-CT-03, J3 | 2 |
| SZ-CT-07 | Gyro, trackpads, botões traseiros, menus radiais | usuário | INSP | PZ controllers; ED templates | — | F-CT-03 | 4 |
| SZ-CT-08 | Detecção de conflitos de layout | usuário | NOVO | — | — | F-CT-03 | 4 |
| SZ-CT-09 | Teste de botões e eixos na UI | usuário | INSP | PZ controllers (diagnóstico) | — | F-CT-03 | 5 |
| SZ-CT-10 | Multiplayer local (ordem de controles) | usuário | INSP | ED/RD (ordem por emulador) | — | F-CT-03 | 4 |
| SZ-CT-11 | Glyphs dinâmicos por tipo de controle | usuário | NOVO | — | — | NAVIGATION §5, UI-TESTS | 5 |

### 13.5 Handheld Desktop (escopo M10-H)

Escopo acrescentado durante a implementação (ADR-0019, submarco M10-H da Fase 4): operar o Desktop Mode (KDE/BigLinux) como plataforma de referência, com perfis, ownership único de entrada e reversibilidade dos efeitos aplicados ao desktop. Não constava da fundação original — proveniência apurada contra os quatro projetos por esta matriz.

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-HD-01 | Perfis KDE `handheld-desktop`/`docked-desktop`/`safe` com contexto e override | usuário | INSP | PZ `apply-handheld.sh`/`apply-docked-*.sh` (modos Steam Deck) | Original aplica modo no Game Mode; aqui o alvo é a sessão KDE, com fingerprint de contexto e override do usuário | F-HD-01, ADR-0019, M10-H | 4 |
| SZ-HD-02 | Contexto de hardware/capabilities (detecção sem exclusividade de distro) | interna | INSP | LT `helpers.lib` (`is_*`); PZ `capabilities/` | Capability-based: ausência de provider degrada a capacidade, não o núcleo | F-HD-01, ADR-0019 §3 | 4 |
| SZ-HD-03 | Ownership exclusivo de entrada (um único owner lógico) | interna | NOVO | — | Conflito genérico mantém o coordenador em modo observador; nunca dois remapeadores | F-HD-02, ADR-0019 §4 | 4 |
| SZ-HD-04 | Providers de input/teclado atrás de portas (InputPlumber opcional) | interna | NOVO | — | InputPlumber só vira owner após validação em hardware | F-HD-02, ADR-0019 §3 | 4 |
| SZ-HD-05 | Snapshot G-STATE persistente antes do primeiro efeito no desktop | interna | INSP | PZ boot backup bundle (`common.sh:260-282`) — padrão de snapshot pré-mutação | Aplica o padrão de backup do PZ a efeitos de sessão KDE | F-HD-03, RB §G-STATE | 4 |
| SZ-HD-06 | Verify + rollback dos efeitos Desktop; crash deixa recovery pendente | usuário | NOVO | — | Nenhum dos quatro reverte mudanças de sessão de desktop | F-HD-03, FM-17, R1 | 4 |
| SZ-HD-07 | Modo seguro sem provider (degradação garantida) | usuário | NOVO | — | — | F-HD-01, ADR-0019 §5 | 4 |
| SZ-HD-08 | Central Qt/QML touch+controle | usuário | INSP | LT app GTK (catálogo); PZ WPF+contrato | Precedente de central gráfica; toolkit e contrato próprios | F-HD-04, ADR-0002 | 4/5 |
| SZ-HD-09 | Bridge efêmera allowlisted (UI↔núcleo) | interna | INSP | PZ contrato UI↔orchestrator (`-UiContractJson`) | Efêmera: sem serviço residente para a central | F-HD-04, SR-19 | 4 |
| SZ-HD-10 | Independência de runtime (zero dependência do PhaseZero em produção) | interna | NOVO | — | Pesquisa/atribuição ao PZ permanecem **documentais**; nenhum import/serviço/path compartilhado | F-HD-05, ADR-0019 §1 | contínuo |
| SZ-HD-11 | Importador legado offline separado (read-only, não empacotado) | usuário | INSP | PZ `emulation layout` (dados a adotar) | Conversão offline por ferramenta separada, fora do pacote | F-HD-05, ADR-0019 §2, PHASEZERO-MIGRATION | contínuo |
| SZ-HD-12 | Gate AST/packaging em CI contra regressão das regras acima | interna | NOVO | — | Fronteiras do ADR-0019 verificadas por CI | F-HD-05, ADR-0019 §6, ST-10 | contínuo |

## 14. Frontends, UI, operações e distribuição

### 14.1 Frontends

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-FE-01 | Adapter Steam (shortcuts.vdf com backup, parser, dedupe) | usuário | APRI | PZ `steam-shortcut.py`; ED/RD via SRM | Corrige: escrita direta em vdf sem backup/dedupe | F-FE-02, RT-13 | 4 |
| SZ-FE-02 | Adapter Steam ROM Manager (parsers) | usuário | INSP | PZ `srm.sh`; ED `runSRM.sh` + parsers | — | F-FE-01 | 4 |
| SZ-FE-03 | Adapter ES-DE (es_systems/es_settings/gamelists) | usuário | INSP | RD (ES-DE embutido); ED setup | — | F-FE-01 | 4 |
| SZ-FE-04 | Adapter RetroArch (cores, playlists) | usuário | INSP | ED emuDeckRetroArch; RD component | — | F-FE-01 | 4 |
| SZ-FE-05 | Adapter RetroDECK (interop de paths compartilhados) | usuário | INSP | PZ `retrodeck.sh` (status/plan/integrate/repair) | — | F-FE-01, RETRODECK-IMPORT | 4 |
| SZ-FE-06 | Adapter Heroic | usuário | INSP | PZ `heroic.sh`/`heroic.py` | — | F-FE-01 | 4 |
| SZ-FE-07 | Import LaunchBox (somente leitura) | usuário | INSP | PZ `launchbox_import.py` | — | F-FE-01 | 4 |
| SZ-FE-08 | Launcher genérico parametrizado | interna | APRI | ED `tools/launchers/*` (1 por emulador); RD `component_launcher.sh` | Corrige duplicação: 1 launcher + perfis | GA §Duplicações | 4 |
| SZ-FE-09 | Núcleo desacoplado de qualquer frontend | interna | NOVO | — | RD é acoplado ao ES-DE | GA §arquitetura, P9 | 4 |

### 14.2 UI

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-UI-01 | Game Mode UI (Godot 4) | usuário | INSP | RD Godot Configurator (`godot-configurator.sh`) | Precedente real de Godot no domínio; UI própria | F-UI-01, ADR-0002 | 5 |
| SZ-UI-02 | Dashboard (pronto/problemas/atualizações/saves/espaço/jobs) | usuário | NOVO | — | — | GA-10, §12.4, W1 | 5 |
| SZ-UI-03 | Biblioteca virtualizada (10k+ itens) | usuário | NOVO | — | — | GA-10, UI-TESTS | 5 |
| SZ-UI-04 | Página do jogo (13 ações agregadas) | usuário | NOVO | — | — | §12.5, W2 | 5 |
| SZ-UI-05 | Centro de BIOS (cartões por plataforma) | usuário | INSP | RD BIOS checker (UX) | Acrescenta import local e hash expansível | §12.6, W3 | 5 |
| SZ-UI-06 | UI de Jobs (etapa real, cancelamento em 2 fases) | usuário | NOVO | — | — | §12.7, W6 | 5 |
| SZ-UI-07 | UI de conflito de save (decisão preservadora) | usuário | NOVO | — | — | GA-05, W4 | 5 |
| SZ-UI-08 | Desktop UI (lote, avançado, logs, migrações) | usuário | INSP | PZ WPF + contrato JSON; LT catálogo GTK | Contrato UI↔núcleo é o padrão herdado do PZ | F-UI-02, ADR-0002 | 5 |
| SZ-UI-09 | QAM adapter opcional (Decky) | usuário | INSP | PZ `install-plugins.sh`, `decky-ws-client.py` | Opt-in por design, escopo restrito | F-UI-03, ADR-0008 | 5 |
| SZ-UI-10 | Degradação limpa sem Decky | usuário | INSP | PZ (Decky já é opcional) | — | FM-11, P9 | 5 |
| SZ-UI-11 | Navegação 100% gamepad + focus graph declarado | usuário | NOVO | — | — | GA-10, §12.3, AC-UI-01 | 5 |
| SZ-UI-12 | Teclado virtual automático | usuário | INSP | PZ `steamdeck keyboard repair` (Maliit/KDE) | — | NAVIGATION §6 | 5 |
| SZ-UI-13 | Tradução erro→impacto→ação (opt-in de detalhes) | usuário | NOVO | — | — | GA-08, §12.1, ERROR-UX | 5 |
| SZ-UI-14 | Acessibilidade (escala 100/125/150/TV, contraste, redução de movimento, labels) | usuário | NOVO | — | Nenhum dos quatro tem acessibilidade formal | GA-14, F-UI-04 | 5 |
| SZ-UI-15 | Fallback zenity (apenas emergência) | usuário | APRI | LT `linuxtoys.lib` (zenity + fallback TTY); RD zenity-first | Corrige: zenity deixa de ser o fluxo principal | ADR-0002, §12.10 | 5 |
| SZ-UI-16 | Assistente de primeira execução | usuário | INSP | RD `finit_options`; ED setup wizard | — | J1 | 5 |

### 14.3 Operações e diagnóstico

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-OP-01 | Logs estruturados JSONL (0600, rotação, níveis) | interna | APRI | PZ `pz_log` (`common.sh:20-33`, rotação `:14`); RD `logger.sh` (níveis) | Corrige: PZ é textual sem estrutura; RD sem higiene de permissão. Junta os dois pontos fortes | GA-08→LOGGING, ADR-0011 | 1 |
| SZ-OP-02 | Proibição de segredos em log (tipo Secret + handler) | interna | NOVO | — | — | SR-13, ST-03 | 1 |
| SZ-OP-03 | Anonimização de paths (`{ROMS}/…`) | interna | NOVO | — | — | LOGGING §política | 1 |
| SZ-OP-04 | `doctor` em camadas (read-only, checks codificados) | usuário | INSP | PZ `-Doctor`, `steamdeck status`, `flatpak audit` | — | F-PL-07 | 1 |
| SZ-OP-05 | `doctor --repair` propõe planos (nunca repara direto) | usuário | APRI | PZ `-Audit -Repair`; `flatpak audit --repair` | Corrige: repair direto vira plano com preview | DIAGNOSTICS | 1 |
| SZ-OP-06 | Watchdogs (mounts, sessão, QAM healthcheck) | interna | NOVO | — | — | DIAGNOSTICS §auto | 2 |
| SZ-OP-07 | Support bundle anonimizado com preview obrigatório | usuário | INSP | RD support/logs; PZ runtime-diagnose | Preview antes de exportar e zero envio automático são novos | F-PL-07, §14, N7 | 5 |
| SZ-OP-08 | Canais stable/beta/dev com lockfile | usuário | INSP | RD main/cooker + install specific release | Formaliza garantias por canal | RELEASE-CHANNELS, ADR-0014 | 6 |
| SZ-OP-09 | Update da plataforma transacional | usuário | INSP | RD update via Flatpak; PZ `updates/` | — | F-PL-08, UPDATE §1 | 6 |
| SZ-OP-10 | Rollback da plataforma (commit OSTree anterior) | usuário | NOVO | — | — | RT-14, UPDATE §2 | 6 |
| SZ-OP-11 | Runbooks de recuperação (R1–R7) | usuário | NOVO | — | — | RECOVERY | 5 |
| SZ-OP-12 | Backup completo do usuário (`--full`) | usuário | APRI | RD `configurator_retrodeck_backup_dialog` (tar de userdata) | Acrescenta manifesto verificável e restauração conferida | BACKUP-FORMAT §Backup completo | 3 |

### 14.4 Migrações e adoção

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-MG-01 | Detecção read-only de instalação EmuDeck | usuário | NOVO | — | — | EMUDECK-IMPORT | 5 |
| SZ-MG-02 | Detecção read-only de instalação RetroDECK (lê `retrodeck.cfg`) | usuário | INSP | PZ `retrodeck status` | — | RETRODECK-IMPORT | 5 |
| SZ-MG-03 | Adoção por referência (dados não são movidos) | usuário | NOVO | — | — | USER-DATA §1, RT-07 | 5 |
| SZ-MG-04 | Relatório de compatibilidade pré-plano | usuário | NOVO | — | — | EMUDECK-IMPORT | 5 |
| SZ-MG-05 | Detecção de drift por dupla-gestão | usuário | NOVO | — | — | R-11, RETRODECK-IMPORT | 5 |
| SZ-MG-06 | Import idempotente (detecta já-adotado por hash) | usuário | NOVO | — | — | USER-DATA §4 | 5 |
| SZ-MG-07 | Adoção do layout `Emulation/` do PhaseZero | usuário | INSP | PZ `emulation layout` | — | PHASEZERO-MIGRATION | 5 |

### 14.5 Build, distribuição e supply chain

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-DS-01 | Flatpak da plataforma (portais, permissões mínimas) | interna | INSP | RD `net.retrodeck.retrodeck.yml` | Diferença: emuladores ficam FORA do nosso Flatpak | ADR-0003 | 6 |
| SZ-DS-02 | Empacotamento multi-formato do helper (rpm/deb/pkgbuild) | interna | INSP | LT `src/buildfiles/` (deb/rpm/pkgbuild/flatpak, flake.nix) | — | ADR-0003 | 6 |
| SZ-DS-03 | Lockfile de dependências com hash | interna | NOVO | — | — | SR-11, SUPPLY-CHAIN | 1 |
| SZ-DS-04 | SBOM por release | interna | NOVO | — | — | SUPPLY-CHAIN, §15 | 1 |
| SZ-DS-05 | Artefatos assinados + proveniência | interna | NOVO | — | — | SUPPLY-CHAIN | 6 |
| SZ-DS-06 | Builds reproduzíveis (meta) | interna | INSP | RD manifest com fontes hashadas | — | SUPPLY-CHAIN | 6 |
| SZ-DS-07 | Instalação sem pipe de script remoto para shell | usuário | APRI | ED `install.sh` (método upstream: `curl` canalizado para `bash`) | Corrige: instalação oficial por Flatpak/pacote com checksum publicado | SR-02, SUPPLY-CHAIN §anti | 6 |
| SZ-DS-08 | Scan de vulnerabilidades em CI | interna | NOVO | — | — | SR-11 | 1 |
| SZ-DS-09 | THIRD-PARTY-NOTICES gerado do SBOM | interna | INSP | RD `other_licenses.txt` | Automatizado | ATTRIBUTION-PLAN §7 | 6 |

### 14.6 Qualidade e verificação (engenharia)

| ID | Função | Camada | Prov. | Origem + evidência | Nota | Ref | Fase |
|---|---|---|---|---|---|---|---|
| SZ-QA-01 | Suíte de testes em CI (unit/integração) | interna | INSP | PZ 122 arquivos Pester + CI (parse+test) | Melhor base isolada: ED/LT praticamente não testam | GA-12, TEST-STRATEGY | 1 |
| SZ-QA-02 | Injeção de falhas (FI-01..20) com crash gates | interna | NOVO | — | PZ tem `resilience.tests.ps1` (Windows), mas não a matriz de 20 classes | GA-12, FAILURE-INJECTION | 1 |
| SZ-QA-03 | Testes de rollback com protocolo de aprovação (§13.6) | interna | NOVO | — | — | ROLLBACK-TESTS | 1 |
| SZ-QA-04 | Golden files de contrato | interna | NOVO | — | — | TEST-STRATEGY §2 | 1 |
| SZ-QA-05 | Lints de fronteira arquitetural (import-linter, escrita fora de core.fs) | interna | NOVO | — | — | MODULE-BOUNDARIES, ST-10 | 1 |
| SZ-QA-06 | Testes de idempotência (2× e compara estado) | interna | NOVO | — | — | RNF-04, TEST-STRATEGY §4 | 1 |
| SZ-QA-07 | Fixtures sintéticas (zero conteúdo protegido) | interna | NOVO | — | — | CONTENT-POLICY, TEST-STRATEGY §3 | 1 |
| SZ-QA-08 | Fuzzing do helper privilegiado | interna | NOVO | — | — | ST-01, AC-PR-01 | 2 |
| SZ-QA-09 | Canary de segredos em logs/bundles | interna | NOVO | — | — | ST-03 | 1 |
| SZ-QA-10 | Testes de UI (focus graph, escalas, glyphs) | interna | NOVO | — | — | UI-TESTS | 5 |
| SZ-QA-11 | Distinção `verified-vm` × `verified-hw` no relatório | interna | NOVO | — | — | §20, HW-matrix | 2 |

---

## 15. Sumário quantitativo

**Total: 262 funções catalogadas** (IDs `SZ-*` únicos). Contagens apuradas por script sobre este arquivo (comandos no rodapé da seção), não estimadas.

### Por proveniência

| Prov. | Qtd | % | Leitura |
|---|---|---|---|
| **NOVO** | 117 | 44,7% | Quase metade do produto é valor que nenhum dos quatro entrega — concentrado no núcleo (transação, journal, jobs, state), na resiliência do Deck (sessão, offline, compat matrix), na proteção de saves e em toda a camada de qualidade/verificação |
| **INSP** | 104 | 39,7% | Conceitos herdados com implementação independente — livre da questão de licença |
| **APRI** | 37 | 14,1% | Funções que existem nos originais **com falha documentada** que corrigimos (cada linha cita `arquivo:linha`) |
| **ADAP** | 4 | 1,5% | Único conjunto sujeito à decisão de licença (detalhe abaixo) |

Funções com origem rastreável (INSP+APRI+ADAP): **145**.

### Por projeto de origem (citações nas 145 linhas com origem)

| Projeto | Citações | Papel confirmado |
|---|---|---|
| **PhaseZero** | 93 | Arquitetura de execução: transação, atomicidade, containment, privilégio, modos Deck/Desktop, CLI/envelope, disciplina de testes |
| **RetroDECK** | 47 | Plataforma e distribuição: Flatpak, manifests de componente, BIOS/UX, presets, canais, logger, backup de userdata |
| **EmuDeck** | 41 | Domínio e cobertura: templates de config, formatos, cloud sync, estrutura de ROMs — e a maior concentração de linhas APRI |
| **LinuxToys** | 11 | Modularidade e portabilidade: metadados declarativos, detecção de distro/capabilities, empacotamento multi-formato |

Soma (192) excede 145 porque linhas de proveniência mista citam mais de um projeto. A distribuição confirma quantitativamente a tese da [ROBUSTNESS-SCORE](ROBUSTNESS-SCORE.md): PhaseZero domina como base de **execução**; RetroDECK como base de **plataforma**; EmuDeck contribui **domínio** (e defeitos a corrigir); LinuxToys contribui **forma**.

Nota de independência: a citação do PhaseZero é **documental** (proveniência de conceito e evidência de auditoria). Conforme ADR-0019, o produto não tem dependência, import, serviço ou path compartilhado com o PhaseZero em runtime — ver SZ-HD-10.

### Por camada

| Camada | Qtd |
|---|---|
| interna | 131 |
| usuário | 127 |
| mista (contrato exposto ao usuário e ao núcleo) | 4 |

### Por fase do roadmap

| Fase | Qtd | |
|---|---|---|
| 1 — Núcleo mínimo | 88 | maior bloco: é onde vivem transação, fs, state, jobs, contratos |
| 2 — Steam Deck Core | 37 | |
| 3 — Conteúdo | 46 | |
| 4 — Emuladores, frontends e Handheld Desktop (M10-H) | 50 | |
| 4/5 — transição | 1 | central Qt/QML (SZ-HD-08) |
| 5 — UI | 28 | |
| 6 — Distribuição | 9 | |
| contínuo | 3 | regras de independência do ADR-0019 |

(Função citada em mais de uma fase conta na primeira.)

> Reprodução das contagens:
> `grep -c '^| SZ-' FUNCTION-PROVENANCE-MATRIX.md` (250 linhas de função)
> `awk -F'|' '/^\| SZ-/{p=$5;gsub(/[ *]/,"",p);c[p]++}END{for(k in c)print k,c[k]}'` (proveniência)
> `awk -F'|' '/^\| SZ-/{gsub(/ /,"",$9);f[$9]++}END{for(k in f)print k,f[k]}'` (fase)

### Linhas ADAP — o conjunto bloqueado pela licença (Q2/ADR-0013)

| ID | Função | Artefato de origem | Alternativa se a licença for incompatível |
|---|---|---|---|
| SZ-CF-04 | Templates de configuração por emulador | ED `configs/` | Reconstruir templates a partir da documentação de cada emulador (custo alto — é o maior valor de reuso do EmuDeck) |
| SZ-LB-04 | Estrutura de pastas por sistema | ED `roms/` | Derivar do formato público do ES-DE (baixo custo) |
| SZ-BI-02 | Banco de hashes de BIOS | ED `checkBIOS.sh`; RD `reference_lists/` | Gerar de fonte com termos de redistribuição claros (G7) |
| SZ-CT-03 | Perfis Steam Input por emulador | ED templates; RD layouts | Criar perfis próprios a partir do vocabulário semântico (custo médio) |

**Consequência:** **258 das 262 funções (98,5%) podem ser implementadas independentemente da decisão de licença** (Q2/ADR-0013). Apenas estas 4 ficam bloqueadas — e todas têm alternativa documentada. Ou seja: a licença não bloqueia a implementação; ela decide apenas o custo de reconstruir estes 4 artefatos.
