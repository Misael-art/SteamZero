# Parecer completo de UX e produto — release instalada

Data: 2026-09-01. Release observada: `2.0.0rc1-667789588f23`.

## Veredito executivo

O produto está visualmente mais coerente e a nova correção de roteamento foi
positiva: a plataforma não é mais aceita silenciosamente como Switch/Eden
quando não possui perfil. Porém, a experiência ainda não está pronta para
cliente final. Apenas Switch possui launch aceito; o ciclo de sessão não fecha
porque o mesmo ID hexadecimal aceito no launch é recusado por `session recover`.

Minha nota global é **5/10**: a casca é clara, moderna e honesta em vários
estados, mas o botão central do produto — jogar e voltar sem deixar lixo de
estado — ainda não é confiável.

## Notas por área

| Área | Nota | Parecer de experiência |
|---|---:|---|
| Central/AURA UI | 7/10 | Boa hierarquia, cabeçalho consistente, navegação por áreas e status de prontidão visível. O banner “Perfil do Desktop desatualizado” tem contraste muito baixo e domina a tela. |
| AURA Launcher | 6/10 | Fullscreen, foco ciano e agrupamento por plataforma são compreensíveis. A busca por `F` não respondeu, não há affordance forte de busca e não há prova de página/retorno. |
| Emulação/launch | 3/10 | 15 executores abrem como programas; apenas Switch aceita jogo. Os demais perfis faltam e o lifecycle deixa sessão running. |
| Biblioteca/ROMs | 6/10 | 231 ROMs são identificadas em 13 plataformas e os nomes aparecem corretamente. A grade mistura arte, placeholders e espaços vazios sem explicar disponibilidade. |
| Mídia/capas | 4/10 | Providers e varredura são visíveis, mas quota, zero atualizações e ausência de candidatos tornam o resultado imprevisível. |
| Temas/configuração | 6/10 | Quatro temas instalados, ações bem rotuladas e receitas declarativas coerentes. Troca tema a tema e aplicação real não foram certificadas. |
| Theme Studio | 4/10 | Parece um bom inspector/preview, mas ainda não transmite ferramenta de autoria completa: canvas editável, undo/redo e timeline não foram demonstrados. |
| Big Picture | 2/10 | Não foi provado atalho Steam, retorno ao Big Picture, controle físico ou jornada de sofá. SRM/ES-DE estão ausentes. |
| Acessibilidade | 5/10 | Foco existe e alvos são amplos; rodapé, estados muted e banner de alerta têm contraste insuficiente. Movimento reduzido/alto contraste foram apenas observados por contrato, não validados tema a tema. |
| Fluidez percebida | 6/10 | Runner concluiu 55 estados com QML 0 e o catálogo carrega; a percepção cai quando ações não respondem e o retorno deixa sessão órfã. |

## Achados P0

1. **Lifecycle inconsistente:** `emulation launch` aceita o ID hexadecimal real
   do Switch; `session recover` rejeita o mesmo ID como inválido. O usuário
   pode fechar a janela e continuar vendo “Em andamento”, sem recuperação.
2. **Cobertura de launch incompleta:** 12 das 13 plataformas com ROM foram
   recusadas porque não possuem perfil de launch para Eden. A recusa é melhor
   que iniciar o emulador errado, mas o produto não entrega a biblioteca
   anunciada.
3. **Big Picture não entregável:** sem frontend/atalho verificável não há
   caminho de sofá completo para iniciar, jogar e retornar.

## Dores P1/P2

- `F` não abriu a busca no Launcher real; o usuário não descobre facilmente
  como pesquisar.
- “Favoritos” mostra zero enquanto há favoritos persistidos no estado; isso
  destrói confiança na organização da biblioteca.
- O alerta marrom de perfil desatualizado usa texto/ações com contraste fraco.
- Rodapé “STEAM MENU / A SELECIONAR / B VOLTAR” é quase ilegível em fundo escuro.
- Em handheld, conteúdo inferior fica cortado sem indicação clara de scroll.
- “Ver (somente lei...)” e nomes longos truncam decisões importantes.
- A tela de mídia explica o domínio, mas não mostra de forma suficiente
  provider selecionado, quota restante, retry e resultado de cada capa.
- A matriz de todos os botões não pode ser considerada concluída: cobertura
  1/17 e o inventário de controles termina por timeout.

## O que está bom

O sistema tem uma linguagem visual consistente: azul/teal para ação e foco,
cartões amplos, cabeçalhos previsíveis e estados de prontidão destacados.
O placeholder por inicial é honesto; é preferível a uma imagem quebrada. A
correção nova de rota também melhora a experiência porque transforma uma falsa
execução em erro explicável. O runner live prova adaptação a Deck, Full HD,
ultrawide e handheld, e os componentes Libretro explicam corretamente por que
não abrem sozinhos.

## Temas e interpretação das ações

As quatro opções são fáceis de localizar. “Aplicar”, “Ver (somente leitura)” e
“Duplicar e editar” formam uma boa separação conceitual entre consumo e autoria.
O problema é a distância entre promessa e affordance: “Duplicar e editar” sugere
um editor completo, enquanto o comportamento visível ainda se aproxima de
inspector. Para um designer de console, faltam preview de estados de foco,
transições, densidade de capa e confirmação de preservação do contexto ao trocar
tema.

O tema ativo é `asset-recipes-demo`; portanto não é correto dizer que o AURA UI
ativo foi validado como o tema AURA. AURA foi listada e planejada, mas não
aplicada nesta auditoria observacional.

## Comparativo de mercado

| Referência | SteamZero está… | Motivo |
|---|---|---|
| Steam Deck / Big Picture | Atrás | Falta jornada de sofá comprovada, busca robusta, launch/return e atalho integrado. |
| Playnite | Atrás | Menor previsibilidade de metadata/artwork e menor cobertura de integrações funcionais. |
| LaunchBox/BigBox | Atrás | Menos maturidade de browse, artwork e fluxo contínuo de jogo. |
| ES-DE | Atrás na entrega atual | A linguagem console-first existe, mas ES-DE oferece uma jornada de frontend mais direta; SRM/ES-DE nem estão presentes no host. |
| Diagnóstico operacional | À frente em potencial | Erros são mais explícitos e planos/rollback são mais honestos, mas isso ainda não substitui a execução end-to-end. |

## Recomendação

A próxima onda deve ser “confiança no Jogar”: uma identidade canônica única do
scan ao launch, perfis corretos por plataforma, `session status/recover` aceitando
os mesmos IDs, fechamento que limpa a sessão e retorno ao mesmo cartão/foco.
Depois disso, completar busca e Big Picture. Só então vale investir em mais
efeitos, polimento de capas ou edição visual avançada.

## Evidência e limites

As 55 capturas estão em `central-live/`; as capturas principais são
`01-launcher-fullscreen.png` e `02-launcher-search.png`. Foram encerrados os
processos e janelas de emuladores iniciados pela equipe. Permaneceu apenas uma
sessão lógica Switch marcada como running, porque a própria API recusou a
recuperação do ID real. Não houve instalação, publicação, rollback, troca de
tema, alteração manual do host ou push.

A suíte focada desta árvore passou com 253 testes; os gates estáticos também
passaram. A suíte integral foi tentada uma vez e expirou em 180 s, no marco de
17%, sem resultado final — isso permanece uma pendência de validação, não uma
aprovação implícita.
