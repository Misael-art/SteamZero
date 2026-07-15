# ACCESSIBILITY — acessibilidade (§12.9)

## Requisitos v1

| Req | Especificação | Verificação |
|---|---|---|
| Escala de UI | 100% / 125% / 150% / TV (10-foot: fontes maiores, distâncias maiores) — sem quebra de layout nem elemento inacessível em nenhuma escala | screenshot tests nas 4 escalas × 2 resoluções |
| Alto contraste | tema dedicado (não filtro), razão ≥ 7:1 para texto essencial | auditoria automatizada de contraste |
| Cor nunca é o único canal | todo estado tem ícone+texto além da cor (ready ✓ / degraded ⚠ / missing ✖) | revisão de design + teste de daltonismo simulado |
| Redução de movimento | desliga animações/parallax/auto-scroll; transições viram cortes | flag global respeitada por todos os componentes |
| Tempo de notificação | duração configurável; notificações críticas persistem até dispensadas | teste de config |
| Remapeamento | ações da UI remapeáveis (além do Steam Input); sem ação exclusiva de stick | matriz de entrada |
| Labels acessíveis | todo elemento interativo com label textual (base para narração futura) | lint de UI |
| Ordem lógica | ordem de foco = ordem de leitura | teste do focus graph |
| Modo baixa visão | escala 150+/TV + alto contraste + fontes pesadas como preset único "Baixa visão" | preset testado |
| Narração (futuro) | arquitetura preparada: labels + eventos de foco expostos; motor TTS fica para v2 (G10 — Godot screen reader é risco pesquisável) | ADR-0002 protótipo mede viabilidade |
| Glyphs dinâmicos | ver NAVIGATION-BY-CONTROLLER §5 | — |

## Princípios

- Acessibilidade entra no DoD de cada tela (não é sprint separada).
- Textos de erro seguem ERROR-UX (frases curtas, sem jargão) — beneficia todo mundo, começa por P1.
- Configurações de acessibilidade ficam no primeiro nível de Configurações e no assistente de primeira execução.
