# PHASEZERO-MIGRATION — relação com o PhaseZero existente

## Postura

O PhaseZero atual (`/mnt/sdcard/Projects/PhaseZero`) **não é modificado** e continua dono dos domínios fora de escopo (boot/VM/Waydroid/homelab — N3). O Unified é um produto novo que assume o domínio jogos/emulação.

## O que migra (quando o usuário tem PhaseZero Linux em uso)

| Ativo PhaseZero | Destino no Unified | Método |
|---|---|---|
| Layout `Emulation/` criado por `pz emulation layout` | adotado como raízes de conteúdo | scan read-only → adoção por link/registro (sem mover) |
| Operações/manifests em `$XDG_STATE_HOME/phasezero/operations/` | histórico importado como registros legados (read-only) | parser dedicado; nada é reexecutado |
| Configs de emuladores aplicadas por `pz emulation * configure` | verify + adoção pelos adapters correspondentes | diff contra templates; divergências viram presets do usuário |
| Perfis de modo steamdeck (handheld/docked) | perfis do Device/Mode Manager | tradução declarativa |
| Instalações EmuDeck/RetroDECK feitas via wrappers | ver EMUDECK-IMPORT/RETRODECK-IMPORT | — |

## O que NÃO migra

Segredos do bootstrap Windows, estado de MCPs/AI, boot entries GRUB, VMs, homelab — fora de domínio.

## Coexistência

- O Unified detecta PhaseZero instalado e regista versões na Compat Matrix; ambos podem coexistir (áreas de estado separadas por XDG).
- Wrappers de emulação do `pz` podem, em versão futura do PhaseZero, delegar ao Unified — decisão do PhaseZero, não deste projeto.
- Nenhuma migração automática: sempre plano+preview+opt-in por seção (USER-DATA-PRESERVATION).
