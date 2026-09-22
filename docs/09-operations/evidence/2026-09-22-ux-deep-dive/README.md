# Adendo de diagnóstico — jornada UX, first-run, fade, interface e ROMs

## Identidade e método

- Release observada: `2.0.0rc1-504d10b14485`.
- Host: Steam Deck LCD, Wayland, saída XWayland `1280×800` para o Launcher.
- Ações de sistema foram somente leitura, launch, captura e encerramento de
  processos criados durante a validação. Nenhuma ROM foi renomeada, movida,
  extraída, convertida ou sobrescrita.
- Ao final, os processos de teste e as janelas de emuladores foram encerrados;
  não restaram `steamzero-launcher`, `qml6` de teste, Dolphin, DuckStation,
  PCSX2, Citron, Ryujinx ou SharpEmu de teste.

## Bloqueio P0 do Launcher com o acervo real

O entry point instalado foi executado sem `--library`, como o usuário faria:

```text
/usr/local/bin/steamzero-launcher
```

Resultado histórico da release instalada: o processo termina antes de criar a
janela QML. A exceção publicada pelo pacote instalado é:

```text
ValueError: section itens excede 512
```

O cache canônico daquela release continha 1.843 registros, mas esse número não
era uma contagem válida de jogos. A auditoria read-only de
`/home/misael/emulation/roms/psvita/` encontrou cinco ZIPs de jogos na raiz e
uma instalação Vita3K descompactada; os 711 PNGs de manual/live area e os BINs
internos estavam sendo promovidos pelo scanner porque `root-wins` aceitava
qualquer extensão conhecida no registro, mesmo quando o manifesto Vita não a
declarava. O resultado indevido foi Vita=684, com 659 PNGs e 20 BINs entre os
falsos jogos.

Correção local posterior: o scanner manifest-backed só deixa a raiz resolver
extensões declaradas pela própria plataforma e reconhece o formato de diretório
`vita3k-app` quando há `sce_sys/param.sfo` e `eboot.bin`. O mesmo diretório agora
produz seis jogos selecionáveis — cinco ZIPs e a app `PCSF00516` —, 723 arquivos
internos não-jogáveis rejeitados e 82 auxiliares de patch/DLC; os originais não
foram alterados. A identidade e o título são lidos do SFO, não do nome do
arquivo. A correção passou 133 testes focados, mas ainda não está na release
instalada. Portanto o crash
do Launcher permanece uma falha física histórica a recertificar, e não deve ser
tratado como prova de que o Vita possui 684 jogos nem como justificativa para
renomeação/extração automática.

## Launcher com acervo reduzido — jornada de entrada

Para separar o defeito de volume dos defeitos de interação, foi usado o fixture
com três jogos reais do cache:

- SNES: `46 Okunen Monogatari`;
- PlayStation: `Alundra`;
- PlayStation 2: `Black`.

O Launcher abriu em XWayland, criou a janela fullscreen e exibiu o título real,
plataforma e instruções de controle. Evidência: [launcher-home-before.png](./launcher-home-before.png).

Foram tentados, sobre a janela ativa:

| Ação | Resultado | Diagnóstico |
|---|---|---|
| `Return` | nenhuma mudança | não abriu detalhes nem jogo |
| `Enter` | nenhuma mudança | não abriu detalhes nem jogo |
| `Space` | não produziu navegação observável | não comprovado como caminho válido |
| clique no cartão | nenhuma mudança | sinal de ativação não chegou à jornada |
| foco explícito da janela + tecla | nenhuma mudança | não elimina o defeito de integração |

Não nasceu processo de emulador, não apareceu página de detalhes, não apareceu
overlay `preparing/launching`, não houve fade-in, não houve fade-out e não houve
retorno de foco. Isso reproduz a lacuna da reauditoria anterior, agora na
release governada instalada.

## Fade e transições

### O que existe no código

- `LauncherShell.qml` possui `returnFadeActive` somente para o retorno após a
  observação de sessão fechada.
- O fade de retorno usa `180 ms` e uma camada preta com `NumberAnimation`.
- O overlay de `preparing/launching/failed` também usa animação de opacidade de
  `180 ms`, mas não é uma transição dedicada de saída da Home para a janela do
  emulador.
