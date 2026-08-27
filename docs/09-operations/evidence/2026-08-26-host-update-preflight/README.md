# Evidência — preflight de release sob injeção de falha (2026-08-26)

Item: `SZ-HOST-UPDATE-TRANSACTIONAL`
Release ativa no host: `2.0.0rc1-720928250e1a`
Bundle íntegro de referência: `2.0.0rc1-720928250e1a`, run `33020786713`

## Por que estes testes, e não o `update` completo

O `nextAction` do item pede exercitar o update transacional contra o host real.
`release_host.py update` **muta o host** e exige autorização explícita na thread
(AGENTS.md §1), que não foi concedida. Os critérios de **recusa** do item,
porém, são prováveis sem tocar em nada: um preflight que recusa não muta.

Estes testes atacam o critério *"o preflight recusa release sem procedência,
hash, CI verde ou espaço livre"*. Todos foram feitos sobre **cópias** do bundle
no scratchpad; o bundle original e o host não foram alterados.

## Baseline

```
$ release_host.py verify-bundle --bundle <bundle íntegro>
ok: true   exit 0
release 2.0.0rc1-720928250e1a   run_id 33020786713   ref refs/heads/main
```

## FI-1 — wheel adulterado, manifesto intacto

Um byte do wheel invertido.

```
{"error": "wheelhouse reprovado: steamzero-2.0.0rc1-py3-none-any.whl:
           sha256 diverge do manifesto", "ok": false}
exit 1
```

**Recusado.** O erro nomeia o arquivo e a natureza da divergência.

## FI-2 — adulteração consistente: wheel E manifesto

Este é o teste que importa. Injetei um arquivo novo dentro do wheel
(`steamzero/INTRUSO.txt`, conteúdo que não veio do commit), recalculei o sha256
e **reescrevi a entrada correspondente** no `WHEELHOUSE-MANIFEST.json`, deixando
wheel e manifesto coerentes entre si.

```
{"error": "hash diverge: dist/steamzero-2.0.0rc1-py3-none-any.whl", "ok": false}
exit 1
```

**Recusado mesmo assim**, e por um caminho diferente do FI-1.

A razão é defesa em profundidade: o bundle carrega **duas âncoras de hash
independentes**. Além do `WHEELHOUSE-MANIFEST.json`, existe
`build/SHA256SUMS`, que eu não havia tocado:

```
1b41e57c61f9c5736a0392289c7d590a6669df91f97397155fc1291a96150534  dist/steamzero-…whl
```

Tornar a fraude consistente exigiria reescrever as duas, e o `publish` ainda
revalidaria o run verde no GitHub. O preflight não depende de uma única fonte
local de verdade.

### Registro de um erro meu

A primeira tentativa de FI-2 reescreveu *todos* os campos `sha256` do manifesto,
inclusive os das dependências. O gate recusou — mas pelo motivo errado
(`attrs`, `jsonschema`, `pillow`… divergentes), não pela adulteração que eu
queria testar. Refiz cirurgicamente, tocando só a entrada do SteamZero. Um teste
que passa pelo motivo errado não prova nada.

## FI-3 e FI-4 — o que NÃO é responsabilidade do `verify-bundle`

Removi o `AUTOMATION-MANIFEST.json` de uma cópia, e em outra troquei
`sourceCommit` por 40 zeros e `runId` por `1`. Nos dois casos:

```
ok: true   exit 0
```

Isso **não é defeito**. `verify-bundle` responde por integridade de artefato, e
a procedência é verificada em outros pontos, medidos no código:

| verificação | onde |
|---|---|
| manifesto × bundle + run verde no GitHub | `_validate_cached_bundle_ci`, chamada por `_prepare_update_bundle` — caminho de **cache do `update`** |
| manifesto × bundle antes de publicar | `_release_assets`, no `publish` |
| run `push` verde do commit exato | `prepare` |

O que fica registrado é a **fronteira**: um bundle já preparado, cujo
`AUTOMATION-MANIFEST` seja apagado ou alterado, passa pelo `verify-bundle` sem
reclamação. Como o conteúdo instalável continua ancorado em duas somas
independentes, o efeito prático é sobre metadado, não sobre código. Vale saber
que `verify-bundle` sozinho não é atestado de procedência.

## O que esta página não prova

Preservação de banco através do update, quarentena de candidata inválida e
rollback disponível antes da ativação continuam **não provados**: todos exigem
executar `update` contra o host, que depende de autorização explícita do
operador. O item segue `partial`.

## Estado do host

Inalterado. Nenhum comando desta página muta o host; `verify-bundle` e `inspect`
são read-only. Release ativa segue `2.0.0rc1-720928250e1a`, com rollback
`2.0.0rc1-92d91d631b80` preservado.
