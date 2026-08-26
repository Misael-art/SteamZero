# Evidência: onde o RetroArch Flatpak procura perfis de controle

Medido em 2026-08-13 no host (Steam Deck LCD, Valve Jupiter) com
`org.libretro.RetroArch` **1.22.2** instalado por usuário
(`~/.local/share/flatpak/app/org.libretro.RetroArch`).

Esta página existe porque a G45 chegou a supor que "abrir o RetroArch uma vez"
destravaria a gravação do perfil. **Não destrava.** Os dados abaixo são do
pacote e da execução reais, não de leitura de documentação.

## 1. O diretório declarado é interno ao sandbox

O RetroArch nunca havia sido executado neste host. Ao rodá-lo uma vez, ele criou
o próprio config a partir do esqueleto do pacote:

```
[INFO] [Config] Using skeleton config "/app/etc/retroarch.cfg" as base for a new config file.
[INFO] [Config] Created new config file in: ".../config/retroarch/retroarch.cfg".
```

E o valor que ficou gravado no config **real** do usuário:

```
joypad_autoconfig_dir = "/app/share/libretro/autoconfig"
```

`/app` é o ponto de montagem somente-leitura do Flatpak: **não existe no host**
(`ls /app` → inexistente). Logo, um diretório *declarado* não é um diretório
*alcançável*, e nada que o SteamZero grave fora do sandbox será lido dali.

## 2. O perfil vai no subdiretório do DRIVER, não na raiz

Contagem de `.cfg` por subdiretório em `share/libretro/autoconfig/`:

| subdiretório | perfis |
|---|---|
| (raiz) | **0** |
| `udev` | 420 |
| `dinput` | 223 |
| `android` | 212 |
| `sdl2` | 67 |
| `hid` | 60 |
| `xinput` | 30 |
| `linuxraw` | 12 |
| `qnx` / `x` / `mfi` / `parport` | 3 / 2 / 1 / 1 |

A raiz tem zero perfis. O driver vem do config:

```
input_joypad_driver = "udev"      # seleciona o subdiretório
input_driver = "x"                # NÃO é este; é o driver de teclado/mouse
```

Gravar em `<joypad_autoconfig_dir>/steamzero.cfg` produziria um arquivo que
nunca seria lido — falha silenciosa. O alvo correto é
`<joypad_autoconfig_dir>/<input_joypad_driver>/`.

## 3. `--appendconfig` funciona, e persiste

Testado com um config COPIADO (o do usuário não foi tocado):

```
flatpak run org.libretro.RetroArch --config <copia> --appendconfig <override>
```

Depois da execução, a cópia continha o valor do override:

```
joypad_autoconfig_dir = "~/.var/app/.../steamzero-autoconfig"
```

Duas consequências para o desenho, ambas importantes:

- o mecanismo **serve** para apontar o RetroArch a um diretório gerenciado e
  gravável em tempo de lançamento;
- o config do RetroArch tem `config_save_on_exit = "true"`, então o valor
  injetado é **persistido** no arquivo usado. Aplicá-lo ao `retroarch.cfg` do
  usuário equivaleria a editá-lo permanentemente, o que a AGENTS.md §5 proíbe.
  Qualquer integração precisa resolver isso (config próprio do SteamZero, ou
  outro mecanismo), e essa decisão **ainda não foi tomada**.

## Estado que o código publica hoje

`awaiting-emulator`, com o detalhe dizendo que o diretório declarado não existe
no host por ser caminho interno do sandbox. Nenhum perfil é declarado aplicado,
e nenhuma escrita é tentada.

## Limpeza

Os artefatos deste teste (`copia-teste.cfg`, `override-teste.cfg`,
`steamzero-autoconfig/`) foram removidos. O `retroarch.cfg` criado pela execução
permanece — é do RetroArch, e é o estado normal de quem abriu o emulador uma
vez; seu `joypad_autoconfig_dir` segue com o valor original do pacote.

---

## 4. Prova ponta a ponta da integração `--appendconfig`

Feita em 2026-08-13, no host, com **joypad virtual** criado via `uinput`
(`SteamZero Virtual Pad`, `2dc8:3001` = 11720:12289 em decimal — os mesmos ids
de um 8BitDo que o RetroArch empacota). O perfil gerenciado foi gerado pelo
CÓDIGO DE PRODUÇÃO (`RetroArchControls.plan/apply`), não à mão.

O teste é um A/B com o mesmo pad conectado, mudando só o `--appendconfig`:

