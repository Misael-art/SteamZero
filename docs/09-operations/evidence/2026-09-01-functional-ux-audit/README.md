# Parecer atualizado de produto — auditoria funcional e UX

Data: 2026-09-01. Release observada: `2.0.0rc1-8733353c1ad9`.

## Veredito

O reparo recente superou o bloqueio da home: a Central instalada exibe títulos
reais e o AURA Launcher abre em fullscreen com o catálogo atual. A experiência
visual tem uma base lógica e uma linguagem coerente, mas ainda não está pronta
para aceite de cliente porque o lançamento de jogos está roteando ROMs de
Dreamcast, Game Boy e Wii U para `platformId=switch`/`emulatorId=eden`.

Esse defeito é P0: a tela pode parecer pronta, mas o primeiro “Jogar” pode
abrir o executor errado. A validação “um jogo por emulador” ficou bloqueada
por esse contrato, não por falta de jogos na biblioteca.

## O que foi realmente exercitado

- Serviço, doctor, sessão gráfica, tema ativo, coleções, playtime, jobs e
  frontends foram observados read-only.
- O runner live produziu 55 capturas, QML terminou com retorno 0 e a origem
  foi `bridge-live`; a nova MANIFEST está em `central-live-873/`.
- A Central física instalada foi aberta e capturada em `01-central-active-8733353c.png`.
- O Launcher AURA real foi aberto em fullscreen e capturado em
  `05-launcher-real-8733353c.png`. A navegação por setas e a tecla `F` não
  produziram mudança observável; a tentativa de busca está registrada em
  `08-launcher-search-8733353c.png`.
- 15 executores standalone iniciaram; 17 cores Libretro recusaram abertura
  própria com a explicação correta de que dependem do RetroArch.
- 13 amostras de plataformas foram lançadas pela rota de jogos, mas nenhuma
  foi aprovada como jogo jogado no emulador correto; consulte
  `game-launch-summary.txt`.
- A matriz publicada de ações foi executada por inventário: 61 locais, 4
  roteadas e 2 bloqueadas com motivo. Ela cobre apenas 1 de 17 superfícies.

## Notas de experiência e visual

O fullscreen do Launcher é limpo, legível e tem foco ciano inequívoco. O uso
de iniciais quando não há capa é honesto e evita cartões “quebrados”. A hierarquia
Início → plataformas → jogos é compreensível e o layout responde a Deck,
handheld, Full HD e ultrawide.

Ainda há fricções importantes: ausência de affordance visível para busca, foco
por teclado/controle não demonstrado na janela real, nomes longos truncados,
cartões sem arte misturados a espaços vazios, rodapé de dicas com contraste
baixo e conteúdo cortado no viewport handheld sem indicação clara de
continuação. O banner de perfil não aplicado ocupa atenção excessiva.

No Theme Studio, as quatro opções de tema aparecem e “Aplicar / Ver / Duplicar
e editar” tornam a intenção compreensível, mas a superfície observada se
comporta mais como inspector do que como autoria completa: não foi demonstrada
edição, undo/redo ou publicação.

O tema ativo do runtime é `org.steamzero.asset-recipes-demo`, não AURA. Portanto
o fullscreen do Launcher foi provado, mas a certificação de AURA aplicado em
runtime não foi feita nesta rodada para não alterar estado persistente.

## Big Picture, frontends e capas

Big Picture/Steam não foi validado como jornada completa: SRM e ES-DE aparecem
como ausentes, não há atalho publicado verificável, e não foram provados
controle físico, busca, launch e retorno. A aplicação tem boa intenção de
“console-first”, mas ainda falta o circuito sofá completo.

A mídia tem providers e receitas declarativas bem modelados. Na prática,
há placeholders e o histórico de ScreenScraper mostra quota excedida. A
interface oferece planejamento de mídia, mas não há comando CLI simples nem
credencial disponível para comprovar um download novo e sua aplicação na
grade; o resultado ficou não certificado.

## Prioridades

1. Corrigir a identidade única do jogo do scan ao launch, incluindo
   `platformId`, `emulatorId`, caminho e `session status`; impedir launch se
   houver divergência.
2. Repetir a matriz com um jogo por plataforma/emulador e verificar janela,
   input, áudio, encerramento e retorno ao mesmo foco.
3. Corrigir a entrada de busca do Launcher e tornar a affordance visível;
   cobrir navegação real por teclado/controle.
4. Expor mídia como fluxo de cliente: provider, credencial, plano, quota,
   progresso, retry e confirmação de capa aplicada.
5. Publicar Big Picture somente depois de SRM/ES-DE, atalho, launch e retorno
   passarem no hardware real.
6. Depois dos bloqueios, polir contraste, scroll handheld, placeholders e
   autoria real do Theme Studio.

## Comparação de mercado

Em relação ao Steam Deck/Big Picture, Playnite, LaunchBox e ES-DE, o SteamZero
tem boa honestidade operacional, separação entre plano e aplicação e uma base
visual própria. Fica atrás na resiliência do catálogo, busca imediata, arte
previsível e confiança do “Jogar”. O próximo investimento deve ser a cadeia
de identidade/execução; polimento visual não compensa um emulador incorreto.

## Limitações e ações do operador

Não houve instalação, publicação, rollback, push ou troca de tema. A inspeção
de boot direto continua dependente de permissão do operador. O teste final de
boot físico e a certificação de controles reais ainda exigem operador/hardware.
