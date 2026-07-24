# WI-D1 — Emulador primário e artwork padrão por plataforma

## Entrega

- separação entre preferência configurada e emulador primário efetivo;
- fallback por precedência quando não há preferência persistida;
- preferência configurada continua publicada mesmo se a instalação estiver
  indisponível, com estado honesto `configured-unavailable`;
- payload inclui `primaryEmulator`, origem da resolução e IDs configurado/efetivo;
- QML seleciona o emulador primário no primeiro snapshot e preserva seleção local
  em refresh posterior da mesma plataforma;
- card de saúde global apresenta nome, estado e origem reais do primário, sem o
  placeholder contraditório “Padrão não definido”;
- jogos Switch publicam `platformId` e um único `fallbackArtworkUrl`;
- `switch.svg` é um fallback original, único e atribuído; cards não duplicam SVG
  em diretórios de jogos ou emuladores.

## Limites

O fallback representa a plataforma, não artwork do jogo, e não altera o estado
do MediaHub. Detecção de instalações externas ao engine gerenciado permanece
destino explícito de F5.

## Evidência

- contrato e controller: preferência configurada, precedência instalada e estado
  indisponível cobertos por testes unitários;
- jornada QML offscreen: seleção inicial do emulador publicado e fallback visual
  da plataforma validados em 1280×800;
- suíte completa: `1279 passed`;
- cobertura total: `85.14%` (mínimo exigido: 85%);
- Ruff, mypy, independência de runtime, fronteiras arquiteturais e
  `git diff --check`: aprovados;
- o helper unitário do controller usa `SessionSecretStore`, impedindo que testes
  leiam o cofre real ou iniciem scraping com credenciais do operador.

Estado: `verified-dev`. A experiência física continua sem alegação
`verified-hw`.