| execução | comando | o que o RetroArch reportou |
|---|---|---|
| **A** — sem overlay | `flatpak run … --verbose --menu` | `[Autoconf] 8BitDo SF30 2.4G conectado na porta 1.` |
| **B** — com overlay | `… --appendconfig <overlay>` | `[Autoconf] SteamZero Virtual Pad conectado na porta 1.` |

Em **A** o RetroArch usou o perfil **empacotado** (`/app/share/libretro/
autoconfig/udev/`). Em **B** usou o **nosso**, no diretório gerenciado — o nome
publicado (`SteamZero Virtual Pad`) só existe no arquivo que o SteamZero gerou.

Isso prova, com o pacote real e sem simulação:

1. o `--appendconfig` redireciona de fato `joypad_autoconfig_dir`;
2. o RetroArch lê o perfil da árvore gerenciada;
3. o subdiretório do driver (`udev`) é obrigatório — o perfil foi gravado em
   `<raiz>/autoconfig/udev/` e foi encontrado ali.

### O que continuou intocado

- `retroarch.cfg` do usuário: `joypad_autoconfig_dir` segue
  `"/app/share/libretro/autoconfig"`, o valor original do pacote;
- `~/.var/app/org.libretro.RetroArch/config/retroarch/autoconfig/`: continua
  vazio;
- o pad virtual e a árvore de teste (`~/.config/steamzero-e2e`) foram removidos.

### Limite conhecido

O pad virtual do `uinput` **não** recebe symlink `-event-joystick` em
`/dev/input/by-id`, que é onde `SysfsInputDevices` procura. A descoberta
automática não o enxergaria; neste teste a identidade foi injetada. Provar a
descoberta ponta a ponta exige um controle físico real.

---

## 5. Descoberta automática com controle FÍSICO real (2026-08-26)

A seção 4 fechou dizendo, com todas as letras: *"o pad virtual do `uinput` não
recebe symlink `-event-joystick` em `/dev/input/by-id`, que é onde
`SysfsInputDevices` procura. A descoberta automática não o enxergaria; neste
teste a identidade foi injetada. Provar a descoberta ponta a ponta exige um
controle físico real."*

Esse limite está fechado. O host É um Steam Deck LCD, então o controle físico
sempre esteve presente — faltava medir.

### Por que esta página voltou

O código de produção cita este diretório:

```
src/steamzero/adapters/input_devices.py:392
    `docs/09-operations/evidence/2026-08-13-retroarch-autoconfig/`
```

Mas ele **não estava na `main`**. O commit que o criou (`e0fd8dd`) ficou numa
branch nunca mergeada, e `git merge-base --is-ancestor e0fd8dd main` responde
não. Ou seja: havia uma afirmação de medição no host, dentro de código
instalado, apontando para evidência inalcançável na linha principal. As seções
1 a 4 acima foram restauradas **verbatim** desse commit; nada foi reescrito.

### O que reproduz hoje, sem alteração

Reconferido em 2026-08-26 no host, com RetroArch `1.22.2`:

| Afirmação da seção 1 | Valor medido hoje |
|---|---|
| `joypad_autoconfig_dir` interno ao sandbox | `"/app/share/libretro/autoconfig"` |
| driver que escolhe o subdiretório | `input_joypad_driver = "udev"` |
| persistência que ameaça o cfg do usuário | `config_save_on_exit = "true"` |

As três reproduzem exatamente. O diagnóstico de 2026-08-13 não envelheceu.

### A descoberta, agora sem injeção

```
$ .venv/bin/python -c "from steamzero.adapters import input_devices; \
    print(input_devices.SysfsInputDevices().identities())"
[DeviceIdentity(name='Steam Deck', vendor_id=10462, product_id=4613)]
```

Corroborado por duas fontes independentes do código:

```
$ ls /dev/input/by-id/ | grep joystick
usb-Valve_Software_Steam_Deck_Controller_<SERIAL>-if02-event-joystick -> ../event7
usb-Valve_Software_Steam_Deck_Controller_<SERIAL>-if02-joystick      -> ../js0

$ cat /sys/class/input/js0/device/id/{vendor,product}
28de 1205
```

`10462 = 0x28DE` (Valve Software) e `4613 = 0x1205` batem com o sysfs. O
symlink `-event-joystick` — exatamente o padrão que `SysfsInputDevices` procura
e que o pad virtual do `uinput` não produzia — existe para o pad real.

O número de série do controle foi substituído por `<SERIAL>` nesta página.

### Resolução do alvo, com o driver lido do host

```
target.path      /home/misael/.config/steamzero/retroarch/autoconfig/udev/steamzero.cfg
overlay_path     /home/misael/.config/steamzero/retroarch/steamzero.cfg
launch_arguments ('--appendconfig', '/home/misael/.config/steamzero/retroarch/steamzero.cfg')
```

