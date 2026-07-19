# STEAM-DECK-HARDWARE-MATRIX — matriz de hardware (§13.4)

Status possível por célula: `verified-hw-readonly`, `verified-hw`, `verified-vm` (não conta
como hardware — §20) ou `untested`. O Deck LCD BigLinux disponível foi usado apenas para
detecção read-only no M10-H; nenhuma mutação de display/input foi marcada verified-hw.

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

## Evidência M10-H (2026-07-15)

| Dispositivo/cenário | Estado | Evidência | Limite |
|---|---|---|---|
| Steam Deck LCD (Valve Jupiter), BigLinux/KDE Wayland | verified-hw-readonly | DMI real, KScreen, painel e capabilities lidos por `desktop status` | apply não executado |
| Owner externo de modo | verified-hw-readonly | padrão genérico encontrou serviço `*-mode-watcher`; status ficou blocked/observer | serviço não foi chamado nem alterado |
| Painel interno eDP-1 800×1280 rotacionado, escala 1,35 | verified-hw-readonly | parser KScreen + status | escala não alterada |
| Maliit/KDE Connect/TTS BigLinux presentes | verified-hw-readonly | capability probe | ativação fim-a-fim pendente |
| InputPlumber | untested | pacote ausente no host | spike obrigatório antes de virar owner; kde-shortcuts é owner por ora |
| Dock/monitor externo | untested no gate | lógica coberta por fake | hotplug real ainda precisa checklist assistido |
| OSK standalone (wvkbd-mobintl) | untested | código + testes automatizados prontos | aguarda validação física no Deck |
| Atalhos KDE globais (Meta+Ctrl+K/D/L, Meta+D) | untested | código + testes automatizados prontos | aguarda validação física no Deck |
| Auto-show de OSK no foco de TextField | untested | código QML + teste de dados prontos | aguarda validação física com Maliit |
| deckInputKeys (botões do Deck como teclas) | verified-hw-readonly | detectado no host real | se false, atalhos KDE físicos não funcionam; InputPlumber futuro |
