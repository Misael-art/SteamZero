# Cobertura backend → interface handheld

Status: contrato executável, schema 1.

A fonte de verdade é `handheld_ui_contracts()` em
`src/steamzero/adapters/desktop_contracts.py`. O mesmo catálogo é publicado por
`GET /contracts` e no campo `dashboard.uiContracts` de `GET /status`. A QML
resolve operações por `id`; somente `/status`, necessário para receber o próprio
catálogo, permanece como rota de bootstrap.

Cada linha da matriz contém:

| Campo | Garantia |
| --- | --- |
| `service`, `endpoint`, `method` | serviço e rota reais da bridge |
| `screen`, `control` | destino visual e controle consumidor |
| `id`, `label`, `enabled`, `reason` | capacidade publicada pelo backend |
| `states` | `ready`, `empty`, `degraded`, `pending`, `failed`, `offline` |
| `confirmation`, `inputSchema` | confirmação e payload aceito |
| `jobSemantics` | síncrono/assíncrono, estados e polling |
| `rollback` | suporte e endpoint de reversão |
| `applicability` | aplicável ou `not-applicable` com justificativa |

## Cobertura deliberadamente não aplicável

| Capacidade | Motivo atual |
| --- | --- |
| Rollback manual de componente | o engine consegue reverter durante a transação, mas a bridge não publica seleção auditável de operação por componente |
| Recovery manual de componente | recovery é interno ao engine e ainda não existe como endpoint Desktop isolado |
| Histórico de perfis | revisão mostra a diferença antes de aplicar e há recovery; o store não publica uma linha do tempo pela bridge |
| Histórico global de operações | o journal existe, mas não há read model sanitizado e paginado para a GUI |
| Restore/migração direta de saves | o domínio possui primitivas transacionais, mas a bridge ainda não resolve com segurança o destino real por jogo/emulador |
| Invalidação/restauração direta de shader cache | o domínio exige raiz, lista de arquivos e fingerprint de driver; esses fatos ainda não são publicados pelo controller |
| Prioridade de mods | ativar, desativar e remover são persistidos; o store atual não possui ordenação/prioridade confiável |
| Exportação de estado | a CLI não possui destino GUI seguro via portal |
| Saúde administrativa | o helper não publica endpoint para a bridge |
| Recuperação de sessão | pertence ao daemon e ainda não tem contrato Desktop |
| Pacote de suporte | política de sanitização existe, geração GUI não |
| Retry/cancel de sync | o snapshot de sync ainda é somente leitura |

A fila de jobs de emulação deixou de ser lacuna: lista, progresso, resultado,
cancelamento seguro e nova tentativa são publicados pela bridge e consumidos
pela Central de tarefas global.

Perfis Steam expõem estado atual, prévia e diferenças no diálogo de revisão,
aplicação confirmada e recovery do launcher. Opções de lançamento, manutenção,
mídia Steam, LSFG e ações transacionais de emulação têm reversão/recuperação
nas rotas indicadas pela matriz. A fila de sync permanece somente como resumo:
conflito, retry, cancelamento e saúde do provider não são inferidos pela QML.

Os escopos Portátil e Dock publicam valores semanticamente distintos derivados
do contexto observado (resolução, escala e controles). TDP, FPS, gráficos e
áudio permanecem marcados como herdados quando o host não fornece valor; a
transição automática é explicitamente indisponível porque ainda não existe um
executor. Assim, a UI não apresenta um desejo como se já tivesse sido aplicado.

Esses itens aparecem desabilitados no catálogo; a interface não cria botões
decorativos para preencher a lacuna.

## Verificação automática

`tests/unit/test_desktop_contracts.py` compara todas as rotas da bridge com o
catálogo, valida os campos e estados, verifica os itens não aplicáveis e impede
que a QML volte a codificar rotas operacionais diretamente.
