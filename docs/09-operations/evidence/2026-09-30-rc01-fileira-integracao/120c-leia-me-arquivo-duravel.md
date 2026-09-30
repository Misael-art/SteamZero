# Acervo estavel — integracao da fileira RC-01 (#239..#247), 30/09-01/10

Criado em 2026-09-30 pela etapa 5 da ordem do operador: "preserve em local
estavel os logs essenciais ainda referenciados em ~/steamzero-retrofe-tmp;
nao dependa de temporarios para sustentar o fechamento".

## O que ha aqui e por que

| bloco | conteudo | quem referencia | criterio de preservacao |
|---|---|---|---|
| `cit-backup-83/` | 7 arquivos (QML+py) no estado anterior ao corte de citacoes do nono elo | docs/09-operations/evidence/2026-09-29-rc01-esde-import-generation/93-guardas-substring-harness-{antes,depois}.log ("snapshot pre-corte") | backup explicitamente proibido de apagar nesta etapa |
| `redl30/` | artefato `steamzero-wheel-8bdbb42a...` baixado do CI (build/, dist/, lock) = 8 arquivos, 11M | docs/09-operations/evidence/2026-09-28-rc01-storage-units/30-ci-terminal-na-cabeca-ee09dbcc.log:127-128 | unica prova binaria de que o wheel daquele SHA contem os arquivos alegados |
| `idtest/`, `idtest2/` | experimentos de identidade da arvore (31 arquivos cada) | docs/09-operations/evidence/2026-09-29-rc01-retrofe-shell-late/31-identidade-da-arvore.md:128,160 | reproduzivel, mas o documento aponta para o caminho; nada foi apagado |
| `scripts/arts30_reconcile.py` | reconcilio bytes-do-zip x size_in_bytes e SHA-256 x digest | 30-ci-terminal-na-cabeca-ee09dbcc.log:17,101 | o log cita o comando; sem o script o comando nao e repetivel |
| `scripts/probe_fold.py` | sonda de geografia da dobra da Home | 2026-09-29-rc01-home-first-fold/34-sonda-geografia-dobra.log:2 | idem |
| `integracao-2026-09-30/` | 115,116,117,118,119,120 — pre-voo, CI por cabeca, conferencia pos-merge, gate de merge, observador do main, preservacao | este acervo | evidencia da propria integracao |

## Integridade

- Copia feita com `cp -a`; os originais continuam em `~/steamzero-retrofe-tmp` (nada foi movido nem apagado).
- `cmp` arquivo a arquivo contra o original: **79 de 79 identicos, 0 diferentes**.
- `MANIFEST.sha256`: 86 entradas; `LC_ALL=C sha256sum -c` => **86/86 OK**.

## O que NAO esta aqui

Os quatro logs citados por caminho absoluto que ja existem no acervo versionado
com o MESMO conteudo (100-checkpoint-integral-nono-elo.log,
102-gate-visual-nono-elo.log, 24-comandos-e-saidas.log,
73-bateria-mutacoes-esde-raiz.py) — a referencia historica aponta para o
temporario, mas a copia canonica esta no repositorio. O
`30-atribuicao-digests.log` do temporario tem 66 linhas e todas elas estao
nas 97 linhas da versao versionada (0 linhas exclusivas; a versao do repositorio
e um superconjunto anotado).
