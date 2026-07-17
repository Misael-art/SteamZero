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
| `rollback-tdp` | operationId: ULID | restaura somente snapshot root associado |
| `recover-tdp` | nenhum | restaura journals pending/rollback-failed |
| `set-gpu-clock` | mhz: int em tabela por modelo | tabela embutida |
| `rollback-gpu-clock` | operationId: ULID | restaura somente snapshot root associado |
| `recover-gpu-clock` | nenhum | restaura journals pending/rollback-failed |
| `install-udev-rule` | ruleId: enum de regras embutidas | conteúdo vem do binário, nunca do chamador |
| `enable-system-unit` | unitId: enum de units embutidas | idem |
| `mount-removable` | uuid: formato UUID validado, ro/rw | UUID existe em /dev/disk/by-uuid; mountpoint gerido pelo helper |
| `write-sysctl` | key: enum permitido, value: range | tabela embutida |
| `rollback-sysctl` | operationId: ULID | restaura somente snapshot root associado |
| `recover-sysctl` | nenhum | restaura journals pending/rollback-failed |

- **O que o helper nunca aceita:** paths arbitrários, strings de shell, scripts, conteúdo de arquivo vindo do chamador (conteúdos privilegiados são embutidos/assinados no próprio helper).
- Audit log próprio (`/var/log/steamzero-admin.log`, append-only, 0600 root) com chamador, ação, parâmetros, resultado.
- Versão do protocolo checada nos dois lados; mismatch = recusa.
- O primeiro efetor host publicado habilita apenas `health`. As ações mutáveis
  continuam na allowlist de protocolo, mas o efetor de produção as recusa até
  cada uma possuir captura do valor anterior, aplicação, verificação e rollback.
- `steamzero admin health` usa o cliente Polkit diretamente no processo
  interativo. Ele não é encaminhado ao daemon: no host real, um `pkexec` iniciado
  pelo serviço user-scoped não adquiriu autorização interativa. O transporte cria
  somente o argv fixo `pkexec steamzero-admin --health`, limita tempo/saída e
  valida o envelope completo; dados do chamador nunca viram argumento de processo.
- O health também inventaria, somente em leitura, `slowPPT`/`fastPPT` do driver
  `amdgpu` e o `SCLK` anunciado pelo DRM. A UI recebe limites observados e o estado
  de convergência das duas rails, mas `manualWriteEnabled` permanece falso.
- O motor interno de TDP já grava journal root `0600` antes da primeira rail,
  verifica ambas, restaura o snapshot em falha e bloqueia novo apply quando há
  operação interrompida. `rollback-tdp` e `recover-tdp` continuam sem transporte
  público até a prova em VM descartável; `mutationsEnabled=false` é vinculante.
- O motor interno de clock GPU segue a interface documentada pelo kernel AMDGPU:
  muda `power_dpm_force_performance_level` para `manual`, envia `s 0 <min>`,
  `s 1 <max>` e `c` a `pp_od_clk_voltage`, e verifica o estado observado. Antes
  disso, persiste min/max e o modo anterior em journal root `0600`; rollback e
  recovery restauram ambos. A implementação só reconhece `OD_SCLK` e limites
  `OD_RANGE` descobertos. Referência normativa: [AMDGPU Thermal Control — Linux
  kernel](https://www.kernel.org/doc/html/latest/gpu/amdgpu/thermal.html).
- `rollback-gpu-clock` e `recover-gpu-clock` também continuam sem transporte
  público. Os testes locais usam uma implementação sysfs descartável; nenhuma
  escrita no clock real é autorizada por essa evidência.
- Os motores TDP, GPU e sysctl usam ainda um lock de processo não bloqueante,
  separado do journal e criado `0600` com `O_NOFOLLOW`. Uma chamada concorrente
  recebe `E-TX-LOCKED`; o journal continua responsável por interrupções entre
  processos, enquanto o lock fecha a corrida antes da criação do journal.
- O motor sysctl resolve chaves por mapa compilado — nunca transforma diretamente
  uma string do chamador em path. Somente `vm.swappiness` (0..200) e
  `vm.compaction_proactiveness` (0..100) possuem apply/verify/rollback/recovery.
  `write-sysctl`, `rollback-sysctl` e `recover-sysctl` permanecem internos até a
  certificação em VM; o helper publicado continua health-only.

## Sandbox Flatpak (quando empacotado assim — ADR-0003)

- Permissões mínimas no manifesto; filesystem só nos diretórios de dados declarados; sem `--filesystem=host`.
- Portais para file chooser (import de dumps) e abrir URLs.
- Comunicação com `steamzero-admin` via D-Bus system bus com policy allowlist (não via `talk-name` amplo).

## Testes exigidos (08-testing/SECURITY-TESTS.md)

- Fuzzing dos parâmetros do helper (AC-PR-01); tentativa de traversal em `uuid`/`unitId`; chamada fora da allowlist; downgrade de protocolo.
