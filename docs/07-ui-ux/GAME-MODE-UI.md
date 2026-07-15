# GAME-MODE-UI

Tecnologia: Godot 4 (ADR-0002, condicionado a protótipo). Resoluções-alvo: 1280×800 (Deck), 1920×1080/4K (dock com escala TV).

## Dashboard (§12.4)

Blocos (cards focáveis):
- **Pronto para jogar** — contagem + acesso à biblioteca filtrada.
- **Problemas críticos** — rollback-failed, storage-missing, conflitos (deep-link).
- **Atualizações** — plataforma e componentes (com canal).
- **Saves pendentes/conflitos** — fila de sync + decisões pendentes.
- **Espaço** — SSD/microSD com barra real e projeção de jobs em fila.
- **Estado do dock/microSD** — modo atual, cartão presente/ausente.
- **Últimos jogos** — retomada em 1 clique.
- **Jobs em execução** — mini-progresso, atalho para Jobs.

## Página do jogo (§12.5)

Header: arte + título + plataforma + estado agregado.
Ações: **Jogar** (primária) · Emulador (qual, versão, abrir config) · Perfil (desempenho/controles/display aplicáveis) · Save (timeline, restaurar, checkpoint) · Backup · Mídia (rever/raspar) · Controles (layout aplicado, testar) · Desempenho (meta FPS, TDP do perfil) · Diagnóstico (verify deste jogo) · Histórico (operações que tocaram este jogo) · Configurações por jogo · Migração (mover para outro volume — plano) · Verificação (hash do dump).

## Centro de BIOS & Firmware (§12.6)

Cartões por plataforma: estado (`presente/ausente/desconhecido/incompatível` — com ícone+texto), região, versão, hash (truncado, expansível para P2), emuladores que usam, última validação, ação **Importar arquivo local** (file portal). Nunca link de download (CONTENT-POLICY).

## Jobs (§12.7)

Lista com: etapa (do pipeline real), progresso honesto (barra só com `total` real), arquivo atual, velocidade, espaço, concluídos/pendentes, avisos; ações pausar/retomar/cancelar (com "cancelando com segurança…").

## Regras Game Mode

- 100% gamepad (NAVIGATION-BY-CONTROLLER); teclado virtual automático em campos de texto.
- Sem operações destrutivas diretas: tudo passa por plano/preview/confirmação (frase tipada para `destructive`).
- Overlay de primeira execução ensina navegação (pulável, reexibível).
- Performance: 60fps na UI do Deck; listas virtualizadas para bibliotecas de 10k+ itens.
