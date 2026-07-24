# WI-G1 — MangoHud por jogo, diff e rollback

## Entrega

- a seleção `off`, `basic` ou `detailed` permanece integrada ao perfil por jogo
  e ao compilador `steamzero-launch`;
- o plano mostra diff campo a campo, revalida biblioteca/capacidades e bloqueia
  MangoHud ou MangoApp ausentes;
- apply agora cria uma operação transacional `steam.gameplay-profile:*`, salva
  perfil e layout de controle atomicamente e retorna `operationId`;
- o estado anterior dos registros afetados é preservado em um registro de undo
  privado e associado à operação;
- rollback restaura ou remove somente os perfis afetados, compensa falha do
  journal e elimina o undo consumido;
- bridge, catálogo Desktop e QML expõem rollback real separado do recovery de
  sessão do launcher.

## Segurança

- IDs de operação e perfis são validados e todas as queries usam parâmetros;
- undo corrompido, ausente, de owner incorreto ou ligado a journal de outro tipo
  falha fechado;
- StateStore aplica upserts e deletes em `BEGIN IMMEDIATE`, com rollback SQLite
  em qualquer exceção;
- o ambiente do launcher contém apenas configs allowlisted de
  `gtool-hud-v1`; nenhum shell ou valor MangoHud arbitrário é aceito;
- a reversão não toca atalhos Steam, arquivos do jogo ou perfis de terceiros.

## Evidência

- suíte integral: 1.438 testes aprovados;
- cobertura total: 85,28%;
- Ruff, mypy em 151 módulos, independência e fronteiras: aprovados;
- fluxo testado: basic → preview diff → detailed → apply → journal → rollback
  → basic restaurado → segunda reversão recusada;
- confirmação incorreta, ambiente alterado, ferramenta ausente e valores fora
  da allowlist permanecem cobertos;
- oito harnesses QML offscreen passaram após a inclusão do controle de undo.

Estado final: `verified-dev`. Renderização perceptual do MangoHud permanece
`PENDING-HUMAN`, conforme G0.
