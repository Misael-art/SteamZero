# INFORMATION-ARCHITECTURE

## Mapa do Game Mode UI

```
Dashboard (home)
├── Continuar jogando (últimos jogos, estado pronto/problema)
├── Biblioteca
│   ├── por plataforma / recentes / favoritos / busca
│   └── Página do jogo (ver GAME-MODE-UI §Página do jogo)
├── Saves
│   ├── pendências de sync / conflitos
│   └── linha do tempo por jogo
├── Emuladores & Ferramentas (componentes)
│   └── detalhe: versão, canal, verify, reparar, atualizar (plano)
├── BIOS & Firmware (Centro — cartões por plataforma)
├── Armazenamento (volumes por UUID, espaço, microSD, migrações)
├── Jobs (em execução / histórico)
├── Perfis (desempenho / controles / display, por escopo)
├── Diagnóstico (doctor, problemas críticos, suporte)
└── Configurações (escala/acessibilidade, rede/offline, canais, avançado)
```

## Mapa do Desktop Mode UI

Mesmos domínios + áreas exclusivas: operações em lote (multi-seleção), importações/migrações (EmuDeck/RetroDECK adoption), visualizador de logs/journal, editor de presets com diff, administração de armazenamento, export/import de estado, schemas.

## QAM (opcional, contexto do jogo em execução)

Save rápido (checkpoint) · restore rápido · perfil de desempenho · status de sync · controle/áudio/tela · diagnóstico contextual. Sem lógica crítica (só chama a API).

## Regras de arquitetura de informação

1. Uma entidade = uma URL/rota interna estável (deep-link entre telas: erro em Dashboard → página do problema).
2. Hierarquia máx. 3 níveis no Game Mode; ações mais frequentes a ≤2 cliques do Dashboard.
3. Toda lista longa: busca + filtro por estado (problema/pronto) + ordenação estável.
4. Símbolos de estado unificados (mesma iconografia de `ready/degraded/missing/blocked` em todas as telas) — não depender só de cor (ACCESSIBILITY).
