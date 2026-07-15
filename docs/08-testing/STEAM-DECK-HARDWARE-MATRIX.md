# STEAM-DECK-HARDWARE-MATRIX — matriz de hardware (§13.4)

Status possível por célula: `verified-hw` / `verified-vm` (não conta como hardware — §20) / `untested`. Preenchimento depende de Q6 (dispositivos disponíveis). Nenhuma célula está verificada nesta fase (G5).

## Dispositivos

| Eixo | Itens |
|---|---|
| Deck | LCD (64/256/512 variantes tratadas como classe única + quirks), OLED (512/1TB) |
| Modo | portátil, dock oficial, docks terceiros (≥2 marcas), HDMI direto, DP via hub |
| Display externo | monitor 1080p60, monitor 1440p/4K com VRR, TV 4K com HDR, TV antiga 720p |
| Entrada | controles internos, BT (DualSense, 8BitDo), USB (Xbox), 2+ controles simultâneos, teclado+mouse |
| Armazenamento | SSD interno, microSD A1/A2 (marcas distintas), microSD lento propositalmente, pendrive USB-C |
| Desktop | AMD (GPU integrada+dedicada), Intel (iGPU), NVIDIA (proprietário) |

## Cenários mínimos por combinação relevante

1. Detecção correta de modelo LCD×OLED (limites de Hz, HDR) — sem depender só de string DMI (múltiplos sinais: painel, EDID, produto).
2. Suspensão/retomada com jogo ativo em cada emulador núcleo (save intacto, input/áudio/display válidos).
3. Dock/undock quente durante jogo — perfil aplicado, fallback quando TV não suporta modo.
4. microSD: remoção quente com jogo instalado nela; reinserção; cartão de outra plataforma (UUID desconhecido).
5. TDP/clock via helper em LCD e OLED (ranges diferentes).
6. Multi-controle local (2 jogadores) com hot-swap.
7. Bateria: job pesado pausando no limiar; retomada ao ligar na energia.
8. Desktop AMD/Intel/NVIDIA: gamescope/mangohud disponibilidade e degradação graciosa quando ausentes.

## Registro

Resultados por release em `test-reports/hw/<versão>/<dispositivo>.json` (gerado por `steamzero doctor --json` + checklist assistido) — vira insumo da Compat Matrix (FM-10).
