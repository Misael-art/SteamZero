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
| Prioridade de mods | ativar, desativar e remover são transacionais, mas os emuladores gerenciados não fornecem ordem determinística verificável; o backend publica a capacidade como ausente e a UI oculta mover acima/abaixo |
| Recuperação de sessão | pertence ao daemon e ainda não tem contrato Desktop |
| Retry/cancel/resolução de conflito de sync | a fila é real e somente leitura; ainda não existe `CloudPort` autenticado nem mutações transacionais allowlisted na bridge |

A fila de jobs de emulação publica lista, progresso, resultado, cancelamento
seguro e nova tentativa. Saves publicam destino confirmado por jogo/emulador,
inventário de backups e restore transacional com rollback byte-idêntico. Shader
cache publica driver/fingerprint, versão, tamanho, backup/restore compatível e
invalidação por rename atômico com recovery. Destinos ambíguos ou inseguros não
produzem botões.

Perfis Steam expõem estado atual, prévia e diferenças no diálogo de revisão,
aplicação confirmada e recovery do launcher. Opções de lançamento, manutenção,
mídia Steam, LSFG e ações transacionais de emulação têm reversão/recuperação
nas rotas indicadas pela matriz. A fila de sync mostra itens e conflitos reais,
mas declara explicitamente modo somente leitura, provider ausente e a
dependência necessária para mutações.

Sistema publica histórico de operações paginado com alvos hashados, estado da
sessão, health administrativo estritamente allowlisted, exportação transacional
do estado sanitizado e bundle de suporte agregado. Ambos exigem destino escolhido
e preview antes do token de confirmação; session recovery permanece ausente.

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
