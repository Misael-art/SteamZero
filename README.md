# SteamZero — Fase 0: Fundação Documental

Plataforma consolidada de jogos e emulação para Steam Deck e desktops Linux, projetada a partir da análise de PhaseZero, EmuDeck, LinuxToys e RetroDECK.

**Estado:** fundação documental completa, aguardando aprovação. **Nenhum código de produção existe neste repositório** e nenhum será escrito até existir `APPROVED_TO_IMPLEMENT` neste diretório (ou autorização textual `APPROVED_TO_IMPLEMENT=true`).

## Metodologia replicável

[METODOLOGIA-SINTESE-DE-PROJETOS.md](METODOLOGIA-SINTESE-DE-PROJETOS.md) — documento autocontido que explica o método de cruzamento e estudo de projetos usado aqui (E1–E8), escrito para que outro agente de IA replique o processo no planejamento de outros produtos. [IMPLEMENTATION-PROMPT.md](IMPLEMENTATION-PROMPT.md) é o prompt de construção correspondente (E8).

## Comece por aqui

1. [FOUNDATION-READINESS-REPORT.md](FOUNDATION-READINESS-REPORT.md) — relatório executivo, classificação `READY FOR PROTOTYPE`, bloqueadores.
2. [docs/OPEN-QUESTIONS.md](docs/OPEN-QUESTIONS.md) — decisões pendentes do responsável (licença é a crítica).
3. [docs/WORKLOG.md](docs/WORKLOG.md) — o que foi feito, com evidências.

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
| `docs/adr` | 18 decisões arquiteturais (0013-licença pendente de decisão) |
| `reference/` | clones somente-leitura dos projetos analisados (declarados no WORKLOG) — **não modificar** |

## Política inegociável

`local-owned-dump-only` — ver [docs/04-security/CONTENT-POLICY.md](docs/04-security/CONTENT-POLICY.md).
