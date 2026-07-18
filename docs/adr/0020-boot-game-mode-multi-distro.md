# ADR-0020 — Boot direto em Game Mode multi-distro (Arch e derivadas)

**Status:** proposto

## Contexto

Incidente real (2026-07-18, host BigLinux): o boot direto em Game Mode falhou em todos
os boots porque a sessão `steamzero-gamemode.desktop` foi instalada em
`/usr/local/share/wayland-sessions/`, enquanto o `/etc/sddm.conf` do BigLinux — lido por
último na precedência do SDDM — restringe `SessionDir=/usr/share/wayland-sessions`.
O autologin publicado pelo oneshot falhou (`Unable to find autologin session entry`),
o greeter assumiu e a sessão legada escolhida degradou para Plasma. A validação do
`prepare()` checava existência do arquivo no disco, não visibilidade na configuração
efetiva do display manager. Além disso, `status()` sem privilégio lê
`/etc/steamzero/gamemode-user`, engole `EACCES` e reporta "não configurado" — falso
negativo exibido na UI durante o incidente.

A lição generaliza: cada derivada Arch (Manjaro, EndeavourOS, CachyOS, Garuda, vanilla)
quebra uma suposição diferente em quatro eixos — display manager (SDDM, GDM, LightDM,
greetd, ly), bootloader (GRUB, systemd-boot, rEFInd, Limine), layout de boot (nome de
kernel/initrd/ucode, subvolume btrfs, ESP) e runtime de sessão. O acerto existente que
deve ser preservado: a entrada de boot só injeta o marcador `steamzero.gamemode=1` no
cmdline; quem age é o oneshot antes do display manager; a sessão depende apenas de
`gamescope` + `steam` detectados em runtime, nunca de pacotes de sessão de terceiros.

## Alternativas

1. **Duas portas (`DisplayManagerPort`, `BootEntryPort`) com adapters por mecanismo,
   validação de configuração efetiva no preflight e verificação pós-boot com backoff**
   (escolhida).
2. Condicionais por distro (`if distro == "biglinux"`) — contras: matriz combinatória
   cresce sem limite; decide por nome, não por comportamento; quebra na próxima
   derivada não mapeada.
3. Bypass total do display manager (unit própria com `Conflicts=display-manager.service`
   iniciando gamescope na VT, modelo SteamOS/ChimeraOS) — contras: assume ownership do
   seat inteiro; conflita com a filosofia de degradação (ADR-0019: ausência degrada uma
   capacidade, não o núcleo); recuperação de falha exige console. Permanece como opção
   futura atrás da mesma porta, não como caminho padrão.
4. Suportar apenas SDDM/GRUB documentadamente — contras: exclui EndeavourOS
   (systemd-boot) e CachyOS (Limine) já no default de instalação.

## Decisão

### Princípio transversal

Toda decisão de comportamento sai de **capacidade detectada** (qual DM responde, qual
bootloader existe, quais binários estão presentes), nunca de nome de distro.
`/etc/os-release` (`ID`, `ID_LIKE`) serve só a telemetria e mensagens. Nenhum arquivo
de configuração alheio é editado; quando um drop-in próprio não pode vencer a
precedência do host (caso `SessionDir`), muda-se a colocação do artefato próprio, não
o arquivo da distro.

### `DisplayManagerPort`

```python
class DisplayManagerPort(Protocol):
    def detect(self) -> DMInfo: ...
    # DM real via symlink de display-manager.service; "unknown" é valor válido.

    def effective_session_dirs(self) -> list[Path]: ...
    # Diretórios de sessão da configuração EFETIVA, reproduzindo a precedência
    # real do DM (SDDM: /usr/lib/sddm/sddm.conf.d → /etc/sddm.conf.d →
    # /etc/sddm.conf; o último vence).

    def publish_autologin(self, user: str, session: str) -> None: ...
    # Pré-condição obrigatória: o arquivo de sessão está dentro de
    # effective_session_dirs(). Violação → E-SESSION-LAUNCH-FAILED com detail
    # acionável, nada é escrito.

    def withdraw_autologin(self) -> None: ...
```

Adapters em ordem de entrega: `sddm` (primeiro; cobre KDE e a maioria das derivadas),
`gdm`, `lightdm`, `greetd`. O arquivo de sessão é instalado em
`/usr/share/wayland-sessions/` — único diretório varrido por todos os DMs em todos os
defaults conhecidos. DM `unknown`: nenhum autologin é escrito; a sessão fica visível no
menu do greeter e o doctor reporta `manual-login-required`.

