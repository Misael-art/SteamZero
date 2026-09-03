# Compilação de layout ES-DE — medição de 2026-09-03

Medição da compilação de temas ES-DE reais para o IR de cena. **Nenhum tema foi
baixado para o repositório nem instalado no host**: os números abaixo são de
compilação offline sobre uma cópia de trabalho descartável, não de renderização
em hardware.

## Origem das medições

Cinco temas ES-DE com licença verificável, fixados por commit:

| Tema | Repositório | Commit | Licença |
|---|---|---|---|
| Iconic | `Siddy212/iconic-es-de` | `0a549ffbe5a392bd818ee4c11a7175b2372591e4` | CC0-1.0 (LICENSE) |
| PlayStation-X | `RobZombie9043/playstation-x-es-de` | `78a6517bc75502951182442b136e0dc50b0ec432` | CC-BY-NC-SA-4.0 (README) |
| NSO Menu Interpreted | `anthonycaccese/nso-menu-interpreted-es-de` | `fdf8858fce9792f5f4380e50f3c4c0907817b16c` | CC-BY-NC-SA-2.0 (README) |
| XMB Menu | `anthonycaccese/xmb-menu-es-de` | `afe3b7b61cb245609e9d0ef905033914baf7675d` | CC-BY-NC-SA-2.0 (README) |
| Modern | `es-de/themes/modern-es-de` (GitLab) | `692eb3672998d011a26373093de8319e43ae13f7` | CC-BY-NC-SA (LICENSE) |

Quatro temas pedidos ficaram de fora por **não declararem licença**:
`shinretro-revisited`, `slick`, `iisu-interpreted` e `retrofix-revisited`. O
`build_manifest` recusa tema sem licença confirmada, e o gate não foi afrouxado.

## O que a medição decidiu no desenho

Amostra de 130 arquivos XML dos cinco temas:

- **0 malformados.** Temas ES-DE são XML conforme, ao contrário dos layouts
  RetroFE. Toda a maquinaria de reparo de `scene_retrofe._sanitize` — comentário
  ilegal, fechamento anônimo, tag trocada — não tem análogo aqui.
- **Propriedades são elementos filhos**, não atributos.
- **Coordenadas são pares normalizados** (`<pos>0.5 0.5</pos>`), o que torna a
  cena independente de resolução.
- **1359 referências `${var}`**, distribuídas em blocos de seleção: 3406
  variáveis em `<language>`, 1433 em `<fontSize>`, 273 em `<colorScheme>`.

A medição também **corrigiu quatro classificações erradas** que eu havia feito
por analogia com o nome: `itemMargin` e `itemSpacing` são pares e não escalares;
`stationary` é enumeração (`withinView`) e não booleano; `scope` aceita `none`.

## Resultado no ponto de entrada real (xmb-menu)

Compilando `theme.xml` com a cadeia de `<include>` resolvida e `system_id=snes`:

| | Só `theme.xml` | Com `<include>` |
|---|---:|---:|
| Elementos | 37 | **58** |
| Degradados | 7 | **3** |
| Cobertura | 0,8409 | **0,9508** |
| Assets literais | 6 | 13 |
| Arte por sistema | recusada | template sobre **212 sistemas** |

As 3 degradações remanescentes são honestas e nomeadas: duas são uma variável
declarada numa variante não selecionada (`${backgroundGameArtType}`) e uma é o
`gameselector`, que carrega apenas lógica de seleção e não desenha nada.

## Arte por sistema

Os ~92% do peso de um tema ES-DE (55 de 59,5 MB no xmb-menu) são arte por
sistema, endereçada por um marcador de tempo de execução:

```xml
<path>${systemContentImagePath}/${system.theme}.png</path>
```

O IR publica isso como template — `{"pattern": "_inc/systems/physical-media/{system}.png",
"parameter": "system"}` — e a substituição só aceita identificador que case com
`SYSTEM_ID`. Validado contra os 214 nomes reais de
`_inc/systems/_metadata-global/`: todos casam, nenhuma exceção.

## Reprodução

Os temas não estão versionados aqui. Para repetir a medição, obtenha a árvore no
commit fixado acima e rode:

```python
from pathlib import Path
from steamzero.domain.theme_import_esde_layout import resolve_includes, available_systems
from steamzero.domain.scene_esde import compile_theme, fidelity_report, Selection
import xml.etree.ElementTree as ET

root = Path("<arvore-do-tema>")
resolved = resolve_includes(root / "theme.xml", system_id="snes",
                            selection=Selection(color_scheme="blue"))
scene = compile_theme(ET.tostring(resolved.root, encoding="unicode"),
                      theme_id="xmb", selection=Selection(variant="gamelist-carousel-cover",
                                                          color_scheme="blue"))
print(fidelity_report(scene), len(available_systems(root)))
```

## O que esta evidência NÃO prova

- que algum tema esteja instalado ou disponível para download no produto;
- que a cena compilada renderize corretamente em hardware;
- desempenho, FPS ou memória — nada foi medido no Deck.

A cobertura de 95% é de **compilação**, e prometer mais que isso a partir deste
número seria exatamente o tipo de alegação que a AGENTS §10 proíbe.
