# Plano — Fase 1: Provar o laço primário (ligar → boot Game Mode → instalar emulador → jogar uma ROM)

## ENTREGA 0 (primeiro passo, antes de qualquer código): registrar este plano como memória persistente

Antes de tocar em código, gravar **este plano integral** em `.zcode/plans/plan-fase1-laco-primario.md` como fonte de verdade da Fase 1. Este documento é o que guia a execução e o ponto de retomada de qualquer sessão futura.

O documento gravado **deve conter uma seção obrigatória "Memória e WORKLOG — disciplina do agente"** com estas regras, que todo agente que executar um item deve seguir:

- **WORKLOG é apêndice-only.** Ao **iniciar** cada item: acrescentar (nunca editar sessões anteriores) um bloco curto em `docs/WORKLOG.md` no formato existente — título `## <AAAA-MM-DD> — <item> — iniciado`, com branch base, escopo, dependências e o que o item entrega. Ao **concluir** cada item (gates verdes, commit feito): acrescentar o bloco de fechamento — o que foi feito, os commits, os testes que provam, e o que **não** foi feito e por quê; declarar explicitamente "Nenhuma ação de host, release ou push foi executada" quando for o caso (AGENTS.md §2/§9).
- **Um item = um commit atômico = um par de blocos WORKLOG** (iniciado + fechado). Nenhum item é concluído sem o bloqueio de fechamento no WORKLOG.
- **Toda decisão de bancada** (escolha entre alternativas, causa raiz descoberta, armadilha evitada) entra no bloco de fechamento do item — é a memória que evita retrabalho (o repo já usa esse padrão; as "decisões que custaram caro" do P0-03 são o modelo).
- **Atualizar `docs/KNOWN-GAPS.md`** quando um gap fecha (G11, capability-matrix "0 cores", etc.) — no mesmo commit do fechamento, nunca depois.
- **Relatório final** ao fim da Fase 1 (AGENTS.md §9): tabela item→commit→testes; fora-de-escopo; ações de host executadas + release ativa + rollback; passos que ainda exigem o operador.

Esta entrega 0 é só gravação de documento + gravação do bloco WORKLOG "plano registrado". Sem código, sem host.

---

## Memória e WORKLOG — disciplina do agente

- **WORKLOG é apêndice-only.** Ao iniciar cada item, acrescentar (nunca editar
  sessões anteriores) `## <AAAA-MM-DD> — <item> — iniciado`, com branch base,
  escopo, dependências e entrega. Ao concluir, acrescentar o bloco de
  fechamento com o que foi feito, commit, testes, o que não foi feito e por
  quê; declarar explicitamente "Nenhuma ação de host, release ou push foi
  executada" quando aplicável.
- **Um item = um commit atômico = um par de blocos WORKLOG.** Nenhum item é
  concluído sem o fechamento correspondente.
- **Decisões de bancada** (alternativas, causa raiz e armadilhas evitadas)
  entram no fechamento do item, para que a próxima sessão não redescubra o
  mesmo contexto.
- **`docs/KNOWN-GAPS.md`** é atualizado no mesmo commit de fechamento quando
  uma lacuna realmente fecha. Check read-only, harness ou código preparado não
  fecham uma lacuna cuja prova física ainda não foi executada.
- O **relatório final** da Fase 1 segue AGENTS.md §9: tabela
  item→commit→testes, fora de escopo, ações de host/release/rollback e os
  próximos passos do operador.

## Estado de retomada auditado em 2026-08-06

O plano original abaixo registra a intenção inicial. A implementação efetiva,
que prevalece sobre detalhes incompatíveis daquela intenção, é:

- **Itens 1–3 concluídos na base `39bd325`:** `kind: core` no schema e bloco
  `core` do manifesto; fonte portátil `archive` pinada (em vez do proposto
  `libretro-core`); `LibretroCoreExecutor`; 17 manifestos `libretro-*`; lockfile
  e matrix com 17 cores instaláveis e 0 plataformas bloqueadas.
