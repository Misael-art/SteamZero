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
