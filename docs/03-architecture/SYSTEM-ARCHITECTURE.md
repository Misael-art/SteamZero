# SYSTEM-ARCHITECTURE

## Visão em camadas

```
┌────────────────────────────────────────────────────────────────────┐
│  APRESENTAÇÃO (sem regra de domínio, sem shell)                    │
│  Game Mode UI (Godot 4)  ·  Desktop UI  ·  QAM adapter (Decky,    │
│  opcional)  ·  CLI `steamzero`                                           │
└──────────────┬─────────────────────────────────────────────────────┘
               │ contrato tipado (JSON-RPC sobre UNIX socket) + eventos
┌──────────────▼─────────────────────────────────────────────────────┐
│  SERVIÇO LOCAL UI/API (`steamzero-core`, daemon por usuário)         │
│  allowlist de ações · validação de schema · authz local ·          │
│  progresso/cancelamento · correlation IDs · ocultação de segredos  │
├────────────────────────────────────────────────────────────────────┤
│  JOB MANAGER            │  NÚCLEO TRANSACIONAL                     │
│  fila·prioridade·pausa  │  scan→plan→preview→backup→stage→apply    │
│  resume·cancel·reboot-  │  →verify→activate→test→commit            │
│  recovery·limites       │  journal · locks · staging · quarentena  │
├────────────────────────────────────────────────────────────────────┤
│  DOMÍNIO                                                           │
│  Library · Content(BIOS/FW/keys) · Saves · Media · Performance ·   │
│  Controls · Session · DeviceMode · Compat                          │
├────────────────────────────────────────────────────────────────────┤
│  ADAPTERS (capacidades declaradas)                                 │
│  Emuladores · Frontends (Steam/SRM/ES-DE/RetroArch/RetroDECK/      │
│  Heroic) · Sistema (flatpak/appimage/pacman/dnf/apt/rpm-ostree) ·  │
│  Display · Áudio · Input · Storage · SteamDeck · Cloud             │
├────────────────────────────────────────────────────────────────────┤
│  PERSISTÊNCIA E OBSERVABILIDADE                                    │
│  State Store (SQLite WAL) · Journal · Backups · Logs estruturados  │
│  · Diagnóstico/Doctor                                              │
└──────────────┬─────────────────────────────────────────────────────┘
               │ apenas para ações da allowlist privilegiada
┌──────────────▼─────────────────────────────────────────────────────┐
│  HELPER PRIVILEGIADO (`steamzero-admin`, processo separado, root)    │
│  allowlist mínima · parâmetros schemados · audit log próprio       │
└────────────────────────────────────────────────────────────────────┘
```

## Regras estruturais

1. **UI nunca executa shell** e nunca escolhe caminhos de arquivo: pede ações nomeadas ao serviço (herda o contrato UI↔orchestrator do PhaseZero, onde a WPF consome `-UiContractJson` e dispara flags — aqui evoluído para RPC persistente).
2. **CLI e UI são o mesmo cliente**: `steamzero` fala com o daemon; em ausência do daemon, `steamzero` pode executar o núcleo in-process (modo single-shot) — mesmo código, mesmos contratos.
3. **Toda mutação passa pelo núcleo transacional** — inclusive as feitas por adapters. Adapter que precisa escrever, escreve via API de staging do núcleo, nunca direto.
4. **Privilégio é exceção**: fluxos padrão (Flatpak --user, AppImage em `~/Applications`, dados em `$XDG_DATA_HOME`) não tocam root. Só TDP/serviços de sistema/montagens passam pelo helper.
5. **Núcleo independente de UI, de frontend e de Decky** (P9); qualquer consumidor pode cair sem derrubar jobs em execução.
6. **Offline-first**: módulos de domínio não fazem I/O de rede direto; pedem ao Cloud/Media adapter, que aplica fila e política de rede.

## Processos e empacotamento (ver ADR-0003/0004)

- `steamzero-core`: daemon por usuário (systemd user service ou D-Bus activation), Flatpak com portais + talk-name próprio, ou nativo.
- `steamzero-admin`: binário pequeno instalado no host (fora do sandbox), ativado por polkit/pkexec com policy própria.
- UIs: mesma Flatpak (Game Mode UI) e Desktop UI; QAM plugin distribuído separadamente (opcional).

## Tecnologias (decididas por ADR)

- Núcleo/daemon/CLI: **Python 3.11+** (ADR-0001), shell apenas como shims finos onde inevitável.
- State: **SQLite WAL** + export JSON (ADR-0005).
- Game Mode UI: **Godot 4** (ADR-0002, sujeito a protótipo com critérios).
- IPC: JSON-RPC 2.0 sobre UNIX domain socket `$XDG_RUNTIME_DIR/steamzero/core.sock`, modo 0700 (ADR-0004).
