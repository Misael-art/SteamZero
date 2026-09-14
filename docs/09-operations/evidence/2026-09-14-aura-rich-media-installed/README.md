# AURA Cinema — prova física pós-QML

Data: 2026-09-14  
Release ativa: `2.0.0rc1-98f0cc5c6fcd`
Source commit: `98f0cc5c6fcd1cca6a467dcf1815ea2836bb81f5`
CI pós-merge: run `34861980121`
Rollback disponível: `2.0.0rc1-dd2221656ef3`

## Resultado visual

O launcher AURA Cinema abriu em fullscreen Wayland com capa central em destaque,
capas vizinhas com escala/opacidade, navegação horizontal, relógio, conexão,
rodapé de controle e fallback legível. A jornada instalada foi capturada na
release `98f0`:

- `36-release-98f0-fullscreen.png`: fullscreen pós-apply com carousel, foco,
  relógio, conexão e fallback legível.
- `37-release-98f0-focus-navigation.png`: seta direita troca o cartão focado no
  carousel, provando que a cena Cinema está ligada ao mapa de foco do Launcher.
- `38-release-98f0-details.png`: detalhes com capa fallback, sistema,
  descrição/screenshot fallback e ação `Jogar`.
- `41-release-98f0-return-focus.png`: retorno pós-jogo ao mesmo cartão.

As capturas `08`–`17` preservam a baseline da release anterior, incluindo a
variante com arte real de Astyanax e o erro controlado do OSD.

A prova anterior de pause/retomada, save-state/disco e composição de sessão está
em `2026-09-13-aura-session-composition/`; ela usa o mesmo código funcional já
presente na release promovida. O bezel gerenciado é anexado somente ao adapter
RetroArch; emuladores sem esse contrato permanecem sem overlay falsificado.

A recaptura pós-apply desta release está em `18-release-dd222-fullscreen.png`,
`19-release-dd222-details.png` e `31-release-dd222-return-focus.png`. Ela mostra
fullscreen, detalhes, fallback legível, navegação e retorno ao mesmo foco.

## Jogo real e degradação controlada

`39-release-98f0-game-launch.png` mostra o jogo NES real no RetroArch Mesen 0.9.9,
iniciado pelo cartão atualmente focado. Com o jogo em execução, o foco voltou ao
Launcher e F1 abriu o OSD semântico AURA em
`40-release-98f0-aura-osd-same-card.png`, com o mesmo título e estado `running`.
O fechamento controlado retornou ao mesmo cartão em
`41-release-98f0-return-focus.png`. Esta é a prova física da cadeia
escolher → aplicar → viver em fullscreen → operar OSD → retornar.

## Medição no hardware

Os três probes (`performance-installed-98f0-*.json`) lançaram o binário instalado em
Wayland/OpenGL, coletaram 360 frames e mediram VRAM pelo `drm fdinfo` do processo:

- startup até o primeiro frame QML: `503–938 ms`;
- VRAM: `85268–95644 KiB`, medida válida;
- frame time p95: `17,819–18,686 ms`.

O p95 reproduzido está acima do critério de `16,7 ms`; portanto a meta de 60 FPS
com p95 normativo não é declarada concluída. O valor é uma medição real do render
loop (`FrameAnimation`), não uma prova de frames apresentados pelo compositor.

## Estado operacional

O instalador confirmou convergência do daemon na release `98f0cc5c6fcd`; a
verificação pós-instalação confirmou current e daemon no mesmo commit. O Doctor
confirmou zero staging, backup e journal órfão e zero operações pendentes. O KDE
não foi reiniciado nem finalizado.
