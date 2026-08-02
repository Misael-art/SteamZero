# HOST-INSTALL — instalação nativa no BigLinux

Este procedimento instala o SteamZero sem depender de PhaseZero, de um checkout
permanente ou do Python do usuário. Ele é destinado ao BigLinux/Manjaro em modo
Desktop e usa `bigsudo` somente para publicar arquivos do sistema.

Para o fluxo retomável usado por agentes — diagnóstico, download do run exato,
validação, instalação, ciclo e publicação — use
[`RELEASE-HOST-AUTOMATION.md`](RELEASE-HOST-AUTOMATION.md). Este documento
permanece como contrato detalhado do instalador subjacente.

## Modelo operacional

| Caminho | Função |
|---|---|
| `/opt/steamzero/releases/<release>` | release imutável, venv e artefatos auditáveis |
| `/opt/steamzero/current` | único ponteiro que ativa/retrocede uma release |
| `/usr/local/bin/steamzero` | comando estável para o usuário |
| `/usr/local/bin/steamzero-gamemode-session` | diagnóstico e inicialização estáveis da sessão Game Mode |
| `/usr/local/libexec/steamzero-gamemode-boot` | seleção GRUB→SDDM reversível, sem runtime legado |
| `/usr/local/libexec/steamzero-host-prepare` | prontidão/preparação KVM-libvirt por família de distro |
| `/usr/local/sbin/steamzero-host` | plano de gerenciamento estável: status e rollback |
| `/usr/local/share/applications/org.steamzero.SteamZero.desktop` | lançador KDE |
| `/usr/local/lib/systemd/user/steamzero-core.{socket,service}` | plano de controle user-scoped, socket-activated |
| `/usr/local/share/wayland-sessions/steamzero-gamemode.desktop` | sessão Game Mode independente, selecionável no SDDM |

Configurações e dados continuam nos diretórios XDG de cada usuário. O instalador
não lê, migra nem apaga esses dados e não procura PhaseZero.

O gerenciador host não acompanha o ponteiro `current`: ele permanece na versão mais
nova instalada para que um rollback da aplicação não restaure bugs antigos do próprio
instalador. Um marcador de ownership impede que um arquivo administrativo alheio seja
sobrescrito.

## Origem dos artefatos

Baixe do workflow da tag. **Não** reutilize wheel ou wheelhouse local antigo.

O wheelhouse precisa trazer `WHEELHOUSE-MANIFEST.json`; o instalador recusa um
conjunto sem manifesto, com hash divergente, gerado de árvore suja, ou que
contenha wheel presente e não declarado. Essa última é a forma de um artefato de
origem desconhecida viajar junto: os declarados conferem, e o intruso passa.

```bash
gh run download RUN_ID --name "steamzero-wheel-COMMIT"
tar --zstd -xf runtime-wheelhouse.tar.zst
python tools/build_wheelhouse.py --out runtime-wheelhouse --validate-only
```

## Preparar artefatos sem root

Partindo de um checkout limpo, em um commit identificável, e de um ambiente de
desenvolvimento criado exclusivamente a partir do lock:

```bash
test -z "$(git status --porcelain)"
SOURCE_COMMIT=$(git rev-parse HEAD)
.venv/bin/python -m pip wheel --no-deps --wheel-dir dist .
.venv/bin/python tools/release_provenance.py verify-wheel --wheel dist/steamzero-*.whl
mkdir -p dist/runtime-wheelhouse
.venv/bin/pip download \
  --only-binary=:all: \
  --require-hashes \
  -r requirements-runtime.lock \
  -d dist/runtime-wheelhouse
sha256sum dist/steamzero-*.whl
```

O `requirements-runtime.lock` contém versões e hashes. O download falha se uma
dependência não tiver wheel binário compatível ou divergir do lock.

## Instalar ou reparar

A identificação não é mais livre: ela é derivada da versão do wheel e dos 12
primeiros caracteres do commit completo. O instalador lê a versão no `METADATA`,
exige o SHA-1 completo e recusa um `--release` que não seja canônico:

```bash
bigsudo /usr/bin/python3 tools/install_host.py install \
  --release 0.1.0a1-${SOURCE_COMMIT:0:12} \
  --wheel dist/steamzero-0.1.0a1-py3-none-any.whl \
  --wheel-sha256 HASH_SHA256_COMPLETO \
  --requirements requirements-runtime.lock \
  --wheelhouse dist/runtime-wheelhouse \
  --source-commit "$SOURCE_COMMIT"
```

