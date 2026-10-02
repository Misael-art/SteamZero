# SteamZero

Plataforma autônoma de jogos e emulação para Steam Deck e desktops Linux.

> **Status:** em desenvolvimento. A instalação versionada, os smoke checks e o rollback foram verificados no host BigLinux. A instalação real em VM e a substituição da fonte EOL do DuckStation continuam pendentes.

Consulte [IMPLEMENTATION-REPORT.md](IMPLEMENTATION-REPORT.md) para detalhes e evidências por fase.

## Metodologia replicável

[METODOLOGIA-SINTESE-DE-PROJETOS.md](METODOLOGIA-SINTESE-DE-PROJETOS.md) — documento autocontido que explica o método de cruzamento e estudo de projetos usado aqui (E1–E8), escrito para que outro agente de IA replique o processo no planejamento de outros produtos. [IMPLEMENTATION-PROMPT.md](IMPLEMENTATION-PROMPT.md) é o prompt de construção correspondente (E8).

## Comece por aqui

1. [IMPLEMENTATION-REPORT.md](IMPLEMENTATION-REPORT.md) — estado por marco, testes, dívidas e limites verificados.
2. [docs/WORKLOG.md](docs/WORKLOG.md) — histórico de implementação com evidências.
3. [FOUNDATION-READINESS-REPORT.md](FOUNDATION-READINESS-REPORT.md) — relatório histórico da fundação documental.
4. [docs/09-operations/HOST-INSTALL.md](docs/09-operations/HOST-INSTALL.md) — instalação nativa versionada, verificação e rollback no BigLinux.

## Mapa da documentação

| Diretório | Conteúdo |
|---|---|
| `docs/00-vision` | visão, princípios, não-objetivos |
| `docs/01-product` | PRD, personas, jornadas, catálogo de features, critérios de aceitação |
| `docs/02-research` | repositórios-fonte, matriz de capacidades, inventário, gaps, scores de robustez, **quadro de funções e proveniência** |
| `docs/03-architecture` | arquitetura, fronteiras, transações, jobs, adapters, privilégio, modos de falha |
| `docs/04-security` | threat model, requisitos, path safety, supply chain, segredos, política de conteúdo, garantias de rollback |
| `docs/05-data` | state model, schemas de config/manifests, migrações, formato de backup |
| `docs/06-api` | contratos CLI/API, JSON schemas, catálogo de erros, eventos, autorização |
| `docs/07-ui-ux` | princípios, IA, Game/Desktop/QAM, navegação por controle, acessibilidade, erro/progresso, wireframes |
| `docs/08-testing` | estratégia, matrizes, injeção de falhas, hardware Deck, segurança, rollback, UI |
| `docs/09-operations` | logging, diagnóstico, support bundle, canais, update/rollback, recovery |
| `docs/10-migrations` | PhaseZero, import EmuDeck/RetroDECK, preservação de dados |
| `docs/11-legal` | matriz de licenças, atribuição, avisos de terceiros, política de reuso |
| `docs/12-roadmap` | roadmap por fases, marcos, riscos, dependências |
| `docs/adr` | decisões arquiteturais, incluindo independência de runtime e isolamento de falhas |
| `reference/` | clones somente-leitura dos projetos analisados (declarados no WORKLOG) — **não modificar** |

## Política inegociável

`local-owned-dump-only` — ver [docs/04-security/CONTENT-POLICY.md](docs/04-security/CONTENT-POLICY.md).

Também é inegociável a independência operacional: `make independence` falha se o
pacote padrão introduzir import, entrypoint, dependência ou literal perigoso de runtime
legado. Migração legada, quando necessária, ocorre apenas por snapshot offline em uma
ferramenta separada e removível.
