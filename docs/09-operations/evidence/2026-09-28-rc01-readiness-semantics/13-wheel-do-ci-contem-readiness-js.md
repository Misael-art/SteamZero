# 13 — O wheel do CI autorizado contém `readiness.js`, byte a byte

Instrução do operador (2026-09-28, item 2a): *"`readiness.js` não estar
git-ignorado não prova empacotamento; verificar a configuração efetiva e o wheel
produzido pelo CI autorizado. Se ainda não há artefato, registrar a prova como
PENDENTE; não montar release fora da regra."*

Este arquivo fecha essa pendência com o artefato do CI, sem construir release
local (AGENTS.md §4: wheel, wheelhouse e manifests pertencem ao fluxo de release
do operador).

## 1. O que a alegação anterior valia, e o que não valia

`08-reachability-cor-de-tinta-guard-e-empacotamento.md` §5 já havia medido o
erro: `git check-ignore` vazio e a regra de `include` em `pyproject.toml` são
*configuração declarada*, não o artefato. A ausência de `.js` no wheel antigo
(`5704c813`) era anterior à existência do arquivo e não provava nada contra ele.
A prova possível é ler o `.js` dentro do wheel produzido pela pipeline
governada.

## 2. Procedimento executado (script `/tmp/ux03_wheel_13.sh`, log
`/tmp/ux03_wheel_13.log`)

```bash
gh run download 36475422213 -n steamzero-wheel-ddab4bda2a13d13a8690ff31ec6ea9e6d5987fc7 \
   -D /tmp/ux03_wheel_proof/wheel          # -D é destino; extrai plano
sha256sum -c <(grep ' dist/steamzero' build/SHA256SUMS)
.venv/bin/python tools/release_provenance.py verify-wheel \
   dist/steamzero-2.0.0rc1-py3-none-any.whl
.venv/bin/python -c "<ler o wheel por zipfile e comparar com git show ec86c228:...>"
```

## 3. Resultados brutos

```
== conteudo do artefato ==
  977 build/provenance.json
  581 build/SHA256SUMS
7479150 dist/runtime-wheelhouse.tar.zst
3159  dist/runtime-wheelhouse/WHEELHOUSE-MANIFEST.json
3780003 dist/steamzero-2.0.0rc1-py3-none-any.whl
18507 requirements-runtime.lock

== integridade conferida contra o SHA256SUMS do proprio CI ==
dist/steamzero-2.0.0rc1-py3-none-any.whl: SUCESSO
build/sbom.cdx.json: SUCESSO
build/provenance.json: SUCESSO
build/pip-audit.json: SUCESSO
dist/runtime-wheelhouse.tar.zst: SUCESSO
dist/runtime-wheelhouse/WHEELHOUSE-MANIFEST.json: SUCESSO

== verificador governado do projeto sobre o wheel do CI ==
{"project": "steamzero", "sha256": "db92dbeda1ff6ec5e8dbe4f0184f47da189543caae57895220ad331cf49309eb", "version": "2.0.0rc1"}

== .js dentro do wheel, byte a byte contra o SHA enviado ==
entradas .js no wheel: ['steamzero/ui/qml/readiness.js']
entradas ui/qml no wheel: 86
steamzero/ui/qml/readiness.js: wheel 8614 B sha256 7d76be27ab727d3f0ae7630e11fa3a2f68cafbdc5d633727429b89cd799e29f5
steamzero/ui/qml/readiness.js: git   8614 B sha256 7d76be27ab727d3f0ae7630e11fa3a2f68cafbdc5d633727429b89cd799e29f5
identico ao SHA enviado: True
```

Leitura: o único `.js` do pacote é exatamente o módulo compartilhado da UX-03,
com o mesmo `sha256` do blob enviado em `ec86c228eeeb6814af2aa6363889341cfff40358`
(8614 bytes). As 86 entradas `ui/qml` confirmam que o diretório inteiro viaja no
wheel, não apenas o `.py`.

## 4. A nuance de identidade, registrada em vez de escondida

Em um run `pull_request`, o `github.sha` usado no nome do artefato é o **merge
ref** (`refs/pull/243/merge` → `ddab4bda…`), não a cabeça enviada. O
`build/provenance.json` guarda as duas coisas (`source.ref`, `source.commit`,
`build.runId`, `sourceTreeState`, `subject.sha256`). Consequência honesta: esta
prova estabelece que o `.js` **entra no wheel construído pela pipeline governada
a partir deste conteúdo**; o wheel nomeado pelo SHA integrado, depois do merge,
continua sendo artefato do fluxo de release do operador, e nada aqui o antecipa.

## 5. Cobertura medida no mesmo artefato do CI

`/tmp/ux03_cov/coverage-3.14.json`, extraído do job `quality` do run
36475422213:

```
pct=85.4897  covered=41761  missing=5603  statements=47364
```

Contra `fail_under = 85` em `pyproject.toml`: 85,4897 % ≥ 85, sem regressão. A
suíte local `tools/run_tests_isolated.py` roda desinstrumentada, então este é o
único número de cobertura que existe — ele vem do CI, não de uma estimativa.

## 6. Erro de processo desta rodada, registrado

`gh run download` nesta versão usa `-D/--dir` como destino (extração **plana**) e
`-p/--pattern` como glob. Passei o nome do artefato em `-D` duas vezes; o
resultado foram dois diretórios de artefato criados na RAIZ do checkout, sem
estrejar nada. Foram movidos para `/tmp` e a árvore foi reconferida
(`git status --short` sem entradas inesperadas). Lição que vale para as próximas
rodadas: temporários de download vivem fora da árvore, e a flag de destino se
confere em `--help` antes do primeiro uso.
