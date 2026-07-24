# WI-A5 — Plataformas cloud declarativas e atalhos reversíveis

## Entrega

- GeForce NOW, Xbox Cloud Gaming e Amazon Luna reutilizam os manifests
  `platform-manifest-v1`, artes originais e URLs HTTPS exatas entregues por F5;
- a central de emulação substitui os placeholders cloud por projeções
  operacionais que distinguem presença do abridor local de disponibilidade do
  serviço, conta, assinatura, catálogo, região e rede;
- a ação de abertura resolve o ID no registro local, recusa plataformas
  desconhecidas ou emuladas e envia ao `xdg-open` somente a URL allowlisted do
  manifesto;
- CLI, JSON-RPC, bridge Desktop e QML publicam a mesma ação `cloud.launch`;
- a sincronização Steam publica os três serviços como atalhos não-Steam usando
  o launcher do SteamZero e argumentos declarativos `cloud launch --platform`;
- plano, confirmação, verificação do VDF, histórico operacional e rollback
  cobrem a publicação dos atalhos.

## Segurança e reversibilidade

- o parser dos manifests exige HTTPS, hostname exato na allowlist, porta
  padrão/443 e ausência de credenciais na URL;
- a UI nunca aceita nem encaminha uma URL fornecida pelo usuário;
- IDs cloud obedecem à gramática fechada do registro; IDs opacos históricos de
  jogos Switch mantêm sua validação própria e não são reinterpretados;
- atalhos cloud usam o marcador exclusivo `steamzero://cloud/`; a sincronização
  preserva atalhos `steamzero://switch/` e todas as entradas de terceiros;
- AppIDs colidentes com qualquer entrada preservada bloqueiam o plano;
- plan e apply recusam Steam em execução, planos de outro domínio e VDF
  malformado; o smoke test relê o VDF escrito;
- rollback da remoção restaura os atalhos cloud anteriores sem alterar os
  atalhos Switch;
- o snapshot declara `serviceAvailability: unverified`: nenhum teste local ou
  offscreen é apresentado como prova de conta, assinatura, região, catálogo,
  rede ou disponibilidade comercial.

## Evidência

- suíte integral: 1.432 testes aprovados;
- cobertura total: 85,30% (mínimo 85%); domínio cloud: 94,67%;
- Ruff, mypy em 150 módulos, fronteiras e independência: aprovados;
- testes dedicados provam URL exata do manifesto, recusa de IDs desconhecidos e
  não-cloud, degradação sem `xdg-open` e ausência de chamadas de rede;
- codec/VDF prova preservação simultânea de atalhos externos, Switch e cloud,
  remoção seletiva, argumentos do launcher, tags e rollback;
- CLI e JSON-RPC usam allowlists fechadas para list, launch, plan e apply;
- a bridge HTTP percorre `/cloud/launch`, enquanto publicação e rollback
  reutilizam os contratos transacionais versionados da emulação;
- oito harnesses QML offscreen passaram após a fiação da ação cloud.

Estado final: `verified-dev`. Não houve acesso aos serviços externos, validação
de assinatura, teste de streaming nem verificação em hardware real. As artes
continuam sendo os fallbacks geométricos originais documentados em
`src/steamzero/ui/assets/ATTRIBUTION.md`; não foram importadas marcas ou imagens
de terceiros nesta entrega.
