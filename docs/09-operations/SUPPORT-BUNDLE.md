# SUPPORT-BUNDLE — pacote de suporte (§14)

## Conteúdo (todo anonimizado)

| Item | Fonte | Anonimização |
|---|---|---|
| Versões (plataforma, componentes, contrato) | state | — |
| Hardware (modelo, displays, volumes) | doctor | UUIDs truncados; sem serial |
| Sistema (distro, SteamOS/Steam Client, flatpak) | doctor | hostname/usuário removidos |
| Estado agregado (contagens por entidade/estado) | state | sem títulos de jogos por padrão (opt-in) |
| Logs selecionados | por correlationId/janela de tempo | paths → `{ROMS}/…` ou hash; scanner de segredos obrigatório |
| Resultado de doctor + testes recentes | doctor/CI local | — |
| Configurações não sensíveis | config.toml filtrado por allowlist de chaves | — |
| Problemas ativos + ações já executadas | event log | — |
| Journal da operação afetada | journal | payloads de conteúdo omitidos |

**Nunca incluído:** keys/firmware/BIOS (nem nomes completos), conteúdo de saves, tokens, e-mail/identidade.

## Fluxo (obrigatório)

1. Usuário aciona (por erro específico ou geral) → 2. bundle montado em staging → 3. **UI/CLI exibe o conteúdo integral** (árvore + preview de cada arquivo) → 4. usuário pode remover itens → 5. usuário confirma → 6. gravado como `.tar.zst` onde o usuário escolher. Sem passo 5 não existe arquivo final. Nenhum envio automático (N7).

`support-bundle-v1.schema.json` descreve o índice (`manifest.json` na raiz do tar) para tooling de suporte.
