# IMPLEMENTATION-ROADMAP — roadmap de implementação (§16)

Pré-condição de TODAS as fases ≥1: aprovação formal (`APPROVED_TO_IMPLEMENT`) + Q2 (licença) decidida.

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

Entregas: Library (scan/plan/apply incremental, dedupe, multidisco, quarentena), import de dumps (safezip), conversões (CHD/RVZ/CSO/NSZ) com staging/espaço/timeout, BIOS/firmware/keys store central (hash db + links), Saves store + timeline + checkpoints + backups incrementais, cloud sync com fila e conflito não-destrutivo, mídia/scraping com cache e rate limit, migração SSD↔microSD.
Critério: AC-LB-*, AC-BI-*, AC-SV-*; RT-06..11.

### F3-PS4 — Ingestão automática de conteúdo, mídia e espaço sem duplicação

Para jogos PS4, o usuário seleciona uma pasta ou arquivo e o SteamZero descobre
automaticamente PKG, patch, pasta extraída, ISO e containers. A identidade e a
apresentação devem permanecer no formato `Bloodborne - Game of the Year Edition
[CUSA03173]`; o usuário não precisa renomear arquivos nem separar manualmente os
componentes. O catálogo registra base e patches por conteúdo validado, hash,
versão, dependência, origem e `MediaIdentity`; variantes físicas convergem para
um único `gameId`.

O fluxo obrigatório é `scan → plan → apply → verify`, com referência ao arquivo
original quando possível. Hardlink e reflink só podem ser escolhidos no mesmo
filesystem; para SD, disco removível, rede ou volumes montados em pontos
variáveis, a identidade usa volume/share + caminho relativo, nunca caminho
absoluto fixo. A busca de mídia prioriza title ID, edição e região; conflitos
entram em revisão e ausência de provider usa fallback legível. O plano deve
exibir o espaço adicional previsto: insignificante para referência/link, ou
aproximadamente 30,07 GiB quando uma cópia local for realmente exigida pelo
adapter. Dados extraídos/instalados pelo shadPS4 são uma linha separada e
precisam ser medidos, não estimados a partir do tamanho do PKG.

Plano detalhado e prompt de execução: [PS4-PKG-STORAGE-RECONCILIATION-PLAN](PS4-PKG-STORAGE-RECONCILIATION-PLAN.md).

### F3-PSVITA — Ingestão unificada de conteúdo, firmware, keys e mídia

Para PS Vita, o usuário seleciona uma raiz, arquivo, disco removível ou compartilhamento. O SteamZero deve reconhecer pasta extraída, VPK, ZIP, VCI, PKG, NoNpDrm e FAGDec sem exigir renomeação ou extração manual. Vitamin é `unsupported` e Maidump fica em `needs-review`, conforme o contrato do Vita3K. A interface agrupa a obra como `Título - Edição [TITLE_ID]`, preservando title ID, content ID, região, edição e source kind.

Firmware, pacote de fontes, keys e licença/zrif são requisitos separados e fornecidos pelo usuário; não são jogos nem devem ser fabricados ou baixados pelo produto. O scan lê `sce_sys/param.sfo`, associa updates/DLC por identidade e só publica `ready` após integridade, requisitos e preflight Vita3K.

O fluxo usa volume/share e caminho relativo para SD, USB e rede. O scan não duplica nem extrai conteúdo grande; staging e instalação são planejados, mensurados e reversíveis. A busca de mídia prioriza plataforma + title ID/content ID e mantém variantes regionais separadas.

Plano detalhado e prompt de execução: [PSVITA-CONTENT-INGESTION-AND-MEDIA-PLAN](PSVITA-CONTENT-INGESTION-AND-MEDIA-PLAN.md) e [PROMPT-PSVITA-CONTENT-INGESTION-AGENT](PROMPT-PSVITA-CONTENT-INGESTION-AGENT.md).

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
