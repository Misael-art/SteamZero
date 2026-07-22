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
| Fila global de jobs | a bridge só expõe jobs de emulação conhecidos |
| Exportação de estado | a CLI não possui destino GUI seguro via portal |
| Saúde administrativa | o helper não publica endpoint para a bridge |
| Recuperação de sessão | pertence ao daemon e ainda não tem contrato Desktop |
| Pacote de suporte | política de sanitização existe, geração GUI não |
| Retry/cancel de sync | o snapshot de sync ainda é somente leitura |

Esses itens aparecem desabilitados no catálogo; a interface não cria botões
decorativos para preencher a lacuna.

## Verificação automática

`tests/unit/test_desktop_contracts.py` compara todas as rotas da bridge com o
catálogo, valida os campos e estados, verifica os itens não aplicáveis e impede
que a QML volte a codificar rotas operacionais diretamente.
