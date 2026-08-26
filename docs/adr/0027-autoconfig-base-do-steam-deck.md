# ADR-0027 — Autoconfig-base próprio para pads que o RetroArch não empacota

**Status:** aceito

## Contexto

O item `SZ-CONTROLS-INPUT-PROFILES` traduz o perfil de controle do usuário para o
formato de autoconfig do RetroArch. A tradução exige um **perfil-base** que
descreva o pad físico: sem ele não há como saber qual índice de botão corresponde
a qual entrada do RetroPad. `AutoconfigCatalog` obtém esse perfil-base do catálogo
que o RetroArch empacota.

Medido no host em 2026-08-26 (Steam Deck LCD, RetroArch 1.22.2, evidência em
`docs/09-operations/evidence/2026-08-13-retroarch-autoconfig/`, seções 6 e 7):

- o catálogo tem 420 perfis `udev` e inclui `Steam_Controller.cfg` (`10462/1142`)
  e `Wireless Steam Controller.cfg` (`10462/4418`);
- o controle **interno do Steam Deck** é `10462/4613`, e nenhum perfil do catálogo
  declara esse `input_product_id`;
- o próprio RetroArch confirma: `[Autoconf] Steam Deck (10462/4613) não
  configurado.`

Consequência: no hardware que este projeto tem como alvo primário, o writer parava
em `awaiting-device` e nenhum perfil de controle chegava ao emulador. O estado era
verdadeiro — não havia base para traduzir — mas a capacidade ficava inalcançável.

## Decisão

O SteamZero passa a **empacotar autoconfigs-base próprios** para pads
comprovadamente ausentes do catálogo de terceiro, começando pelo Steam Deck.

1. Os arquivos vivem em `src/steamzero/autoconfig/<driver>/` e viajam no wheel.
2. `bundled_autoconfig_directories()` acrescenta esse diretório **depois** do
   catálogo do RetroArch, nunca no lugar dele.
3. Um pad só entra se o catálogo de terceiro não o cobrir. Se os dois
   descreverem o mesmo pad de formas diferentes, `AutoconfigCatalog.match`
   devolve `ambiguous-autoconfig` e nada é gravado — a ambiguidade permanece
   visível em vez de ser resolvida por precedência silenciosa.
4. O arquivo empacotado **não** carrega `MANAGED_MARKER`: ele é dado de origem,
   equivalente ao de terceiro, e não um artefato gerenciado gravado no host.

### Como os índices são obtidos

Os índices não são copiados de documentação nem inferidos de outro pad. São
medidos no dispositivo real e verificados por duas fontes independentes:

- `ioctl` do joydev em `/dev/input/js0` (`JSIOCGBTNMAP`, `JSIOCGAXMAP`);
- varredura ascendente do bitmap de teclas do próprio dispositivo em
  `/sys/class/input/event7/device/capabilities/key`, a partir de `BTN_MISC`.

As duas produzem listas **idênticas** (24 códigos), o que mostra que a numeração
é propriedade do bitmap do dispositivo e não de um driver específico. Qualquer
driver que enumere ascendentemente a partir de `BTN_MISC` — convenção do joydev e
do driver `udev` do RetroArch — chega aos mesmos índices.

## Alternativas rejeitadas

**Casamento sem `product_id` exato, caindo para um perfil genérico compatível.**
Rejeitada: o `Steam_Controller.cfg` do mesmo vendor tem layout diferente
(`input_b_btn = "0"`, sem os códigos `0x121`/`0x122`/`0x126` que o Deck expõe nos
índices 0–2). Aceitar casamento aproximado gravaria um arquivo que o RetroArch
lê e que mapeia os botões errados — o falso verde que a §8 do AGENTS.md existe
para impedir.

**Declarar o Steam Deck não-suportado para autoconfig gerenciado.** Rejeitada: o
Deck é o alvo primário do projeto, e a lacuna é do pacote de terceiro, não do
hardware. Desistir aqui esvaziaria a capacidade justamente onde ela mais importa.

**Editar o `retroarch.cfg` do usuário para apontar `joypad_autoconfig_dir` à
nossa árvore.** Rejeitada, e já era: viola a §5 do AGENTS.md. O mecanismo segue
sendo `--appendconfig` em tempo de lançamento, com `config_save_on_exit`
desligado no overlay — ver seções 3 e 4 da evidência.

## Consequências

- O pad do Deck passa de `awaiting-device` para `pending-write`, com 12 bindings
  resolvidos e zero não resolvidos. Medido, não presumido.
- Cada novo pad empacotado exige a mesma medição em hardware real e a prova de
  ausência no catálogo de terceiro. Não se adiciona perfil por analogia.
- O risco de colisão futura com o catálogo do RetroArch é contido pelo caminho
  `ambiguous-autoconfig`, que recusa gravar em vez de escolher.

## O que este ADR não decide

A confirmação botão a botão — pressionar cada controle e observar o RetroArch
reagir conforme o mapa — exige interação humana e permanece em aberto no item. A
derivação acima é sólida e verificada por duas fontes, mas não substitui essa
observação final.