O subdiretório `udev` foi derivado do `input_joypad_driver` REAL do usuário, não
suposto — que é a lição da seção 2.

### O que NÃO está provado nesta página

`retroarch_launch_arguments('org.libretro.RetroArch')` devolve hoje **tupla
vazia**, e isso está correto: nenhum perfil foi materializado ainda, e o código
recusa passar `--appendconfig` apontando para arquivo inexistente. Portanto,
desta sessão:

- ✅ descoberta automática resolve o pad físico real;
- ✅ alvo e driver resolvidos contra o host real;
- ❌ gravação do autoconfig gerenciado — NÃO executada;
- ❌ marcador de ownership no arquivo publicado — não observável sem a gravação;
- ❌ recusa de sobrescrever arquivo de terceiro — não exercitada;
- ❌ perfil chegando ao lançamento real — depende da gravação.

A gravação exige `controls apply` com token de confirmação, e o classificador do
harness bloqueou essa chamada nesta sessão. O item permanece aberto.

### Estado do host ao fim desta sessão

Nada foi gravado. `~/.config/steamzero/retroarch/` continua **inexistente** e o
`retroarch.cfg` do usuário segue intocado:

```
sha256  a9945f5a4e6176ff5e2d9bc88b113355e1547f0650ba1104d74bbdf15e879393
114561 bytes   mtime 2026-08-13 05:24:22
```

---

## 6. Por que o Steam Deck para em `awaiting-device` (2026-08-26)

Com um perfil de controle ATIVO (`standard-gamepad` para `snes`, aplicado pelo
caminho governado `controls plan` → `controls apply`), o writer publica:

```
state   awaiting-device
label   Perfil traduzido; aguardando controle reconhecido
target  ~/.config/steamzero/retroarch/autoconfig/udev/steamzero.cfg
```

Isso NÃO é defeito nosso. É o produto degradando com verdade.

### A causa, medida no pacote real

`RetroArchControls.status()` só resolve quando o catálogo empacotado do
RetroArch casa com o dispositivo. O catálogo é legível — 420 perfis em
`.../org.libretro.RetroArch/x86_64/stable/active/files/share/libretro/
autoconfig/udev` — e contém dois perfis da Valve:

| arquivo | `input_vendor_id` | `input_product_id` | dispositivo |
|---|---|---|---|
| `Steam_Controller.cfg` | 10462 | 1142 | Steam Controller |
| `Wireless Steam Controller.cfg` | 10462 | 4418 | Wireless Steam Controller |

O controle embutido deste host é **10462 / 4613** (`0x28DE` / `0x1205`). Busca
exaustiva no catálogo:

```
$ grep -rl 'input_product_id = "4613"' <catalogo>/udev/
(nenhum resultado)
```

**O RetroArch 1.22.2 não empacota autoconfig para o controle interno do Steam
Deck.** O vendor casa; o produto não existe no catálogo.

### Por que parar é o comportamento certo

Sem perfil-base do catálogo não há como traduzir o RetroPad para os eixos e
botões REAIS deste pad. Gravar assim mesmo produziria
`autoconfig/udev/steamzero.cfg` com bindings inventados — um arquivo que o
RetroArch leria e que mapearia o controle errado. `awaiting-device` diz a
verdade e não grava nada, que é a AGENTS.md §8.

### Consequência para o item

O bloqueio de `SZ-CONTROLS-INPUT-PROFILES` neste host **não** é o harness nem
falta de controle físico. É uma lacuna do pacote do RetroArch. Fechar o item
exige uma decisão de produto, não mais medição:

1. o SteamZero passa a trazer um autoconfig-base próprio para o Steam Deck
   (`10462/4613`), derivado do pad real; ou
2. a resolução deixa de exigir casamento exato de `product_id` e cai para um
   perfil genérico compatível, com o risco explícito registrado; ou
3. o item declara o Steam Deck como não-suportado para autoconfig gerenciado e
   a UI diz isso ao usuário.

Nenhuma delas é medição — todas mudam contrato. Por isso o item continua
`partial`, e a próxima ação é a decisão, não mais um teste.

### Estado do host

`~/.config/steamzero/retroarch/` **continua inexistente** — nada foi gravado. O
único efeito desta sessão é o perfil ativo em
`~/.config/steamzero/input-profiles/active/snes/platform-default.json`, criado
pelo caminho governado com rollback G-FULL. O `retroarch.cfg` do usuário segue
`sha256 a9945f5a…9393`, idêntico ao baseline.
