# ADR-0019 — Independência de runtime e isolamento de falhas

**Status:** aceito

## Contexto

O SteamZero nasceu de síntese de projetos existentes, mas precisa funcionar como produto
autônomo no Deck. Compartilhar serviços, scripts ou estado criaria falhas correlacionadas,
ownership duplo de input/display e rollback dependente de software externo.

## Decisão

1. O pacote padrão não possui dependência, import, entrypoint, path, serviço ou chamada
   de runtime para PhaseZero.
2. Pesquisa e atribuição permanecem documentais. Migração é uma conversão offline por
   ferramenta separada, read-only e não empacotada.
3. KDE, Steam, InputPlumber, teclados e integrações são providers opcionais atrás de
   portas. Ausência degrada uma capacidade, não o núcleo.
4. Entrada tem um único owner lógico. Conflito genérico mantém o coordenador em modo
   observador; nunca são iniciados dois remapeadores.
5. Cada perfil Desktop grava snapshot persistente antes do primeiro efeito. Verify
   falho reverte; crash deixa recovery pendente; modo seguro não exige provider.
6. CI executa um gate AST/packaging que impede regressão dessas regras.

## Consequências

O sistema pode oferecer menos automação quando um provider falta, mas status, plano,
recuperação e acesso físico permanecem disponíveis. Integrações futuras precisam provar
timeout, fallback, rollback e remoção sem quebrar o SteamZero.
