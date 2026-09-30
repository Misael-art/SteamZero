# Auditoria de citações do oitavo elo (2026-09-29)

Depois de `c2bae146` reconfrontar 56 citações de outras frentes, a mesma regra foi
aplicada às citações que **esta frente escreveu**. Toda referência da forma
`arquivo:NNN` na prosa dos arquivos deste lote foi lida contra a árvore e conferida
pelo conteúdo da linha, não pelo número.

| onde | citação | o que alega | conteúdo lido | veredito |
|---|---|---|---|---|
| gate `:7` | `Main.qml:901`-`:908` | `apiUrl`/`apiToken` vêm de argumento na inicialização | `const apiMarker = args.indexOf("--steamzero-api")` … `apiToken = args[apiMarker + 1]` | OK |
| gate `:8` | `Main.qml:339` | `desktopTruthNeedsAttention` | `readonly property bool desktopTruthNeedsAttention: statusHasData && [` | OK |
| gate `:9` | `Main.qml:334` | `hasConflicts` | `readonly property bool hasConflicts: Boolean(desktopStatus.context` | OK |
| gate `:11` | `Main.qml:496` | `pushError` | `function pushError(errorObj) {` | OK |
| gate `:15` | `Main.qml:421`-`:422` | `statusBandVisible = statusIsLoading \|\| statusStale \|\| statusBandIsError` | `readonly property bool statusBandVisible: statusIsLoading \|\| statusStale` / `|| statusBandIsError` | OK |
| gate `:38` | `test_ui_shell_esde_import_dialog.py:925` | os 48 px já exigidos dentro do shell | `assert largura >= 48 and altura >= 48, (` | OK |
| gate `:293` | `Main.qml:420` | `statusBandIsError = statusPhase === "error" && !bridgeUnavailable` | `readonly property bool statusBandIsError: statusPhase === "error" && !bridgeUnavailable` | OK |
| harness `:294` | `check_central_loading.qml:334` | precedência de renovar pela mesma função do botão "Tentar de novo" | `window.retryStatus()` | OK |
| gate `:342` | `adapters/desktop_ui.py:990`-`:1001` | "o argv é o da produção: `qml6`, o caminho do `Main.qml`, `--`, `--steamzero-api`, `--steamzero-token`" | `stdin=subprocess.DEVNULL,` / `env={**os.environ, …}` / `while process.poll() is None:` / `server.server_close()` | **FALSA** |
| harness `:14` | `adapters/desktop_ui.py:990`-`:1001` | idem | idem | **FALSA** |
| README `:63` | `adapters/desktop_ui.py:990`-`:1001` | idem | idem | **FALSA** |
| cartão `evidence[...]` | `adapters/desktop_ui.py:990-:1001` | idem | idem | **FALSA** |

## A causa, medida

O argv da produção está em `src/steamzero/adapters/desktop_ui.py:980`-`:989`:

```
980                [
981                    executable,
982                    str(qml_path),
983                    "--",
984                    "--steamzero-api",
985                    f"http://127.0.0.1:{server.server_port}",
986                    "--steamzero-token",
987                    token,
988                    *capability_arguments,
989                ],
```

e `:990` em diante é `stdin=`/`env=`/o laço de `poll()`/`server_close()` — outra coisa.
A conferência foi feita também contra a **base** `2d6a8957` (`git show`), onde o
resultado é o mesmo: `:990` já era `stdin=subprocess.DEVNULL`. Não é deriva de número
provocada por edição de terceiros — `desktop_ui.py` não está entre os doze arquivos
desta frente. É citação que escrevi errada na primeira passada e repliquei quatro vezes
(gate, harness, README do lote e a entrada de evidência do cartão normativo).

## O que muda com a correção

Quatro ocorrências passam a ler `adapters/desktop_ui.py:980`-`:989`. Nenhuma asserção,
nenhum argv realmente usado pelo harness e nenhum número medido muda: o que estava
errado era o endereço citado, não a jornada executada — o gate constrói o mesmo argv
(`qml6`, caminho do `Main.qml`, `--`, `--steamzero-api`, `--steamzero-token`) e foi com
ele que as 264 px de chrome e os 36 px de alvo foram medidos.

Revalidação proporcional (o delta é prosa em arquivo de teste, como em `c2bae146`):
o gate desta frente reexecutado, os `ruff`/`mypy`/`status-check` correspondentes, e o
digest renovado por último na árvore congelada. O checkpoint integral de sete passos
rodou **antes** desta correção, sobre a árvore `{{ARVORE}}`; a diferença entre as duas
árvores é conferível caminho a caminho e linha a linha (só as quatro linhas de prosa).
