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
| `/usr/local/sbin/steamzero-host` | plano de gerenciamento estável: status e rollback |
| `/usr/local/share/applications/org.steamzero.SteamZero.desktop` | lançador KDE |

Configurações e dados continuam nos diretórios XDG de cada usuário. O instalador
não lê, migra nem apaga esses dados e não procura PhaseZero.

O gerenciador host não acompanha o ponteiro `current`: ele permanece na versão mais
nova instalada para que um rollback da aplicação não restaure bugs antigos do próprio
instalador. Um marcador de ownership impede que um arquivo administrativo alheio seja
sobrescrito.

## Preparar artefatos sem root

Partindo de um checkout limpo e de um ambiente de desenvolvimento já criado:

```bash
.venv/bin/python -m build --wheel --outdir dist
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

Escolha uma identificação única e informe explicitamente o hash obtido acima:

```bash
bigsudo /usr/bin/python3 tools/install_host.py install \
  --release 0.1.0.dev0-REVISAO-host1 \
  --wheel dist/steamzero-0.1.0.dev0-py3-none-any.whl \
  --wheel-sha256 HASH_SHA256_COMPLETO \
  --requirements requirements-runtime.lock \
  --wheelhouse dist/runtime-wheelhouse
```

A instalação é offline depois que o wheelhouse foi preparado. Ela copia os
artefatos, cria um venv próprio, instala dependências exigindo os hashes, executa
`pip check`, `steamzero --version` e `steamzero doctor --json`, e somente então
troca `current`. Repetir o mesmo comando com a mesma release e hash é idempotente
e também repara links de integração incompletos.

Uma pasta com `.installing.json` representa interrupção anterior. Uma nova
execução só a reconstrói quando release e hash coincidem; divergências são
recusadas. Arquivos preexistentes não gerenciados em `/usr/local` nunca são
sobrescritos.

## Verificar

```bash
steamzero --version
steamzero doctor --json
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
```

O rollback altera o ponteiro `current`; não reinstala pacotes e não reverte dados
XDG do usuário. Migrações incompatíveis de dados exigirão a política específica
de backup/restauração antes de uma versão estável.

## Limites atuais

- integridade é garantida por hashes locais e lock completo; assinatura de release
  e SBOM pertencem ao M14/M15;
- o instalador publica a aplicação e o lançador, mas não aplica automaticamente
  perfis de display/input nem instala componentes Flatpak;
- a autorização permanece a cargo do agente polkit do KDE; senha nunca deve ser
  passada em argumento, arquivo ou chat.