- **Item 5a concluído em `8a0425b`:** check read-only `boot.direct` no doctor.
- **Item 4 (código) concluído em `4d4c989`:** driver de certificação M10,
  protocolo e provisionador que exige autorização. A execução de VM real e a
  evidência física **não** foram feitas; DEBT-A7 não pode ser declarado fechado.
- **Restante pendente:** merge/CI na linha principal e os itens 5b–5h. Todos
  exigem primeiro a autorização explícita do operador descrita em AGENTS.md;
  este plano não autoriza mutação de host, release, VM, reboot nem push.

---

## Decisões de arquitetura (justificadas na bancada — vão no documento gravado)

**BE-2 — cores: `kind: core` + source type `libretro-core` + `CoreExecutor` dedicado.**
O sistema já foi projetado para um `kind: core` existir: o gate `_core_providers` em `tools/capability_matrix.py:67-74` devolve `{m.id for m in manifests if m.kind == "core"}` e `test_core_providers_are_derived_not_asserted` (`tests/unit/test_capability_matrix.py:50-57`) o trava. Hoje o valor é `0` e 15 plataformas ficam bloqueadas. Logo, estender o enum é o caminho **pretendido**. O contrato "core exigido" já está completo ponta-a-ponta: manifesto de plataforma → `launch.core` → registry sancionado `PLATFORM_CORES` (`launch_profile.py:43-71`) → probe `find_core` → **recusa jogar** em `emulation.py:1066-1076`. Falta só o caminho de **instalação**. O `CoreExecutor` reusa a camada de transação (`steamzero.core.transaction`) — staging→backup→intent→activate→verify→smoke→commit, WAL journal, rollback por hash, crash recovery — mesma de `AdapterEngine`/`FlatpakExecutor`; destino = dir de cores do RA resolvido por `find_core`/`_CORE_DIRS` (`launch_profile.py:228-258`).

**BE-1 — 3 emuladores do M10: RetroArch + PCSX2 + PPSSPP** (flatpak, sem keys/firmware). RetroArch destrava 15 plataformas via BE-2; os outros dois são flatpaks puros — menor risco no primeiro ciclo de VM. Switch (AppImage, keys+firmware) e plataformas com BIOS vão para a43+. DuckStation (EOL no `component-lock.json:57`) sai do M10.

**CX-2 — boot direto:** majoritariamente ação do operador (protocolo pós-reboot). De código, fecho o gap secundário que identifiquei: o `doctor` não checa boot → adiciono check `boot.direct` read-only.

## Pré-requisito (sem host)
- Nova branch de `origin/main@39bd325` (a atual `codex/b0-capability-matrix` está totalmente mesclada).
- Commits atômicos por item; 4 gates após cada um: `.venv/bin/python tools/run_tests_isolated.py tests -q`, `.venv/bin/ruff check src tools tests`, `.venv/bin/mypy src`, `make independence boundaries`. Cobertura não regride.
- Não construo wheel (AGENTS.md §4). Toda ação de host exige autorização do operador na thread atual (AGENTS.md §1).

---

## Item 1 — `kind: core` no contrato de adapter (BE-2, fundação)
Estende o enum `kind` e adiciona source type `libretro-core`; o registry valida invariantes novos. Sem executor ainda.
- `adapter-v1.schema.json:25-31`: enum `kind` → add `"core"`. `:214-220`: enum `sources[].type` → add `"libretro-core"`. Novo conditional `allOf`: `libretro-core` exige `url`+`sha256`+`version`, proíbe `ref`/`remote`.
- `registry.py:148-176`: `libretro-core` entra no grupo dos portáteis (url+sha256 obrigatórios; ref/remote proibidos), sem exigir commit 64-hex. Mantém `additionalProperties:false`. Invariante novo: manifesto `kind: core` deve pertencer a `platforms` cujo core está em `PLATFORM_CORES` (validação cruzada manifesto↔sancionado, mesma classe de `launch_profile.py:126-135`).
- Lockfile fixture de teste primeiro (tuple de validação em `lockfile.py:93-141` estendido se preciso). `make update-capability-matrix` regrava `CAPABILITY-MATRIX.md`.
- **Testes** (`test_registry.py`/`test_adapters.py`): core válido carrega; fora do enum reprova; core não-sancionado reprova; sem sha256 reprova (`E-SUPPLY-NO-CHECKSUM`); mistura de campos reprova; lockfile drift reprova. Gates.

