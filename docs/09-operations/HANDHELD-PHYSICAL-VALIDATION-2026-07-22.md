# Validação física handheld — 2026-07-22

Status: **parcial; P7 não concluído**.

Este registro separa fatos observados no hardware de interações que exigem um
operador humano. Nenhuma ação sintética é contabilizada como teste de toque,
controle ou teclado virtual.

## Ambiente observado

| Fato | Evidência observada |
| --- | --- |
| Hardware | Valve Jupiter (Steam Deck LCD), GPU AMD VanGogh/amdgpu |
| Sessão | KDE Plasma/KWin 6.6.6, Wayland, Qt 6.11.1, composição OpenGL |
| Painel interno | `eDP-1`, modo físico 800×1280, rotação para 1280×800, escala 1,35, geometria lógica 949×593 |
| Dock | `DP-1` conectado, 2560×1080 a 74,99 Hz, escala 1 |
| Entrada detectada | duas interfaces `Valve Software Steam Deck Controller`, `Steam Deck` e sensores de movimento |
| Fonte executada | commit `58d3bae`, diretamente do worktree; nenhuma release foi construída ou instalada |
| Privacidade | execução com `HOME` e XDG temporários e vazios; as capturas não contêm biblioteca, conta, paths ou nomes do operador |

## Capturas sanitizadas

| Cenário | Resultado visual | Arquivo | SHA-256 |
| --- | --- | --- | --- |
| Painel interno 1280×800 | layout compacto, cabeçalho, escopos, CTA e rodapé visíveis; nenhuma cobertura inferior observada na tela inicial de Emulação Global | `evidence/2026-07-22-handheld-p7/internal-1280x800.png` | `6d10df216da9a5a86a5dcfa2abdef3fed5fba88a292cdb59a4c1a75b610381f9` |
| Painel interno — reteste de contraste | CTA primário compacto renderizado com texto claro após substituir o controle genérico pelo `DarkButton` do projeto | `evidence/2026-07-22-handheld-p7/internal-1280x800-contrast-retest.png` | `8ac933a5a00bff754312d4c5080611ca6441d7b62dcbccc3098d815bb6795462` |
| Dock 2560×1080 | sidebar, conteúdo central, contexto lateral e rodapé visíveis sem sobreposição na tela inicial de Emulação Global | `evidence/2026-07-22-handheld-p7/dock-2560x1080.png` | `e3a260aa80d69a167455d99ab3cd6605985f302959e6faf14869017379672f50` |

As capturas são do compositor físico. A janela foi movida entre outputs por
atalho allowlisted do KWin; isso valida apenas renderização nos outputs, não
entrada física.

## Continuação em 2026-07-23

A execução maximizada no painel físico revelou texto escuro no CTA primário
compacto, embora o botão estivesse habilitado. A causa era o uso direto de
`Button`, que não garantia o `contentItem` claro neste compositor/paleta. O CTA
passou a usar `DarkButton`; um check QML fixa a cor do conteúdo habilitado e a
captura de reteste confirma o resultado em 1280×800.

Depois da correção passaram: 1179 testes no ambiente padrão, 1179 com
`XDG_RUNTIME_DIR` extenso, Ruff, mypy (136 arquivos), independence, boundaries,
`qmllint` e `git diff --check`. Um fixture isolado com ROM, save e shader
sintéticos foi preparado para permitir que o operador percorra também Por jogo,
drawer, Saves e Shader cache sem acessar conteúdo real.

## Checklist de interação física

| Item | Esperado | Resultado |
| --- | --- | --- |
| Toque | alvos acionáveis, scroll e drawers respondem sem toque deslocado | **não executado — requer operador** |
| D-pad | foco previsível em todos os controles e áreas | **não executado — requer operador** |
| Analógicos | navegação/rolagem sem perda de foco | **não executado — requer operador** |
| A/B/X/Y | selecionar, voltar e ação contextual coerentes com o rodapé | **não executado — requer operador** |
| Teclado virtual | abre, não cobre campo ativo e restaura foco | **não executado — requer operador** |
| Foco e retorno de drawers | foco entra no drawer e retorna ao controle de origem | **não executado — requer operador** |
| Rolagem automática | foco sempre traz o controle para a viewport | **não executado — requer operador** |
| Legibilidade | texto e estados legíveis na distância real de uso | **não executado — requer avaliação humana** |
| Áreas inferiores | nenhuma ação fica coberta pelo rodapé | **aprovado apenas na tela inicial capturada; restante não executado** |
| Movimento reduzido | transições ficam instantâneas e sem perda de contexto | **não executado — requer operador** |
| Portátil | fluxo completo no painel interno | **apenas renderização inicial observada** |
| Dock | fluxo completo no monitor externo | **apenas renderização inicial observada** |

## Cobertura das telas exigidas

| Tela/fluxo | Resultado desta sessão |
| --- | --- |
| Visão geral | não percorrida fisicamente |
| Emulação Global | renderização inicial observada em portátil e dock; interação não testada |
| Todas as áreas de Emulação | não percorridas fisicamente |
| Emulador | não percorrido fisicamente |
| Por jogo e drawer completo | não percorrido fisicamente |
| Portátil | renderização inicial observada; interação não testada |
| Dock | renderização inicial observada; interação não testada |
| Steam | não percorrida fisicamente |
| Perfis | não percorrida fisicamente |
| Estado da sincronização | não percorrida fisicamente |
| Sistema | não percorrida fisicamente |
| Credenciais e scraping | não percorridas fisicamente |
| Central de tarefas | não percorrida fisicamente |

## Bloqueio e próximo passo

P7 só pode ser encerrado depois de um operador percorrer a matriz acima no
Deck, registrar aprovado/reprovado por linha e fornecer evidência sanitizada
dos problemas encontrados. Qualquer reprovação deve gerar correção e repetição
do cenário físico. Até isso ocorrer, release, wheel, wheelhouse e instalação
permanecem bloqueados.
