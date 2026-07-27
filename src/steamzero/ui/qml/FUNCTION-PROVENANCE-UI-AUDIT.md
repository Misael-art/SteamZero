# Auditoria da matriz de funções — recorte UI

Data: 2026-07-18 · branch: `codex/ui-emulacao` · classificação: `verified-dev`

Fonte auditada: `docs/02-research/FUNCTION-PROVENANCE-MATRIX.md`. Esta auditoria não
substitui a matriz normativa; ela confronta a relação com código, contratos e testes
existentes sem alterar adapters, domínio ou schemas.

## Integridade da relação

- A matriz possui **262 IDs únicos** e 266 ocorrências de linhas `SZ-*`; quatro IDs
  reaparecem no sumário ADAP.
- O total declarado de 262 IDs únicos está correto.
- O comando de reprodução documentado no rodapé informa “250 linhas de função” e está
  desatualizado em relação ao próprio arquivo.

## Estado global verificável

| Bloco | Estado | Evidência e limite |
|---|---|---|
| M1–M3: TX/FS/State/Jobs/API | entregue em `verified-dev` | FI-04, contratos golden, jobs e gate completo verdes; daemon UNIX/peer credentials e alguns itens avançados permanecem dívida |
| M4–M6: Deck Core | entregue na lógica, parcial em hardware | device/mode/storage/helper/session testados com portas fake; mutações reais e matriz de hardware não concluídas |
| M7–M9: conteúdo | entregue nos critérios automatizados, integrações reais parciais | biblioteca 10k, BIOS/saves e sync verdes; conversores externos, scraper e migração física continuam não verificados |
| M10 | parcial | engine/manifests/Flatpak `verified-dev`; instalação mutável dos três componentes e fonte DuckStation ainda bloqueiam fechamento |
| M10-H | foundation | Desktop QML, bridge efêmera, perfis e recovery existem; apply de hardware continua não verificado |
| M11 | não iniciado | adapters Steam/SRM/ES-DE e frontends ausentes |
| M12 | parcial antecipado apenas na Desktop UI | shell QML e testes de foco existem; Game Mode UI/biblioteca/jogo ainda ausentes |
| M13 | não iniciado | adoção EmuDeck/RetroDECK em hardware ausente |
| M14–M15 | não iniciados como release | instalador host é foundation; Flatpak da plataforma, canais assinados, SBOM e release stable ausentes |

## IDs de UI e apresentação

| ID | Estado | O que existe | Falta / dependência |
|---|---|---|---|
| SZ-HD-08 | **foundation** | central Qt/QML responsiva, touch-friendly e navegável | validação real de controle/touch e composição com os read models da Fase 5 |
| SZ-UI-01 | **ausente** | — | Game Mode UI Godot 4; fora do toolkit e do escopo desta branch |
| SZ-UI-02 | **parcial** | visão geral, prontidão, componentes, Steam, sync e doctor | espaço e Jobs não existem no payload atual |
| SZ-UI-03 | **ausente** | — | read model paginado/virtualizado da biblioteca e contrato para 10k+ itens |
| SZ-UI-04 | **ausente** | — | jogo selecionado, escopo e ações agregadas no contrato |
| SZ-UI-05 | **backend sem apresentação** | domínio BIOS existe e é testado | read model de plataformas/arquivos/compatibilidade/import local |
| SZ-UI-06 | **backend sem apresentação** | Job Manager existe e é testado | lista/eventos/etapa real/cancelamento expostos à UI |
| SZ-UI-07 | **backend sem apresentação** | conflito de sync preserva ambas as versões | itens conflitantes e ações allowlisted de decisão no payload |
| SZ-UI-08 | **foundation** | Desktop UI com perfis, componentes, Steam, sync, recovery e diagnóstico | lote, logs/journal e migrações dependem de contratos futuros |
| SZ-UI-09 | **ausente** | — | capability e adapter QAM/Decky opt-in |
| SZ-UI-10 | **entregue na Desktop UI** | nenhum fluxo depende de Decky; ausência não quebra o shell | validar novamente quando SZ-UI-09 existir |
| SZ-UI-11 | **parcial verificado** | grafo principal, D-pad/Enter/Escape via Qt, histórico, seções e retorno de foco | `QtGamepad` não está instalado; LT/RT/View, hot-swap e Nintendo A/B exigem runtime/input real |
| SZ-UI-12 | **entregue na foundation** | ação de teclado usa provider allowlisted e mostra indisponibilidade | validação assistida Maliit/Steam em hardware |
| SZ-UI-13 | **entregue** | erro comunica falha, impacto conservador e ação “Ver diagnóstico” | códigos mais específicos dependem do erro estruturado recebido |
| SZ-UI-14 | **entregue em dev** | 100/125/150%, preset TV, alto contraste, reduced motion, labels e alvos ≥48 px | auditoria assistida com zoom do sistema, leitor de tela, touch e hardware |
| SZ-UI-15 | **ausente** | — | fallback zenity/TTY pertence ao adapter/launcher, não à QML |
| SZ-UI-16 | **ausente** | — | estado explícito de primeira execução e passos allowlisted; não pode ser inferido de campo ausente |
| SZ-CT-11 | **parcial** | rail usa ícones vetoriais independentes do tema | glyphs por tipo de controle e hot-swap precisam de `currentInput/glyphSet` real |
| SZ-QA-10 | **parcial forte em dev** | Qt Quick Test cobre foco, escalas, contraste, filtros, loading e retorno; goldens multi-resolução | controle/touch/hot-swap e hardware físico não verificados |

## Contratos necessários antes dos itens bloqueados

Não criar fallbacks sintéticos. Os itens acima precisam, no mínimo, de read models ou
capabilities equivalentes a:

1. `libraryPage` paginado e seleção de jogo;
2. `gameDetail` com ações allowlisted e estados observed/applied;
3. `biosPlatforms` e plano de import local;
4. `jobs` com etapa, progresso real e cancelabilidade;
5. `saveConflicts` com ambas as versões preservadas;
6. `storageSummary`/espaço verificado;
7. `currentInput`, `glyphSet` e eventos de hot-swap;
8. `firstRun` explícito, versionado e idempotente;
9. capability Decky/QAM;
10. lifecycle/capability de janela Steam e read model de lançamento gerenciado.

Até esses contratos existirem, mostrar telas “completas” com fixtures permanentes violaria
a verdade operacional e a separação QML→apresentação definida pela própria matriz.
