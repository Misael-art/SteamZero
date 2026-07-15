# DEPENDENCY-PLAN — plano de dependências

## Dependências de decisão (bloqueantes)

| Dependência | Bloqueia | Estado |
|---|---|---|
| Q2 licença do Unified (ADR-0013 pendente de decisão do titular) | qualquer reuso de código; Fase 1 | ABERTA |
| Q1 nome do produto | **RESOLVIDA: SteamZero** (CLI `steamzero`, daemon `steamzero-core`, helper `steamzero-admin`); resta o ID Flatpak (org de hospedagem) | RESOLVIDA (2026-07-15) |
| APPROVED_TO_IMPLEMENT | Fases 1–6 | ABERTA |
| Q6 hardware de teste | marcos `verified-hw` (M15) | PARCIAL: Deck LCD/BigLinux disponível; OLED/docks/TVs pendentes |

## Dependências técnicas externas (runtime)

| Dependência | Uso | Plano se indisponível |
|---|---|---|
| Python 3.11+ | núcleo | empacotado no Flatpak; nativo: requisito de pacote |
| SQLite (stdlib) | state | — |
| Flatpak + portais | instalação de emuladores, file chooser | fallback AppImage/nativo por adapter |
| systemd user | daemon activation, inibidores de suspensão | fallback: launch manual + polling (degradado documentado) |
| polkit | helper privilegiado | sem polkit ⇒ funcionalidades privilegiadas off com explicação |
| gamescope/gamemode/mangohud | perfis de desempenho | detecção; perfis degradam graciosamente |
| Godot 4 (build da UI) | Game Mode UI | risco R-04; plano B Qt/QML |
| Qt 6/QML | central Desktop opcional | backend/CLI seguem; `desktop ui` explica runtime ausente |
| KDE/KScreen/KWin | polimento Desktop no BigLinux | detector genérico e modo seguro; efeitos ausentes são skipped |
| InputPlumber | owner opcional de entrada | KDE/Steam/controle físico; exige marcador de validação local |
| chdman/dolphin-tool/maxcso/nsz | conversões | ferramentas por manifesto com hash; ausência ⇒ conversão indisponível por formato |
| rclone (ou lib equivalente) | cloud sync | avaliação na Fase 3 (ADR novo se lib própria) |
| Bancos de hash (dat) | verificação de dumps/BIOS | termos de uso a validar (G7/THIRD-PARTY) |

PhaseZero não pertence à tabela: é fonte histórica de pesquisa, não dependência. O único
conversor legado é uma ferramenta offline não empacotada e pode ser apagado sem efeito
no produto instalado (ADR-0019).

## Dependências entre fases

Ver IMPLEMENTATION-ROADMAP §Ordenação. Contratos da Fase 1 (envelope, plan, adapter.json, event) congelam em M2 — mudanças posteriores só aditivas ou com major.

## Cadeia de suprimentos

Lockfiles com hash desde o primeiro commit; SBOM no CI desde a Fase 1 (não deixar para a Fase 6).
