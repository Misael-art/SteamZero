# WI-R0 — Tabela integer normativa e sharp-bilinear

## Entrega

- contrato `retro-integer-scaling-v1` define política sem stretch e sem crop;
- o cálculo puro seleciona o maior fator inteiro que cabe no viewport;
- fonte maior que o viewport cai explicitamente em `sharp-bilinear`, sem fator
  inteiro fictício;
- toda linha publica fonte, viewport, saída, margens, cobertura, motivo e
  fallback sharp-bilinear;
- dimensões são limitadas a 1–8192 e booleanos não são aceitos como inteiros.

## Tabela normativa 1280×800

| Sistema/modo | Fonte | Fator | Saída |
|---|---:|---:|---:|
| GB/GBC LCD | 160×144 | 5× | 800×720 |
| GBA LCD | 240×160 | 5× | 1200×800 |
| NES/Famicom 240p | 256×240 | 3× | 768×720 |
| SNES 224p | 256×224 | 3× | 768×672 |
| Mega Drive 224p | 320×224 | 3× | 960×672 |
| Arcade 240p | 320×240 | 3× | 960×720 |
| PlayStation 240p | 320×240 | 3× | 960×720 |

O fallback de cada linha preserva a razão geométrica dentro do viewport com
`sharp-bilinear`. PAR e modos adicionais por jogo serão compostos em R2; a
tabela não afirma que toda ROM usa a geometria normativa.

## Evidência

- suíte integral: 1.463 testes aprovados;
- cobertura total: 85,37%;
- cobertura do domínio de integer scaling: 100%;
- Ruff, mypy em 154 módulos, independência e fronteiras: aprovados;
- oito harnesses QML offscreen aprovados;
- testes cobrem fatores conhecidos, margens, ausência de crop/stretch,
  downscale sharp-bilinear e dimensões adversariais.

Estado final: `verified-dev`. R0 não introduz mutação nem nova rota QML; o
contrato será consumido pelo catálogo de presets `retro-experience-v1` em R1.
