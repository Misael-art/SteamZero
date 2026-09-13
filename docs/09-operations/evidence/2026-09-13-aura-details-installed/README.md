# AURA Cinema — detalhe instalado e recuperação

Data: 2026-09-13  
Release ativa: `2.0.0rc1-54bf42f619ec`  
Source commit: `54bf42f619ec430eed5f5cec83cb9388be5c5f8f`  
CI pós-merge: run `34768050136`  
Rollback disponível: `2.0.0rc1-183a1f0dfce7`

## Jornada física

O comando `/usr/local/bin/steamzero-launcher` abriu a janela `SteamZero` em
fullscreen no compositor KDE/Wayland. O catálogo canônico real carregou a
coleção `snes`; o foco inicial estava em `Alcahest (Japan) (Translated PtBr)`.

- `01-baseline.png`: fullscreen AURA Cinema com carrossel, capa central,
  vizinhas reduzidas, conexão online, relógio e rodapé de controles.
- `02-entrega-funcional.png`: `Enter` abriu o detalhe real; a ação `Jogar`
  ficou focada, a descrição ausente foi informada, e o painel de screenshots
  exibiu o fallback `Screenshots não publicados`.
- `03-recuperacao.png`: `Esc` retornou ao mesmo cartão e à mesma coleção.

O catálogo tinha 1.124 jogos, mas zero `coverUrl`, `bannerAsset`, `media` ou
`screenshotUrls`. O resultado visual é, portanto, a variante de fallback
legível prevista pelo contrato; nenhuma arte de outro jogo foi usada para
simular uma capa real.

## Medição física

Os JSONs `04-performance-launcher-process.json` e
`05-performance-navigation.json` medem o processo QML da janela instalada,
não uma cena offscreen. Durante a navegação foram enviados 23 comandos de
direção em 12,253 s; o RSS máximo foi 159.387.648 bytes e o uso foi 2,04% de
um núcleo. `startupMs`, frame time/p95 e VRAM ficaram `null`/`false`: a sonda
existente `theme_perf_probe.py` instancia `SceneRepeater`, não
`LauncherMain`, e não seria válido atribuir seus números ao Launcher.

## Estado pós-teste

O serviço e o socket permaneceram ativos e convergidos na release acima. O
`steamzero state audit --json` posterior devolveu `clean: true`, com zero jobs
stalados, staging, backups ou journals órfãos. O processo do Launcher e o
daemon de input usados somente para a captura foram encerrados; não houve
reboot, encerramento ou reinício da sessão KDE.

## Limites

Esta evidência promove a prova física do detalhe, fallback e retorno de foco.
Não certifica 60 FPS/p95/startup/VRAM, nem fecha pause/OSD, save-state,
troca de disco, bezels, fades ou lançamento/retorno de um jogo real.
