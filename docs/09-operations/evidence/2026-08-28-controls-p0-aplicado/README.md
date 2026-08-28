# P0 — autoconfig do Deck aplicado na release instalada (2026-08-28)

Item: `SZ-CONTROLS-INPUT-PROFILES`. Release ativa durante toda a prova:
`2.0.0rc1-3b296a949316` (as correções de drift/erros já estão em `main`,
mas AINDA NÃO nesta release — o que foi provado aqui é o código instalado).

## O que foi executado

O operador instruiu a sequência da central (dois cliques no cartão de
controles). O ambiente do agente não tem injeção de entrada gráfica confiável
(ydotool/kdotool: clique absoluto não atravessa a aceleração do ponteiro do
KWin; foco por teclado é inconsistente na grade). O apply foi então executado
pelas **duas chamadas exatas por trás dos dois cliques**, no processo, com o
python DA RELEASE INSTALADA, contra o estado real — `plan_emulation_action` +
`apply_emulation_action` do bridge da própria central:

- plano `01M142BPD7XVNCER4A39A1SJGF`, apply `status: ok`,
  operação `01M142BPHEG4EANPKX2SMZ4G6W`;
- estado do cartão: `pending-write` → **`applied`**; o botão
  "Aplicar perfil no RetroArch" deixou de ser oferecido (regra G45: não
  oferecer confirmação que não muda nada).

## Provas no disco (todas na release instalada)

1. `~/.config/steamzero/retroarch/autoconfig/udev/steamzero.cfg` criado —
   580 bytes, 16 bindings, dispositivo identificado
   (`input_device = "Steam Deck"`, vendor 10462). Cópia em
   `03-steamzero-autoconfig-gerado.cfg`.
2. Marcador de ownership na primeira linha: `# SteamZero-Managed: true`.
3. Recusa de arquivo de terceiro: `_probe_target` sobre arquivo sem marcador
   → `no-marker` ("o arquivo não tem o marcador do SteamZero"); o arquivo
   gerido passa limpo.
4. `retroarch.cfg` do usuário **intocado**: sha256
   `a9945f5a4e6176ff5e2d9bc88b113355e1547f0650ba1104d74bbdf15e879393`,
   idêntico ao baseline antes e depois.
5. `launch_arguments()` deixa de ser tupla vazia:
   `('--appendconfig', '/home/misael/.config/steamzero/retroarch/steamzero.cfg')`
   — o overlay com `joypad_autoconfig_dir` apontado para a árvore nossa e
   `config_save_on_exit = "false"`.
6. Idempotência: replan após apply recusado com
   `E-TX-STALE-PLAN: Perfil aplicado` (causa honesta no detail).
7. Rollback disponível e NÃO acionado: `operations rollback-apply` da
   operação acima; reverter destruiria a evidência sem pedido.

## Capturas

- `01-central-home-release-instalada.png` — central aberta pela release
  instalada (Visão geral, 95 títulos, navegação A/B de gamepad ativa na
  barra inferior).
- `02-biblioteca-switch-acervo-real.png` — Biblioteca → Nintendo Switch
  (15 jogos, acervo real; Demon Slayer Kimetsu no Yaiba 2 é o alvo do
  perfil aplicado).
- **Não há captura do cartão de controles em verde**: a navegação sintética
  até a página do jogo provou-se não confiável (foco inconsistente na grade),
  e captura decorativa é proibida. O cartão mostra o estado `aplicado` com o
  botão sumido; a verificação visual final é do operador — Emulação → jogo →
  cartão de controles (o pad já responde: A seleciona, B volta).

## Pendente para fechar o item

- Verificação visual do cartão pelo operador (rota acima).
- "Chegada do perfil ao lançamento real": abrir um jogo da plataforma e
  confirmar o autoconfig ativo no RetroArch (`--appendconfig` no argv do
  `flatpak run`), com o `retroarch.cfg` saindo byte a byte idêntico.
