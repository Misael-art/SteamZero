# Evidência — recuperação do smoke AppImage do shadPS4

Data: 2026-09-14  
Release observada: `2.0.0rc1-1f030b2d76da`  
Fonte: `1f030b2d76da314ee40f9ecc6ff301cbf9e63148`  
Rollback disponível: `2.0.0rc1-98f0cc5c6fcd`

## Resultado

O primeiro ciclo governado de componentes foi executado com o plano
`01M2H5VZNJ2X7DAJTNPZ7JFK4D` e o job
`01M2H5WBF2PDEHJWYFT9D5XR44`. O artefato zip v0.18.0 foi obtido pelo digest
fixado `3cf0f669...90c4a4`; a verificação de integridade passou, mas o smoke
direto do AppImage terminou em `E-TX-VERIFY-FAILED` (`smoke-failed`). O job fez
rollback e o componente voltou a `missing`; a auditoria não encontrou staging,
job ou operação órfãos.

## Causa e correção

O arquivo real é um zip com um único `Shadps4-sdl.AppImage`. Executar o wrapper
diretamente depende de FUSE neste host e expira sem saída. O `--appimage-extract`
do mesmo arquivo funciona, e o `squashfs-root/AppRun --help` interno termina com
código 0. O manifesto agora declara `verify.smokeMode: appimage-extract`; o
lifecycle extrai em diretório temporário privado, exige um `AppRun` regular e
executa o smoke interno com o ambiente `APPDIR`. O schema, o lockfile e o teste
de integração foram atualizados juntos.

## Limite da prova

Esta evidência é de diagnóstico e recuperação, não é uma prova de lançamento de
jogo. A busca direcionada no host não encontrou dump PS4 (`.pkg`, `.pup` ou
imagem equivalente); não há PNG funcional a registrar nesta etapa. Depois que
um conteúdo PS4 real estiver disponível, a etapa física deve registrar
`01-baseline.png`, `02-entrega-funcional.png` e `03-recuperacao.png`, sem expor
tokens ou dados pessoais.

## Reexecução automatizada

```text
PYTHONPATH=src .venv/bin/python tools/run_tests_isolated.py \
  tests/integration/test_component_lifecycle.py \
  tests/integration/test_adapters.py \
  tests/unit/test_platform_ps4_catalog.py -q
110 passed
```

O gate integral subsequente executou `6048 passed, 47 skipped` e deixou apenas
uma falha de consistência causada pelo digest do próprio fechamento; após a
renovação do digest, o rerun do último falho passou (`1 passed`). As três
falhas de socket por caminho UNIX longo foram reproduzidas com o temporário
curto e passaram; os oito cenários conformance do shadPS4 também passaram.
