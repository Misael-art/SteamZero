# 6. Responsabilidades e fronteiras de alteração

Este plano foi ajustado para um agente de IA implementar em sequência. A divisão abaixo
serve para revisão e evita mudanças acidentais fora do domínio.

## 6.1 Donos lógicos

| Área | Responsabilidade |
|---|---|
| Domínio | modelo, resolução determinística, herança e limites |
| Adapter | descoberta segura, recursos builtin, XDG e catálogo |
| Transação | plan/apply/verify/rollback de preferência e pacote |
| API Desktop | read model e ações allowlisted |
| QML | consumo de tokens, preview e gerenciador |
| Segurança | path safety, formatos, limites e conteúdo não executável |
| QA | contrato, falhas, QML offscreen, foco e regressão visual |

## 6.2 Arquivos compartilhados

Os seguintes arquivos são pontos de conflito e devem ser alterados em commits próprios,
depois de a fundação estar verde:

- `src/steamzero/adapters/desktop_dashboard.py`;
- `src/steamzero/adapters/desktop_contracts.py`;
- `src/steamzero/adapters/desktop_ui.py`;
- `src/steamzero/ui/qml/Main.qml`;
- `src/steamzero/core/paths.py`;
- `docs/WORKLOG.md`.

Antes de cada alteração, o agente deve confirmar que o arquivo não mudou desde o início
da tarefa. Se mudou, deve rebasear/reconciliar conscientemente; nunca sobrescrever.

## 6.3 Revisões exigidas

| Marco | Revisão principal |
|---|---|
| contrato | arquitetura, compatibilidade e schema |
| catálogo | segurança de filesystem e conteúdo |
| transação | rollback, idempotência e ownership |
| bridge | autenticação, allowlist e ausência de shell |
| QML | foco, acessibilidade, warnings e visual padrão |
| pacote externo | limites, licença e fallback |

## 6.4 Matriz RACI compacta

| Entrega | Implementa | Revisa/aprova |
|---|---|---|
| `theme-manifest-v1` | agente da tarefa | mantenedor de arquitetura |
| catalog/validator | agente da tarefa | segurança |
| preferência transacional | agente da tarefa | core/transações |
| integração QML | agente da tarefa | UI/UX + acessibilidade |
| tema nativo de referência | agente da tarefa | design + UI |
| aceite físico | operador | operador |

Um agente pode implementar todas as etapas, mas não pode marcar a inspeção física como
aprovada por meio de harness offscreen.
