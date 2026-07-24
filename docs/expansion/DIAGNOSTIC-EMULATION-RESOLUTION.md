# Resolução do diagnóstico de emulação de 2026-07-23

O catálogo foi produzido sobre `codex/desktop-ergonomia-d0` (`43ec946`). Ele é
evidência válida daquela branch, mas não descreve integralmente
`codex/expansao-master-steamzero`, que já contém módulos removidos do trunk.

## Diferenças confirmadas na linha consolidada

- scraping possui fontes Python, portas, cache, dispatcher, ScreenScraper e
  SteamGridDB; F1 ainda centralizou todo HTTP em `core.net`;
- scan Switch já classifica `base`, `update` e `dlc` e publica contagens por
  raiz/jogo; falta concluir projeção específica de conteúdo nos emuladores;
- lifecycle local de mods/cheats, stores, ações import/state/remove e UI já
  existe; falta compor busca e instalação pelos catálogos terceiros;
- `nsz.convert` já chega ao plano transacional do
  `SwitchRomConversionService`; falta verificar e completar a jornada UI;
- MediaHub, busca remota em job e ações import/select/clear/publish já existem;
  falta concluir a exposição uniforme em todas as superfícies;
- `game.delete` já produz plano reversível da ROM, mas a cascata de artefatos
  gerenciados ainda não está provada;
- preferências global e por jogo de emulador já são persistidas; o defeito real
  remanescente era não selecionar o valor publicado no QML e não haver fallback
  efetivo por precedência.

## Regra de execução

Cada D-item será fechado dentro do WI de produto correspondente ou por um WI
transversal pequeno quando corrigir uma lacuna já implementada. Nenhum módulo
será reescrito apenas porque está ausente na branch de inspeção.