A instalação é offline depois que o wheelhouse foi preparado. Ela copia os
artefatos, cria um manifesto v4 com versão, commit e estado `clean`, instala as
dependências exigindo os hashes, executa
`pip check`, `steamzero --version` e `steamzero doctor --json`, e somente então
troca `current`. Repetir o mesmo comando com a mesma release e hash é idempotente
e também repara links de integração incompletos.

Uma pasta com `.installing.json` representa interrupção anterior. Uma nova
execução só a reconstrói quando release e hash coincidem; divergências são
recusadas. Arquivos preexistentes não gerenciados em `/usr/local` nunca são
sobrescritos.

Depois da primeira instalação, ative somente o socket do usuário corrente:

```bash
systemctl --user daemon-reload
systemctl --user enable --now steamzero-core.socket
systemctl --user status steamzero-core.socket --no-pager
steamzero-gamemode-session --check
```

O serviço sobe sob demanda. A sessão **SteamZero Game Mode** aparece no seletor do SDDM e
sempre possui fallback para Plasma. O instalador da release não muda a sessão padrão. A
ativação separada abaixo é a única operação que publica entrada própria no GRUB e seleção
temporária no SDDM:

```bash
bigsudo /usr/local/libexec/steamzero-gamemode-boot enable --user misael
/usr/local/libexec/steamzero-gamemode-boot status
```

Para reverter, use `bigsudo /usr/local/libexec/steamzero-gamemode-boot disable`.

## Preparar laboratório agnóstico

O laboratório virtual cobre clean install, update, rollback, packaging e smoke de UI. Ele
não declara `virtio-gpu` equivalente ao AMDGPU do Deck; TDP, clock, KScreen, dock e suspend
continuam no hardware físico com snapshot e recuperação.

```bash
/usr/local/libexec/steamzero-host-prepare status
/usr/local/libexec/steamzero-host-prepare plan
bigsudo /usr/local/libexec/steamzero-host-prepare apply \
  --user misael --confirm PREPARAR-VIRTUALIZACAO
```

O comando detecta pacman, apt ou dnf, usa listas de pacotes compiladas sem shell, habilita
libvirt, converge a rede `default` e adiciona o usuário ao grupo `libvirt` quando presente.
No BigLinux/Manjaro o conjunto inclui QEMU desktop, libvirt, virt-install, OVMF, swtpm,
dnsmasq e iptables-nft. É necessário relogin quando a associação ao grupo mudar.

## Convergir o daemon (obrigatório)

**A instalação não está concluída quando o `current` muda.** O instalador roda
como root e as units são de escopo de usuário, válidas para todos os usuários da
máquina: ele não sabe qual sessão reiniciar, e declara `daemonRefresh.state =
pending`.

Foi aceitar esse `pending` como conclusão que produziu a regressão da a37 — o
`current` apontava para a release nova e o daemon a35 seguiu respondendo por dois
dias.

Como o **usuário da sessão**, nunca como root:

```bash
/usr/local/sbin/steamzero-host converge \
  --expect-release "$(basename "$(readlink -f /opt/steamzero/current)")"
```

Esse gate vive no gerenciador estável, fora de `current`, e continua disponível
mesmo quando a release alvo é antiga e não possui `steamzero service refresh`.
Ele compara a release esperada, a ativada e a identidade do daemon. Para releases
anteriores à identidade completa, confirma `daemonVersion`, PID e que
`/proc/<pid>/exe` pertence ao `venv/bin` da release ativa. Só devolve sucesso em
`converged`.

| estado | significado | ação |
|---|---|---|
| `converged` | o daemon responde na release ativada | concluído |
| `mismatch` | `--expect-release` diverge do `current` | **nada foi reiniciado**; conferir o que foi instalado |
| `pending` | o daemon respondeu com a release ANTIGA depois do restart | investigar a unit; é o estado da a37 |
| `timeout` | o daemon não respondeu | conferir socket e journal |
| `restartFailed` | `systemctl --user restart` falhou | ver `systemctl --user status` |
| `unreadable` | `current` ou a release ativa não pôde ser verificada | reparar a instalação antes de reiniciar |