- O `LauncherSessionPeripherals.qml` possui fade baseado no read model de
  periféricos/Bezel, não um fade global de lançamento.

### O que foi fisicamente provado

Nada da sequência de fade do Launcher foi provado no caminho de usuário, porque
a ativação do cartão não acontece. Os testes QML de estado e retorno passam,
mas são provas de contrato/harness, não observação compositor-a-compositor.

Diagnóstico: a aplicação tem uma implementação parcial de fade de retorno e
overlay, mas não há certificação de fade-in de lançamento, fade-out de saída,
tempo percebido, sincronização com o primeiro frame do emulador ou restauração
do foco na tela real.

## First-run e interfaces reais dos emuladores

### DuckStation

Launch físico com display real para `Alundra` retornou `started`, mas abriu:

[duckstation-setup-wizard.png](./duckstation-setup-wizard.png)

O primeiro passo é o **DuckStation Setup Wizard**, com etapas visíveis de:

- idioma e tema;
- BIOS;
- diretórios de jogos;
- configuração de controle;
- gráficos;
- RetroAchievements;
- seleção de interface e visual;
- conclusão.

Consequência: o jogo não começa diretamente. O contrato atual registra apenas
o processo criado; não detecta o wizard nem comunica ao usuário que a execução
está parada em configuração inicial. A tentativa de avançar por injeção X11 não
foi promovida como controle físico confiável no Wayland.

### Dolphin

A janela de jogo real permaneceu aberta após o launch anterior e exibiu:

[dolphin-game.png](./dolphin-game.png)

O conteúdo chegou à tela **WARNING—HEALTH AND SAFETY**, com “Press any button to
continue”. A janela principal também publicou que não encontrou ISOs/WADs na
coleção:

[dolphin-main.png](./dolphin-main.png)

Diagnóstico: o processo pode estar correto e o jogo pode ter sido localizado,
mas a jornada ainda está bloqueada por first-step do emulador. O SteamZero não
detectou nem tratou essa tela intermediária; o resultado `spawn` anterior não
equivale a “jogo pronto para jogar”.

### PCSX2

O PCSX2 standalone abriu a interface real com biblioteca de seis títulos:

[pcsx2-desktop.png](./pcsx2-desktop.png)

Não foi observado wizard de primeira execução nessa configuração já existente.
Porém o launch governado de `Black` apresentou falha de handoff. O processo
Flatpak terminou e o log registrou:

```text
Startup Error: Requested filename
'/home/misael/emulation/roms/ps2/Black (USA) (Translated PtBr).chd' does not exist.
```

O arquivo existe no host e tem aproximadamente `978.9 MiB`; o problema é o
sandbox Flatpak, que remapeia o acesso para `/run/user/1000/doc/...` e não
recebeu uma autorização/caminho materializado para a ROM. Diagnóstico: `started`
não significa que PCSX2 abriu o jogo; a rota precisa traduzir o caminho para o
portal/documento ou conceder o filesystem correto antes de lançar.

### Ryujinx e SharpEmu

As janelas deixadas por launches anteriores também foram observadas:

- [ryujinx.png](./ryujinx.png): biblioteca visível, 32/32 jogos carregados;
- [sharpemu.png](./sharpemu.png): biblioteca vazia, com ação “Open file”.

Esses registros comprovam interface inicial real, mas não comprovam uma partida
interativa nem o comportamento de retorno/fade.

## Auditoria visual da interface SteamZero

A auditoria live da bridge gerou 55 capturas em múltiplas resoluções e
superfícies:

[MANIFEST.json](./ui-audit/MANIFEST.json)

Exemplos:

- [fullhd-emulators.png](./ui-audit/fullhd-emulators.png);
- [emulation-area-overview.png](./ui-audit/emulation-area-overview.png);
- [library-games-grid.png](./ui-audit/library-games-grid.png);
- [studio-themes.png](./ui-audit/studio-themes.png).

O harness terminou com código 0; as 55 imagens têm conteúdo e contexto. A
interface expôs visualmente:

- banner de **Perfil do Desktop desatualizado** em contraste fraco no tema
  escuro;
- área de Emulação com 64 plataformas técnicas, 16 emuladores instalados,
  um ausente e um em atenção;
