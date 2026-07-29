# THIRD-PARTY-NOTICES — avisos de terceiros (estado da Fase 0)

Este arquivo será gerado automaticamente do SBOM em releases. Nesta fase, registra o conhecido:

## Fontes de análise (não redistribuídas)

- EmuDeck © dragoonDorise & contributors — GPL-3.0 — https://github.com/dragoonDorise/EmuDeck
- LinuxToys © psygreg & contributors — GPL-3.0 — https://github.com/psygreg/linuxtoys
- RetroDECK © RetroDECK team & contributors — GPL-3.0 — https://github.com/RetroDECK/RetroDECK (inclui `other_licenses.txt` com avisos de componentes embutidos)
- RetroDECK/components © RetroDECK team — GPL-3.0
- PhaseZero © Misael-art — sem licença publicada (uso mediante titularidade — Q3)

## Dependências previstas do produto (a fixar na Fase 1 com SBOM)

Python 3.11+ (PSF), SQLite (public domain), Godot 4 (MIT), jsonschema/pydantic (MIT), ruamel.yaml (MIT), defusedxml (PSF), zstandard (BSD). Lista definitiva com versões e hashes no lockfile.

## Assets redistribuídos no repositório

### Liberation Sans 2.1.5 — fixture de teste visual

Primeiro asset binário de terceiro redistribuído neste repositório. A pendência
G7 exigia inventário item a item antes de qualquer redistribuição; esta entrada
É esse inventário, para este item.

| campo | valor |
|---|---|
| Família | Liberation Sans |
| Versão | 2.1.5 (lançada em 2021-09-30) |
| Licença | SIL Open Font License 1.1 com nome reservado — `OFL-1.1-RFN` |
| Nome reservado | `Liberation` |
| Titulares | Digitized data © 2010 Google Corporation (com nomes reservados Arimo, Tinos, Cousine); © 2012 Red Hat, Inc. |
| Mantenedor | Vishal Vijayraghavan — Red Hat, Inc. |
| Upstream | https://github.com/liberationfonts/liberation-fonts |
| Artefato | `liberation-fonts-ttf-2.1.5.tar.gz`, sha256 `7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0` |
| Uso | **exclusivamente** fixture de teste visual; não acompanha o produto, não é usada pela UI |
| Local | `tests/fixtures/fonts/liberation-sans-2.1.5/` |

Arquivos incluídos (as quatro faces da família Sans; Serif e Mono do tarball
original foram descartados por não terem consumidor):

- `LiberationSans-Regular.ttf` — sha256 `76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8`
- `LiberationSans-Bold.ttf` — sha256 `788abee4c806d660e8aee46689dd8540cd4bb98da03dcc9d171ce3efd99a9173`
- `LiberationSans-Italic.ttf` — sha256 `e5bae5c4cde31f22142753855f4f8fb86da6ff39955ed3c0a11248b0d16948b0`
- `LiberationSans-BoldItalic.ttf` — sha256 `698da70fc191cc5f33ad4d6d3fe830fe4624b898ea2e3169955928b7c491f1ee`

Texto integral da licença em `tests/fixtures/fonts/liberation-sans-2.1.5/OFL.txt`,
autores em `AUTHORS.txt`, ambos copiados sem alteração do artefato oficial.

Os arquivos **não são modificados nem renomeados**. A OFL com nome reservado
proíbe distribuir versão modificada mantendo o nome `Liberation`, e nada aqui
altera os binários.

## Pendências (G7)

- Licenças de assets (ícones, artes, sons) dos projetos-fonte: **não inventariadas** — nada de assets de terceiros será redistribuído até inventário item a item. **Exceção já inventariada:** Liberation Sans 2.1.5, acima, redistribuída como fixture de teste com licença, autores, hashes e origem registrados.
- `other_licenses.txt` do RetroDECK: aplicável apenas se algo dali for derivado; revisar na Fase 4.
- Bancos de hashes (dat-files No-Intro/Redump): verificar termos de redistribuição antes de embarcar (alternativa: gerar a partir de fontes com termos claros).
