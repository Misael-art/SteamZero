# THIRD-PARTY-NOTICES — avisos de terceiros

Em releases futuras este arquivo será gerado/atualizado a partir do SBOM
(CycloneDX) e do inventário fino em `ASSET-INVENTORY.md`. Nesta fase registra o
conhecido e o que já está no repositório.

## Fontes de análise (não redistribuídas)

Material de pesquisa da fundação; **nenhum asset ou código desses projetos é
redistribuído** no produto (política ADR-0019 + REUSE-POLICY):

- EmuDeck © dragoonDorise & contributors — GPL-3.0 — https://github.com/dragoonDorise/EmuDeck
- LinuxToys © psygreg & contributors — GPL-3.0 — https://github.com/psygreg/linuxtoys
- RetroDECK © RetroDECK team & contributors — GPL-3.0 — https://github.com/RetroDECK/RetroDECK (inclui `other_licenses.txt` com avisos de componentes embutidos)
- RetroDECK/components © RetroDECK team — GPL-3.0
- PhaseZero © Misael-art — sem licença publicada (uso mediante titularidade — Q3)

## Dependências de runtime (SBOM na release)

Python 3.11+ (PSF), SQLite (public domain), PySide6/Qt (LGPL/GPL conforme
empacotamento), jsonschema/pydantic (MIT), ruamel.yaml (MIT), defusedxml (PSF),
zstandard (BSD), e demais pins do lockfile. Lista definitiva com versões e
hashes no SBOM de cada release (M14/M15).

## Inventário fino de assets (G7)

**Inventário autoritativo item a item:** [`ASSET-INVENTORY.md`](ASSET-INVENTORY.md)
(72 arquivos com SHA-256 em 2026-08-10, base `39bd325`). Resumo abaixo.

### Liberation Sans 2.1.5 — fixture de teste visual

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
| Uso | **exclusivamente** fixture de teste visual; não acompanha o produto |
| Local | `tests/fixtures/fonts/liberation-sans-2.1.5/` |

Arquivos incluídos:

- `LiberationSans-Regular.ttf` — sha256 `76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8`
- `LiberationSans-Bold.ttf` — sha256 `788abee4c806d660e8aee46689dd8540cd4bb98da03dcc9d171ce3efd99a9173`
- `LiberationSans-Italic.ttf` — sha256 `e5bae5c4cde31f22142753855f4f8fb86da6ff39955ed3c0a11248b0d16948b0`
- `LiberationSans-BoldItalic.ttf` — sha256 `698da70fc191cc5f33ad4d6d3fe830fe4624b898ea2e3169955928b7c491f1ee`

Texto integral da licença em `tests/fixtures/fonts/liberation-sans-2.1.5/OFL.txt`.
Os arquivos **não são modificados nem renomeados** (OFL com RFN).

### Ícones de UI empacotados

Atribuição humana em `src/steamzero/ui/assets/ATTRIBUTION.md`; hashes em
`ASSET-INVENTORY.md` §1.

| grupo | licença | redistribuição |
|---|---|---|
| BigIcons Papient derivados (`dolphin-emu`, `duckstation`, `retroarch`, `steam`) | GPL-3.0 | sim, com atribuição |
| Fallbacks geométricos e `steamzero-mark.png` | GPL-3.0-or-later (SteamZero) | sim |
| `eden.svg`, `citron.svg` | GPL-3.0-or-later (projetos upstream) | sim, com atribuição |
| `ryubing.png` | asset oficial Ryubing; uso identificativo | sim **só** como identificação; marcas dos titulares |

### Fixtures e baselines

- `tests/fixtures/scene-media/*` — covers sintéticos SteamZero (fixture-only)
- `tests/qml/golden/*` e `src/steamzero/ui/qml/golden/*` — baselines visuais
  geradas pelo harness do projeto (fixture-only; G14)
- `docs/09-operations/evidence/**` — capturas de validação (evidência, não produto)

## Pendências residuais (não bloqueiam assets já no tree)

1. **Assets dos projetos-fonte de referência:** continuam **fora** do tree e
   **fora** do produto. Se algum dia for desejado redistribuir um item, inventário
   fino **antes** da cópia (mesmo processo de `ASSET-INVENTORY.md`).
2. **`other_licenses.txt` do RetroDECK:** só se houver derivação concreta.
3. **Dat-files No-Intro/Redump:** não embarcados; verificar termos antes de
   qualquer redistribuição (alternativa: gerar de fonte com termos claros).
4. **Templates de controle de terceiros:** não copiar packs sem licença
   inventariada; preferir perfis gerados pelo SteamZero.
