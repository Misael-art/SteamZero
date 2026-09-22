# IMPLEMENTATION-ROADMAP — roadmap de implementação (§16)

Pré-condição de TODAS as fases ≥1: aprovação formal (`APPROVED_TO_IMPLEMENT`) + Q2 (licença) decidida.

## Baseline operacional reconciliado — 2026-09-22

A release governada `2.0.0rc1-504d10b14485` está instalada e convergida no host.
Ela já prova a central, o scan real, o inventário dos 33 componentes, rotas de
lançamento, pausa/retomada, save/load state, bezel RetroArch, jobs de mídia e
parte da jornada visual. Isso não fecha a release funcional: a fonte autoritativa
continua sendo `docs/status/items/*.json`, e os detalhes físicos ficam nos três
relatórios de evidência de 2026-09-22 referenciados pelo item
`SZ-EMULATION-REAL-DUMP-VALIDATION`.

O diagnóstico consolidado reordena a execução por risco de jornada:

1. **P0 — entrada e lançamento:** fechar G48 (Launcher acima de 512 itens e
   ativação), G49 (first-run resiliente) e G50 (handoff Flatpak/portal do PCSX2).
2. **P1 — conteúdo e autoria:** fechar G51 (extração/renomeação/normalização),
   G52 (provider e qualidade de mídia), G53 (autoria de efeitos e medição do
   Theme Studio) e G54 (fixtures/jornadas ES-DE e RetroFE).
3. **Certificação — experiência completa:** somente depois medir fade-in,
   fade-out, retorno de foco, gameplay interativo por plataforma, multi-disc,
   PS4/PS5 e desempenho na release instalada.

Nenhum item acima deve ser promovido por teste offscreen, inspector, fixture
reduzido ou simples existência de processo. Cada fechamento exige estado real,
causa de degradação visível, limpeza dos processos e evidência vinculada ao
item de status.

## Fase 0 — Fundação documental ✅ (esta entrega)

Inventário, matriz de capacidades, licenças, PRD, arquitetura, threat model, UX, contratos de API, schemas, plano de testes, roadmap, riscos. Nenhum código de produção.

## Fase 1 — Núcleo mínimo (base de tudo)

Entregas: repositório estruturado (MODULE-BOUNDARIES aplicado por lint), `core.fs` (atomic/staging/containment), núcleo transacional + journal + locks + quarentena, State Store + migrações numeradas (0001 baseline; 0002 Desktop Experience), Job Manager (fila, pausa/resume/cancel, recovery pós-crash), CLI `steamzero` (envelope v2), catálogo de erros inicial, logging estruturado, doctor mínimo, suíte: unit + FI-04/06/15 + RTs do núcleo + golden files de contrato.
Critério de saída: AC-TX-01..04 verdes; kill em cada etapa do pipeline recuperável.

## Fase 2 — Steam Deck Core

O fechamento operacional desta fase e das integrações Steam das fases 4–5 é
detalhado em [STEAM-SESSION-ROADMAP](STEAM-SESSION-ROADMAP.md), com baseline
honesta, ordem R1–R10 e gates de hardware.

Entregas: Device/Mode Manager (handheld/docked-*/desktop + fallback de display), Session Manager (§11.1) com hooks suspend/resume, monitor de volumes por UUID (microSD), modo offline + fila, Compat Matrix inicial, helper privilegiado `steamzero-admin` (TDP/sysctl/udev allowlist) + polkit, perfis de desempenho básicos (aplicar/restaurar).
Critério: AC-SD-01/02, AC-OF-01, AC-PR-01/02 em VM; checklist HW iniciado (Q6).

## Fase 3 — Conteúdo

Entregas: Library (scan/plan/apply incremental, dedupe, `MULTIDISC-DESCRIPTOR-RECONCILIATION`, quarentena), import de dumps (safezip), conversões (CHD/RVZ/CSO/NSZ) com staging/espaço/timeout e atualização transacional dos descritores derivados, BIOS/firmware/keys store central (hash db + links), Saves store + timeline + checkpoints + backups incrementais, cloud sync com fila e conflito não-destrutivo, mídia/scraping com cache e rate limit, migração SSD↔microSD.
Critério: AC-LB-*, AC-BI-*, AC-SV-*; RT-06..11.

## Fase 4 — Emuladores e frontends

Entregas: engine de adapters + schema adapter.json + lockfile de componentes; adapters núcleo (lista PRD §7); templates de config (derivação EmuDeck conforme REUSE-POLICY); adapters de frontend Steam/SRM/ES-DE/RetroArch/RetroDECK/Heroic; ações semânticas de controle + perfis Steam Input; launcher genérico com perfis por jogo.
Critério: instalar/atualizar/verify/rollback de cada adapter em VM; matriz de licenças por componente validada.

Progresso M10: engine portátil, três manifests, lockfile anti-drift e executor Flatpak
user-scoped recuperável estão `verified-dev`; a demonstração mutável em VM e a fonte
substituta do DuckStation EOL ainda bloqueiam o fechamento do marco.

### M10-H — Handheld Desktop Foundation

Submarco prioritário dentro da Fase 4: BigLinux/KDE como plataforma de referência sem
exclusividade de distro; contexto de hardware/capabilities; perfis
`handheld-desktop`/`docked-desktop`/`safe`; ownership único; teclado em fallback;
snapshot G-STATE; recovery pós-crash; CLI e central Qt/QML. InputPlumber permanece
opcional e só vira owner após validação em hardware. Este submarco não renumera M11–M15.

## Fase 5 — UI

Entregas separadas: **AURA UI** na central de gerenciamento (dashboard, BIOS
center, jobs, saves/conflitos, configurações, lote, imports, logs/journal e
manutenção) e **AURA Launcher** fullscreen (home, biblioteca, busca, coleções,
página do jogo, launch/return e recuperação por controle). O Launcher consome o
sistema visual, mas possui item, gates e certificação próprios. A fase também
fecha a **Theme Engine** declarativa e o **Theme Studio** visual definidos em
`01-product/THEME-ENGINE-AND-STUDIO.md`; tokens ou editor de paleta isolados não
satisfazem esses marcos. Inclui ainda QAM opcional e testes de UI (focus graph,
escalas e erros).
Critério: AC-UI-01..03; jornadas J1–J9 automatizadas onde possível.

## Fase 6 — Distribuição

Entregas: Flatpak (manifest + portais) + helper host instalável, canais stable/beta/dev + lockfiles, update/rollback da plataforma (RT-14), SBOM+assinaturas+CI de release, documentação de usuário, migração de instalação beta→stable.
Critério: FOUNDATION §17 operacional → release 1.0 stable.

## Ordenação e dependências

1→2→3→4→5→6 com sobreposição controlada: 3 pode iniciar quando 1 estiver estável (2 em paralelo); 5 exige contratos de 1 congelados e consome 2–4 por trás de feature flags. Detalhe de dependências externas em DEPENDENCY-PLAN.md.
