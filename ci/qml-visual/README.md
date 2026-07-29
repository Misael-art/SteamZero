# Imagem canônica do gate visual QML

O ambiente **é** o contrato. As baselines em `tests/qml/golden/` não comparam "o
texto renderizado" — comparam pixels produzidos por uma combinação exata de Qt,
FreeType, HarfBuzz e fontconfig. Trocar qualquer um deles muda a imagem sem
mudar uma linha de código, e a divergência apareceria como regressão.

## Por que uma imagem, e não `apt`/`pacman` no runner

Duas coisas foram verificadas no CI, não supostas:

O runner do **Ubuntu 24.04 não tem o runtime QML**. `/usr/lib/qt6/bin/` traz
`qmldom`, `qmleasing`, `qmlformat`, `qmllint`, `qmlls`, `qmlplugindump`,
`qmlpreview`, `qmlprofiler`, `qmltc`, `qmltestrunner` e `qmltime` — e **nenhum
`qml`**. A provisão de Qt no CI nunca funcionou; o `skipif` dos harnesses legados
escondeu isso desde que existe.

E mesmo que tivesse, o Ubuntu 24.04 traz **Qt 6.4.2** enquanto as baselines
foram geradas em **6.11.1**. O gate reprovaria por diferença de Qt, não por
regressão.

## Por que `pacman -Syu` no build, e não `-Sy`

A primeira versão deste Containerfile usava `-Sy` para "preservar" a base
fixada. Isso é **upgrade parcial**, que o Arch quebra por design — e quebrou: o
`pyexpat` saiu com símbolo indefinido, justamente o parser que lê os layouts do
RetroFE.

O digest da base semeia o build de um ponto conhecido. Quem congela o
**resultado** é o digest da imagem construída, que o workflow referencia.
Atualizar durante o build não afrouxa nada; afrouxaria se acontecesse a cada
execução do teste, e é isso que esta imagem existe para evitar.

## Conteúdo

Registrado em `environment.lock.json` e verificado na entrada do gate.
Divergência reprova **antes** de renderizar, em vez de virar diferença de pixel
sem causa aparente.

| componente | versão |
|---|---|
| Qt runtime | 6.11.1 |
| qt6-declarative | 6.11.1-3 |
| qt6-base | 6.11.1-1 |
| fontconfig | 2:2.18.2-1 |
| freetype2 | 2.14.3-1 |
| harfbuzz | 14.2.1-1 |
| Python | 3.14.6-1 |

A fonte **não** vem da imagem: vem de `tests/fixtures/fonts/`, e o harness isola
o fontconfig nela. A imagem não precisa ter fonte nenhuma instalada — e não tem,
o que é melhor: não há o que sombrear a empacotada.

## Publicar uma versão nova

```bash
gh workflow run qml-visual-image.yml
```

O workflow constrói, publica em `ghcr.io/misael-art/steamzero-qml-visual` e
imprime o digest. Fixe-o em `.github/workflows/ci.yml`, no job
`qml-visual-linux`. **Nunca referencie por tag** — tag é mutável, e a autoridade
do gate é o digest.

## Se as baselines divergirem depois de trocar a imagem

Nesta ordem, sem atalho:

1. confirmar que a diferença vem **exclusivamente** da troca de ambiente;
2. rodar `update-qml-goldens` dentro da mesma imagem;
3. revisar `expected`, `actual`, `diff` e `metrics.json`;
4. versionar em commit separado.

```bash
docker run --rm -v "$PWD":/w -w /w \
  ghcr.io/misael-art/steamzero-qml-visual@sha256:<digest> \
  sh -c 'pip install --break-system-packages --require-hashes -r requirements-dev.lock \
         && python tools/update_qml_goldens.py --write'
```

Baseline regravada sem alguém olhar é carimbo, não verificação.
