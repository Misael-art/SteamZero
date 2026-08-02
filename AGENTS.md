# AGENTS.md — Governança para agentes trabalhando neste repositório

Regras obrigatórias para qualquer agente (IA ou humano) atuando no SteamZero,
especialmente em trabalho paralelo. Cada regra existe por causa de um incidente
real; violar uma delas já quebrou o boot do host em produção.

## 1. Instalação no host exige autorização explícita

Por padrão, agentes não instalam nem revertem releases no host. A exceção é uma
autorização explícita do operador, na thread atual, para instalar ou atualizar o
SteamZero com `bigsudo`. Essa autorização vale somente para a release, branch e
sessão indicadas; não se transfere para outros agentes ou trabalhos futuros.

Quando autorizado, o agente pode executar exclusivamente `bigsudo
/usr/bin/python3 tools/install_host.py install/rollback ...` e as verificações
read-only necessárias. Continua proibido executar `sudo`, usar `bigsudo` para
comandos arbitrários, chamar `steamzero-host` para mutações ou editar diretamente
`/opt/steamzero`, `/usr/local`, `/etc` ou `/boot`.

O caminho preferencial é `tools/release_host.py`. Ele se localiza pelo próprio
arquivo, valida commit/bundle/rollback e gera os únicos argv privilegiados
permitidos acima. A automação não amplia autorização: `install`, `rollback`,
`cycle` e `publish` continuam exigindo autorização explícita na thread atual e
o token exato mostrado pelo comando. Falha de autenticação, CI, hash,
proveniência, convergência ou idempotência encerra o fluxo; o agente não continua
com comandos manuais equivalentes.

> Incidente 2026-07-19: um agente de UI instalou uma release construída de árvore
> desatualizada (sem os entry points de Game Mode). O boot direto caiu no greeter
> por dois dias de trabalho. O preflight do instalador hoje bloqueia essa ativação
> (`recusando ativar release sem binários exigidos pelo boot direto ativo`), mas o
> bloqueio é a última linha de defesa — não substitui os preflights abaixo.

Antes de instalar ou reverter, todos estes preflights são obrigatórios:

- branch e commit de origem identificados, sem base obsoleta;
- quatro gates da seção 6 verdes no commit que será instalado;
- wheel e wheelhouse gerados de fonte commitada, com hash e entry points de boot
  conferidos; nenhuma release é construída de alterações não commitadas;
- release canônica vinculada ao `--source-commit` completo;
- inspeção do estado atual e confirmação de que os artefatos tocados têm os
  marcadores de ownership do SteamZero;
- plano de rollback conhecido antes da ativação.

O agente nunca contorna falha de preflight. Após a instalação, valida versão,
doctor, units e sessões de forma read-only. Reinicialização física continua sendo
ação do operador, depois que o agente declarar o host pronto para o teste.

## 2. Trabalhe só na sua branch e nos seus arquivos

- Crie sua branch a partir da base que o operador indicar e trabalhe SOMENTE nela.
  Nunca commite em branch de outro agente nem em branch já mergeada.
- Respeite o escopo de arquivos da sua tarefa. Se precisar mudar algo fora dele,
  registre no relatório final em vez de editar.
- Arquivo compartilhado entre frentes (ex.: `desktop_dashboard.py`, QML consumido
  por múltiplas tarefas): isole a mudança em commit próprio, por último.
- `docs/WORKLOG.md`: não toque durante o trabalho; ao final, apenas ACRESCENTE a
  sua própria sessão (nunca edite sessões anteriores).

## 3. Base atualizada é pré-requisito, não detalhe

Antes de começar, confirme que sua branch descende do tip atual da linha
principal de desenvolvimento indicada pelo operador. Sintomas de base obsoleta
neste repo (pare e peça rebase se encontrar qualquer um):

- `src/steamzero/__init__.py` com `__version__ = "0.1.0.dev0"`;
- `tools/install_host.py` gerando `"schemaVersion": 1` ou sem `--source-commit`;
- ausência de `src/steamzero/adapters/steam_boot.py` / `steam_session.py`.

> Incidente 2026-07-19: a branch `codex/ui-emulacao` estava sobre base obsoleta;
> o wheel construído dela não tinha a cadeia de boot. Build de árvore velha +
> instalação = host quebrado.

## 4. Não construa artefatos de release fora de pedido explícito

`pip wheel`, wheelhouse e manifestos são parte do fluxo de release do operador.
Agente não roda build de release "para testar" — os testes do repo não precisam
de wheel. Se um wheel aparecer em `dist/` no seu diff, remova-o do commit.

## 5. Artefatos de host têm dono único

- Instalador (`tools/install_host.py`) é dono de: `/opt/steamzero`,
  `/usr/local/bin|libexec|sbin` (symlinks), sessão em
  `/usr/share/wayland-sessions/`, units de usuário, polkit.
- `steam_boot` é dono de: unit oneshot do sistema, entrada GRUB, autologin SDDM,
  `/etc/steamzero/gamemode-user`.
- Todo arquivo publicado carrega marcador (`# SteamZero-Boot-Managed: true` /
  `X-SteamZero-Managed=true`) e o código recusa tocar arquivo sem marcador.
  Preserve esse padrão em qualquer artefato novo; nunca escreva remoção/troca
  de arquivo de host sem checagem de ownership.
- Nunca edite configuração de terceiros (`/etc/sddm.conf`, units alheias). Se a
  precedência do host vencer um drop-in próprio, mude a colocação do NOSSO
  artefato (lição do incidente SessionDir/BigLinux de 2026-07-18, ADR-0020).

## 6. Gates são inegociáveis

Após CADA item (não só no final):
`.venv/bin/python tools/run_tests_isolated.py tests -q`,
`.venv/bin/ruff check src tools tests`, `.venv/bin/mypy src`,
`make independence boundaries`. Cobertura não regride. Nunca enfraqueça ou
delete um teste para passar; se um contrato mudou de verdade, documente no
commit qual e por quê.

## 7. Independência de projetos de referência (ADR-0019)

PhaseZero, RetroDECK e LinuxToys foram apenas pesquisa. Nenhuma referência em
código, string de UI, unit, path ou marcador. O gate `make independence` e
`test_runtime_independence.py` exigem a AUSÊNCIA da referência — não reintroduza
nem "só um comentário".

## 8. Falha degrada, nunca trava

Qualquer caminho novo de boot/sessão deve terminar, no pior caso, em greeter ou
desktop utilizável com causa registrada (journal/status/doctor). Tela preta,
loop de login ou falha silenciosa reprovam a mudança. Padrões existentes:
fallback de desktop em `steam_session`, backoff de autologin, `ExecStartPre` de
limpeza no unit, estado `unknown`/`permissionDenied` no `status()`.

## 9. Ao terminar

Relatório final com: tabela item→commit→testes que provam; o que ficou fora de
escopo e por quê; ações de host executadas, release ativa e rollback disponível;
e os passos que ainda exigem o operador (especialmente teste físico de boot).
Push apenas da SUA branch; nunca force push.
