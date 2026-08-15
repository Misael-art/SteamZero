# RELEASE-HOST-AUTOMATION — promoção e atualização transacional

`tools/release_host.py` reduz o fluxo repetitivo de identificar versão, localizar
o artifact correto, instalar, convergir e publicar sem criar uma segunda
implementação do instalador. A autoridade continua nos contratos existentes:

- CI gera wheel, wheelhouse, SBOM, auditoria, proveniência e checksums;
- `build_wheelhouse.validate()` confere o conjunto;
- `tools/install_host.py` é o único escritor privilegiado do host;
- `/usr/local/sbin/steamzero-host converge` confirma geração e idempotência;
- uma certificação separada decide se tag e pre-release podem ser publicadas.

O caminho recomendado para atualizar um host existente é `update`. Os comandos
`prepare`, `install` e `rollback` continuam disponíveis para diagnóstico e
recuperação explícita, mas não precisam mais ser encadeados manualmente no fluxo
normal.

## Invariantes

1. Nenhuma subação infere autorização de uma execução anterior.
2. `inspect`, `verify-bundle` e `prepare` não usam `bigsudo`.
3. `install`, `rollback` e `cycle` produzem apenas:

   ```text
   bigsudo /usr/bin/python3 tools/install_host.py install ...
   bigsudo /usr/bin/python3 tools/install_host.py rollback ...
   ```

4. O subprocesso privilegiado sempre usa `cwd` na raiz descoberta a partir do
   próprio script. O diretório de onde o agente chamou a automação é irrelevante.
5. O bundle precisa vir de exatamente um run `push` verde de `origin/main`, no
   SHA completo solicitado.
6. Checkout, manifesto, wheel, lock, proveniência e run precisam declarar o
   mesmo commit e versão.
7. Toda ativação executa convergência e uma segunda chamada idempotente.
8. `update` mantém um lock durante a transação inteira; duas atualizações nunca
   planejam ou ativam simultaneamente.
9. Falha anterior à ativação mantém o host intocado. Falha posterior à ativação
   executa rollback automático, duas convergências e todos os smokes novamente.
10. Cada nova execução, inclusive recuperação, exige o token exato do plano;
    autorização não é inferida do journal de uma execução anterior.
11. Não há fallback silencioso, tag antecipada ou troca automática de emulador
    padrão.

## Atualizar em um comando

Primeiro, conferir o plano sem mutar o host:

```bash
rtk .venv/bin/python tools/release_host.py update --to origin/main --plan
```

Para executar interativamente:

```bash
rtk .venv/bin/python tools/release_host.py update --to origin/main
```

O controlador atualiza `origin/main`, exige `HEAD == origin/main` e worktree
limpa, localiza exatamente um run `push` verde, baixa ou reutiliza o bundle do
cache por SHA completo e valida wheel, wheelhouse, checksums, proveniência, SBOM
e auditoria. Antes de pedir confirmação, ele ainda prova:

- espaço livre com margem;
- release ativa integralmente verificável e apta a rollback;
- ownership de todos os destinos que o instalador pode publicar;
- doctor saudável, nenhuma operação pendente e schema de dados compatível;
- socket e serviço ativos;
- daemon convergido com `current`.

O plano mostra release atual, destino, SHA, rollback, preservação dos dados XDG
e que boot não será alterado. O token contém as duas releases completas:

```text
ATUALIZAR-<rollback>-PARA-<target>
```

Automação não interativa deve fornecer o mesmo token exibido pelo `--plan`:

```bash
rtk .venv/bin/python tools/release_host.py update \
  --to origin/main \
  --confirm-update ATUALIZAR-<rollback>-PARA-<target>
```

Somente dois argv privilegiados existem no controlador, ambos delegados ao
instalador canônico:

```text
bigsudo /usr/bin/python3 tools/install_host.py install ...
bigsudo /usr/bin/python3 tools/install_host.py rollback ...
```

O sucesso automático declara `deploymentHealthy=true` e sempre mantém
`physicalCertification=false`. Boot físico, controles, vídeo, áudio e jogo real
continuam sendo gates do operador, nunca inferidos do offscreen ou do daemon.

### Journal, retomada e quarentena

O lock e os journals ficam em
`${XDG_STATE_HOME:-~/.local/state}/steamzero/release-automation/transactions`.
O evento `discovered` é persistido antes do download. Depois são gravados,
atomicamente e com `fsync`, os estados:

```text
discovered → bundle-verified → preflight-passed → approved → install-started
→ activated → convergence-passed → smokes-passed → committed
```

Em falha pós-ativação:

```text
rollback-required → rollback-started → rollback-activated
→ convergence-passed → rollback-verified → failed-safe
```

Se o rollback também falhar, serviço e socket são parados e o terminal é
`rollback-failed`, com comando exato de recuperação. Journals registram somente
identidade de release/commit, hashes, fase, horário e resumo allowlisted; senha,
token, credencial, ROM e caminhos de biblioteca/usuário são descartados.

Reexecutar `update` encontra a transação não terminal sob o mesmo lock. Se o
target já estiver ativo, ele é verificado e commitado somente se saudável; caso
contrário, o rollback é completado idempotentemente. Uma release que falha após
ativação recebe estado `failed-verification` em `quarantine/` e deixa de ser
elegível para nova ativação automática.

### Provas antes do commit

Depois da ativação, `update` exige:

- `current`, manifesto, versão, commit e hashes da release esperada;
- duas convergências, sendo a segunda sem restart nem nova tentativa;
- identidade do daemon e executável pertencentes ao venv ativo;
- doctor `ok=true`, socket e serviço ativos;
- `steamzero-gamemode-session --check` verde;
- `Main.qml` iniciado por cinco segundos em Qt offscreen e estado XDG temporário;
- hash de `state.db` do usuário inalterado.

