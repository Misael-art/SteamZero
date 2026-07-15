# IMPLEMENTATION-ROADMAP — roadmap de implementação (§16)

Pré-condição de TODAS as fases ≥1: aprovação formal (`APPROVED_TO_IMPLEMENT`) + Q2 (licença) decidida.

## Fase 0 — Fundação documental ✅ (esta entrega)

Inventário, matriz de capacidades, licenças, PRD, arquitetura, threat model, UX, contratos de API, schemas, plano de testes, roadmap, riscos. Nenhum código de produção.

## Fase 1 — Núcleo mínimo (base de tudo)

Entregas: repositório estruturado (MODULE-BOUNDARIES aplicado por lint), `core.fs` (atomic/staging/containment), núcleo transacional + journal + locks + quarentena, State Store + migrações numeradas (0001 baseline; 0002 Desktop Experience), Job Manager (fila, pausa/resume/cancel, recovery pós-crash), CLI `steamzero` (envelope v2), catálogo de erros inicial, logging estruturado, doctor mínimo, suíte: unit + FI-04/06/15 + RTs do núcleo + golden files de contrato.
Critério de saída: AC-TX-01..04 verdes; kill em cada etapa do pipeline recuperável.

## Fase 2 — Steam Deck Core

Entregas: Device/Mode Manager (handheld/docked-*/desktop + fallback de display), Session Manager (§11.1) com hooks suspend/resume, monitor de volumes por UUID (microSD), modo offline + fila, Compat Matrix inicial, helper privilegiado `steamzero-admin` (TDP/sysctl/udev allowlist) + polkit, perfis de desempenho básicos (aplicar/restaurar).
Critério: AC-SD-01/02, AC-OF-01, AC-PR-01/02 em VM; checklist HW iniciado (Q6).

## Fase 3 — Conteúdo

Entregas: Library (scan/plan/apply incremental, dedupe, multidisco, quarentena), import de dumps (safezip), conversões (CHD/RVZ/CSO/NSZ) com staging/espaço/timeout, BIOS/firmware/keys store central (hash db + links), Saves store + timeline + checkpoints + backups incrementais, cloud sync com fila e conflito não-destrutivo, mídia/scraping com cache e rate limit, migração SSD↔microSD.
Critério: AC-LB-*, AC-BI-*, AC-SV-*; RT-06..11.

## Fase 4 — Emuladores e frontends

Entregas: engine de adapters + schema adapter.json + lockfile de componentes; adapters núcleo (lista PRD §7); templates de config (derivação EmuDeck conforme REUSE-POLICY); adapters de frontend Steam/SRM/ES-DE/RetroArch/RetroDECK/Heroic; ações semânticas de controle + perfis Steam Input; launcher genérico com perfis por jogo.
Critério: instalar/atualizar/verify/rollback de cada adapter em VM; matriz de licenças por componente validada.

### M10-H — Handheld Desktop Foundation

Submarco prioritário dentro da Fase 4: BigLinux/KDE como plataforma de referência sem
exclusividade de distro; contexto de hardware/capabilities; perfis
`handheld-desktop`/`docked-desktop`/`safe`; ownership único; teclado em fallback;
snapshot G-STATE; recovery pós-crash; CLI e central Qt/QML. InputPlumber permanece
opcional e só vira owner após validação em hardware. Este submarco não renumera M11–M15.

## Fase 5 — UI

Entregas: Game Mode UI (dashboard, biblioteca, página do jogo, BIOS center, jobs, saves/conflitos, configurações, acessibilidade), expansão da Desktop UI QML iniciada no M10-H (lote, imports offline, logs/journal, manutenção), QAM adapter opcional, testes de UI (focus graph, escalas, erros).
Critério: AC-UI-01..03; jornadas J1–J9 automatizadas onde possível.

## Fase 6 — Distribuição

Entregas: Flatpak (manifest + portais) + helper host instalável, canais stable/beta/dev + lockfiles, update/rollback da plataforma (RT-14), SBOM+assinaturas+CI de release, documentação de usuário, migração de instalação beta→stable.
Critério: FOUNDATION §17 operacional → release 1.0 stable.

## Ordenação e dependências

1→2→3→4→5→6 com sobreposição controlada: 3 pode iniciar quando 1 estiver estável (2 em paralelo); 5 exige contratos de 1 congelados e consome 2–4 por trás de feature flags. Detalhe de dependências externas em DEPENDENCY-PLAN.md.
