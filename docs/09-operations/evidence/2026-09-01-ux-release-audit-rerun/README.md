# Reauditoria UX da release ativa — 2026-09-01

## Escopo e limite

Reexecução somente leitura, sem instalação, rollback, `theme apply`, `emulation launch`, alteração de preferência, varredura, download ou mutação da sessão. O objetivo foi validar o caminho que o usuário pediu: abrir pelo Launcher, ativar um jogo real, observar entrada/saída e revisar as superfícies de temas e Theme Studio.

Release observada: `2.0.0rc1-145cf9d44738` (`145cf9d44738b4ceb50a591355149137575b4ecb`). O daemon estava convergido nessa release. O teste terminou sem processos SteamZero de UI, Launcher, QML ou emuladores abertos.

## Resultado executivo

O P0 de exibição do catálogo melhorou: o Launcher abre com nomes reais, incluindo `1969 (Homebrew) (SMS)`, e não com hashes. O catálogo canônico também mantém 231 jogos distribuídos em 13 plataformas com estado `ready` no workspace.

O fluxo de produto ainda não está certificável: no Launcher real, com foco em uma ROM `.sms`, `Return`, clique e as teclas de navegação testadas não ativam o cartão. A tela não muda, o hash das capturas antes/depois é idêntico e nenhum processo de emulador nasce. Portanto fade-in, lançamento de jogo, fade-out, retorno ao mesmo foco e restauração do estado do host permanecem não provados — e a falha atual é anterior a todos esses pontos.

Na central desktop, a auditoria live terminou com 55 capturas e QML return code 0. A Biblioteca mostra capas reais em alguns títulos e placeholders em outros; o Theme Studio aparece e declara ações de visualização/duplicação, mas os textos de ação truncam. O banner de perfil desatualizado e o rodapé de dicas de controle continuam com contraste insuficiente no tema visual observado. O menu lateral mostra Emulação desabilitada; a tentativa de abrir Temas pelo item visível não mudou a tela na instância manual.

## Evidências

- `launcher/01-home.png`: Launcher real, ROMs `.sms` visíveis e foco inicial.
- `launcher/02-before-activation.png` e `launcher/03-after-return-click.png`: antes/depois do Return e clique; imagens com o mesmo SHA-256, sem transição ou navegação.
- `central-live/MANIFEST.json`: 55 capturas live, origem `bridge-live`, viewport 1280×800, QML return code 0.
- `central-live/fullhd-overview.png`: home e banner de perfil.
- `central-live/library-games-grid.png`: Biblioteca, mistura de capas e placeholders.
- `central-live/studio-themes.png`: Temas/Theme Studio, ações e truncamentos.
- `central-live/emulation-area-media.png`: área de mídia, varredura e estado visível.
- `05-central-drawer.png` e `06-central-themes-click-noop.png`: navegação manual do drawer.

## Encaminhamento

1. Corrigir e provar a ativação do cartão na release instalada por Return/Enter/controle/clique acessível.
2. Reexecutar com uma ROM real por cada plataforma que tenha jogo canônico, sempre via Launcher, registrando emulador, janela, tempo de abertura, jogo, encerramento e retorno.
3. Só então avaliar fade-in/fade-out, foco restaurado, backdrop, controle, saves e estado pós-jogo.
4. Separar a cobertura dos arquivos físicos: 8.016 arquivos não equivalem aos 231 jogos publicados; ZIP/7Z continuam fora ou parcialmente classificados e não devem ser lançados por bypass.
5. Corrigir o contraste e o truncamento das ações do Theme Studio e esclarecer a semântica de planejar o tema já ativo.