## Item 2 — `CoreExecutor` que entrega cores (BE-2, executor)
Novo `src/steamzero/adapters/core_executor.py`, espelhando `AdapterEngine` (`engine.py:66-317`) sobre a transação compartilhada.
- Construtor injetável: `artifacts: ArtifactPort` (default `HttpsArtifactPort`), `store`, `registry`, `now`. Rede só via porta injetada.
- `resolve_cores_dir()`: consulta `find_core`/`_CORE_DIRS`; RA ausente → `E-CONTENT-UNSUPPORTED` ("instale o RetroArch antes de instalar cores" — honra `launch_profile.py:11-15`).
- `plan_install`: fetch → `crypto.digest_bytes` → compara `sha256` (`E-SUPPLY-CHECKSUM`) → cache `data_home/downloads/cores/<sha256>` → `transaction.plan_copy_files` destino `<cores_dir>/<core>_libretro.so` (extrai se `.zip`); `confirm_token=secrets.token_urlsafe(24)`.
- `apply`: `transaction.apply(...)` com callback verify = re-hash + smoke (carregamento core via RA headless se possível; nunca finge sucesso). `status`: re-hash → `missing`/`installed`/`degraded`. `rollback`: `transaction.rollback`.
- Roteamento: `route_for` (`lifecycle.py:125-173`) ganha branch `kind=="core"` → `executor="core"`, `installable` se sha256+url presentes e RA detectável; `"core"` no enum do `LifecycleRoute` (`:95-115`); delegado `_core()` na fachada `ComponentLifecycle` (`:316`).
- **Testes** (`tests/integration/test_core_executor.py`, padrão `test_component_lifecycle.py`): `FakeArtifacts`, `monkeypatch` XDG + `fs.ensure_state_layout()`; plan→apply→verify→rollback; sha256 errado; RA ausente recusa; smoke-failure auto-rollback; crash recovery (`SimulatedKill`); idempotência; roteamento; matrix missing/installed/degraded. Gates.

## Item 3 — 17 manifestos de core em produção (BE-2 parcial)
- Manifestos `src/steamzero/adapters/manifests/<core>.adapter.json` para os 17 sancionados (`mgba, mesen, snes9x, genesis_plus_gx, fbneo, mednafen_pce, mednafen_ngp, mednafen_wswan, bluemsx, fuse, vice_x64, puae, stella, freeintv, mednafen_vb, opera, mupen64plus_next`): `kind: core`, `platforms` do inverso de `PLATFORM_CORES`, `sources: [{type: libretro-core, url, sha256, version}]`. **Hashes de fonte oficial libretro/RetroArch, proveniência registrada — nunca inventados.**
- Lockfile atualizado; `validate_registry_lock` verde; matrix verde com 17 cores entregues. M10 (PCSX2/PPSSPP/RetroArch) já é flatpak nos manifests existentes — nada novo.
- **Testes**: `test_bundled_registry_loads_verified_emulation_adapters` estendido p/ 17 cores; lockfile drift; matrix versionada. Gates. A partir daqui o produto **declara** capacidade de entregar cores (verified-dev); instalação física vem nos Itens 5/6.

## Item 4 — Harness de VM descartável para M10 (BE-1 / DEBT-A7)
Fecha DEBT-A7. Hoje não existe VM versionada; o host tem lab KVM/libvirt (WORKLOG Sessão 29).
- `tools/vm_harness/`: criação de VM descartável via `virt-install`/cloud-init (Arch base + SDDM + flatpak), snapshot btrfs antes, e driver que executa `component plan/apply/rollback` reais contra `flatpak` real para RetroArch + PCSX2 + PPSSPP, 3 ciclos completos cada (install→update→rollback→roll-forward).
- Protocolo `OPERATIONAL-TRUST-GATES.md:19-35` (8 passos) embutido. Driver valida argv `_FLATPAK_*` (`flatpak.py`), commit hash pós-deploy, snapshot restaurado, smoke.
- Evidência em `docs/diagnostics/<data>-m10-vm-evidence.md`.
- **Testes** (`test_vm_harness.py`): testam o **driver** com `FakeFlatpak`/`FakeArtifacts` (a VM real roda fora da suíte, sob autorização).
- **Governança:** rodar a VM real paralisa e pede autorização antes de provisionar no host (consome KVM/CPU/disco). Gates do código do driver após este item.

