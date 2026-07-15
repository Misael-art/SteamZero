# MILESTONES — marcos verificáveis

Complexidade em T-shirt (S/M/L/XL) — sem datas (dependem de Q6/Q10 e capacidade de equipe; estimar em sprints na aprovação).

| # | Marco | Fase | Complexidade | Demonstração objetiva |
|---|---|---|---|---|
| M1 | "Kill-proof core": pipeline transacional sobrevive a SIGKILL em toda etapa | 1 | L | suíte FI-04 verde em CI |
| M2 | CLI contratada: `steamzero` com envelope v2 + golden files | 1 | M | `steamzero doctor --json` validado por schema |
| M3 | Jobs resilientes: pausa/resume/cancel/reboot-recovery | 1 | L | demo gravável de reboot no meio de job |
| M4 | Deck-aware: modos + fallback de display + microSD UUID em VM | 2 | L | FI-07/12 verdes |
| M5 | Helper privilegiado auditado | 2 | M | ST-01 fuzzing verde |
| M6 | Sessão segura: suspend/resume com checkpoint (VM) | 2 | L | FI-09 verde |
| M7 | Biblioteca transacional: scan→plan→apply→rollback com 10k fixtures | 3 | L | RT-06/07 + benchmark |
| M8 | BIOS center backend + saves timeline | 3 | M | AC-BI/SV verdes |
| M9 | Sync não-destrutivo com conflito preservador | 3 | L | J6 automatizada |
| M10 | Engine de adapters + 3 emuladores núcleo fim-a-fim | 4 | XL | instalar/atualizar/rollback DuckStation/RetroArch/Dolphin em VM |
| M10-H | Handheld Desktop BigLinux/KDE autônomo e resiliente | 4 | L | status/plan/apply/recovery no Deck; zero dependência legada; UI QML navegável |
| M11 | Frontends: Steam shortcuts + SRM + ES-DE sem duplicação | 4 | L | idempotência 2× verificada |
| M12 | Game Mode UI navegável 100% controle (dashboard+biblioteca+jogo) | 5 | XL | suíte focus graph verde |
| M13 | Adoção EmuDeck/RetroDECK em máquina real de teste | 5 | L | relatório de import sem perda (hashes) |
| M14 | Flatpak + canais + update/rollback da plataforma | 6 | L | RT-14 verde; downgrade demonstrado |
| M15 | Release 1.0 stable com SBOM/assinaturas + docs de usuário | 6 | M | checklist §17 completo com hardware (Q6) |
