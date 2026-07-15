# COMPONENT-DIAGRAM

```mermaid
graph TB
    subgraph Apresentação
        GM[Game Mode UI<br/>Godot 4]
        DT[Desktop UI]
        QAM[QAM Adapter<br/>Decky - opcional]
        CLI[CLI steamzero]
    end

    subgraph "steamzero-core (daemon de usuário)"
        API[API Server<br/>allowlist + schemas + authz]
        EV[Event Bus<br/>progresso/estado]
        JM[Job Manager]
        TX[Núcleo Transacional<br/>journal/locks/staging/quarentena]
        subgraph Domínio
            LIB[Library]
            CNT[Content<br/>BIOS/FW/Keys]
            SAV[Saves]
            MED[Media]
            PERF[Performance]
            CTRL[Controls]
            SES[Session Manager]
            MODE[Device/Mode Manager]
            COMPAT[Compat Matrix]
        end
        subgraph Adapters
            AEMU[Emuladores*]
            AFE[Frontends:<br/>Steam/SRM/ES-DE/RetroArch/RetroDECK/Heroic]
            ASYS[Sistema:<br/>flatpak/appimage/pacman/dnf/apt/ostree]
            AHW[Hardware:<br/>display/áudio/input/storage/deck]
            ACLOUD[Cloud]
        end
        ST[(State Store<br/>SQLite WAL)]
        LOG[Logs estruturados]
        BAK[(Backups/Quarentena)]
    end

    ADM[steamzero-admin<br/>helper privilegiado<br/>polkit + allowlist]

    GM --> API
    DT --> API
    QAM --> API
    CLI --> API
    API --> JM
    API --> EV
    JM --> TX
    LIB & CNT & SAV & MED & PERF & CTRL & SES & MODE & COMPAT --> TX
    JM --> LIB & CNT & SAV & MED & PERF & CTRL
    SES --> MODE
    Domínio --> Adapters
    TX --> ST
    TX --> BAK
    TX --> LOG
    AHW -.ações privilegiadas.-> ADM
    ASYS -.montagens/serviços.-> ADM
```

\* Emuladores = adapters manifest-driven; a lista v1 está no PRD §7.

## Notas

- Setas cheias = chamadas em processo; tracejadas = IPC com o helper privilegiado.
- O Event Bus entrega progresso/estado a todos os consumidores conectados; UI que morre e volta re-hidrata pelo State Store + replay de eventos do job.
- Backups/Quarentena são áreas de disco geridas exclusivamente pelo núcleo transacional (formato em 05-data/BACKUP-FORMAT.md).
