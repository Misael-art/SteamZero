# Liberation Sans 2.1.5 — fonte determinística para testes visuais

## Por que existe

As baselines visuais precisam do MESMO arquivo em toda máquina. A família não
basta como identidade: verificado nesta bancada, o pacote `ttf-liberation`
2.1.5 do Manjaro e o artefato oficial 2.1.5 têm hashes diferentes.

```
sistema (Manjaro ttf-liberation 2.1.5)  baccc64becc3eb7d104b7c84d99f5314…
artefato oficial 2.1.5                  76d04c18ea243f426b7de1f3ad208e92…
```

Uma baseline gerada com a do sistema não reproduziria no runner do CI, e a
divergência apareceria como regressão de código.

## Origem

Tarball oficial de TTFs pré-construídos da release 2.1.5, linkado da página do
release no repositório upstream:

```
https://github.com/liberationfonts/liberation-fonts/files/7261482/liberation-fonts-ttf-2.1.5.tar.gz
sha256  7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0
```

Publicado em 2021-09-30. **Não** foi copiado do sistema operacional, de mirror,
de pacote de distribuição reconstruído nem da instalação do desenvolvedor.

Nota para quem for atualizar: as releases da Liberation não têm *assets* na API
do GitHub. O tarball está anexado como arquivo do release e só aparece no HTML
da página — `releases/tags/2.1.5` retorna `assets: []`.

## Faces incluídas

As quatro da família Sans, porque os goldens exercitam peso e itálico:

| arquivo | peso | estilo |
|---|---|---|
| `LiberationSans-Regular.ttf` | 400 | normal |
| `LiberationSans-Bold.ttf` | 700 | normal |
| `LiberationSans-Italic.ttf` | 400 | italic |
| `LiberationSans-BoldItalic.ttf` | 700 | italic |

Bold e itálico vêm empacotados em vez de sintetizados pelo Qt: a síntese varia
entre plataformas, e um golden que dependesse dela deixaria de reproduzir sem
nenhuma mudança de código.

Serif e Mono do tarball original não foram incluídos — nenhuma fixture os usa, e
binário sem consumidor é peso sem verificação.

## Licença

SIL Open Font License 1.1 com nome de fonte reservado (`OFL-1.1-RFN`). O texto
integral está em `OFL.txt`, e os mantenedores em `AUTHORS.txt`, ambos copiados
sem alteração do artefato oficial.

O nome reservado é "Liberation": a família **não** pode ser renomeada nem
modificada mantendo o nome. Nada aqui altera os arquivos.

## Uso

Exclusivamente fixture de teste visual. Não é distribuída com o produto e não é
usada pela UI. Registrada em `docs/11-legal/THIRD-PARTY-NOTICES`.

## Atualização

Trocar de versão exige: baixar o artefato oficial da nova versão, regravar
`manifest.json` com os hashes reais, atualizar THIRD-PARTY-NOTICES e regerar
todas as baselines com `make update-qml-goldens` — revisando as imagens no
commit. O gate de integridade reprova antes disso.
