# LOCAL-API-CONTRACT — API do serviço local

## Transporte

- JSON-RPC 2.0 sobre UNIX domain socket `$XDG_RUNTIME_DIR/steamzero/core.sock` (dir 0700, socket 0600); peer credentials verificadas (SO_PEERCRED: mesmo UID).
- Sem TCP por padrão. Modo remoto não existe no v1 (nem atrás de flag).
- Eventos: subscription via mesmo socket (notificações JSON-RPC) — ver EVENTS-AND-PROGRESS.

Exceção transitória M10-H: enquanto a central QML ainda não migrou todo o fluxo, `desktop ui` cria
uma bridge HTTP somente em `127.0.0.1`, porta aleatória e token de 256 bits, encerrada
junto ao processo QML. A bridge expõe apenas status/plan/apply/reset/recover/keyboard,
mantém `confirmToken` e não aceita conexão remota. Não é API pública nem modo remoto.

## Superfície (allowlist — dispatch apenas de métodos registrados)

Espelha os domínios da CLI (mesma camada de ações): `system.hello` (negocia
`contractVersion`), `system.capabilities`, `<dominio>.<ação>` para queries,
`plan.create`, `plan.get`, `job.submit {planId, confirmToken}`,
`job.{list,get,pause,resume,cancel}`, `events.subscribe {filters}`,
`state.{export}`, `support.{bundlePreview,bundleWrite}`.

A superfície implementada em F4 acrescenta `jobs.list`, `operations.list` e
`events.page` paginados à allowlist fechada. `events.subscribe` é um método
especial de leitura: depois do resultado de confirmação, a mesma conexão fica
dedicada às notificações `events.event` e termina com `events.complete`.

F6 acrescenta `controls.profiles`, `controls.plan`, `controls.apply` e
`controls.rollback`. Campos de plataforma, perfil, escopo e orientação são
enums/IDs limitados; apply exige o token single-use e rollback aceita somente
uma operação cujo journal declare `input-profile.activate:*`.

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

Daemon ativável por `steamzero-core.socket` (systemd user) — a primeira chamada sobe o
serviço. A CLI usa o socket quando ele existe e faz fallback in-process somente quando a
conexão ainda não foi estabelecida. Falha após o envio é ambígua e **não** repete mutação
localmente. Queda do daemon com jobs ativos → recovery na subida (JOB-LIFECYCLE).

Para stream, a CLI também só usa fallback local quando nunca conectou. Depois do
ack, perda de transporte causa até três reconexões com o último cursor entregue;
resposta fora de ordem, duplicada ou incompatível falha como erro de contrato.
Filtros são listas exatas e limitadas, mensagens são limitadas a 1 MiB e cada
assinatura mantém somente uma página (máximo 256 eventos) em memória.

Implementado em `0.1.0a8`: `system.hello`, `system.capabilities` e a allowlist inicial de
doctor, jobs, state, components, sessão de jogo e Desktop. Cada método aceita apenas campos
registrados, limita mensagem/conexão/mutações e rejeita UID diferente pelo `SO_PEERCRED`.
Não existe `shell.exec`, listener TCP ou dispatch por reflexão.

Desde `0.1.0a11`, `session.environment` expõe o snapshot Linux read-only usado pelo
reconciliador futuro. O método não recebe parâmetros nem oferece uma contraparte mutável.

Desde `0.1.0a34`, consultas paginadas e assinatura de eventos usam o mesmo socket
autenticado. O handler de assinatura termina quando o peer desconecta ou o daemon
entra em shutdown; uma conexão de stream não aceita comandos adicionais.
