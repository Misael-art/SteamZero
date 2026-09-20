# AURA — prova física de troca de disco

Esta captura valida o contrato multidisco com conteúdo real, um adapter real e
um emulador real, sem alterar os ZIPs de origem. O SteamZero
`RetroArchSessionPeripheral` leu o `.m3u` gerenciado, publicou quatro
identidades `set:disc` e executou `eject → next → insert` para o disco 2 e
depois `eject → previous → insert` para retornar ao disco 1.

Sequência observada:

- `01-baseline.png`: Street Fighter II em execução com o disco 1 inserido.
- `02-delivery.png`: execução após a troca para o disco 2 pelo adapter.
- `03-recovery.png`: retorno ao disco 1 pelo adapter.

O log do PUAE confirmou `Disk (1)`, depois `Disk (2)` e novamente `Disk (1)`;
o read model do adapter confirmou `activeDisc: 0 → 1 → 0`, preservando os ids
estáveis `amiga:street-fighter-ii-world-warrior:1992:disc-1..4`.

Ambiente observado: RetroArch Flatpak 1.22.2, core PUAE 5.3.1, modelo A1200,
Kickstart A1200 presente no host. Os quatro ZIPs reais foram extraídos somente
para `/tmp` e as fontes permaneceram intactas.

Limite honesto: esta é prova física do adapter e do ciclo do emulador a partir
do checkout `3acc2104`; a release instalada do SteamZero continuou sendo
`2.0.0rc1-c3b14a040b7c`, pois a instalação governada da nova release aguardava
autenticação. Portanto, a promoção da mesma captura dentro do Launcher
instalado permanece uma etapa distinta.
