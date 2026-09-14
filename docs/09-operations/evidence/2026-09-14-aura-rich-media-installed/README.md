# AURA Cinema — prova física pós-QML

Data: 2026-09-14  
Release ativa: `2.0.0rc1-dd2221656ef3`  
Source commit: `dd2221656ef34c0c01c2fee6979706d9d2083eff`  
CI pós-merge: run `34837460662`  
Rollback disponível: `2.0.0rc1-7e66e98cb766`

## Resultado visual

O launcher AURA Cinema abriu em fullscreen Wayland com capa central em destaque,
capas vizinhas com escala/opacidade, navegação horizontal, relógio, conexão,
rodapé de controle e fallback legível. A jornada instalada foi capturada na
release nova:

- `18-release-dd222-fullscreen.png`: fullscreen pós-apply com carousel, foco,
  relógio, conexão e fallback legível.
- `19-release-dd222-details.png`: detalhes com capa fallback, sistema,
  descrição/screenshot fallback e ação `Jogar`.
- `31-release-dd222-return-focus.png`: retorno pós-jogo ao mesmo cartão.

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

`20-release-dd222-launch.png` mostra o jogo NES real no RetroArch Mesen 0.9.9,
iniciado pelo cartão atualmente focado. O OSD nativo do emulador aparece em
`21-release-dd222-osd.png`; após fechar o conteúdo, `31-release-dd222-return-focus.png`
mostra o retorno ao mesmo cartão AURA. Isso não substitui o OSD semântico do
Launcher: a prova AURA correspondente continua em
`2026-09-13-aura-session-composition/03-pause.png`, enquanto a recaptura desta
release mantém esse gap explicitamente separado do OSD nativo.

## Medição no hardware

Os três probes (`performance-installed-dd222-*.json`) lançaram o binário instalado em
Wayland/OpenGL, coletaram 360 frames e mediram VRAM pelo `drm fdinfo` do processo:

- startup até o primeiro frame QML: `561–768 ms`;
- VRAM: `66760–90128 KiB`, medida válida;
- frame time p95: `17,636–18,182 ms`.

O p95 reproduzido está acima do critério de `16,7 ms`; portanto a meta de 60 FPS
com p95 normativo não é declarada concluída. O valor é uma medição real do render
loop (`FrameAnimation`), não uma prova de frames apresentados pelo compositor.

## Estado operacional

O instalador confirmou convergência do daemon na release `dd2221656ef3` e uma
segunda verificação idempotente (`restarted=false`); o Doctor confirmou zero
staging, backup e journal órfão e zero operações pendentes. O KDE não foi
reiniciado nem finalizado.
