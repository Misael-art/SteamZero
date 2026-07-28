# Contrato de recorte e máscara — reserva para o P0-08

**Estado:** reservado, não implementado.
**Implementação:** P0-08 — *View Transitions and Basic Effect Stack*.

Este documento existe por uma razão específica: `AppearanceSpec.clip` é um
booleano herdado do QML — recorta ou não recorta, sempre retangular. Ele não
cobre canto arredondado, avatar circular, cover que desaparece em degradê nem
transição em íris. Descobrir isso *depois* de congelar o schema obrigaria a
migrar todo tema já importado.

Acrescentar um campo é barato. Mudar a forma de um campo que temas já usam, não.
Por isso os campos existem agora, vazios, e o contrato está escrito antes do
código.

Nada aqui deve ser implementado no VS-03 nem no P0-03.

## Campos reservados

Em `AppearanceSpec`:

| Campo | Papel |
|---|---|
| `clip_spec` | Recorte geométrico eficiente, além do booleano |
| `mask_stack` | Pilha ordenada de máscaras de alpha/luminância |
| `hit_test_shape` | Região de **interação**, separada da aparência |

A separação entre `mask_stack` e `hit_test_shape` é deliberada. Uma cover
circular não deve encolher o alvo de toque: a máscara é aparência, o hit test é
acessibilidade. Confundir os dois produz uma interface bonita e inoperável —
e o defeito só aparece para quem usa controle ou toque, não para quem revisa a
captura.

## `ClipSpec`

Recorte geométrico, caminho de menor custo.

```
shape:            rect | roundedRect | circle | ellipse | path
affects:          self | children | subtree
coordinateSpace:  local | parent | view
antialias, invert, radius, cornerRadii, center, size, path, fillRule
```

Casos previstos: cover com cantos arredondados, avatar circular, vídeo
recortado, container com recorte, recorte herdado por todos os descendentes.

## `MaskSpec`

Máscara por alpha ou luminância.

```
source:           shape | asset | gradient | vector | element
channel:          alpha | luminance
inverted, thresholdMin, thresholdMax, feather
operation, coordinateSpace, transform, fit
```

## `MaskStack`

Combinação ordenada: `replace`, `intersect`, `union`, `subtract`, `xor`.

```yaml
maskStack:
  - roundedRect
  - gradientFade
```

Uma cover arredondada que também desaparece gradualmente na parte inferior.

## `HitTestShape`

Contrato **separado** da máscara visual, e a separação é o ponto.

A máscara pode deixar uma cover circular enquanto o alvo de toque permanece
retangular e acessível. Se a região de interação seguisse a máscara, cada canto
arredondado encolheria a área clicável, e transição em íris tornaria a tela
progressivamente inoperável durante a animação.

O defeito não aparece na captura: a imagem fica correta. Ele aparece para quem
usa toque ou controle.

## Transições mascaradas — `ViewTransitionMaskSpec`

```
irisClose, irisOpen, circularReveal, linearWipe,
radialWipe, gradientReveal, assetReveal, elementAnchoredReveal
```

Transição circular:

```yaml
target: outgoingView
mask:
  source: { kind: circle, center: view.center, radius: autoCover }
timeline:
  property: mask.radius
  from: autoCover
  to: 0
```

`autoCover` calcula a distância até o canto mais distante. Precisa funcionar em
4:3, 16:9 e 21:9 — um raio fixo deixaria canto descoberto na proporção mais
larga, e o artefato apareceria só no monitor de quem tem 21:9.

O centro poderá ser ligado a: centro da view, posição fixa, percentual, elemento
selecionado, cover selecionada, `gameSurface`.

## Propriedades animáveis

`centerX`, `centerY`, `radius`, `width`, `height`, `rotation`, `scaleX`,
`scaleY`, `feather`, `thresholdMin`, `thresholdMax`, `opacity`.

## Ordem de composição

```
conteúdo
→ clip geométrico
→ mask stack
→ borda
→ sombra/glow externo
→ efeitos
→ opacidade/blend
→ composição no pai
```

A ordem é conceitual até o P0-08 validá-la. Está registrada agora porque a
ordem errada produz resultados plausíveis — uma sombra recortada pela própria
máscara parece uma escolha de design, não um defeito.

## Fallbacks

| Indisponível | Degrada para |
|---|---|
| `roundedRect` | clip retangular |
| transição circular | crossfade |
| máscara alpha | opacity fade |
| mask stack | primeira máscara suportada |

Todo fallback produz veredito `fallback` ou `approximated`, com
`originalValue`, `resolvedValue`, `fallbackKind`, `reason` e `sourceReference`
— o mesmo registro que o adapter QML já exige para degradação. Nenhum ocorre em
silêncio.

## Segurança

Máscara não pode usar caminho físico, URL arbitrária, captura de aplicação
externa, referência circular ou shader arbitrário do tema.

A detecção de ciclo precisa cobrir o caso indireto: *A* usa *B* como máscara e
*B* usa *A*. Um ciclo de máscaras não trava numa exceção clara — ele consome
memória até o compositor morrer, e o sintoma aparece longe da causa.

## Desempenho

**Analíticas** (`rect`, `roundedRect`, `circle`, `ellipse`) usam o caminho de
menor custo, sem superfície intermediária.

**Por textura, vetor complexo ou elemento** podem exigir superfície
intermediária, e precisam de: cache, limite de resolução, limite de
aninhamento, limite de passes, perfil mínimo e fallback.

## Backend visual

O gate atual é `visual-software`: determinístico, sem GPU, mesmo resultado em
qualquer runner. Ele **não** valida máscara composta, blur, glass, shader,
partícula, vídeo, efeito sobre `gameSurface` nem transição mascarada avançada.

Fica reservada a categoria `visual-rhi` para isso. Um golden de um backend não
vale para o outro, e tratá-los como intercambiáveis produziria diferenças que
parecem regressão sem nenhuma mudança de código.

`visual-rhi` **não** é implementado no VS-03. Só a separação é preservada.
