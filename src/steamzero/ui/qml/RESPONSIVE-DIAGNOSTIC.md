# Diagnóstico responsivo da UI Desktop

Escopo observado antes da refatoração: `Main.qml` e `DarkButton.qml` na branch
`codex/ui-emulacao`. O contrato da bridge foi tratado como somente leitura.

| Tela/componente | Problema | Causa no QML | Resolução afetada | Correção planejada | Risco | Teste |
|---|---|---|---|---|---|---|
| Shell | Deck usa a mesma composição de desktop | breakpoint único por largura e sidebar de 184/228 px | 1280×800 e janelas baixas | tokens por perfil lógico, rail portátil e largura máxima | médio | render 1280×800 e focus smoke |
| Shell | conteúdo se estica sem limite | área principal sempre preenche o `RowLayout` | ultrawide e 4K | container central limitado e centralizado | baixo | render 2560×1080 e 4K |
| Tipografia | tamanhos e margens dispersos | `font.pixelSize`, 28 px e alturas repetidos | todas, sobretudo 125/150% | escala tipográfica e métricas compartilhadas | médio | `qmllint` e screenshots |
| Banner | conflito repete a explicação da sidebar | banner fixo de 72 px e card lateral | todas | alerta expandido/compacto com reconhecimento | baixo | estado com/sem conflito |
| Footer | comandos ultrapassam a largura | linha fixa com cinco labels e gap de 24 px | Deck e janela estreita | footer adaptativo por comandos disponíveis | baixo | 800/1280 px e texto longo |
| Emuladores | filtro vazio mantém seleção e inspector | seleção é validada contra a lista completa | qualquer resolução | seleção validada contra o resultado filtrado e empty state | alto | alternar filtros e refresh |
| Emuladores | linha usa altura 94 px e colunas rígidas | `height`, 180 px e 132 px fixos | Deck, 150% e traduções longas | delegates por `implicitHeight`, reflow e drawer | médio | 0/1/3 itens e título longo |
| Steam | lista/inspector repetem o problema dos emuladores | estrutura duplicada e painel fixo de 292 px | Deck e ultrawide | seleção filtrada, empty state e inspector adaptativo | médio | filtros, refresh e ação indisponível |
| Perfis | canvas pouco orientativo | combo único dentro de card mínimo de 180 px | todas | cards de perfil com recomendado/desejado/aplicado/observado | médio | com/sem perfil aplicado |
| Saves e Sync | três cards vazios dominam a tela | cards sempre visíveis, mesmo com contadores zero | todas | empty state orientativo; resumo apenas com dados | baixo | fila 0 e fila com dados |
| Sistema | checks e ações podem cortar texto | alturas e `elide` fixos | Deck e zoom de texto | cards de altura implícita e wrap | baixo | mensagens curtas/longas |
| Rolagem | navegação desloca pixels, não seções | `ScrollView` sem anchors semânticos | telas longas | navegador por anchors pós-layout e reduced motion | médio | PgUp/PgDown, clique e wheel |
| Carregamento | só há spinner de 22 px na sidebar | `pendingRequests` não possui estado de experiência | toda operação lenta | overlay tardio, indeterminado e acessível | baixo | request curto, lento, erro e timeout |
| Steam externa | não há lifecycle de janela no payload atual | bridge só expõe `/steam/open` allowlisted | Wayland/X11 | manter contexto e fallback visual; coordenação real fica fora do QML | alto | retorno/falha com contrato atual |

## Invariantes

- QML não executa shell, não escreve estado operacional e não cria endpoints.
- Percentual de progresso não é exibido quando o total é desconhecido.
- `recommended`, `desired`, `applied`, `observed`, `degraded` e `unverified`
  permanecem distintos; campo ausente é apresentado como não verificado.
- Toda mutação continua passando por plano, `confirmToken` e bridge allowlisted.
