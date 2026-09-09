# AURA — matriz de dependências de capacidades AURA-01..AURA-18

Entrega da frente A0 do plano
[AURA-FULLSCREEN-PLATFORM-EXECUTION-PLAN.md](AURA-FULLSCREEN-PLATFORM-EXECUTION-PLAN.md)
(Onda 0, item "matriz de dependências e critérios P0/P1/P2"). Este documento
registra dependências e critérios; **não declara nenhuma capacidade
implementada**. O estado real de cada capacidade vive em
`docs/status/items/` — extraia estado dos itens, nunca daqui.

## Critérios de aceite por prioridade

- **P0 — bloqueante do primeiro release console-like.** Uma capacidade P0 só
  está "pronta" quando integrada, empacotada e validada fisicamente no host
  (release citada, evidência PNG). A publicação do release fullscreen exige
  **todos** os P0 fechados: AURA-01, 02, 03, 06, 08, 11, 12, 18.
- **P1 — acompanhante do primeiro ciclo, não bloqueante isoladamente.** Pode
  entrar no release se fechada, mas sua ausência não impede a publicação; deve
  degradar honestamente (estado explícito, nunca silêncio): AURA-04, 05, 07,
  09, 10, 13, 15, 17.
- **P2 — adiável sem perda da jornada principal.** Só entra com backend
  provado e medição no hardware indicado; até lá permanece contrato/protótipo,
  sem aparecer como pronto: AURA-14, 16.

Critério transversal (qualquer prioridade): ausência de recurso, arte,
credencial ou rede produz **explicação e próximo passo**, nunca tela vazia;
nenhuma superfície falsifica estado; nenhuma alegação de desempenho sem
medição no hardware e na release citados.

## Matriz

| ID | Capacidade | Prioridade | Entrega mínima | Depende de | Onda | Agente |
|---|---|---|---|---|---|---|
| AURA-01 | Shell fullscreen e navegação | P0 | home, coleções, busca, página, foco, launch/return | AURA-02, AURA-06, input | 2 | A4 |
| AURA-02 | Metadados canônicos e import/export | P0 | schema, proveniência, ES-DE, RetroFE, Pegasus, LaunchBox, Playnite, Steam, RetroArch | biblioteca | 1 | A1 |
| AURA-03 | Pipeline de imagem | P0 | ingestão, crop, escala, cache, JPEG/PNG/WebP/SVG seguro | AURA-02, Theme Engine | 2 | A2 |
| AURA-04 | Effect graph e movimento | P1 | blur, cor, máscara, sombra, transições e tiers | AURA-03, medição de performance | 2 | A3 |
| AURA-05 | Paleta, glass e composição | P1 | cor dinâmica, fanart blur, highlight, cover flow, fallback | AURA-03, AURA-04 | 2 | A3/A4 |
| AURA-06 | Biblioteca automatizada | P0 | watcher opt-in, scan, integridade, dedupe, conversão, fila | AURA-02, jobs | 1 | A5 |
| AURA-07 | Hardware e perfis | P1 | GPU/RAM/display/input, handheld/desktop/dock, presets | diagnóstico, lifecycle | 3 | A6 |
| AURA-08 | BIOS, firmware e keys | P0 | requisitos por plataforma, hash, região, estado visual | manifests, biblioteca | 3 | A7 |
| AURA-09 | Lifecycle e shadPS4 | P1 | install/update/verify/rollback, PS4 governado | manifests, supply chain | 3 | A8 |
| AURA-10 | Enhancement registry | P1 | IDs, registry curado, dry-run, apply/revert, anti-cheat | AURA-02, adapters | 4 | A9 |
| AURA-11 | Pause menu e OSD | P0 | pausa, volume, screenshot, save/load, retorno seguro | sessão, input | 5 | A10 |
| AURA-12 | Saves e save-state gallery | P0 | thumbnail, timestamp, playtime, slots, backup | adapters de sessão | 5 | A10 |
| AURA-13 | Cards, fade, bezels, multi-game | P1 | cards de instrução, fade, overlays, discos, manuais | AURA-11, mídia | 5 | A11 |
| AURA-14 | Marquee e multi-monitor | P2 | display secundário seguro e degradável | display context | 6 | A11/A13 |
| AURA-15 | Notificações e emergência | P1 | toasts, hotkeys globais, kill seguro, Central | daemon, sessão | 6 | A13 |
| AURA-16 | Sync, achievements, netplay | P2 | providers opcionais, offline-first, consentimento | AURA-12, rede | 6 | A13 |
| AURA-17 | Theme Studio | P1 | canvas, árvore, inspector, efeitos, timeline, pacote | Theme Engine | 6 | A12 |
| AURA-18 | Desempenho e certificação | P0 | FPS, frame time, VRAM, startup, input latency, evidência | todas as superfícies | 6 | A14 |

## Grafo de dependências (resumo)

```
A0 (contratos/fixtures)
├── A1 metadados ──┬── A4 shell ──────────────┐
│                  ├── A5 biblioteca ops      │
│                  ├── A7 BIOS/keys           │
│                  ├── A9 enhancements ──┐    │
│                  └── A10 sessão/saves ─┼──┐ │
├── A2 pipeline ── A3 effects ──┬─ A4 ────┘  │ │
│                               └─ A12 ──────┼─┤
├── A6 hardware ───────────────────────────── │ │
└── A8 lifecycle ── A9 ───────────────────────┘ │
                     A10 ── A11 cards/fade      │
                     A10 ── A13 providers       │
                     A14 integração/medição ◄───┘ (fecha por último;
                         falha física reabre o item responsável)
```

## Contratos congelados nesta frente (A0)

- `src/steamzero/schemas/game-record-v1.schema.json` — GameRecord canônico com
  MediaRole e Provenance (origem, timestamp, confiança, política de conflito).
- `src/steamzero/schemas/enhancement-entry-v1.schema.json` — EnhancementEntry
  com categoria fechada (sem cheats), fonte https com checksum e licença.
- `tests/fixtures/aura-contracts/` — fixtures de exceção: arte ausente,
  conflito de fontes, multi-disc, BIOS ausente, save conflitante, operação
  interrompida, campos de versão futura.
- `docs/adr/0028-aura-cinema-tema-default.md` — direção visual, tiers,
  fallbacks, acessibilidade e budget de desempenho do tema default.

## Critérios de aceite do produto final

O AURA Cinema e a plataforma só podem ser promovidos quando:

1. a primeira tela abre com foco válido e navegação completa sem mouse;
2. a biblioteca canônica apresenta títulos, capas, fanart e fallback sem
   identificadores técnicos expostos;
3. jogar abre o runtime correto, sem duplicar processos, e retorna ao mesmo
   foco;
4. ausência de BIOS, emulador, arte, credencial ou rede produz explicação e
   próximo passo, não tela vazia;
5. toda operação mutável mostra plano, risco, progresso real, cancelamento
   seguro, resultado e recuperação;
6. save-state, Pause, OSD, cards e fade existem somente onde o adapter declara;
7. tema externo é seguro, reproduzível, acessível e não executa código;
8. low/balanced/cinematic degradam sem perda de jogabilidade;
9. performance é medida no hardware e na release citados;
10. todos os P0 estão integrados, empacotados e fisicamente validados.
