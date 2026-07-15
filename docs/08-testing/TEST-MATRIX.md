# TEST-MATRIX — matriz funcional × critérios

Cada célula referencia ACs (01-product/ACCEPTANCE-CRITERIA.md) e classes de falha (FAILURE-INJECTION).

| Funcionalidade | Unit | Integração | Falhas | Rollback | Hardware | UI |
|---|---|---|---|---|---|---|
| Instalação componente (flatpak/appimage/nativo) | schema manifesto | AC-IN-01..03 | FI-01..05 | RT-01 | HW: por dispositivo | fluxo instalar |
| Atualização/canais | lockfile | AC-IN-03 | FI-02,04 | RT-02 | — | plano/preview |
| Desinstalação | inventário | preserva dados usuário | FI-04 | RT-03 | — | confirmação |
| Reparação | verify units | repara só camada quebrada | FI-09 | RT-04 | — | — |
| Config emuladores | parsers round-trip | diff/preset/restore-defaults | FI-14 (json/xml inválido) | RT-05 | — | editor diff |
| Biblioteca scan | classificadores | incremental correto | FI-13 (symlink), FI-16..18 | n/a (read-only AC-LB-01) | microSD real | listas 10k |
| Conversões ROM | planejador espaço | AC-LB-02 | FI-06 (ENOSPC), FI-19 | RT-06 | I/O microSD real | job em lote |
| Import dumps | safezip property-based | AC-LB-03 | FI-16..18 | RT-07 (cópia) | pendrive real | assistente |
| BIOS store | hash db | links seguros AC-BI-01/02 | FI-13 | RT-08 | — | centro BIOS |
| Saves timeline | dedupe blobs | AC-SV-01..03 | FI-08..09, FI-20 | RT-09 | suspensão real | timeline/conflito |
| Cloud sync | fila | conflito preserva ambos | FI-01 (rede) | RT-10 | — | status sync |
| Mídia/scraping | sanitização | cache/rate limit | FI-03 payload | RT-11 (órfãos→quarentena) | — | — |
| Perfis desempenho | resolução de camadas | aplica/restaura ao sair | FI-09 | RT-12 (G-STATE) | TDP em Deck real | página perfil |
| Controles | conflitos de layout | hot-swap | FI-11 (device loss) | — | BT/USB reais | teste de eixos |
| Frontends (Steam/SRM/ES-DE) | geradores | shortcuts dedupe, vdf backup | FI-14 | RT-13 (vdf restore) | Steam real | — |
| Session manager | máquina de estados | hooks flush/checkpoint | FI-08..10 | — | suspensão real | — |
| Modos/dock | máquina + fallback | cadeia de fallback | FI-12 (display) | restore de modo | docks reais (matriz HW) | — |
| microSD | UUID tracking | FM-06 semântica | FI-07 | — | cartão real | estado volume |
| Offline | fila | AC-OF-01 | FI-01 | — | modo avião real | pendências |
| Job manager | fila/prioridade | pause/resume/cancel/reboot | FI-04, FI-15 | recovery | — | cards de job |
| API/CLI | schemas golden | contrato v2 | FI-15 | — | — | — |
| Helper privilegiado | validação params | polkit deny | ST-01 fuzz | valores anteriores | Deck real (TDP) | — |
| Support bundle | anonimização | preview obrigatório | — | — | — | revisão |
| Update da plataforma | migrações encadeadas | canais | FI-04 durante migração | RT-14 (state.db restore) | — | — |
