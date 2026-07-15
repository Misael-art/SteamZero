# DIAGNOSTICS — diagnóstico

## `steamzero doctor` (precedente: PhaseZero `-Doctor -DryRun`, `pz steamdeck status`, `pz flatpak audit`)

Read-only. Verifica em camadas, cada check com `pass|warn|fail` + código + ação:

1. **Plataforma:** daemon, versão, state.db íntegro (PRAGMA integrity_check), journal sem intents abertos, locks órfãos, espaço em staging/backups.
2. **Sistema:** distro/família, flatpak disponível, portais, systemd user, gamescope/gamemode/mangohud presença, versão SteamOS/Steam Client vs Compat Matrix.
3. **Hardware:** modelo Deck (múltiplos sinais, não só DMI), modo atual, displays, controles, volumes por UUID (presentes/ausentes), erros de I/O recentes.
4. **Componentes:** verify leve de cada instalado (versão, executável, config parseável).
5. **Conteúdo:** BIOS ausentes por plataforma em uso, jogos `unavailable`, quarentena não revisada, conflitos de save pendentes.
6. **Rede/sync:** conectividade (sem falhar offline — informa modo), fila pendente.

Saída humana e `--json` (envelope v2). `--repair` propõe planos (nunca repara direto — cada reparo é transação com preview).

## Auto-diagnóstico contínuo

- Watchdogs leves: monitor de mounts (UUID), monitor de sessão, healthcheck do QAM adapter.
- Problemas viram `alert` no event bus → card no Dashboard (persistente até resolver).
- Cada alerta referencia o runbook correspondente em RECOVERY.md.
