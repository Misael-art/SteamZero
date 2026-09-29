# 22 — empacotamento de `sizes.js` no wheel: o que está provado e o que está pendente

Arquivo novo em `src/steamzero/ui/qml/` só vale se chegar ao instalador. A regra de
UX-03 é não confundir "não está no `.gitignore`" com "está no wheel", então a
afirmação abaixo é separada em prova efetiva de configuração e prova empírica do
artefato.

## Prova de configuração (efetiva, medida nesta árvore)

* backend: `hatchling==1.31.0` (`pyproject.toml:3-4`);
* seleção do wheel: `[tool.hatch.build.targets.wheel] packages = ["src/steamzero"]`
  (`pyproject.toml:34-35`) — inclui **tudo** abaixo do pacote, filtrado por
  `.gitignore`; não existe `MANIFEST.in` no repositório (a lista de exceções é o
  próprio `artifacts = ["src/steamzero/_build_info.py"]`);
* `git check-ignore -v src/steamzero/ui/qml/sizes.js tests/qml/check_storage_units.qml`
  terminou com código **1** (nenhum dos dois é ignorado).

Pelo mesmo caminho entrou `readiness.js`, que hoje está no instalador da release
`2.0.0rc1-e2af2562ebba`.

## Prova empírica: **PENDENTE** desta rodada

O wheel precisa ser lido do artefato gerado pela CI autorizada do PR desta branch —
construir release fora do fluxo do operador é proibido (`AGENTS.md §4`). O que já se
sabe do fluxo, medido no run do quinto elo:

* run `36502112454` (head `c0de54c9`) publicou
  `steamzero-wheel-f610e7783b02f38fed66f624e3121e786634cbfd`, 11.186.421 bytes;
* o nome carrega o SHA do **merge commit** que o GitHub fez de `c0de54c9` sobre
  `3495c49d` (`f610e7783`, `2026-09-29T00:14:33Z`), não o SHA do head: conferir o
  conteúdo de um wheel exige casar o artefato com esse merge ref.

Para fechar com esta branch no CI, o comando é ler o artefato do próprio run e
listar o pacote — sem construir nada:

```
gh run download <run-id> -n steamzero-wheel-<merge-sha> -D /tmp/ux04_wheel
unzip -l /tmp/ux04_wheel/*.whl | grep 'ui/qml/sizes\.js'
```

Enquanto isso não rodar, a entrega afirma: **configuração inclui, artefato ainda não
conferido**. Não se registra como provado.
