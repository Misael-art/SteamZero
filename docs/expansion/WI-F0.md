# WI-F0 — Saneamento da baseline de qualidade

## Motivo

O tip-base `c94d249` estava limpo e os gates funcionais documentados passaram,
mas a reprodução independente de `make cov` mediu 81,37%, abaixo do mínimo
normativo de 85%. Nenhuma feature de expansão pode começar sobre esse estado.

## Mudanças

- testes comportamentais para `ns-emu-mod-downloader`, SEMD e NSECM sem rede ou
  binários externos;
- testes do SteamGridDB, dispatcher, cache, HTTPS, limites, redirects e códigos
  de falha;
- testes do MediaHub `masters → optimized → views`, auditoria, ownership,
  publicação Steam e rollback;
- testes do read model Switch, candidatos, fallback, seleção, otimização,
  publicação e cobertura;
- testes da bridge Desktop para ações registradas e lançamentos Steam por argv
  fixo;
- registro de `E-SCRAPE-HTTP-ERROR` e `E-SCRAPE-OFFLINE`, que eram emitidos pelo
  adapter mas recusados pelo catálogo autoritativo.

## Garantias

- nenhum acesso a rede, credencial, ROM, mídia pessoal ou serviço do host;
- nenhuma exclusão de arquivo da medição, `pragma: no cover` ou redução de
  `fail_under`;
- subprocessos e HTTP são fakes determinísticos;
- WORKLOG permanece intocado durante o WI;
- a branch-base não foi alterada.

## Evidência

Antes: 1219 testes, cobertura 81,37%.

Após os novos testes, a medição limpa e integral alcançou 85,05% com 1251 testes
aprovados em 76,26 s.

Gates finais:

- `pytest tests -q`: 1251 passed;
- `ruff check src tools tests`: aprovado;
- `mypy src`: aprovado em 137 arquivos;
- `make independence boundaries`: aprovado, sem violações;
- `make cov`: aprovado com 85,05%;
- `git diff --check`: aprovado.

Estado final: `verified-dev`. Este resultado não representa validação física.
