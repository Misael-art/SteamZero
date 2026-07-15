# EMUDECK-IMPORT — adoção de instalação EmuDeck existente

## Detecção (read-only)

Sinais: `~/emudeck/` (settings/backend), `$HOME/Emulation/` (layout roms/bios/saves/storage), emuladores Flatpak/AppImage conhecidos, `EmuDeck.desktop`, parsers SRM configurados, `~/.config/EmuDeck/`.

## Relatório de compatibilidade (antes de qualquer plano)

- Emuladores encontrados (origem, versão) × adapters disponíveis.
- Estrutura de ROMs: EmuDeck usa layout ES-DE (`Emulation/roms/<sistema>`) — compatível por design; divergências (pastas custom) listadas.
- BIOS em `Emulation/bios` → candidatas ao store central (por hash contra o BIOS-db).
- Saves: **atenção** — EmuDeck espalha saves por emulador com symlinks para `Emulation/saves`; o import cataloga os alvos reais e cria a timeline inicial a partir deles.
- Configs: diff entre o instalado e os templates EmuDeck conhecidos → customizações do usuário viram presets preserváveis.
- Cloud sync EmuDeck (rclone): detectado e **desativado só com consentimento** (dois sincronizadores simultâneos = corrupção; o relatório explica).

## Plano de adoção (princípios)

1. **Adoção por referência, não por movimentação:** ROMs/BIOS/saves ficam onde estão; o Unified registra volumes+relpaths. Reorganização física é operação separada, opcional, transacional.
2. Nada é desinstalado: EmuDeck permanece funcional; o usuário decide depois (com aviso de dupla-gestão: mudanças pelo EmuDeck após adoção geram drift detectado pelo verify).
3. Originais de qualquer arquivo tocado (configs) vão para backup padrão.
4. Rollback do import = remover registros + restaurar configs — o sistema volta a ser "só EmuDeck".

## Fora de escopo do import

Recriar o instalador EmuDeck; importar instalações Windows do EmuDeck; ler credenciais rclone (usuário reconecta o provedor no Unified — segredos nunca são copiados).
