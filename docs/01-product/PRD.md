# PRD — SteamZero

## 1. Problema

Hoje o usuário de Steam Deck/Linux que quer emulação séria escolhe entre:

- **EmuDeck**: cobertura enorme, mas scripts sem strict mode, sem rollback, paths hard-coded, migrações destrutivas (evidência: `functions/EmuScripts/emuDeckDuckStation.sh` move a config Flatpak e desinstala o Flatpak sem backup nem confirmação granular; 0/228 scripts com `set -euo pipefail`).
- **RetroDECK**: appliance Flatpak coeso, mas monolítico (tudo dentro de um Flatpak), com framework interno baseado em `eval` (26 ocorrências em `functions/framework.sh`) e acoplado ao ES-DE.
- **Ferramentas genéricas (LinuxToys)**: instaladores simples e modulares, mas sem noção de estado, transação ou domínio de emulação.

Nenhuma oferece: transações com rollback verificado, estado auditável, save-safety em suspensão/dock, modo offline garantido e operação 100% por controle fora do frontend.

## 2. Público

Ver PERSONAS.md. Resumo: (P1) iniciante console-like; (P2) entusiasta que quer controle e auditoria; (P3) usuário desktop Linux multi-distro.

## 3. Proposta

Plataforma composta por (§4 do prompt mestre):

```
Game Mode UI ──┐
Desktop UI ────┤                     ┌─ Adapters (emuladores, frontends, sistema)
QAM (opcional)─┼─► Serviço local ───►├─ Núcleo transacional ─► Journal/Backups
CLI ───────────┘    UI/API           ├─ Job Manager
                                     └─ State Store (SQLite)
                    Sistema de diagnóstico + backup/rollback transversais
```

## 4. Requisitos funcionais (síntese; catálogo completo em FEATURE-CATALOG.md)

RF-01 Instalação/atualização/reparo/remoção de emuladores e frontends por manifesto, com staging, checksum, verify e rollback.
RF-02 Biblioteca: scan incremental, organização, conversão (CHD/RVZ/CSO/NSZ), dedupe, quarentena, multi-disco, migração SSD↔microSD.
RF-03 Store central de BIOS/firmware/keys: hashes, compatibilidade por emulador/versão/região, links seguros, nunca em logs.
RF-04 Saves: store central, backups incrementais com linha do tempo, checkpoint pré-suspensão, cloud sync com fila offline e resolução de conflitos que preserva ambos os lados.
RF-05 Mídia/metadados: scraping multi-provedor com cache, rate limit, associação por hash, detecção de órfãos.
RF-06 Desempenho: perfis por jogo/dispositivo/estado (LCD/OLED, portátil/dock, bateria/energia) sobre GameMode/Gamescope/MangoHUD/TDP.
RF-07 Controles: Steam Input, ações semânticas universais (sair, salvar estado, carregar, pausar, avanço rápido...), hot-swap, gyro, botões traseiros.
RF-08 Frontends: adapters para Steam, SRM, ES-DE, RetroArch, RetroDECK, Heroic; núcleo desacoplado de qualquer um.
RF-09 Sessão Deck: máquinas de estado de sessão (§11.1) e de modo (handheld/docked-tv/docked-monitor/desktop), fallback de display, microSD por UUID.
RF-10 Diagnóstico: doctor, logs estruturados, pacote de suporte anonimizado e revisável.
RF-11 Contratos: CLI JSON estável, API local com allowlist, eventos de progresso, cancelamento.

## 5. Requisitos não-funcionais

RNF-01 Toda operação mutável segue o pipeline transacional (03-architecture/TRANSACTION-MODEL.md); rollback aprovado pelos critérios de §13.6.
RNF-02 Segurança conforme 04-security/SECURITY-REQUIREMENTS.md (strict mode, sem eval, sem curl|bash, allowlist, path safety, menor privilégio).
RNF-03 Offline-first (P8); operações locais nunca bloqueiam por rede.
RNF-04 Idempotência verificada por teste (executar 2× = mesmo estado).
RNF-05 UI 100% navegável por gamepad; acessibilidade conforme 07-ui-ux/ACCESSIBILITY.md.
RNF-06 Sem dependência obrigatória de Decky (P9).
RNF-07 Logs sem segredos/keys/conteúdo de saves (14 do prompt; 09-operations/LOGGING.md).
RNF-08 Suportar SteamOS Stable/Beta, Arch, Fedora, Bazzite (Ubuntu se Q-decidido), Flatpak/AppImage/nativo conforme 08-testing/TEST-MATRIX.md.

## 6. Fora de escopo

Ver 00-vision/NON-GOALS.md.

## 7. Métricas de aceitação do produto

- 100% das operações mutáveis com rollback testado por injeção de falha (nas classes de §13.3).
- 0 operações destrutivas sem plano+preview+backup+confirmação.
- Boot-to-play offline: jogo local inicia sem rede em ≤ tempo do frontend nativo +10%.
- Nenhum save perdido nos cenários de suspensão/queda de energia simulados.
- Cobertura de emuladores v1 ≥ conjunto núcleo (RetroArch, Dolphin, PCSX2, DuckStation, melonDS, PPSSPP, RPCS3, Ryujinx-sucessores/Citron/Eden, Cemu, Xemu, Vita3K, MAME, Azahar) via adapters manifest-driven.

## 8. Dependências e riscos

Ver 12-roadmap/DEPENDENCY-PLAN.md e 12-roadmap/RISK-REGISTER.md.
