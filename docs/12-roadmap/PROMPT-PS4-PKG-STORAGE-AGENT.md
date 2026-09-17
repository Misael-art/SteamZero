# Prompt para agente — PS4 PKG sem duplicação

Você implementará somente a capacidade descrita em
`docs/12-roadmap/PS4-PKG-STORAGE-RECONCILIATION-PLAN.md`.

## Regra de isolamento

Antes de editar:

1. leia `docs/ACTIVE-WORK.md`;
2. crie uma branch `codex/ps4-pkg-storage-<data>` a partir do tip atual indicado
   pelo coordenador;
3. não edite arquivos em ownership exclusivo de outros workstreams;
4. se a integração exigir um arquivo compartilhado, entregue primeiro um
   contrato/adaptador novo e registre o handoff; não faça merge silencioso em
   `Main.qml`, manifestos PS4, lockfiles, catálogo canônico ou código do Launcher;
5. não instale nada no host e não reinicie KDE.

## Entrega

Implemente uma camada independente de reconciliação de PKG, preferencialmente em
arquivos novos, por exemplo:

```text
src/steamzero/domain/ps4_package_reconciliation.py
tests/unit/test_ps4_package_reconciliation.py
```

A camada deve oferecer operações puras e transacionais equivalentes a:

```text
scan(source_roots)
plan(records, adapter_capabilities)
apply(plan, confirmation)
verify(operation)
rollback(operation)
```

Não crie cópia de 30 GiB durante o scan. O `plan` deve decidir entre
`reference`, `hardlink`, `reflink` e `copy`, informando `additionalBytes` e a
razão da escolha.

## Requisitos obrigatórios

- preservar o nome de apresentação:
  `Bloodborne - Game of the Year Edition [CUSA03173]`;
- não renomear, mover ou apagar os PKGs originais;
- validar conteúdo real do PKG, title ID, content ID, versão, tipo e hashes;
- distinguir base e patch mesmo quando os nomes forem ruins;
- modelar dependência patch → base;
- resolver mídia por identidade de volume/share e caminho relativo;
- tratar volume ausente como `missing`, nunca como novo caminho fixo;
- detectar duplicatas por hash;
- usar hardlink/reflink somente quando o filesystem comprovar suporte;
- manter `pathHint` apenas como informação humana;
- informar cerca de 30,07 GiB de fonte e o acréscimo previsto separadamente;
- medir a área realmente instalada pelo adapter;
- publicar no catálogo somente após verify e contrato de lançamento;
- manter rollback e preservar manifestos anteriores.

## Não faça

- não altere `64-playstation-4.platform.json`;
- não altere `shadps4.adapter.json`, lockfiles ou catálogo canônico;
- não altere `Main.qml`, Launcher/QML ou cena ES-DE;
- não copie arquivos grandes em fixtures;
- não trate o nome `[BASE]` como prova do papel;
- não transforme PKG em ZIP/7Z;
- não apague duplicatas;
- não use caminho absoluto como identidade;
- não alegue prova física sem release instalada e captura verificável.

## Testes mínimos

Crie fixtures pequenas com cabeçalhos/metadata sintéticos e teste:

1. base + patch compatível;
2. patch sem base;
3. mesmo PKG em dois roots;
4. volume removível com mount point alterado;
5. share de rede indisponível;
6. caminho relativo contendo espaços e acentos;
7. hardlink permitido;
8. reflink indisponível;
9. cópia exigida com custo declarado;
10. falha no apply preservando o manifesto anterior;
11. rollback;
12. apresentação sem expor o ID técnico como título principal.

Execute os gates exigidos pelo repositório, registre as falhas pré-existentes
separadamente e entregue:

- commit isolado;
- relatório com arquivos exclusivos tocados;
- contrato de integração para o owner do PS4/shadPS4;
- instruções de apply/verify sem mutação automática do host.
