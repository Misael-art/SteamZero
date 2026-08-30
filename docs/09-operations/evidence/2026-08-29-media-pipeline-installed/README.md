# Evidência física — mídia instalada em 2026-08-29

Release observada: `2.0.0rc1-a897f8ffcfed` no Steam Deck LCD (Valve Jupiter).
O rollback disponível é `2.0.0rc1-3b296a949316`.

- `01-baseline.json`: masters registrados por plataforma antes da busca.
- `02-search-missing.json`: job real sobre os 212 jogos canônicos. A leitura
  original registrou incorretamente quota; a reavaliação posterior mostrou que
  o transporte descartava o corpo do HTTP 403 e convertia credencial recusada
  em quota. O cofre não continha `ssid`/`sspassword` pessoais. Nenhum master
  novo foi aplicado; a busca deve ser repetida somente após o operador
  configurar essas credenciais.
- `02-entrega-funcional.png`: captura da central instalada, com capa e hero
  artwork reais. A versão ativa é vinculada por `04-active-release.json`.
- `03-after-search.json`: contagem de masters depois do job.
- `06-platform-migration-plan.json`: plano do layout novo contra o acervo real:
  no-op seguro, pois o único master em disco não está registrado nem pode ser
  associado a uma plataforma sem adivinhação.

Limite observado: a arte mostrada pela central vem da fonte legada
`media/switch`, enquanto `media_masters` permanece vazio antes e depois da
busca. Artwork não está resolvido nesta entrega. A separação nova de masters
não foi instalada nesta release; ela é coberta pelo commit funcional `0ce9009`.
