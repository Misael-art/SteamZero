# ADR-0023: Via `web-receiver` como primeiro receptor concreto

- **Status:** Aceito
- **Data:** 2026-07-25
- **Driver:** Implementação WI-S1

## Contexto

O ADR-0022 definiu quatro protocolos de transmissão (`GAME_STREAM`, `STEAM_REMOTE_PLAY`, `SCREEN_MIRROR`, `MEDIA_CAST`) e uma arquitetura de receptor multi-provedor. A primeira via a ser implementada precisava de um alvo que:
1. Não exigisse hardware de terceiros (TV Android, tablet, etc.) para teste;
2. Funcionasse no aparelho de desenvolvimento (Steam Deck);
3. Permitisse verificação offline de todo o pipeline (captura → encoder → transporte → decodificação → degradação → reconexão).

O navegador local (loopback) atende todos os critérios e, adicionalmente, serve como receptor de contingência real quando o usuário não tem um cliente nativo.

## Decisão

1. **`web-receiver` é a primeira via implementada.** Ela tem dupla função: veículo de verificação sem hardware de terceiros e receptor de contingência real.

2. **O plano de mídia é delegado ao GStreamer.** O produto não escreve codec, congestionamento nem retransmissão. `webrtcbin` + encoder do sistema (`x264enc` ou VA-API quando disponível) + `opusenc`.

3. **Ordem revisada das vias**, por ordem de preferência no `screencast.py`:
   1. `game-stream` — Sunshine/Moonlight, Android TV, Tizen/webOS, outro PC (latência mais baixa)
   2. **`web-receiver` — navegador (este WI)**
   3. `steam-remote-play` — Steam Link
   4. `screen-mirror` — Miracast/Wi-Fi Direct (TV sem app)
   5. `media-cast` — trailers, vídeo, música (DLNA/CAST)

4. **O navegador não substitui a via nativa.** Sem app na TV, a decodificação e o controle dependem do navegador do aparelho; a latência é inerentemente pior que um pipeline nativo com codec decodificado por hardware.

5. **Fronteira preservada: sinalização loopback neste WI.** Nada de rede local ainda. B0 (Web UI LAN, família/kiosk) segue `backlog-protected` e não é tocado.

## Consequências

- Positivas: verificação offline de ponta a ponta; receiver HTML serve como fallback real.
- Negativas: sem app nativo na TV a latência é maior; a qualidade depende do navegador do dispositivo alvo.
- Neutras: `CastProtocol.WEB_RECEIVER` é adicionado ao enum existente; a preferência de cada modo coloca `GAME_STREAM` (app nativo) antes de `WEB_RECEIVER`.
