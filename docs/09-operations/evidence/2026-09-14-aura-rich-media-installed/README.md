# AURA Cinema — prova física pós-QML

Data: 2026-09-14  
Release ativa: `2.0.0rc1-f734c97cdb3c`  
Source commit: `f734c97cdb3cb31767c1a8adb65d657252f1f356`  
CI pós-merge: run `34824781870`  
Rollback disponível: `2.0.0rc1-c059ad798a59`

## Resultado visual

O launcher AURA Cinema abriu em fullscreen Wayland com capa central em destaque,
capas vizinhas com escala/opacidade, navegação horizontal, relógio, conexão,
rodapé de controle e fallback legível. A jornada instalada foi capturada na
release nova:

- `08-release-f734-baseline.png`: fallback sem capa para `'89 Dennou Kyuusei`.
- `10-release-f734-astyanax.png`: arte real de Astyanax centralizada no carousel.
- `11-release-f734-details.png`: detalhes com capa real, sistema, descrição
  fallback, screenshots fallback e ação `Jogar`.
- `12-release-f734-recovery.png`: Esc devolveu o foco ao mesmo cartão.

A prova anterior de pause/retomada, save-state/disco e composição de sessão está
em `2026-09-13-aura-session-composition/`; ela usa o mesmo código funcional já
presente na release promovida. O bezel gerenciado é anexado somente ao adapter
RetroArch; emuladores sem esse contrato permanecem sem overlay falsificado.

## Jogo real e degradação controlada

`15-release-f734-session-focused-full.png` mostra um jogo NES real no RetroArch
Mesen 0.9.9. Na tentativa de abrir o OSD a partir de um cartão diferente da
sessão já existente, o launcher exibiu `AURA-OSD-SESSION-001` em
`16-release-f734-osd.png`; Esc recuperou a tela em
`17-release-f734-osd-recovery.png`. Isso prova erro visível e recuperação, mas
deixa aberta uma repetição limpa do fluxo `jogar → F1 → pausar/retomar` na mesma
sessão e no mesmo cartão.

## Medição no hardware

Os três probes (`performance-installed*.json`) lançaram o binário instalado em
Wayland/OpenGL, coletaram 360 frames e mediram VRAM pelo `drm fdinfo` do processo:

- startup até o primeiro frame QML: `696–975 ms`;
- VRAM: `123980–132792 KiB`, medida válida;
- frame time p95: `17,993–18,551 ms`.

O p95 reproduzido está acima do critério de `16,7 ms`; portanto a meta de 60 FPS
com p95 normativo não é declarada concluída. O valor é uma medição real do render
loop (`FrameAnimation`), não uma prova de frames apresentados pelo compositor.

## Estado operacional

O instalador confirmou convergência do daemon e uma segunda verificação idempotente;
o Doctor confirmou zero staging, backup e journal órfão e zero operações pendentes.
O KDE não foi reiniciado nem finalizado.
