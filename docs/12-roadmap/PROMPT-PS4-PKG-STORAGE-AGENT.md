# Prompt para agente — ingestão automática de conteúdo PS4, mídia e armazenamento resiliente

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

## Princípio de experiência

O usuário escolhe uma pasta, disco, share ou arquivo. O sistema faz a descoberta,
classificação, agrupamento e busca de mídia automaticamente. Não exija que o
usuário renomeie arquivos, separe base/patch, remova `psgames.by` ou informe
title ID manualmente. Só peça confirmação quando houver ambiguidade real; em
qualquer outro caso preserve o conteúdo e degrade para um fallback legível.

## Entrega

Implemente uma camada independente de ingestão e reconciliação de conteúdo PS4,
preferencialmente em
arquivos novos, por exemplo:

```text
src/steamzero/domain/ps4_content_reconciliation.py
tests/unit/test_ps4_content_reconciliation.py
```

A camada deve oferecer operações puras e transacionais equivalentes a:

```text
scan(source_roots)
classify(content)
resolve_game(content_sources)
resolve_media(media_identity)
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
- convergir PKG, patch, pasta extraída e ISO para um único `gameId` quando a
  identidade interna for compatível;
- reconhecer automaticamente PKG, pastas com `sce_sys`/`param.sfo`/`eboot.bin`,
  ISO, BLS, PUP e componentes SELF/ELF/`.sprx`/`.prx`;
- classificar PUP como firmware, BLS como container e executáveis/módulos como
  componentes internos, nunca como jogos independentes;
- não renomear, mover ou apagar os PKGs originais;
- validar conteúdo real, title ID, content ID, versão, tipo e hashes;
- distinguir base e patch mesmo quando os nomes forem ruins;
- modelar dependência patch → base;
- derivar `MediaIdentity` com plataforma, title ID, título canônico, edição,
  região e aliases;
- buscar mídia por title ID + plataforma + edição antes de usar título/alias;
- guardar provider, ID externo, papel de mídia, hash, licença, confiança e
  `matchedBy`;
- nunca associar arte de outro jogo por semelhança de nome; usar fallback quando
  não houver correspondência segura;
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
- não trate o nome do arquivo como identidade do jogo;
- não transforme PKG em ZIP/7Z;
- não apague duplicatas;
- não use caminho absoluto como identidade;
- não baixe mídia durante o scan sem plano; o jogo deve aparecer imediatamente
  com placeholder quando a mídia estiver indisponível;
- não alegue prova física sem release instalada e captura verificável.

## Testes mínimos

Crie fixtures pequenas com cabeçalhos/metadata sintéticos e teste:

1. base + patch compatível;
2. patch sem base;
3. pasta extraída com `sce_sys/param.sfo` e `eboot.bin`;
4. ISO sem suporte comprovado pelo adapter;
5. PUP excluído do catálogo de jogos;
6. BLS inspecionado sem associação cega;
7. mesmo conteúdo em dois roots;
8. volume removível com mount point alterado;
9. share de rede indisponível;
10. caminho relativo contendo espaços e acentos;
11. hardlink permitido;
12. reflink indisponível;
13. cópia exigida com custo declarado;
14. mídia exata por title ID;
15. mídia conflitante ou provider ausente com fallback;
16. falha no apply preservando o manifesto anterior;
17. rollback;
18. apresentação sem expor o ID técnico como título principal.

Execute os gates exigidos pelo repositório, registre as falhas pré-existentes
separadamente e entregue:

- commit isolado;
- relatório com arquivos exclusivos tocados;
- contrato de integração para o owner do PS4/shadPS4;
- instruções de apply/verify sem mutação automática do host.
