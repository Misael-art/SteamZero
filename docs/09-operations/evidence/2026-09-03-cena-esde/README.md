# Renderização da cena ES-DE — 2026-09-03

Primeira vez que um tema ES-DE instalado vira pixel. Fecha parcialmente
`GAP-THEME-ESDE-SCENE-NOT-RENDERED`: a cena desenha numa prévia, e **ainda não
substitui a aparência da central**.

## Dois defeitos que impediam qualquer renderização

Nenhum dos dois estava no renderizador. Ambos foram medidos, não supostos.

### 1. `<include>` aninhado em bloco de seleção nunca era seguido

É como o tema publica a geometria:

```xml
<aspectRatio name="16:10"><include>./aspect-ratio-16-10.xml</include></aspectRatio>
```

`resolve_includes` só seguia `<include>` no topo do arquivo. O bloco ficava na
árvore e o arquivo jamais era aberto. Medido no xmb-menu: **2 de 27 elementos
posicionados**.

Corrigido seguindo o include do bloco ESCOLHIDO. Os não escolhidos vão para
`deselected`, e não para `missing`: as outras seis proporções existem em disco,
e chamá-las de ausentes culparia um arquivo que está lá.

### 2. Elemento partido entre arquivos virava dois elementos

`theme.xml` diz qual arte o elemento usa; `aspect-ratio-16-10.xml` diz onde ele
fica. É o mesmo `<image name="system-content">`, e o ES-DE os funde por nome.
Empilhá-los produzia um elemento com arte e sem posição e outro com posição e
sem arte — **nenhum dos dois desenhável**.

Depois da mesclagem, o gamelist do xmb-menu foi de **1 para 8 elementos
desenhados**.

## O número que eu tinha reportado errado

Declarei **95,08% de cobertura** como se fosse fidelidade. Não era. A cobertura
conta elementos compilados, e os elementos que carregam `pos`/`size` nunca eram
visitados: dava para ter 95% e uma tela em branco. A métrica media a coisa
errada e tranquilizava em vez de informar.

Por isso a prévia mostra `desenhados / total` e a lista do que não desenhou com
o motivo — a distinção entre compilado e desenhado agora está na tela.

## Uma escolha contra a captura mais bonita

A primeira versão desenhava elemento sem geometria no tamanho natural em (0,0).
Produzia uma imagem impressionante — um controle de SNES em tela cheia — que era
**layout inventado**, o que o critério de aceitação do item proíbe. Hoje esse
elemento não desenha e aparece como `sem geometria declarada`.

## Capturas

| Arquivo | O que mostra |
|---|---|
| `01-cena-gamelist.png` | Gamelist do xmb-menu em 16:10: geometria do tema, ícones do pacote, e o rodapé com 8 de 28 desenhados / 31 assets |
| `02-cena-system-esparsa.png` | System view: o cartucho de SNES posicionado (arte por sistema) e o resto vazio |

A segunda está aqui de propósito. O peso visual daquela view é o carrossel, que
não desenha — mostrar só a captura boa daria uma impressão que a medição não
sustenta.

## Verificação

- `tests/unit/test_theme_scene.py` — 6 testes. Os três de regressão foram
  provados a falhar sem a correção (`git stash` nos dois módulos); o da
  mesclagem falha com "2 elementos, um com asset e outro com layout", que é a
  falha semântica e não um erro de assinatura.
- `tests/qml/check_scene_esde_view.qml` — 8 testes no `qmltestrunner`.
- `tests/qml/check_theme_scene_preview.qml` — 7 testes, incluindo que **toda
  dimensão de seleção chega à rota**: a proporção decide a geometria, e um
  seletor que não sai no payload seria decorativo.

## O que esta evidência NÃO prova

- **A central continua com a aparência dela.** A cena aparece numa prévia sob
  demanda; nada foi ativado. `GAP-THEME-ESDE-SCENE-NOT-RENDERED` segue aberta
  para a substituição real.
- **`carousel`, `video`, `helpsystem`, `textlist`, `badges` e `rating` compilam
  e não desenham.** No system view do xmb isso deixa só 2 desenháveis.
- Os vínculos aparecem como `{title}`, `{platform}`: a superfície não tem dados
  de jogo, e escrever um título plausível faria a prévia mentir.
- Capturas geradas no checkout, **não na release instalada**, e nada foi medido
  em FPS, GPU ou memória.