- Biblioteca com 1.832 jogos projetados e mistura de capas reais e placeholders;
- Temas sem perfil aplicado, espaço de temas em `0 B em 0 arquivos` na captura
  live, e somente a superfície de verificação disponível;
- instruções de rodapé e alguns estados de alerta com baixo contraste no tema
  escuro.

O manifesto marcou 40 warnings como “do QML do SteamZero”, mas a inspeção do
texto mostrou que todos eram do plugin externo Breeze/KDE:

```text
qrc:/qt/qml/org/kde/breeze/ProgressBar.qml
qrc:/qt/qml/org/kde/breeze/TextArea.qml
```

Diagnóstico adicional: o classificador de warnings do próprio auditor está
incorreto para URLs `qrc:/qt/qml/org/kde/...`; ele não deve reprovar o produto
por esses warnings sem antes corrigir a separação entre warnings próprios e
externos. O Qt/Breeze ainda emite warnings reais de terceiros, que devem ser
tratados ou isolados no ambiente visual, mas a contagem “40 do SteamZero” é
falsa.

## Scan, identidade, nomes e arquivos

O scan real da release encontrou:

| Métrica | Resultado |
|---|---:|
| arquivos encontrados | 16.513 |
| jogos catalogados | 1.843 |
| jogos no cache com caminho existente | 1.843 |
| não identificados | 0 |
| erros do scan | 0 |
| incompatíveis | 1.342 |
| ignorados | 13.082 |
| estado `unverified` no cache | 1.827 |
| estado `ready` no cache | 16 |
| formato `unknown` | 700 |
| formato `zip` | 610 |
| formato `7z` | 312 |
| diagnóstico `compressed-format` | 970 |
| diagnóstico `no-reader` | 818 |
| diagnóstico `not-iso9660` | 35 |

O scan é determinístico e não perde o caminho físico, mas ainda promove uma
quantidade grande de entradas para o catálogo sem identidade executável
verificada. O fato de `pathExists=1843/1843` não significa que o emulador consiga
ler o arquivo dentro do sandbox, como demonstrado pelo PCSX2.

### Falso diagnóstico de nomes Vita

O cache da release instalada possui 61 grupos de nomes exatamente duplicados,
totalizando 611 registros. A maior parte aparece como PlayStation Vita, com
arquivos `001`, `002`, `003` até `044`, mas a inspeção do caminho físico mostrou
que eles são PNGs de manual/live area dentro da instalação descompactada do
Vita3K, não jogos Vita independentes.

Diagnóstico corrigido: há dois problemas encadeados. Primeiro, o scanner
promovia arquivos internos por aplicar `root-wins` a extensões não declaradas
no manifesto. Só depois disso a camada de nomeação recebia `001.png` e os
demais nomes de assets e os publicava como títulos. A correção deve começar no
scanner; não se deve tentar “resolver” esses nomes por renomeação em massa.
Após a correção, os arquivos internos ficam fora da lista de jogos e a
duplicidade Vita precisa ser recontada numa nova varredura/release.

### Extração, normalização e renomeação

- Nenhum archive real foi renomeado nesta rodada. Os cinco ZIPs têm os seguintes
  nomes canônicos planejados a partir do SFO: `LittleBigPlanet PlayStation Vita
  [PCSA00017].zip`, `ULTIMATE MARVEL VS. CAPCOM 3 [PCSE00004].zip`, `Dengeki
  Bunko- Fighting Climax [PCSE00639].zip`, `THE KING OF FIGHTERS '97 GLOBAL
  MATCH [PCSE01224].zip` e `Uncharted- Golden Abyss [PCSF00001].zip`.
- A pasta `app/PCSF00516` é um jogo Vita3K válido. O empacotador derivado gera
  um ZIP com o conteúdo na raiz (`sce_sys/`, `eboot.bin`, etc.) em
  `.steamzero/derived/playstation-vita/`, sem alterar a origem; a aplicação
  física desse pacote e o rename transacional ainda dependem da próxima release
  governada.
- Nenhuma ROM foi renomeada no host real.
- As funções de biblioteca, organização, rename window, conversão NSZ,
  classificação, multidisc e variantes de título têm cobertura automatizada.
