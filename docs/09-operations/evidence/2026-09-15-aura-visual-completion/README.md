# AURA Cinema — fechamento visual na release instalada

Data: 2026-09-15
Release ativa: `2.0.0rc1-1d55b4ca4127`
Source commit: `1d55b4ca41275c1aec5b344e89877b5abd4690fd`
Rollback disponível: `2.0.0rc1-1f030b2d76da`
KDE: sessão preservada; nenhum reboot ou encerramento da sessão foi executado.

A correção `01856c71` foi integrada em `main` como `5d64d87c` e passou o CI do
merge. A ativação governada foi tentada duas vezes com o token exato, mas o
`pkexec` ficou aguardando o agente polkit sem apresentar prompt. As tentativas
foram canceladas antes da execução privilegiada; a release acima permaneceu
ativa e nenhum processo de instalação ficou vivo.

## Prova visual

- `01-baseline.png`: central AURA UI observada antes da abertura do Launcher.
- `02-entrega-funcional.png`: AURA Cinema real em fullscreen na sessão Wayland,
  com carousel, foco central, nomes, cabeçalho, estado online, relógio e ações.

A captura foi recortada para excluir outras janelas e dados pessoais do desktop.

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

Como diagnóstico, a mesma release foi medida com `QSG_RENDER_LOOP=basic`
injetado pela sonda: p95 16,168 ms, startup 1123 ms e VRAM 77,4 MiB
(`performance-installed-opengl-basic-candidate.json`). Isso valida o ajuste de
pacing proposto, mas não é promoção da release nova: falta instalar o commit
`5d64d87c` e repetir três vezes sem override externo.

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
focados passaram. A suíte integral da correção terminou com `6047 passed, 47
skipped, 4 failed`: três falhas por `AF_UNIX path too long` no diretório
temporário profundo e uma falha de identidade de sessão sob escrita do daemon
real. Os quatro testes foram reexecutados com `TMPDIR=/tmp` e passaram. Mypy
passou em 279 arquivos; CI do merge ficou verde em todas as matrizes.
