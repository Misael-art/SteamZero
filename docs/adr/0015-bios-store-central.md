# ADR-0015 — Centralização de BIOS/firmware/keys com links por consumidor

**Status:** aceito

## Contexto
§10.4. EmuDeck usa `Emulation/bios` + checkBIOS com hashes; RetroDECK usa `retrodeck/bios` + BIOS checker; PhaseZero tem `bios.sh` + shared-content (links). Emuladores esperam paths próprios.

## Alternativas
1. **Store central única (fonte de verdade) + links/materialização por emulador via adapter** (escolhida).
2. Cópia por emulador — duplicação, divergência, auditoria impossível.
3. Configurar cada emulador para apontar ao central — nem todos suportam; adapter decide (link vs config) por capacidade.

## Decisão
Store em `$XDG_DATA_HOME/steamzero/bios/objects/sha256/<prefix>/<sha256>` 0700; a visão canônica fica em `bios/platforms/<platform>/<canonical-name>` como symlink para o objeto. Entrada = import local por SHA-256 contra catálogo versionado (só metadados); adapters declaram necessidade e recebem uma projeção, nunca uma segunda fonte de verdade; keys nunca entram em logs (SR-14); auditoria verifica objeto, projeções e exceções materializadas.

## Consequências
Centro de BIOS da UI lê o store; RETRODECK/EMUDECK-IMPORT adotam por referência e oferecem consolidação transacional opcional.

## Riscos
Emulador que exige cópia física real (sem symlink em FAT/exFAT) — adapter materializa cópia gerida com verificação de sincronia pelo verify.

## Revisão
Fase 3 com os 5 primeiros adapters que consomem BIOS.
