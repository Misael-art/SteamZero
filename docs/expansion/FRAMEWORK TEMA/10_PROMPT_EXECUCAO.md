# 10. Prompt de execução para o agente implementador

Copie o bloco abaixo para uma nova tarefa Codex. Antes de iniciar, substitua somente os
campos entre `<...>` com a base e a branch aprovadas pelo operador.

```text
# Tarefa — implementar o framework declarativo de temas do SteamZero

Implemente integralmente, em sequência e com um commit por marco, o plano em:

/mnt/sdcard/Projects/Port_Steam/docs/expansion/FRAMEWORK TEMA/

## Base e branch

- Base indicada pelo operador: <branch-ou-commit-base>
- Crie uma branch própria: codex/theme-framework
- Não trabalhe nem commite na branch de outro agente.
- Antes de editar, confirme que a branch descende do tip atual da base indicada.
- Se a árvore ou um arquivo compartilhado mudar por outra sessão, pare, mostre o
  conflito e reconcilie a base; não sobrescreva.

## Leitura obrigatória

Leia integralmente:

- AGENTS.md e /home/misael/.codex/RTK.md;
- todos os arquivos de docs/expansion/FRAMEWORK TEMA, na ordem do README;
- docs/adr/0002-ui-godot-gamemode-qt-desktop.md;
- docs/adr/0019-independencia-runtime-isolamento-falhas.md;
- docs/07-ui-ux/ACCESSIBILITY.md;
- docs/07-ui-ux/DESKTOP-MODE-UI.md;
- docs/07-ui-ux/NAVIGATION-BY-CONTROLLER.md;
- docs/08-testing/TEST-STRATEGY.md;
- contratos e testes atuais da bridge Desktop e do QML.

Consulte a memória do projeto antes de decidir arquitetura. Trate ADRs aceitos como
decisões fechadas.

## Objetivo

Acrescentar temas nativos aprimorados e temas locais de terceiros à central Qt/QML
existente. O framework deve ser orientado a dados, offline, transacional, navegável por
controle e resiliente. O backend/CLI devem continuar funcionando sem Qt e sem tema
externo.

Temas builtin e externos usam o mesmo `theme-manifest-v1`. A diferença é somente origem
e confiança. Pacote externo NUNCA executa QML, JavaScript, Python, binário ou shader,
nem acessa rede, paths absolutos ou arquivos fora da raiz.

## Entregas e commits obrigatórios

Execute WI-T0 até WI-T7 conforme
07_ROADMAP_DEPENDENCIAS_E_PARALELIZACAO.md:

1. `theme: define declarative theme contract`
2. `theme: add resolver and builtin themes`
3. `theme: add secure local theme catalog`
4. `theme: add transactional theme preferences`
5. `desktop: expose allowlisted theme controls`
6. `qml: consume resolved semantic theme tokens`
7. `qml: add controller-first theme manager`
8. `docs: close theme framework hardening`

Não compacte os marcos em um commit gigante. Se um marco precisar mudar arquivo
compartilhado, faça essa integração em commit próprio e revalide o arquivo imediatamente
antes de editar.

## Contratos essenciais

- Schema fechado (`additionalProperties: false`) e empacotado no wheel.
- Preferência validada por `theme-preference-v1.schema.json`.
- Tema padrão `org.steamzero.default`, irremovível e sempre elegível.
- Segundo builtin que usa exatamente as mesmas capacidades de tema externo.
- Diretórios XDG derivados por `steamzero.core.paths`.
- QML recebe apenas tema final resolvido; não lê pacote externo.
- Preview é efêmero; ativação/instalação/remoção usam plan + confirmToken + apply +
  verify + rollback.
- Alto contraste e movimento reduzido prevalecem sobre tokens.
- Erro em um pacote degrada aquele pacote e preserva startup/catálogo.
- Rotas são específicas/allowlisted e nunca aceitam comando ou destino arbitrário.
- A instalação pode receber uma origem local explicitamente selecionada, apenas para
  leitura; o destino é sempre derivado no backend do ID validado e da raiz XDG.
- Códigos `E-THEME-*` entram primeiro no catálogo de erros e em seus testes.

## Segurança e testes

Escreva os testes de risco junto da implementação. Cubra no mínimo:

- schema válido, chaves desconhecidas, versão e herança/ciclo;
- traversal, absoluto, symlink, arquivo especial, URL e código proibido;
- limites de tamanho, contagem, profundidade e dimensão;
- raster inválido e SVG ativo/externo;
- tema padrão, alternativo, externo, incompatível e corrompido;
- preview/cancel, apply/rollback, idempotência e remoção do ativo;
- bridge autenticada e falha estruturada;
- QML offscreen em 949×593 e 1280×800;
- foco, alvo de 48 px, alto contraste, movimento reduzido e ausência de warnings;
- empacotamento de schema, builtins, Theme.qml e assets.

Preserve ou aumente cobertura. Não apague, relaxe ou transforme teste comportamental em
asserção tautológica.

## Gates após CADA marco

Todo comando shell deve começar por `rtk`.

rtk .venv/bin/pytest tests -q
rtk .venv/bin/ruff check src tools tests
rtk .venv/bin/mypy src
rtk make independence boundaries

Rode também testes focados e `qmllint`/harnesses QML quando disponíveis. Se Qt estiver
ausente, registre skip; não chame isso de validação física.

## Proibições

- Não usar sudo ou bigsudo.
- Não instalar/reverter release no host.
- Não construir wheel/wheelhouse/dist.
- Não tocar em .env, segredos, wheelhouse, diagnósticos ou fixtures de outra frente.
- Não introduzir nova dependência, migração de banco, marketplace, download remoto,
  editor visual, Game Mode ou tema executável sem parar e pedir decisão/ADR.
- Não force-push.
- Não editar sessões anteriores de docs/WORKLOG.md; no final, apenas acrescente a sua.

## Condições de parada

Pare e peça revisão se:

- a base estiver obsoleta;
- houver mudança concorrente em arquivo compartilhado;
- o tema padrão não preservar o visual;
- um gate falhar por causa desta tarefa;
- segurança depender de “confiar” no pacote;
- for necessário ampliar o escopo.

## Encerramento

Faça revisão final do diff e execute novamente os quatro gates. Entregue:

| Item | Commit | Testes focados | Quatro gates |
|---|---|---|---|

Informe também arquivos/contratos criados, cobertura, riscos, itens adiados, ações de host
(esperado: nenhuma), validações físicas ainda necessárias e a branch publicada. Faça push
apenas da sua branch e nunca force-push.
```
