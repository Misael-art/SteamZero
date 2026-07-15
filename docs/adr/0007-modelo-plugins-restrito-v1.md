# ADR-0007 — Plugins: v1 restrito a manifestos declarativos; código de terceiros adiado

**Status:** aceito

## Contexto/Problema
Extensibilidade atrai comunidade, mas carregamento de código de terceiros é a maior superfície de supply chain (T-06); §5.1 proíbe carregamento automático de pasta e execução de função por string.

## Alternativas
1. **v1: adapters declarativos de terceiros (dados), sem código; v2: plugins assinados+sandbox** (escolhida).
2. Plugins Python livres desde v1 — risco inaceitável (equivale a Decky-store sem revisão).
3. Nenhuma extensibilidade — perde a força da comunidade que fez EmuDeck/RetroDECK crescerem.

## Decisão
Conforme PLUGIN-MODEL.md: `adapters.d/` aceita apenas manifests 100% declarativos com sha256 obrigatório, badge "não verificado" e consentimento explícito; hooks de terceiros não são carregados no v1.

## Consequências
Roadmap v2 precisa de ADR próprio (assinatura, sandbox, permissões declaradas) antes de qualquer código de terceiro rodar.

## Revisão
Ao fim da Fase 6, medir demanda real da comunidade; abrir ADR de plugins v2 se justificado.
