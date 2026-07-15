# DESKTOP-MODE-UI

Tecnologia candidata: Qt Quick/QML ou frontend web local (ADR-0002 decide com protótipo; contrato de API idêntico torna a escolha reversível).

## Foco (§12.2): poder e densidade para P2/P3

- **Operações em lote:** multi-seleção em biblioteca/componentes (converter 200 ISOs → CHD; verificar hashes de uma plataforma inteira; aplicar preset a N jogos) — sempre 1 plano composto com preview e progresso por item.
- **Configurações avançadas:** editor de presets com origem por campo, diff antes de aplicar, restore-defaults por seção.
- **Importação/migração:** assistentes EmuDeck/RetroDECK adoption (10-migrations) com relatório em três painéis: encontrado / plano / resultado.
- **Logs e diagnóstico:** visualizador de logs estruturados com filtro por correlationId/jobId; journal de operações navegável (o que, quando, backup onde, reverter).
- **Schemas:** visualização dos contratos (ajuda P2 a automatizar por CLI).
- **Manutenção:** GC de backups (com preview), quarentena (inspecionar/restaurar/descartar), verificação de integridade de volumes.
- **Administração de armazenamento:** volumes por UUID, migrações SSD↔microSD, relatório de integridade.

## Regras

1. Mesmo backend, mesma allowlist — a UI desktop não tem poderes extras além de `destructive` com confirmação tipada.
2. Gamepad também funciona aqui (P3 usa TV+controle no desktop), mas atalhos de teclado existem.
3. Tabelas exportáveis (CSV/JSON) para auditoria.
4. Nunca editar arquivos de config "no braço" pela UI: sempre pelos parsers estruturados com diff (F-CF-01).