## Item 5 — Certificação física no host (BE-1 + BE-2 + CX-2) — exige autorização de host por etapa
- **5a (código):** check `boot.direct` read-only no `doctor` (`doctor.py`) consultando `steam_boot.status()` (não exige root; `unknown`/`permissionDenied` em vez de falso negativo — ADR-0020). Gates.
- Merge itens 1–5a em `main` → CI verde → **PARO e peço autorização de host** para 5b–5h.
- **5b:** prepare release a43 via `tools/release_host.py prepare --commit <full>`. inspect limpo; bundle verificado.
- **5c (token `INSTALAR-<release>`):** install a43 (rollback `0.1.0a42-39bd325cee60`); convergência dupla; doctor `ok=true` (com `boot.direct`).
- **5d:** M10 físico — `component plan/apply/rollback` RetroArch+PCSX2+PPSSPP no host, 1 ciclo cada; **instalar os 17 cores** via `CoreExecutor** → primeiro jogo canônico jogável (NES/SNES/MD/Arcade via RA+core).
- **5e:** refresh de mídia com quota real (BE-8/G28 validação física).
- **5f (reboot do operador):** boot direto Game Mode (G11) — protocolo ADR-0020 + `STEAM-GAMEMODE-SESSION.md`: pre-reboot audit → reboot → Steam GamepadUI sem greeter → retorno Plasma → 3 falhas → greeter (backoff) → `disable` → host restaurado.
- **5g:** primeiro jogo canônico ponta-a-ponta — abrir biblioteca → escolher jogo → jogar → sair. **O laço primário provado.**
- **5h:** tag `v0.1.0a43` só após 5f+5g verdes, no commit certificado exato.
- **Relatório final (AGENTS.md §9):** item→commit→testes; release ativa + rollback; rótulo **`verified-vm`** RetroArch/PCSX2/PPSSPP (verified-hw exige matriz Deck, DEBT-A0, fora desta fase); KNOWN-GAPS atualizado (G11 fecha, "0 cores" → 17, CX-1/3/4 resolvidos no host).

## O que NÃO muda (escopo protegido)
Switch (keys+firmware, AppImage) e plataformas com BIOS → a43+. Tema/UI (Fase 3 do diagnóstico) → paralelo. Cores via build local do RA → M14. Cleanup do acervo XDG ~1,1 GB → bloqueado até autorização.

## Riscos e mitigações
- Contrato de adapter muda (Item 1): invariantes aditivos, nenhum manifesto existente quebra; capability-matrix auto-reflete.
- Hashes de core errados (Item 3): fonte oficial libretro/RetroArch, proveniência registrada, smoke de carregamento.
- VM consome host (Item 4): paro e peço autorização antes de provisionar.
- Boot direto quebra host (Item 5f): ExecStartPre cleanup, backoff, fallback Plasma, `disable`, snapshot btrfs + console de recuperação (ADR-0020).
- §8 (falha nunca trava): `CoreExecutor` herda transação (rollback automático); `doctor boot.direct` reporta `unknown`/`permissionDenied`.

## Sequência de execução (commits atômicos)
1. **Entrega 0:** grava `.zcode/plans/plan-fase1-laco-primario.md` (com seção "Memória e WORKLOG") + bloco WORKLOG "plano registrado". Sem código, sem host.
2. Item 1 → testes → gates → commit → bloco WORKLOG iniciado+fechado.
3. Item 2 → ... → Item 5a (cada um: testes → gates → commit → WORKLOG).
4. Merge 1–5a em main → CI verde → **paro, peço autorização de host**.
5. Após autorização: 5b→5c→5d→5e→(reboot)5f→5g→5h→relatório + KNOWN-GAPS.
