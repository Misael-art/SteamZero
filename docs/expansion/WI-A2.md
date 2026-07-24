# WI-A2 — Histórico operacional e rollback contextual

## Entrega

- `feat-operation-history-v1` publica histórico paginado por cursor, detalhe,
  alvo sanitizado, estado observado e disponibilidade contextual de rollback;
- o `StateStore` permanece o índice autoritativo e journals são lidos somente
  como evidência; uma reconciliação limitada a 1.000 entradas cobre stores
  legados ainda vazios sem voltar a materializar o diretório em cada consulta;
- operações transacionais e deployments Flatpak mantêm rotas distintas:
  journals comuns usam `transaction.rollback`, enquanto Flatpak usa seu
  executor pinado e revalida o deployment corrente;
- CLI e daemon expõem `operations list|show|rollback-plan|rollback-apply`;
- a bridge Desktop publica detalhe, preview e apply no catálogo fechado de
  contratos;
- a página Sistema oferece Detalhes e Desfazer, com diálogo de revisão antes da
  confirmação e retorno de foco no fechamento.

## Segurança e rollback

- o preview persiste `operationId`, rota, expiração e fingerprint da evidência,
  mas nunca expõe paths reais;
- apply exige `confirmToken`, recarrega o plano, verifica expiração, estado
  `committed`, fingerprint, plano transacional original e estado atual de cada
  alvo;
- journals são aceitos somente no caminho canônico, como arquivo regular sem
  symlink, com até 4 MiB e 4.096 registros sequenciais do mesmo `operationId`;
- intents são comparados aos IDs, destinos, fontes e backups do plano original;
- arquivos alterados depois do preview são preservados e produzem
  `E-TX-STALE-PLAN`;
- rollback só retorna sucesso depois de observar `rolled-back` no `StateStore`;
- planos consumidos são idempotentemente recusados e operações inválidas
  continuam visíveis como `invalid`, sem botão mutável.

## Evidência

- suíte integral: 1.409 testes aprovados;
- cobertura total: 85,20% (mínimo 85%); domínio do histórico: 86,94%;
- Ruff, mypy strict em 147 módulos, fronteiras e independência: aprovados;
- testes dedicados cobrem escrita, remoção, movimento, symlink, operação sem
  mudanças, Flatpak contextual, reconciliação legada, token incorreto,
  expiração, consumo único, journal corrompido, symlink de evidência,
  adulteração do intent e mudança do alvo após preview;
- CLI, JSON-RPC real e bridge HTTP percorrem detalhe → preview → confirmação →
  rollback verificado;
- oito harnesses QML offscreen passaram, incluindo o diálogo de rollback em
  949×593 e 1280×800;
- wheel `steamzero-0.1.0a34-py3-none-any.whl` de verificação contém
  `feat-operation-history-v1.schema.json`.

Estado final: `verified-dev`. Não há alegação de validação em hardware real; a
evidência de UI é exclusivamente offscreen.