- A bateria específica executada terminou com **227 testes aprovados em
  261,41 s**, sem alteração no snapshot persistente do host.

Diagnóstico: o contrato transacional está coberto, o scanner Vita e o plano de
empacotamento foram exercitados com a estrutura real, mas o comportamento real
de extração/renomeação ainda não foi certificado com mutação do acervo do usuário.
É necessário um plano explícito com cópia/sandbox, dry-run, preview de nomes,
conflito, rollback e validação do resultado no scanner antes de tocar os 970
archives comprimidos.

### Relação para Gestão de arquivos

O inventário agora publica uma relação genérica de conteúdo, válida para todas
as plataformas que declarem formatos nativos de diretório. Um jogo em pasta tem
seus arquivos e subpastas como `directory-member`; updates/DLCs e itens não
classificados permanecem como `auxiliary-content` da plataforma, sem virar
jogos. A leitura real Vita produziu 713 membros relacionados à app
`app/PCSF00516` e 119 itens auxiliares ainda sem proprietário inequívoco. O
diretório `.steamzero/derived` é excluído do inventário do usuário para que
artefatos gerados não sejam duplicados.

Esse vínculo é a base da operação de gestão: selecionar jogo-base → incluir ou
excluir conteúdo relacionado → mostrar preview → confirmar → verificar e
permitir rollback. A rota governada `library.root.audit` consome esse modelo em
qualquer plataforma, e `library.vita.package` aplica o mesmo ciclo para a app
Vita3K: validação, plano, confirmação, job assíncrono e ZIP derivado atômico.
A aplicação mutável de limpeza/rename/empacotamento no host real ainda não foi
executada nesta release; não há exclusão ou renomeação silenciosa.

## Controle e limitação da observação

O host é Wayland. A janela SteamZero foi executada por XWayland, mas a injeção
de teclado/clique não produziu ativação observável na jornada do Launcher.
`wmctrl`/`xdotool` também não são prova equivalente ao botão físico do Deck.
Portanto:

- o fato de o cartão estar focado visualmente não prova que o controle A/Enter
  chega ao QML;
- a ausência de mudança após tecla/clique é um defeito ou bloqueio de integração
  real que precisa ser resolvido antes da certificação;
- os testes QML de gestos/retorno passam em harness, mas ainda não substituem
  teste com o input provider real do Deck.

## Veredito complementar

O diagnóstico anterior deve ser corrigido nos seguintes pontos:

1. não houve apenas “falta de observação de fade”; a jornada completa está
   bloqueada pelo limite de 512 itens e, no fixture reduzido, pela ativação sem
   efeito;
2. DuckStation e Dolphin possuem first-step visual que impede considerar
   `spawn` como jogo pronto;
3. PCSX2 tem interface funcional standalone, mas o handoff governado falha no
   acesso à ROM no Flatpak;
4. o auditor visual classifica warnings Breeze como warnings próprios;
5. a tratativa de nomes Vita é objetivamente incorreta para 611 registros;
6. extração, renomeação e normalização passaram apenas em contratos/testes
   isolados, não em mutação controlada do acervo real;
7. fade-in, fade-out, gameplay interativo e retorno de foco continuam sem prova
   física.

### Próxima ordem de tratativa

1. Corrigir o catálogo do Launcher para suportar 1.832+ jogos sem exceção.
2. Corrigir a ativação real por input provider/controle e repetir a jornada.
3. Fazer o Launcher detectar first-run/wizard ou entregar um estado explicativo
   ao usuário.
4. Corrigir o handoff Flatpak do PCSX2 e testar novamente com o CHD real.
5. Corrigir a identidade/nome Vita antes de qualquer renomeação em massa.
6. Só então medir fade-in/fade-out, primeiro frame, gameplay, pausa, saves,
   Bezel e retorno por plataforma.
7. Executar um dry-run de extração/normalização com cópia isolada e registrar
   preview, conflitos, rollback e novo scan.

O complemento posterior de mídia, first-run e Theme Studio está em
`../2026-09-22-media-theme-first-run/README.md`, incluindo autenticação real,
busca individual, lote assíncrono, aplicação/otimização, auditoria de
qualidade, matriz de configuração inicial e maturidade do editor/efeitos.
