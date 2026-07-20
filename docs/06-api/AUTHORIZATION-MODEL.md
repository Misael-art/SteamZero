# AUTHORIZATION-MODEL — autorização local

## Premissa

Ambiente single-user (Deck) com processos do mesmo UID potencialmente não confiáveis (T-05). Não é um modelo multiusuário de rede — é defesa em profundidade local + prevenção de ações destrutivas não intencionais.

## Classes de ação

| Classe | Exemplos | Requisito |
|---|---|---|
| `read` | status, listas, timeline | conexão válida (mesmo UID via SO_PEERCRED) |
| `mutate-safe` | scan de biblioteca, criar plano, pausar job próprio | conexão válida |
| `mutate-confirm` | apply de qualquer plano | `confirmToken` do plano (single-use, expira, emitido só via `plan.create`) |
| `destructive` | GC de backups, esvaziar quarentena, delete de timeline | confirmToken **+** frase de confirmação tipada na UI/CLI (`--confirm-destructive <texto>`) |
| `privileged` | via helper | polkit por ação (autenticação do usuário conforme policy do sistema) |
| `secrets` | gravar token cloud | write-only; leitura nunca existe na API |

## Regras

1. confirmToken vincula {plano, params, precondições} — não autoriza nada além daquele plano (aprovação não generaliza).
2. QAM/Decky adapter recebe um escopo restrito: apenas `read` + ações rápidas pré-declaradas (`saves.checkpoint`, `perf.applyProfile`) — nunca `destructive` (07-ui-ux/QAM-INTEGRATION).
3. Sem sistema de contas/senha local no v1 (complexidade sem ameaça correspondente); reavaliar com multi-user (Q9).
4. Rate limit em ações `mutate-*` por conexão (anti-loop de cliente bugado).
5. Toda decisão de authz é logada com correlationId (sem dados sensíveis).
6. `admin.health` usa `pkexec` com argv fixo e não aceita parâmetros. Ações
   mutáveis são recusadas no cliente antes de iniciar o helper até que o efetor
   host correspondente tenha plano, verify e rollback certificados.
