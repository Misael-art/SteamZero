# AURA Cinema — fechamento visual na release instalada

Data: 2026-09-15
Release ativa: `2.0.0rc1-1d55b4ca4127`
Source commit: `1d55b4ca41275c1aec5b344e89877b5abd4690fd`
Rollback disponível: `2.0.0rc1-1f030b2d76da`
KDE: sessão preservada; nenhum reboot ou encerramento da sessão foi executado.

## Continuação de instalação governada

O candidato pós-merge `2.0.0rc1-a71ba77a7d5d` foi preparado pelo
`release_host.py prepare` a partir de `a71ba77a7d5dbaf94c659bd56c756b7d565ab407`,
com o run de CI `34975470323`; `verify-bundle` passou e o wheel foi conferido
com SHA-256 `a1ef36b2be24466a3b69ad9cd81483516decaf4ecd2236e2963761e079d102a6`.

O comando autorizado de instalação foi iniciado com o token exato
`INSTALAR-2.0.0rc1-a71ba77a7d5d`, mas o polkit não apresentou autenticação em
aproximadamente quatro minutos. O invólucro foi interrompido sem ativação;
nenhum `bigsudo`, `pkexec` ou `install_host.py` permaneceu ativo. A release
continua `2.0.0rc1-1d55b4ca4127` e `orphanStaging=0`. Esta tentativa não é
prova física do candidato.

## Prova visual

- `01-baseline.png`: central AURA UI observada antes da abertura do Launcher.
- `02-entrega-funcional.png`: AURA Cinema real em fullscreen na sessão Wayland,
  com carousel, foco central, nomes, cabeçalho, estado online, relógio e ações.
- `04-game-session-baseline.png`: tela real de um jogo RetroArch lançado pelo
  catálogo; prova o ciclo de sessão do host, não a release candidata.
- `05-launcher-installed-baseline.png`: baseline do Launcher instalado com
  carousel, busca e foco; registra o ID técnico de plataforma que o commit
  `29afef6` corrige na ponte.
- `07-details-focused.png`: página de detalhes sem mídia, com fallback legível.
- `08-carousel-art.png`: carousel com capas reais do registro local.
- `09-search-focused.png` e `10-search-results.png`: busca focada e resultados
  reais com capas.
- `11-search-selected.png`: detalhe selecionado com capa; screenshots e
  fanart continuam dependentes da ingestão do registro canônico.

A captura foi recortada para excluir outras janelas e dados pessoais do desktop.
`06-details-installed-baseline.png` não é promovida: ficou parcialmente
encoberta por uma janela externa durante a sessão e não é evidência limpa.

## Medição física pós-QML

O probe `tools/launcher_perf_probe.py --backend opengl` mediu a janela real, não
um harness offscreen. Resultado repetido:

| amostra | startup | p95 frame time | pico RSS | pico VRAM |
|---|---:|---:|---:|---:|
| 1 | 1043 ms | 18,619 ms | 359,9 MiB | 107,1 MiB |
| 2 | 680 ms | 19,902 ms | 350,7 MiB | 105,5 MiB |
| 3 | 955 ms | 20,293 ms | 354,4 MiB | 109,3 MiB |

Startup e VRAM atendem aos limites registrados; o p95 não atende ao alvo de
16,7 ms. A capacidade permanece `degraded` até uma otimização ser medida em
três execuções consecutivas dentro do limite.

## PS4 e recuperação

O ciclo governado de `shadps4` foi executado após a instalação da release. O
download e a verificação do zip pinado ocorreram, mas o job
`01M2J1Y4A6BPTNJDSDYR28EGAK` terminou em `rolled-back` com
`E-TX-VERIFY-FAILED`. O componente voltou a `missing`; `steamzero state audit`
reportou zero jobs órfãos, staging, backups ou journals órfãos. Não há dump PS4
no host para a prova de lançamento, portanto não há captura de jogo fabricada.

## Estado honesto

Mídia rica, busca tolerante/nome apresentado, composição Cinema, OSD, bezel,
fade, troca de disco e contrato de save-state estão integrados na linha
principal. Save/load só aparece habilitado quando o adapter concreto o declara;
o host ainda não tem uma prova física de save-state. PS4 e p95 permanecem
pendências abertas e não foram promovidos por esta captura.

## Gates

Lint, formatação, fronteiras, independência, lockfile, matriz e 20 testes
focados passaram. A suíte integral terminou com `6046 passed, 47 skipped` e
três falhas somente por caminho UNIX temporário longo; os três testes foram
reexecutados com `TMPDIR=/tmp` e passaram. Mypy passou isoladamente em 279
arquivos.

## Revalidação do smoke PS4

O PR #181 (`0a111ec`) corrigiu o ambiente do smoke AppImage: cada execução
recebe HOME e raízes XDG privadas, previamente criadas, e nunca grava no
ambiente do daemon. O AppImage oficial v0.18.0, SHA-256
`3cf0f669c089411775a2434a41ca9c391fb7d24c1a1521ee45dd1d36f390c4a4`, passou o
smoke `--appimage-extract` + `AppRun --help` fora da raiz de componentes. A
prova durável está em `shadps4-smoke-after-xdg-fix.json`.

A nova execução física do apply depende da release governada derivada de
`b45f65983a28223ed5b33ef4f64f12a2c29516d1`; até ela ser instalada, o resultado
positivo acima não promove o componente no host.

## Medições candidatas adicionais

As quatro medições novas estão preservadas como `performance-candidate-df1*.json`.
Elas confirmam startup entre 132 ms e 2138 ms, VRAM entre 15,1 MiB e 67,2 MiB,
mas p95 entre 16,84 ms e 21,67 ms; a execução threaded piorou o p95. Portanto,
o alvo de 16,7 ms continua aberto e o modo básico permanece a escolha segura.
