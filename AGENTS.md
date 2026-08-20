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
- Antes de delegar ou iniciar uma frente, registre/atualize o `workstream` em
  `docs/status/workstreams/` e leia `docs/ACTIVE-WORK.md`. Caminhos exclusivos
  não podem ser compartilhados por duas frentes ativas; arquivos compartilhados
  só entram no commit final de integração.
- Toda capacidade e toda alteração normativa precisa ter um item em
  `docs/status/items/` com escopo, evidência e próxima ação. Rode `make
  status-check`; não alegue estado a partir de um relatório, roadmap ou WORKLOG.
- `docs/WORKLOG.md`: não toque durante o trabalho; ao final, apenas ACRESCENTE a
  sua própria sessão de fechamento (nunca edite sessões anteriores). A reserva
  de início pertence ao workstream, não a um bloco provisório no WORKLOG.

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
`.venv/bin/ruff check src tools tests`,
`.venv/bin/ruff format --check src tools tests`, `.venv/bin/mypy src`,
`make independence boundaries`. Cobertura não regride. Nunca enfraqueça ou
delete um teste para passar; se um contrato mudou de verdade, documente no
commit qual e por quê.

> Incidente 2026-08-03: o CI aplicou `ruff format` por conta própria no PR #46
> (CONTROLS-E2E) porque o gate de formatação rodou só lá. `ruff check` não cobre
> formatação; rode `ruff format --check` antes de commitar.

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

## 9. Execução autônoma, entrega física e evidência visual

O padrão deste projeto é execução contínua, orientada a entregas reais. Uma vez
definidos o item, a branch e as autorizações necessárias, o agente avança sem
pedir confirmação entre etapas ou perguntar se deve continuar. Atualizações
intermediárias devem ser curtas e sempre informar: resultado observado, bloqueio
concreto (se houver) e próxima ação.

Cada item deve seguir este ciclo, sem pular etapas aplicáveis:

1. reproduzir o defeito ou registrar um baseline verificável;
2. identificar a causa raiz e implementar a menor correção completa;
3. executar testes focados durante a investigação e os gates integrais da seção
   6 somente no fechamento da correção;
4. criar commit funcional isolado e fazer push apenas da branch autorizada;
5. acompanhar os gates remotos e, quando a thread atual autorizar explicitamente,
   publicar a release pelo fluxo governado;
6. instalar no host real somente conforme a autorização, o token e os limites da
   seção 1, sem atalhos ou mutações manuais equivalentes;
7. validar a experiência real no artefato instalado, incluindo os fluxos de
   sucesso, erro e recuperação aplicáveis, idempotência, preservação de dados e
   versão efetivamente ativa;
8. registrar evidência física, atualizar status e documentação, criar o commit
   documental isolado e fazer push da branch autorizada;
9. avançar imediatamente ao próximo item elegível.

Push, publicação, instalação, rollback e qualquer outra ação externa ou
privilegiada não são implicitamente autorizados por esta seção. A thread atual
deve conceder a autorização exigida, com o escopo definido pelas seções
anteriores. Depois de concedida, o agente não volta a pedir confirmação entre
passos já abrangidos; tokens de confirmação continuam sendo obtidos e usados
exatamente como o fluxo governado exigir. Sem autorização, o agente conclui tudo
o que for seguro até os gates e o commit local, registra o bloqueio exato e não
simula nem alega entrega física.

Não repita a suíte integral por cautela entre observações do mesmo ciclo. Se uma
falha de infraestrutura se repetir após uma tentativa, trate-a como defeito
reproduzível: teste focado, causa raiz, correção mínima e prova antes de retomar o
item. Um item cuja validação física falhou permanece aberto e volta ao início
desse ciclo; não avance apenas porque os testes automatizados passaram.

Cada etapa fisicamente entregue deve conter ao menos uma captura PNG do resultado
funcional real da release instalada. Quando aplicável, inclua também evidência do
erro controlado e da recuperação. A captura principal deve aparecer no relatório
da etapa e os arquivos devem ficar no diretório de evidências do item, com nomes
ordenados como `01-baseline.png`, `02-entrega-funcional.png` e
`03-recuperacao.png`. Mostre junto a versão/release ativa por evidência verificável
e remova ou oculte tokens, segredos e dados pessoais antes de persistir qualquer
imagem ou registro.

