# Materialização multidisco e ingestão de archives — 2026-09-20

## Resultado de software

Esta branch implementa `multidisc.materialize` como ação confirmável que cria
um job assíncrono. O job valida o conjunto, copia ou extrai para
`.steamzero/derived/<platform>/<set>/`, publica o `.m3u` com ownership
`SteamZero-MultiDisc-Managed` por transação e remove o staging ao terminar.
Falha, conflito de playlist, archive inseguro e cancelamento não escrevem no
acervo original nem substituem uma playlist do usuário.

ZIP é validado com limites de traversal, symlink, tamanho e expansão. RAR/7z
somente seguem quando o backend `7z`/`7zz` lista e extrai o membro por stdout
com limite; sem backend o estado é `unsupported-content`. X68000 permanece em
`needs-platform-contract` porque o manifesto ainda declara o suporte M3U como
unsupported; nenhum suporte falso é promovido.

O scan canônico passa a publicar candidatos multidisco com `setId`, título,
estado, motivo, `sourcePaths`, `systemId` e `libraryRoot`, permitindo que a UI
dispare a ação sem adivinhar ou reorganizar o acervo.

## Testes e gates

- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_multidisc_materializer.py -q`: **6 passed**.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_emulation_runtime_remediation.py tests/unit/test_emulation_controller.py -q`: **145 passed**.
- `ruff check src tools tests`: **passed**.
- `ruff format --check src tools tests`: **passed**.
- `mypy src`: **passed**.
- `tools/lint_boundaries.py`: **passed**.
- `tools/check_independence.py`: **passed**.

A suíte isolada integral foi iniciada no worktree, executou até 27% e depois
encerrou o processo sem devolver o rodapé terminal; por isso não é promovida a
gate verde nem é atribuído um número final inexistente. O resultado não deixou
runner ativo e não apresentou traceback no trecho observado.

## Host e prova física

Nenhuma instalação, rollback, download de firmware proprietário, reboot ou
alteração manual do host foi executada. A versão somente leitura observada foi
`/usr/local/bin/steamzero --version` → `2.0.0rc1`.

A inspeção atual de `/home/misael/emulation/roms/` não encontrou `.m3u`. Uma
observação anterior de uma playlist Amiga não foi reproduzida nesta leitura e
não é usada como evidência. A prova física deve ocorrer depois de uma release
governada contendo este commit, com um conjunto Amiga/X68000 que tenha contrato
de adapter comprovado.

Os dumps PS4/PS5 permanecem `unsupported-content`/`needs-review` enquanto o
acervo contiver apenas `.rar`/`.exfat` sem payload aceito (`pkg`/`elf`/`bin`).
Dreamcast tem CHD e boot Flycast previamente observado, sem gameplay
interativo; Xbox tem ISO mas o xemu parou na configuração da máquina; Xbox360
tem ISO, porém o runtime Xenia está degradado. Esses fatos não são convertidos
em gameplay-proven sem conteúdo/runtime legítimo e prova física.
