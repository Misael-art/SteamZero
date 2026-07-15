# LOCAL-API-CONTRACT — API do serviço local

## Transporte

- JSON-RPC 2.0 sobre UNIX domain socket `$XDG_RUNTIME_DIR/steamzero/core.sock` (dir 0700, socket 0600); peer credentials verificadas (SO_PEERCRED: mesmo UID).
- Sem TCP por padrão. Modo remoto não existe no v1 (nem atrás de flag).
- Eventos: subscription via mesmo socket (notificações JSON-RPC) — ver EVENTS-AND-PROGRESS.

Exceção transitória M10-H: enquanto o daemon persistente não existe, `desktop ui` cria
uma bridge HTTP somente em `127.0.0.1`, porta aleatória e token de 256 bits, encerrada
junto ao processo QML. A bridge expõe apenas status/plan/apply/reset/recover/keyboard,
mantém `confirmToken` e não aceita conexão remota. Não é API pública nem modo remoto.

## Superfície (allowlist — dispatch apenas de métodos registrados)

Espelha os domínios da CLI (mesma camada de ações): `system.hello` (negocia `contractVersion`), `system.capabilities`, `<dominio>.<ação>` para queries, `plan.create`, `plan.get`, `job.submit {planId, confirmToken}`, `job.{list,get,pause,resume,cancel}`, `events.subscribe {filters}`, `state.{export}`, `support.{bundlePreview,bundleWrite}`.

Regras próprias do SteamZero (UI nunca importa funções do orquestrador; só contrato):

1. **Nomes de método são enum registrado**; método desconhecido = erro padrão, sem reflexão (P4, SR-19).
2. **Parâmetros validados por JSON Schema** publicado (JSON-SCHEMAS.md); erro de validação aponta o campo.
3. **Mutação = duas fases**: `plan.create` → `job.submit(planId, confirmToken)`. Não existe método "faça X agora" mutável.
4. **AuthZ local** por classe de ação (AUTHORIZATION-MODEL.md).
5. **Progresso/cancelamento** nativos: todo job emite eventos; `job.cancel` sempre aceito (cancel seguro).
6. **Segredos**: métodos de configuração de cloud recebem segredos write-only (nunca retornados); UI usa portais/keyring quando possível.
7. **Correlação**: toda chamada aceita/gera `correlationId` propagado a logs e eventos.
8. **Versionamento**: `system.hello` retorna `contractVersion` (semver); cliente incompatível recebe instrução de atualização, nunca comportamento silencioso diferente.

## Erros

Formato único: `{code: "E-…", title, detail, impact, action, operationId?, docs?}` — códigos do ERROR-CATALOG. JSON-RPC `error.data` carrega esse objeto.

## Disponibilidade

Daemon ativável por socket unit (systemd user) — primeira chamada sobe o serviço; queda do daemon com jobs ativos → recovery na subida (JOB-LIFECYCLE).