O agente só deve pausar por dependência realmente externa: autorização ainda não
concedida, token obrigatório, ação física exclusiva do operador (como reboot),
segredo indisponível, decisão de produto materialmente ambígua, risco destrutivo
fora do escopo ou bloqueio externo comprovado. Quando houver outro item seguro e
independente no mesmo escopo, registre o bloqueio e prossiga nele autonomamente.

## 10. Taxonomia AURA e dimensão da plataforma de temas

Antes de trabalhar em temas, UI, Launcher, scene graph, assets ou efeitos, leia
obrigatoriamente `docs/01-product/AURA-SURFACES.md` e
`docs/01-product/THEME-ENGINE-AND-STUDIO.md`. O projeto possui quatro capacidades
independentes: **AURA UI**, **AURA Launcher**, **Theme Engine** e **Theme Studio**.
Código, teste, instalação ou captura de uma delas nunca promove o estado de outra.

A filosofia normativa é **“renderize, não edite”**: o pacote guarda o asset-fonte
e uma receita declarativa; variações de cor, contorno, máscara, composição e efeito
são produzidas pela engine e apenas cacheadas. Não aceite múltiplos assets
pré-editados como substituto de uma capacidade prometida pela engine.

Liberdade criativa não amplia a fronteira de confiança. Tema de terceiros não
executa QML, JavaScript, Python, shell, binário, biblioteca ou shader arbitrário;
usa somente scene graph, bindings, componentes e effect nodes allowlisted. Toda
afirmação de desempenho GPU, FPS, memória ou fidelidade visual exige medição no
hardware e na release indicados, nunca inferência de teste offscreen.

## 11. Estude a arquitetura antes de implementar

Nenhuma implementação começa sem localizar, no código existente, quem já resolve
aquele problema. Antes da primeira linha, o agente responde por escrito, no
relatório ou no commit: qual módulo já faz isto, por que ele não serve, e o que
a nova peça acrescenta que a atual não permite. Não achar equivalente é uma
resposta válida — mas só depois de procurar.

A arquitetura deste projeto centraliza decisões de propósito, e as garantias
vêm justamente do acoplamento. Um caminho paralelo não fica "isolado": ele perde
silenciosamente tudo o que o caminho oficial valida.

> Incidente 2026-08-20: o AURA Launcher ganhou scanner de biblioteca, resolução
> de executor, detecção de emulador instalado e provisão automática — todos
> próprios. Cada um duplicava algo existente e perdia o que estava acoplado:
> `scan_library` classifica base/update/DLC e ignora auxiliares; `launch_profile`
> monta argv com ROM atômica e core como propriedade da plataforma;
> `_settings_for_game_with_global` aplica o emulador padrão e
> `_resolve_primary_emulator` já faz o fallback para o primary instalado;
> `launch_game` exige chaves projetadas no Switch e registra a sessão. O caminho
> paralelo teria lançado um `.nsp` de update, sem chaves, e reportado sucesso —
> e chegou a marcar 15 jogos como "não jogáveis" lendo um campo que não é a
> fonte da decisão.

Regras práticas:

- procure por capacidade, não por nome: `grep` pelo verbo (scan, launch, argv,
  install) antes de criar módulo com esse verbo no nome;
- mutação de estado usa o fluxo transacional do projeto (`plan` → `apply`), não
  chamada direta ao executor;
- I/O de arquivo passa por `core.fs`; processo, por adapter; nenhuma das duas
  coisas no domínio;
- toda peça nova declara qual porta consome e qual contrato publica, para que a
  próxima expansão tenha onde se apoiar;
- quando a estrutura atual não couber, a saída é **estendê-la** com o mesmo
  padrão — nunca contorná-la em paralelo.

## 12. Ao terminar

Relatório final com: tabela item→commit→testes que provam; o que ficou fora de
escopo e por quê; ações de host executadas, release ativa e rollback disponível;
e os passos que ainda exigem o operador (especialmente teste físico de boot).
Atualize o item de status, regenere `docs/STATUS.md` e `docs/ACTIVE-WORK.md` e
então acrescente o fechamento ao WORKLOG. Push apenas da SUA branch; nunca force
push.
