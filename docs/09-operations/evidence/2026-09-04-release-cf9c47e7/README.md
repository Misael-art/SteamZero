# Validação física da release 2.0.0rc1-cf9c47e7b55b — 2026-09-04

Host Valve Jupiter (`misael-jupiter`), KDE/Wayland. Release instalada pelo fluxo
governado a partir do run de CI verde `33898677854` no commit
`cf9c47e7b55b0cea680c00578736c4475185361a` (`main`).

Rollback disponível: `2.0.0rc1-a44f52964b3e`.

`doctor`: `runtime.provenance` e `service.generation` na release ativa; dois
warns já conhecidos (`staging.orphan`, `boot.direct` sem permissão de inspeção).

## Método

Toda injeção seguiu a regra da sessão: janela resolvida **por PID**, foco
conferido **antes e depois**, e reativação após cada captura porque o
`spectacle` rouba o foco. Onde a tecla produziu movimento, o próprio movimento
é o controle positivo — ele prova, de uma vez, que o canal estava vivo e que a
janela certa recebeu.

## Provado

### Foco de teclado inicial do Launcher

A primeira tecla depois de abrir navega, **sem nenhum clique de mouse**.

| Observação | Resultado |
|---|---|
| Janela do Launcher | `{6fac0330…}`, `getwindowpid` = 517655 |
| Foco antes e depois da injeção | 517655 nas duas medições |
| Seta direita (primeira interação) | **9.012 pixels** mudaram |
| Anel de foco | cartão 1 → cartão 2 (`'89 Dennou` → `Aladdin`) |

Antes da correção, a mesma medição dava zero. `01-abertura-sem-mouse.png` e
`02-apos-primeira-seta.png`.

### Cena `qml6` não fica órfã

Visível antes mesmo do encerramento: o filho nasce em **grupo próprio**
(`pgid 517655`, não o `517638` do wrapper). Após `kill -TERM` no wrapper, o
`qml6` morreu junto e **nenhuma janela `SteamZero` restou**.
`03-apos-encerrar-sem-orfa.png`.

## Achado novo: Enter não ativa o botão de menu da central

Medido com o canal provado vivo e o foco no botão, o que a auditoria anterior
não tinha:

| Gesto no botão de menu focado | Pixels |
|---|---|
| `Enter` | **0** |
| `Space` | **913.959** (o menu abre) |
| `Tab` (controle positivo) | 5.193 |

O mesmo botão responde a um gesto e ignora o outro. `05-menu-abre-com-space.png`
mostra o menu aberto por Space. O clique de mouse também não produziu efeito
mensurável nesta janela, o que fica como observação separada e não confirmada.

## NÃO provado: os ícones oficiais aparecendo na tela

O empacotamento está correto e verificado na release instalada:

- os **41 assets** estão em `site-packages/steamzero/ui/assets/`;
- `../assets/pcsx2.png` resolve a partir de `qml/Emulation.qml`.

Mas na tela de Emulação, nas linhas de PCSX2 e Vita3K — **ambos com logo oficial
empacotado, e PCSX2 em PNG, portanto sem depender do plugin SVG** — nenhum
logotipo aparece. `06-emulacao-linhas-sem-icone-visivel.png`.

Não afirmo que os ícones estão quebrados: pode ser recorte de layout, a posição
de rolagem capturada, ou o modelo desta view não carregar `iconAsset`. Afirmo o
que medi: **não observei os ícones renderizando**, e a causa segue em aberto.

Vale registrar um contrato aparentemente violado, encontrado na leitura:
`Main.qml:44` declara que "caminho vindo de manifesto é dado externo e nunca vai
direto para `Image.source`", e existe `assetSource()` para resolvê-lo pela
allowlist — mas essa função **não é chamada em lugar nenhum**, e
`Emulation.qml:3471` usa `modelData.iconAsset` diretamente como `Image.source`.

## Capturas

| Arquivo | Conteúdo |
|---|---|
| `01-abertura-sem-mouse.png` | Launcher recém-aberto, anel no primeiro cartão |
| `02-apos-primeira-seta.png` | após a primeira seta: anel no segundo cartão |
| `03-apos-encerrar-sem-orfa.png` | após encerrar o wrapper: nenhuma janela restante |
| `04-central-visao-geral.png` | central na release instalada, 1134 títulos |
| `05-menu-abre-com-space.png` | menu aberto por Space (Enter não abriu) |
| `06-emulacao-linhas-sem-icone-visivel.png` | PCSX2 e Vita3K sem logotipo visível |

## Fronteira

Continua não provado o ciclo `selecionar → jogar → sair → voltar ao mesmo
cartão`, que é a próxima etapa do Launcher. A divergência de contagem entre a
central (1.134) e o Launcher (1.119) permanece aberta e visível nas capturas.