### `BootEntryPort`

```python
class BootEntryPort(Protocol):
    def detect(self) -> BootloaderInfo: ...
    # grub | systemd-boot | refind | limine | unknown

    def install_entry(self, spec: BootEntrySpec) -> None: ...
    def remove_entry(self) -> None: ...

    def set_oneshot(self) -> None: ...
    # "Reiniciar em Game Mode" uma única vez (grub-reboot /
    # bootctl set-oneshot) sem tocar a configuração permanente.
```

Adapters em ordem de entrega: `grub` (extraído do código atual: `/etc/grub.d/42_*` +
`grub-mkconfig`), `systemd-boot` (entrada `.conf` em `$ESP/loader/entries/`), depois
`refind`/`limine`. O `BootEntrySpec` continua sendo derivado do `/proc/cmdline`
corrente (kernel, initrd, ucode, rootflags) — nunca de nomes de arquivo assumidos.
Bootloader `unknown`: entrada não é instalada; a sessão permanece acessível pelo
greeter.

### Preflight e verificação pós-boot

`enable` executa preflight completo antes de qualquer efeito: DM detectado e
suportado; sessão dentro do `SessionDir` efetivo; `gamescope`, `steam` e fallback
desktop presentes; bootloader detectado. Qualquer falha aborta sem instalação parcial.

O oneshot grava marcador "Game Mode solicitado"; a sessão grava "Game Mode iniciado".
Solicitado sem iniciado = falha real de boot: causa registrada, backoff após N falhas
consecutivas (autologin removido para não prender o usuário em loop), estado exposto no
doctor e na UI. Falha de boot nunca pode ser silenciosa nem repetir indefinidamente.

`status()` distingue `EACCES` de "não configurado" (`permissionDenied: true` no
payload); telemetria sem privilégio não pode reportar falso negativo.

### Matriz de compatibilidade (laboratório KVM existente)

Cenário único fim-a-fim por VM: `enable` → reboot → gamepadui sem greeter → `disable`
→ host restaurado. Cada bug de compatibilidade novo vira um caso na matriz.

| VM | Eixo coberto |
|---|---|
| Arch vanilla + SDDM/GRUB | baseline |
| BigLinux/Manjaro KDE | `/etc/sddm.conf` sobrescrevendo defaults (incidente real) |
| EndeavourOS + systemd-boot | adapter systemd-boot |
| Arch + GDM | adapter GDM |
| CachyOS | Limine + kernel não-padrão |

## Consequências

- Pré-requisito de implementação: reconciliar no repositório a árvore da release
  instalada `0.1.0a25` (commit `2b9f65e54a4b`, hoje fora do versionamento), origem de
  `adapters/steam_boot.py` e `steam_session.py`.
- Correção imediata, antes das portas: sessão movida para
  `/usr/share/wayland-sessions/` + `status()` sensível a permissão. Resolve o incidente
  BigLinux e já é o comportamento correto universal.
- `steam_boot.py` é decomposto no par de adapters `sddm` + `grub`; contratos novos
  entram em `ports.py`; cada DM/bootloader novo é um adapter + uma linha na matriz,
  sem tocar o domínio.
- A remoção da cadeia legada PhaseZero no host (entrada GRUB, unit, sessão, scripts)
  permanece ação externa do usuário, conforme ADR-0019 e PHASEZERO-MIGRATION.

## Riscos

- Reproduzir a precedência de configuração de cada DM pode divergir de versões futuras
  do DM (mitigação: verificação pós-boot detecta a divergência no primeiro boot real;
  matriz de VMs cobre as versões empacotadas pelas derivadas).
- `set_oneshot` depende de suporte do bootloader (`grubenv` em btrfs exige
  `GRUB_DEFAULT=saved`); adapter deve detectar e degradar para entrada permanente.
- Backoff agressivo demais pode mascarar falhas intermitentes (mitigação: contador e
  causa persistidos e expostos no doctor, nunca só removidos).

## Revisão

Reavaliar a alternativa 3 (sessão dedicada sem DM, modelo SteamOS) quando a matriz
tiver ≥ 4 distros verdes e houver demanda por boot < 10 s; ela entraria como adapter
adicional de `DisplayManagerPort`, não como substituição.
