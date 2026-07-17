# HOST-INSTALL — instalação nativa no BigLinux

Este procedimento instala o SteamZero sem depender de PhaseZero, de um checkout
permanente ou do Python do usuário. Ele é destinado ao BigLinux/Manjaro em modo
Desktop e usa `bigsudo` somente para publicar arquivos do sistema.

## Modelo operacional

| Caminho | Função |
|---|---|
| `/opt/steamzero/releases/<release>` | release imutável, venv e artefatos auditáveis |
| `/opt/steamzero/current` | único ponteiro que ativa/retrocede uma release |
| `/usr/local/bin/steamzero` | comando estável para o usuário |
| `/usr/local/bin/steamzero-gamemode-session` | diagnóstico e inicialização estáveis da sessão Game Mode |
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
artefatos, cria um manifesto v3 com versão, commit e estado `clean`, instala as
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
sempre possui fallback para Plasma. O instalador não muda a sessão padrão, não habilita
autologin e não toca no GRUB.

## Verificar

```bash
steamzero --version
steamzero doctor --json
systemctl --user is-active steamzero-core.socket
systemctl --user is-active steamzero-core.service
steamzero-gamemode-session --check
bigsudo /usr/local/sbin/steamzero-host status
```

O `status` recalcula os hashes do wheel, lock e gerenciador da release, confere
proprietário/permissões e repete os smokes com estado XDG temporário. Resultado
`ok: false` deve bloquear uma atualização ou rollback até investigação.

## Rollback

As releases anteriores são retidas. Liste-as e ative uma versão verificada:

```bash
ls -1 /opt/steamzero/releases
bigsudo /usr/local/sbin/steamzero-host rollback --release RELEASE_ANTERIOR
steamzero doctor --json
systemctl --user daemon-reload
```

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
- boot direto em Game Mode continua bloqueado até snapshot Btrfs restaurável, TTY e console
  remoto comprovados. Selecionar a sessão no SDDM é suportado; reconfigurar GRUB para uma
  sessão gráfica não é o mecanismo correto e não é realizado;
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
