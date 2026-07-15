# SECRETS-HANDLING — tratamento de segredos

## Inventário de segredos do produto

| Segredo | Origem | Armazenamento | Exposição permitida |
|---|---|---|---|
| Tokens OAuth/API de cloud sync (rclone-like) | usuário conecta provedor | keyring do sistema (Secret Service API) quando disponível; fallback: arquivo 0600 cifrado (chave derivada local) | nunca em API/logs; write-only |
| Credenciais RetroAchievements (se suportado) | usuário | idem | idem |
| Chaves de assinatura de release | CI | fora do produto (KMS/secret do CI) | — |
| Keys/firmware de console do usuário | import local | NÃO são segredos do produto, são conteúdo do usuário: store de conteúdo com permissão 0600, nunca em logs (SR-14) | status + hash truncado |

## Regras

1. Tipo `Secret[str]` no núcleo: repr/format mascarado (`***`); serializadores recusam; logger rejeita registro contendo o valor (verificação por canary em testes).
2. Segredos nunca em argv (visível em /proc), nunca em env de subprocessos filhos que não precisem, nunca no state.db em claro, nunca no support bundle.
3. Entrada de segredo: apenas por UI (campo mascarado)/CLI prompt sem eco/portal do provedor; nunca por parâmetro de linha de comando em produção.
4. Rotação: revogar token = apagar do keyring + invalidar filas de sync pendentes que o usavam.
5. Precedente positivo a herdar: PhaseZero mantém `bootstrap-secrets.json` fora do VCS e tem ADR de rotação (docs/adr/0001-secrets-rotation-state-machine.md) — o Unified eleva isso a keyring nativo.
