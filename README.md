# SteamZero

Plataforma autônoma de jogos e emulação para Steam Deck e desktops Linux. A pesquisa
histórica avaliou PhaseZero, EmuDeck, LinuxToys e RetroDECK, mas nenhum deles é
dependência de build, instalação, runtime, recuperação ou testes do SteamZero.

**Estado:** implementação aprovada e em andamento. Fases 1–2 e o critério de
saída da Fase 3 possuem backend `verified-dev` (RT-06..11 verdes). A Fase 4 começou
com schema/registry, três manifests núcleo e lifecycle portável transacional do M10;
o M10-H adiciona a fundação Handheld Desktop para BigLinux/KDE, com status real no
Steam Deck LCD, perfis transacionais e UI Qt/QML opcional. Aplicação real dos perfis,
executor Flatpak e demais marcos continuam pendentes. Consulte
`IMPLEMENTATION-REPORT.md` para evidências e limites.

## Metodologia replicável

[METODOLOGIA-SINTESE-DE-PROJETOS.md](METODOLOGIA-SINTESE-DE-PROJETOS.md) — documento autocontido que explica o método de cruzamento e estudo de projetos usado aqui (E1–E8), escrito para que outro agente de IA replique o processo no planejamento de outros produtos. [IMPLEMENTATION-PROMPT.md](IMPLEMENTATION-PROMPT.md) é o prompt de construção correspondente (E8).

## Comece por aqui

1. [IMPLEMENTATION-REPORT.md](IMPLEMENTATION-REPORT.md) — estado por marco, testes, dívidas e limites verificados.
2. [docs/WORKLOG.md](docs/WORKLOG.md) — histórico de implementação com evidências.
3. [FOUNDATION-READINESS-REPORT.md](FOUNDATION-READINESS-REPORT.md) — relatório histórico da fundação documental.

## Mapa da documentação

| Diretório | Conteúdo |
|---|---|
| `docs/00-vision` | visão, princípios, não-objetivos |
| `docs/01-product` | PRD, personas, jornadas, catálogo de features, critérios de aceitação |
| `docs/02-research` | repositórios-fonte, matriz de capacidades, inventário, gaps, scores de robustez |
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
