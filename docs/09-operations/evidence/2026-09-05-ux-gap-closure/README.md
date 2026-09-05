# Fechamento UX — catálogo de temas no bootstrap

Prova física da release `2.0.0rc1-ca9ab317fc3c`, commit
`ca9ab317fc3cefdd4088add8cb58a55dc67f7cd2`, instalada pelo fluxo governado em
2026-09-05. Rollback disponível: `2.0.0rc1-085169f47186`.

## Resultado observado

1. `01-installed-central-themes.png`: estado transitório imediatamente após a
   abertura; a aba Temas ainda mostra zero arquivos e o botão Atualizar fica
   desabilitado enquanto os contratos não chegaram.
2. `02-installed-central-themes.png`: a seção Temas foi aberta na release
   instalada.
3. `03-installed-central-themes-after-bootstrap.png`: após o bootstrap, a
   Central mostra 5 entradas, 567,3 MB em 4.125 arquivos e estados `Instalado`;
   não há o toast anterior de contrato ausente.

Consulta read-only da bridge, feita com o token mantido somente em memória:

```json
{"entries":5,"excluded":4,"storeUsage":{"blobs":4125,"bytes":594819462},"error":null}
```

## Integridade da evidência

| Arquivo | SHA-256 |
|---|---|
| `01-installed-central-themes.png` | `c6765f870d884a7e9a69feeb05980f4e645fa7ae7ec6f03780701f8ea4437b71` |
| `02-installed-central-themes.png` | `c416ff24d3bef1cc51958ab0de7b5b3f9b08aa1ddb707cee2d6b7f178a0334ba` |
| `03-installed-central-themes-after-bootstrap.png` | `ecce9805fd1fa09120bf8471c93f8fb38f267e32639d4a0014f0bb6fc526a808` |

O serviço SteamZero foi convergido e validado idempotentemente pelo
`release_host.py`. Nenhum reboot, logout, encerramento ou finalização da sessão
KDE foi executado; o launcher KDE existente permaneceu ativo.

Os gaps de contraste do alerta, semântica do tema ativo, gate de contratos
órfãos e roteamento live-launcher continuam explicitamente fora deste fechamento
e permanecem no item de status.
