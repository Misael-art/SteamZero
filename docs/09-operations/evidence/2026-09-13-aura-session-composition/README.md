# AURA Cinema — composição de sessão instalada

Data: 2026-09-13  
Release ativa: `2.0.0rc1-79af5e5b20d5`  
Source commit: `79af5e5b20d51fa1d073f37c146a149c09525622`  
CI pós-merge: run `34787859486`  
Rollback disponível: `2.0.0rc1-54bf42f619ec`

## Jornada física

O launcher instalado abriu em fullscreen no monitor Wayland de 1280×800, com
o tema AURA Cinema, carrossel horizontal, foco central, capas vizinhas,
coleção, relógio, conexão e rodapé de controles.

- `01-baseline.png`: home AURA fullscreen com fallback legível quando o
  catálogo não publica arte.
- `02-entrega-funcional.png`: F1 abriu o OSD sobre a página do jogo real;
  `running`, `Pausar` focado e ações allowlisted ficaram visíveis.
- `03-pause.png`: Enter acionou pausa e o State Store confirmou
  `running → suspended`; o foco mudou para `Retomar`.
- `04-resume.png`: Enter acionou retomada e o State Store confirmou
  `suspended → running`.
- `05-erro-controlado.png`: o encerramento por janela deixou o processo
  encapsulado vivo; após SIGTERM controlado no PID do jogo, o watcher publicou
  `closed` e o OSD exibiu `AURA-OSD-SESSION-001`, sem tela preta silenciosa.
- `06-recuperacao.png`: Esc fechou o OSD e devolveu o foco ao mesmo cartão e
  à mesma coleção.

O jogo usado foi `'89 Dennou Kyuusei Uranai (Japan)'`, plataforma
`nes-famicom`, sessão `01M2EH3KRY3KDBVY4AT14RZMG7` e game id
`c51dbc23e9b3258b761df058`. A transição foi executada pelo adapter instalado,
não por um mock QML.

## Medição instalada

`performance-installed.json` registra a janela e o processo QML da release
instalada. Foram enviados 20 eventos de navegação em 0,258839 s; uma amostra
do processo registrou 162072 KiB de RSS e 4,3% de CPU. O backend efetivo foi
`software`.

Frame time/p95, VRAM e startup até a primeira superfície utilizável continuam
sem medição válida: o probe disponível não instrumenta `LauncherMain`, e uma
tentativa em background matou a ponte ao encerrar o shell. O valor dessa
tentativa não foi promovido como desempenho.

## Estado pós-teste

`steamzero service status --json` confirmou daemon e socket convergidos na
release acima. `steamzero state audit --json` confirmou `clean=true`, zero jobs
stalados, staging, backups ou journals órfãos. O launcher, o jogo e processos
auxiliares do teste foram encerrados; a sessão KDE não foi reiniciada nem
finalizada.

Esta evidência fecha a cadeia física bridge → catálogo → render para o OSD de
pausa/retomada. Save-state gallery, troca de disco, bezels, fades e a medição
de frame time/VRAM permanecem fora deste item.
