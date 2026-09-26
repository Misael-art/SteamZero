# Cadência de validação e promoção

O desenvolvimento acontece em lotes verticais coesos. Durante um lote, rode os
testes focados da área alterada e lint/formatação dos arquivos tocados. A suíte
integral, mypy, boundaries, independence e `make status-check` são gates do
checkpoint de fechamento do lote, antes do commit funcional. Execute esse
checkpoint uma vez por lote estável.

Antecipe gates integrais somente quando a mudança tocar bootstrap,
empacotamento, host, segurança ou contrato transversal; quando uma falha focada
indicar regressão fora do módulo; ou quando o operador pedir. Para artefato de
status gerado, regenere a visão/digest e repita só a validação de status
pertinente.

Push ocorre após o checkpoint local completo, em um único envio por lote. Depois
dele, registre branch, SHA e run; avance em trabalho seguro independente. O CI
remoto é consultado em estado terminal antes de merge/release, após notificação
ou quando não houver trabalho local independente. Falha de CI volta ao teste ou
gate que a demonstrou; não reinicia a suíte integral só porque houve demora.

Fluxo de promoção: lote local estável → checkpoint integral → push → CI
terminal → merge → CI da main → preparação de release → instalação governada →
evidência física. Cada etapa mantém as autorizações específicas descritas em
`AGENTS.md`.