`mismatch` falha **fechada**: nenhum serviço é reiniciado. Agir sobre premissa
errada apagaria a evidência de o que falhou na instalação.

O comando é idempotente: com o daemon já na release esperada e executando pelo
venv correto, ele não reinicia nada. Se o processo errado sobreviver ao restart,
as units gerenciadas são paradas para não servir dados de outra release.

## Verificar

```bash
steamzero --version
steamzero doctor --json
systemctl --user is-active steamzero-core.socket
systemctl --user is-active steamzero-core.service
steamzero-gamemode-session --check
/usr/local/libexec/steamzero-gamemode-boot status
/usr/local/libexec/steamzero-host-prepare status
bigsudo /usr/local/sbin/steamzero-host status
/usr/local/sbin/steamzero-host converge --expect-release RELEASE_ATIVA
```

O `status` recalcula os hashes do wheel, lock e gerenciador da release, confere
proprietário/permissões e repete os smokes com estado XDG temporário. Resultado
`ok: false` deve bloquear uma atualização ou rollback até investigação.

## Rollback

As releases anteriores são retidas. Liste-as e ative uma versão verificada:

```bash
ls -1 /opt/steamzero/releases
bigsudo /usr/local/sbin/steamzero-host rollback --release RELEASE_ANTERIOR
/usr/local/sbin/steamzero-host converge --expect-release RELEASE_ANTERIOR
steamzero doctor --json
```

O gate estável é obrigatório **também no rollback**. Um rollback que
deixasse o daemon na release nova é o incidente da a37 ao contrário — e
igualmente invisível.

O rollback altera o ponteiro `current`; não reinstala pacotes e não reverte dados
XDG do usuário. Migrações incompatíveis de dados exigirão a política específica
de backup/restauração antes de uma versão estável.

## Limites atuais

- integridade local é garantida por hashes e lock completo; o CI também gera
  auditoria OSV, SBOM CycloneDX, checksums e proveniência local do wheel;
  atestação Sigstore em repositório privado depende de GitHub Enterprise Cloud ou
  de um assinador externo a ser selecionado antes do canal de release;
- o instalador publica a aplicação e o lançador, mas não aplica automaticamente
  perfis de display/input nem instala componentes Flatpak;
- boot direto publica somente um marcador e deixa a seleção gráfica a cargo do SDDM; a
  certificação pós-reboot ainda precisa comprovar Game Mode, retorno ao Plasma e greeter
  depois de três falhas em cada release/hardware;
- a autorização permanece a cargo do agente polkit do KDE; senha nunca deve ser
  passada em argumento, arquivo ou chat.

O instalador também publica `/usr/local/libexec/steamzero-admin` e a policy
`io.github.misael-art.steamzero.admin` quando o wheel contém o entry point. O smoke
read-only é:

```text
pkexec /usr/local/libexec/steamzero-admin --health
```

O resultado deve declarar `mutationsEnabled=false` enquanto os efetores R3 com
verify/rollback não estiverem certificados. Um health saudável não autoriza TDP,
GPU, sysctl, mount ou units por antecipação.

O mesmo fluxo pode ser comprovado com `steamzero admin health --json`. Esta ação
interativa é executada pela CLI e deliberadamente não atravessa o daemon
user-scoped; a resposta só é aceita quando helper e CLI concordam sobre envelope,
exit code e protocolo.

Em hardware AMDGPU compatível, `data.hardware` informa a disponibilidade e os
limites observados de TDP/GPU. `railsConverged=false` é condição degradada; nunca
se deve aplicar perfil assumindo que `slowPPT` e `fastPPT` já coincidem.

Os motores transacionais internos de TDP e clock GPU podem ser exercitados em
interfaces descartáveis, mas isso não altera o contrato público: `mutationsEnabled`
e `manualWriteEnabled` permanecem falsos até certificação em VM, recovery após queda
real do helper e validação posterior no hardware com protocolo de recuperação.

O mesmo vale para sysctl: a presença do motor transacional interno não publica
`write-sysctl`. Testes de instalação devem copiar a forma de `/proc/sys` para uma
árvore temporária e injetar o writer descartável; nunca usar o host principal como
primeira bancada de `swappiness` ou compactação de memória.