Qualquer reprovação nessa etapa inicia o rollback automático. O target permanece
instalado para diagnóstico, sem voltar a ser candidato silenciosamente.

## Diagnóstico read-only

Pode ser chamado de qualquer worktree:

```bash
rtk .venv/bin/python tools/release_host.py inspect
```

O relatório compara:

- branch, `HEAD`, `origin/main`, limpeza e versão do pacote;
- symlink `current`, release e commit do manifesto instalado;
- autenticação do GitHub CLI;
- CLI, doctor, socket e serviço;
- `component list`.

O diagnóstico de componentes é informativo. Enquanto GAP-G27 estiver aberto,
uma falha de lifecycle AppImage/Flatpak é publicada como falha; a automação não
tenta “corrigir” instalando ou trocando o default.

## Preparar o bundle do CI

`prepare` não constrói wheel local. Ele descobre o run `push` verde do commit,
baixa o artifact nomeado pelo SHA, extrai o wheelhouse em diretório temporário,
valida tudo e só então renomeia o diretório para o destino:

```bash
rtk .venv/bin/python tools/release_host.py prepare \
  --commit SHA_COMPLETO \
  --output /caminho/duravel/a42-SHA12
```

Precondições:

- GitHub CLI autenticado;
- worktree limpa;
- `HEAD == origin/main == --commit`;
- saída inexistente ou vazia.

Repetir contra destino preenchido reprova. Isso impede juntar arquivos de runs
diferentes.

Um bundle já obtido pode ser conferido sem rede:

```bash
rtk .venv/bin/python tools/release_host.py verify-bundle \
  --bundle /caminho/duravel/a42-SHA12
```

## Instalar

Instalação requer autorização explícita atual para a release e o rollback. O
token contém a release canônica e evita aplicar uma versão que mudou entre
planejamento e execução:

```bash
rtk .venv/bin/python tools/release_host.py install \
  --bundle /caminho/duravel/a42-SHA12 \
  --rollback-release 0.1.0a41-31b30211ba85 \
  --confirm-install INSTALAR-0.1.0a42-SHA12
```

A automação exige que o rollback já exista com manifesto. Este comando legado
não possui rollback automático; prefira `update` para uma ativação supervisionada.
Depois do instalador:

1. converge para a release esperada;
2. repete o converge e exige idempotência;
3. roda doctor;
4. exige socket e serviço ativos;
5. relê `current`.

Eventos são acrescentados atomicamente em
`${XDG_STATE_HOME:-~/.local/state}/steamzero/release-automation/<release>.json`.
Esse arquivo é evidência operacional, não contém keys, ROM paths ou tokens.

## Rollback e ciclo físico

Rollback isolado:

```bash
rtk .venv/bin/python tools/release_host.py rollback \
  --release 0.1.0a41-31b30211ba85 \
  --confirm-rollback REVERTER-0.1.0a41-31b30211ba85
```

Ciclo completo, depois de autorização explícita:

```bash
rtk .venv/bin/python tools/release_host.py cycle \
  --bundle /caminho/duravel/a42-SHA12 \
  --rollback-release 0.1.0a41-31b30211ba85 \
  --confirm-cycle \
  '0.1.0a42-SHA12->0.1.0a41-31b30211ba85->0.1.0a42-SHA12'
```

Cada direção inclui duas convergências. O resultado `machineCycle=passed` prova
somente instalação, rollback, roll-forward, doctor, units e idempotência. Não
equivale a UI física, boot, Game Mode, lançamento de ROM ou `verified-hw`.

## Publicar tag e pre-release

Publicação exige:

- checkout limpo no commit do bundle;
- GitHub CLI autenticado;
- notes existentes;
- JSON de certificação aprovado;
- confirmação exata da tag.

Formato mínimo da certificação:

```json
{
  "schemaVersion": 1,
  "release": "0.1.0a42-SHA12",
  "sourceCommit": "SHA_COMPLETO",
  "verdict": "approved",
  "requiredGates": {
    "machineCycle": true,
    "physicalUi": true,
    "canonicalRomLaunch": true,
    "statePreserved": true
  }
}
```

Todos os valores declarados em `requiredGates` precisam ser `true`. O arquivo
não é gerado automaticamente porque os gates físicos não podem ser inferidos de
CI, VM ou offscreen.

```bash
rtk .venv/bin/python tools/release_host.py publish \
  --bundle /caminho/duravel/a42-SHA12 \
  --certification /caminho/A42-CERTIFICATION.json \
  --notes /caminho/A42-RELEASE-NOTES.md \
  --confirm-publish v0.1.0a42
```

Se a tag já existir no commit exato, a operação é idempotente. Se apontar para
outro commit, a automação reprova. A tag nunca é movida e force-push não existe
no código. A pre-release recebe wheel, wheelhouse compactado, manifesto, lock,
checksums, SBOM, auditoria, proveniência, manifesto da automação e certificação.
Depois do upload, o digest SHA-256 publicado pelo GitHub é comparado com cada
arquivo local; asset ausente é retomado, asset divergente reprova sem
`--clobber`.

## Falhas que devem parar o agente

- credencial GitHub inválida;
- branch ou base obsoleta;
- worktree suja;
- mais de um run verde candidato;
- checksum, proveniência, lock, wheel ou commit divergente;
- rollback não instalado;
- `current` diferente do alvo;
- converge, idempotência, doctor ou unit reprovados;
- certificação ausente, parcial ou de outra release.

Depois de uma dessas falhas, preserve o journal/evidência e diagnostique a
causa. Se `update` terminou `failed-safe`, o host já voltou à release anterior e
o comando ainda retorna erro para que a release reprovada não pareça aprovada.
Não substitua a automação por uma sequência manual que pule o gate reprovado.
