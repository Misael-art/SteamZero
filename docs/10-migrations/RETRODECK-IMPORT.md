# RETRODECK-IMPORT — adoção de instalação RetroDECK existente

## Detecção (read-only)

Flatpak `net.retrodeck.retrodeck` instalado; `~/retrodeck/` (ou path movido — ler `retrodeck.cfg` para raízes reais: roms/bios/saves/states/media/themes, que o RetroDECK permite mover individualmente); versão do Flatpak.

## Especificidades vs EmuDeck

- RetroDECK é um appliance: emuladores vivem **dentro** do Flatpak — não são adotáveis como componentes individuais. O import adota **dados** (ROMs, BIOS, saves, states, mídia ES-DE), não os emuladores.
- Saves/states têm layout central próprio (`~/retrodeck/saves`, `states`) → mapeamento direto para a timeline inicial.
- Mídia do ES-DE (`downloaded_media`) e gamelists são adotáveis pelo adapter ES-DE.
- Presets do Configurator (borders, widescreen etc.) são registrados como "estado RetroDECK" informativo; não são traduzidos automaticamente no v1 (fidelidade duvidosa — vira preset só com confirmação por item).

## Coexistência e dupla-gestão

- RetroDECK continua instalado e funcional; o Unified pode ser configurado para tratar o RetroDECK como **frontend adapter** (jogar via RetroDECK usando os mesmos dados) — precedente direto: `pz emulation retrodeck integrate/status/plan/repair` do PhaseZero (`linux/emulation/retrodeck.sh`).
- Aviso de dupla-gestão: mover pastas pelo Configurator do RetroDECK após a adoção gera drift; o verify detecta e o doctor aponta re-sincronização de registros (plano).

## Rollback

Import é por referência (como EMUDECK-IMPORT): reverter = remover registros; nenhum dado do RetroDECK é alterado sem operação explícita e transacional.
