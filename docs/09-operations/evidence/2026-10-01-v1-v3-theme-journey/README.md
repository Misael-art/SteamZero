# V1–V3 — pacote de demonstração para B_VISUAL

Branch `codex/v1-v3-theme-journey-2026-10-01`; commits V1 `c36edbc3`, V3 `1e3a17ef`, V2 `ee9431e2` e seguinte.
**Nível de prova: testes automatizados locais. Não há release instalada nem prova física.**

## Dados
Tema criado no próprio Studio ("Jornada"); biblioteca sintética isolada (`theme.scene.render` com
`synthetic: true`); nenhuma biblioteca Steam privada, ROM, BIOS ou save.

## Passos para repetir (UI)
1. Temas → Novo tema → nome "Jornada".
2. Studio: em "Enquadramento de mídia" escolha `focusedCover`; Ajuste `contain`, Orientação `auto`, Alinhamento vertical `top`.
3. Desfazer (volta ao ajuste anterior), Refazer (reaplica); "Não salvo" deve seguir o histórico.
4. Salvar; Fechar; reabrir o tema na lista — as escolhas devem permanecer.
5. Exportar; importar o `.zip` novamente: mesmo id exige escolher "como cópia" (id novo, nome "(cópia)"); o original fica intacto.
6. Aplicar: o diálogo deve dizer "Tema da central; não altera a Engine nem o Launcher". Confirmar e reverter (rollback).
7. Preview de cena: deve mostrar a "Biblioteca de demonstração" e nenhuma ação "Jogar".

## Provas automatizadas
`tests/unit/test_theme_authoring_journey.py` (jornada + resolver de runtime), `tests/integration/test_media_fit_parity.py`
(512 combinações JS↔Python), `tests/unit/test_synthetic_library_isolation.py`.

## Limites
Controles do Studio não foram exercitados por input real nem capturados; teclado/gamepad e seletor nativo não certificados;
fixtures ES-DE/RetroFE, AURA Cinema e execução no Launcher pendentes; FPS/memória não medidos.
