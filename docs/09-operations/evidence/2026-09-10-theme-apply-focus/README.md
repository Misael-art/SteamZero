# Evidência física — aplicação AURA e foco da cena ES-DE

## Identidade da prova

- Release instalada: 2.0.0rc1-c2436c5b8fed
- Source commit: c2436c5b8fed69637e7ed6742c9b0df1fcaf851f
- Daemon: convergido na mesma release e commit
- Tema ativo: org.steamzero.aura 1.0.0
- Operação de aplicação: 01M262PAZK4ZRGMJ9ACQSB1ME1
- PID do harness QML da captura: 1101176
- Sessão: host real, QT_QPA_PLATFORM=offscreen, componentes importados do diretório instalado

O harness desenha os tokens AURA no conteúdo e usa SceneEsdeView.qml da
release instalada. A cena começa com foco no título e, no mesmo processo,
move para o carrossel por moveFocus("down"); o anel é o SceneFocusRing do
componente instalado.

## Capturas

Comando de reprodução:

~~~text
QT_QPA_PLATFORM=offscreen /usr/sbin/qml6 /tmp/steamzero-installed-scene-capture.qml
~~~

| Arquivo | Estado | SHA-256 |
|---|---|---|
| 01-baseline.png | foco inicial no título | cccad0a1b6d4ac8bb2200da073207e0791dbb98298ebd889cc56f6d5b81e7a1a |
| 02-entrega-funcional.png | após navegação ao carrossel; anel ciano visível | 1bf38f3bc48d5762670ffbbd12d88ec9b76452946c90680b9244b9812c8cef0a |

As duas imagens são PNG 1280×800, sem tokens de autenticação, keys ou dados
pessoais.

## Desempenho pós-QML

Comando:

~~~text
QT_QPA_PLATFORM=wayland /mnt/sdcard/Projects/Port_Steam/.venv/bin/python tools/theme_perf_probe.py --qml-dir /opt/steamzero/current/venv/lib/python3.14/site-packages/steamzero/ui/qml --theme org.steamzero.asset-recipes-demo --duration 6 --warmup 2 --width 1280 --height 800 --out performance-installed.json
~~~

Resultado em performance-installed.json: 360 amostras, média 16.723 ms,
p50 16.648 ms, p95 19.375 ms, máximo 35.521 ms, startup 172 ms,
RSS máximo 150936 KiB e VRAM máxima 55420 KiB medida por DRM fdinfo.

O startup, RSS e VRAM ficaram dentro dos limites registrados. O p95 de frame
time excedeu a meta de 16.7 ms; esta evidência não declara 60 FPS nem fecha
o critério de frame time. A próxima ação é otimizar/repetir a medição no mesmo
perfil, não mascarar o resultado.

## Estado do host

- state audit: limpo, sem staging/backups/journals órfãos
- doctor: orphanStaging=0, pendingOperations=0
- Rollback da release disponível para 2.0.0rc1-e2b333678882
- Nenhum reboot, logout ou encerramento da sessão KDE foi executado
