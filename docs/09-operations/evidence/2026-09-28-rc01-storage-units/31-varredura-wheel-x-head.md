# 31 — Prova de **artefato**: cada entrada do wheel conferida contra os blobs do head `af6a5c6e`

Pergunta do operador (item 3): o artefato produzido pelo CI contém o que este PR alega —
**"arquivo rastreado pelo Git ou configuração de packages não basta"**. A resposta abaixo
vem do arquivo dentro do `.whl`, lido byte a byte, não do `MANIFEST.in` nem do
`pyproject.toml`.

## Sujeito

| grandeza | leitura |
|---|---|
| run terminal do CI | `36562493380` (`ci`), `completed` / `success`, `headSha=af6a5c6ed8523c04030d25b1d391e885a3b3b48e` |
| artefato | `steamzero-wheel-1ce5763f84fdda6a3455d6beb845e59a365215c0` (id 11030816760, 11 187 807 bytes, não expirado) |
| proveniência declarada pelo build | `repository=Misael-art/SteamZero`, `ref=refs/pull/244/merge`, `commit=1ce5763f…` |
| sujeito | `steamzero-2.0.0rc1-py3-none-any.whl`, 3 781 401 bytes, `sha256 1579bda1c9ce2a401bfda734d246320831ef948b96823833b911bcc6b945b87d` |
| coerência | o `sha256` do sujeito bate com `build/SHA256SUMS` **e** com `subject.sha256` de `build/provenance.json`; o arquivo baixado bate com os dois |

## Método (somente leitura, zero escrita no checkout)

`31-varredura-wheel-x-head.py` → log bruto `31-varredura-wheel-x-head.log`.

1. Descompacta o wheel para fora do checkout e enumera as entradas, ignorando `*.dist-info/`.
2. Lista os blobs do head com `git ls-tree -r --format=%(objecttype) %(objectname) %(path) af6a5c6e`
   e lê cada blob com `git cat-file --batch`.
3. Todo `git` roda com `GIT_OPTIONAL_LOCKS=0` e `GIT_INDEX_FILE` apontando para um índice
   descartável **fora** do checkout, para que a varredura não escreva no `.git` da frente.
4. Pareia por caminho (`src/` + caminho-do-wheel) e compara os bytes.
5. Confere os dois sentidos: wheel→head (o que está no artefato existe no head, idêntico?)
   e head→wheel (o que está no head `src/steamzero/` foi empacotado?).

## Resultado

```
entradas_wheel=625 arquivos_head=2768
pareados=619 identicos=619 diferentes=0
diferentes=[]
so_no_wheel=['steamzero/_build_info.py (gerado no build)']
so_no_head=[]
```

- **619 idênticos, 0 diferentes** entre as entradas pareadas do wheel e os blobs do head.
- `so_no_head=[]`, com o denominador medido à parte:
  `git ls-tree -r --name-only af6a5c6e -- src/steamzero | wc -l` = **619** — exatamente o
  número de pares. Composição: 298 `.py`, 183 `.json`, 61 `.qml`, 39 `.svg`, 28 `.png`,
  5 `.md`, **2 `.js`**, 1 `.txt`, 1 `.html`, 1 `.cfg`.
- A única entrada do wheel sem par no head é `steamzero/_build_info.py`, gerada durante o
  build (`SOURCE_COMMIT=…`, `SOURCE_DIRTY=False`).

Arquivos específicos deste eixo, pelo caminho dentro do wheel:

| entrada | bytes | `sha256` | identidade |
|---|---|---|---|
| `steamzero/ui/qml/sizes.js` | 2 377 | `6d5ca418e514258fe6e55d1e9e5c2011fc9e306b6eb023bda77ee6be315a4829` | idêntica ao blob de `src/steamzero/ui/qml/sizes.js` em `af6a5c6e` |
| `steamzero/ui/qml/readiness.js` | 8 614 | (conferida na varredura) | idem |
| `steamzero/ui/qml/ThemeEditorPanel.qml` | 135 745 | (conferida na varredura) | idem |

## Comparação com o artefato do run anterior da mesma fileira

Wheels de `ee09dbcc…` (merge `8bdbb42a…`) e de `af6a5c6e…` (merge `1ce5763f…`): 625 entradas
nos dois, **623 idênticas**, 2 diferentes — `steamzero-2.0.0rc1.dist-info/RECORD` e
`steamzero/_build_info.py`, os dois únicos arquivos que *devem* mudar quando muda o commit
de origem. Nenhum arquivo de produto divergiu entre os dois artefatos.

## Distinção preservada: cabeça da branch × ref de merge

O build saiu de `refs/pull/244/merge` (`1ce5763f…`), não do head `af6a5c6e…`. A varredura
acima compara o conteúdo do wheel com os blobs do **head**, e coincide 619/619; a etiqueta
de origem dentro do pacote (`_build_info.SOURCE_COMMIT`) aponta para o **merge ref**. As
duas coisas são medidas e continuam sendo coisas diferentes — a segunda não é prova da
primeira, e a coincidência de conteúdo é o que autoriza ler o artefato como retrato do head.

## O que isto **não** prova

1. Não é integração: `origin/main` continua `3495c49d…` e nenhum dos elos da fileira é
   ancestral dele.
2. Não é release instalada: a do host é `2.0.0rc1-e2af2562ebba` (`e2af2562`, 26/09), onde
   `git ls-tree` **não** encontra `sizes.js` nem `readiness.js` — nem naquele commit, nem em
   `origin/main`.
3. Não cobre o oitavo elo em diante: cada cabeça nova precisa do próprio artefato lido.
