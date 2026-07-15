# LOW-FIDELITY-WIREFRAMES — wireframes de baixa fidelidade (ASCII)

## W1. Dashboard (Game Mode, 1280×800)

```
┌──────────────────────────────────────────────────────────────┐
│  ◉ SteamZero          🎮 handheld · 🔋 62% · ⇅ sync ok │
├──────────────────────────────────────────────────────────────┤
│ ┌────────────────────────────┐ ┌───────────────────────────┐ │
│ │ ▶ CONTINUAR JOGANDO        │ │ ⚠ PROBLEMAS (1)           │ │
│ │ [art] Metroid Prime        │ │ microSD "SD-Red" ausente  │ │
│ │ ontem · pronto ✓           │ │ 3 jogos indisponíveis     │ │
│ └────────────────────────────┘ └───────────────────────────┘ │
│ ┌──────────────┐ ┌──────────────┐ ┌────────────────────────┐ │
│ │ BIBLIOTECA   │ │ SAVES        │ │ JOBS (1 em execução)   │ │
│ │ 412 jogos    │ │ 2 pendentes  │ │ Convertendo ISO→CHD    │ │
│ │ 9 plataformas│ │ 1 conflito ⚠ │ │ ▓▓▓▓▓░░░ 12/31 · 42MB/s│ │
│ └──────────────┘ └──────────────┘ └────────────────────────┘ │
│ ┌──────────────┐ ┌──────────────┐ ┌────────────────────────┐ │
│ │ EMULADORES   │ │ BIOS ✓/✖     │ │ ESPAÇO                 │ │
│ │ 12 ok, 1 ⚠   │ │ psx✓ ps2✖ …  │ │ SSD ▓▓▓▓░ 82GB livre   │ │
│ └──────────────┘ └──────────────┘ └────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│ (A) Abrir  (B) —  (Y) Buscar  (☰) Opções   LB/RB Abas        │
└──────────────────────────────────────────────────────────────┘
```

## W2. Página do jogo

```
┌──────────────────────────────────────────────────────────────┐
│ [ boxart ]  METROID PRIME (GameCube)          estado: ✓ pronto│
│             Dolphin 5.0-21xxx · perfil "Dock 4K" · SSD        │
├──────────────────────────────────────────────────────────────┤
│ ▶ JOGAR                                                       │
│ ── Saves ──────────── linha do tempo (5) · último: hoje 14:02 │
│ ── Desempenho ─────── meta 60fps · TDP 12W · FSR ✓            │
│ ── Controles ──────── layout "GC padrão" · testar entradas    │
│ ── Emulador ───────── config deste jogo · restaurar padrão    │
│ ── Verificação ────── hash ✓ (validado há 3 dias)             │
│ ── Migração ───────── mover para microSD (plano: 1,4GB)       │
│ ── Histórico ──────── 4 operações · último backup: ontem      │
├──────────────────────────────────────────────────────────────┤
│ (A) Selecionar (B) Voltar (X) Checkpoint (View) Detalhes      │
└──────────────────────────────────────────────────────────────┘
```

## W3. Centro de BIOS (cartão)

```
┌── PlayStation ───────────────────────────────┐
│ scph5501.bin  ✓ presente · US · hash a1b2…   │
│ usado por: DuckStation, RetroArch(Beetle)    │
│ validado: hoje                                │
│ scph5500.bin  ✖ ausente · JP (opcional)      │
│ [ Importar arquivo local ]                    │
└──────────────────────────────────────────────┘
```

## W4. Conflito de save (J6)

```
┌── Existem dois progressos diferentes deste jogo ─────────────┐
│   ESTE DECK                     │   NUVEM (desktop-casa)      │
│   hoje 14:02 · 32h10m jogadas   │   ontem 23:47 · 31h52m      │
│   [ Usar este ]                 │   [ Usar este ]             │
│        [ Manter os dois por enquanto (recomendado) ]          │
│  Nada é apagado: a versão preterida fica na linha do tempo.   │
└──────────────────────────────────────────────────────────────┘
```

## W5. Erro com ação (padrão ERROR-UX)

```
┌── ⚠ A atualização falhou. A versão anterior foi restaurada ──┐
│ O download do DuckStation não conferiu com a assinatura      │
│ esperada e foi descartado.                        (E-SUPPLY-  │
│ Impacto: você continua na versão atual, funcionando.CHECKSUM) │
│ [ Tentar novamente ]  [ Ver detalhes ]  [ Exportar diagnóstico]│
└──────────────────────────────────────────────────────────────┘
```

## W6. Job em lote (Desktop Mode)

```
┌ Converter 31 jogos PS2 → CHD ────────────────────────────────┐
│ etapa: apply (14/31) · original preservado até verificação    │
│ ▓▓▓▓▓▓▓░░░░ 46% (12,3 GB de 26,8 GB) · 41 MB/s · ETA 6min     │
│ atual: "Shadow of the Colossus (disc 1).iso"                  │
│ ✓12 concluídos · ⚠1 aviso (espaço apertado) · 17 pendentes    │
│ [Pausar] [Cancelar com segurança]        espaço livre: 38 GB  │
└──────────────────────────────────────────────────────────────┘
```

Wireframes de todas as demais telas seguem estes 6 padrões (card, página de entidade, centro de estado, decisão binária preservadora, erro, job).
