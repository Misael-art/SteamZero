# PRIVILEGE-BOUNDARIES — fronteiras de privilégio

## Inventário: o que realmente precisa de root

| Operação | Precisa de root? | Caminho sem root |
|---|---|---|
| Instalar emulador Flatpak | não (`flatpak --user`) | padrão |
| AppImage | não (`~/Applications`) | padrão |
| ROMs/BIOS/saves/mídia | não ($XDG_DATA_HOME / mounts do usuário) | padrão |
| Perfis Steam Input, shortcuts | não (arquivos do usuário Steam) | padrão |
| Pacote nativo (pacman/dnf/apt) | sim | oferecer alternativa Flatpak primeiro |
| TDP/clock GPU | sim (sysfs) | — (helper) |
| systemd system service / udev rule / montagem automática de removível | sim | user services quando possível |
| sysctl de performance | sim | — (helper) |

Lição do PhaseZero: o `pz_admin_run` (common.sh:39-52) escala **por comando individual**, nunca por bloco — princípio mantido. O LinuxToys usa `sudo` liberalmente dentro de scripts (ex.: `sudo flatpak override` global em `faugus.sh`) — anti-padrão aqui: overrides Flatpak do usuário não precisam de root.

## Helper `steamzero-admin`

- Processo separado, instalado no host (fora do sandbox Flatpak), acionado via polkit (`pkexec`) com policy própria por ação.
- **Allowlist fechada** (enum, não string livre). Rascunho v1:

| Ação | Parâmetros (schemados) | Validação |
|---|---|---|
| `health` | nenhum | somente leitura; versão, protocolo e UID efetivo |
| `set-tdp` | watts: int 3..30 | range por modelo (LCD/OLED) |
| `set-gpu-clock` | mhz: int em tabela por modelo | tabela embutida |
| `install-udev-rule` | ruleId: enum de regras embutidas | conteúdo vem do binário, nunca do chamador |
| `enable-system-unit` | unitId: enum de units embutidas | idem |
| `mount-removable` | uuid: formato UUID validado, ro/rw | UUID existe em /dev/disk/by-uuid; mountpoint gerido pelo helper |
| `write-sysctl` | key: enum permitido, value: range | tabela embutida |

- **O que o helper nunca aceita:** paths arbitrários, strings de shell, scripts, conteúdo de arquivo vindo do chamador (conteúdos privilegiados são embutidos/assinados no próprio helper).
- Audit log próprio (`/var/log/steamzero-admin.log`, append-only, 0600 root) com chamador, ação, parâmetros, resultado.
- Versão do protocolo checada nos dois lados; mismatch = recusa.
- O primeiro efetor host publicado habilita apenas `health`. As ações mutáveis
  continuam na allowlist de protocolo, mas o efetor de produção as recusa até
  cada uma possuir captura do valor anterior, aplicação, verificação e rollback.

## Sandbox Flatpak (quando empacotado assim — ADR-0003)

- Permissões mínimas no manifesto; filesystem só nos diretórios de dados declarados; sem `--filesystem=host`.
- Portais para file chooser (import de dumps) e abrir URLs.
- Comunicação com `steamzero-admin` via D-Bus system bus com policy allowlist (não via `talk-name` amplo).

## Testes exigidos (08-testing/SECURITY-TESTS.md)

- Fuzzing dos parâmetros do helper (AC-PR-01); tentativa de traversal em `uuid`/`unitId`; chamada fora da allowlist; downgrade de protocolo.
