# Prova física: cena ES-DE em fullscreen após apply

Data: 2026-09-10  16:26 BRT

Esta é a prova do ciclo bridge → catálogo → render na release instalada. O
tema central aplicado continua sendo `org.steamzero.aura` 1.0.0; a cena ES-DE
é uma superfície explícita do catálogo para um tema instalado e não é
apresentada como substituição automática da AURA UI nem como AURA Launcher.

## Proveniência e estado

| Campo | Valor |
|---|---|
| Release ativa | `2.0.0rc1-172c020e03b6` |
| Commit de origem | `172c020e03b6ac2b31af5bdb7e0b12c41bea57df` |
| Run `push` verde | `34517925470` |
| Wheel SHA-256 | `1bf5aee209580877e8b55bcf94f1fe3b0d9223026be2b6dc4fbdb01f8014619a` |
| Rollback disponível | `2.0.0rc1-c2436c5b8fed` |
| Serviço | `converged`; daemon confirmou o commit acima |
| Tema central ativo | `org.steamzero.aura` 1.0.0 |
| Cena escolhida | `org.esde.xmb-menu` |
| Processo da central | QML `Main.qml`, PID 1453693 |

Comandos read-only após a instalação:

```text
steamzero --json service status → state=converged, daemonCommit=172c020e...
steamzero --json state audit → clean=true, orphanStaging=0,
  orphanBackups=0, orphanJournals=0, pendingOperations=0
steamzero --json doctor → degraded somente em boot.direct=unknown por permissão
```

## Entrega visual

`01-fullscreen-after-render.png` foi capturada no compositor Wayland real por
um harness QML temporário que consultou `theme.catalog.list` na bridge real,
selecionou o XMB Menu instalado, abriu `ThemeSceneFullscreen` e esperou o
render antes de chamar `grabToImage`. A imagem mostra o chrome `Cena · XMB
Menu`, a cena ocupando a janela, o foco ciano e a dica real de navegação:
`setas navegam · Enter/Space ativam`.

SHA-256: `de5e129485cb2090d7a3758ce781dc3042705d28c73df1f8d9a3cd6089f8b4eb`.

Os textos `{title}`, `{item}`, `{playTime}` e `{players}` permanecem visíveis
porque são bindings de dados do IR sem uma biblioteca de jogos fornecida pelo
renderizador. Isso é uma limitação declarada do conteúdo runtime, não um dado
inventado para a captura.

Os componentes instalados usados na captura têm os mesmos hashes do checkout
do commit instalado:

```text
ThemeSceneFullscreen.qml  5ee92b1364de694d56f2d1e36e9db484b1f5e4d04ead801217b19860ce620d6b
ThemeScenePreview.qml     f31a79cf6f09e4fe1b76788286e9d8b2a16930ce530ea2e1a0354354094ca03f
ThemeCatalogPanel.qml     96d4d19f0a29d76d99333b7c502e074dad38c8f314970420754bd08252f53a3e
```

## Performance refeita

Sonda na QML instalada (`/opt/steamzero/current/venv/lib/python3.14/site-packages/steamzero/ui/qml`), superfície 1280×800, 2 s de warmup e 6 s de medição:

| frames | média | p50 | p95 | máximo | startup | RSS pico | VRAM pico |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 360 | 16,735 ms | 16,636 ms | 18,254 ms | 32,442 ms | 118 ms | 150988 KiB | 55420 KiB |

O p95 continua acima do DoD de 16,7 ms; portanto não há alegação de 60 FPS.
O método mede o render loop e a VRAM via DRM fdinfo, não frames apresentados
pelo compositor. O JSON bruto está em `02-performance-installed.json`.

Nenhuma reinicialização, logout ou encerramento da sessão KDE foi executado.
