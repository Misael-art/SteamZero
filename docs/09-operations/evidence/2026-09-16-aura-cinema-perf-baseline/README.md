# Baseline de desempenho do AURA Cinema — 2026-09-16

Esta medição foi executada contra a janela Wayland real do host, sem harness
offscreen, na release ativa `2.0.0rc1-3c4b563242a9`. Ela é um baseline de
comparação antes da instalação da candidata `2.0.0rc1-5ecab7d7c2fd`, preparada
a partir do `main` pós-merge do PR #188.

Resultado: startup de `185 ms`, p95 do render loop de `14,587 ms`, pico RSS de
`151588 KB` e pico VRAM de `47268 KB`, medido por DRM fdinfo agrupado por
`drm-client-id`. O p95 ficou abaixo do limite de `16,7 ms` nesta amostra, mas
isso não promove a meta: a mudança de release ainda não foi instalada e a
medição não representa frames apresentados pelo compositor.

O arquivo `01-baseline.json` é comparativo. A captura PNG funcional e a medição
final exigidas pelo item continuam pendentes para a release candidata.
