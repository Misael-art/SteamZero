# Evidência física — AURA Launcher, primeira abertura no host (2026-08-26)

Item: `SZ-AURA-LAUNCHER`
Release ativa: **`2.0.0rc1-720928250e1a`**
Host: Valve Jupiter (Steam Deck LCD), tela interna eDP-1

O `nextAction` do item pedia "capturar a primeira evidência FÍSICA do Launcher:
home com acervo real". A captura foi feita — e mostrou um defeito.

## 1. O defeito, na primeira abertura

`01-defeito-home-com-hashes.png` é a home do Launcher rodando da release
instalada, capturada com `spectacle -a` (só a janela, sem o resto da área de
trabalho).

Os cartões da seção **Biblioteca** exibem identificadores em hash no lugar dos
títulos:

```
ae18c7e53583298461a0edea
a9507530c1ddaeeae712f9c3
bc994316d636765e17c21f65
e2553881b8ab608300343652
```

A biblioteca está corretamente ligada — os cartões existem, o foco funciona, a
seção é populada. O que falha é o rótulo.

Comparação que isola o problema: a central desktop (`Main.qml`), no mesmo host e
na mesma release, exibe `Demon Slayer Kimetsu no Yaiba the Hinokami Chronicles 2`
sem dificuldade. O dado tem título; o Launcher é que não o encontrava.

## 2. Causa raiz

A biblioteca canônica publica o rótulo de cada jogo na chave **`name`**. Medido
no acervo real do host:

```
chaves do primeiro jogo: bannerAsset, contentKind, coverUrl, dlcCount,
  emulatorId, evidence, fingerprint, format, id, identityDiagnosis,
  identityScheme, identityVerified, mediaSource, metadataSource, name, path,
  platform, size, state, statusLabel, titleId, updateCount, updateVersion,
  version

id   = ae18c7e53583298461a0edea
name = 1969 (Homebrew) (SMS)
```

Não existe chave `title`. E `build_titles` lia exatamente isso:

```python
titles[identifier] = str(game.get("title") or identifier)
```

Com `title` sempre ausente, o fallback para o id disparava em **todo** o acervo —
não num caso de borda. O comentário da própria função dizia que o título viajava
à parte "para a home não acabar mostrando `celeste` onde o usuário espera
`Celeste`"; a intenção estava certa e a leitura, errada.

## 3. Correção

`build_titles` passa a ler `name`, mantendo `title` como alias aceito porque
outras fontes o usam.

Validado contra o acervo real do host:

```
jogos no acervo real .......... 80
títulos resolvidos ............ 80
ainda caindo no id ............ 0

ae18c7e53583298461a0edea  ->  1969 (Homebrew) (SMS)
1f40d4d28a0476a35c8bbaeb  ->  Aladdin (Music Replacement + Button Fix + improvement)
88f9b356a0d013fdc4285216  ->  Alex Kidd - The Lost Stars (Hack) (Improvements Voice) (SMS)
24c1a173224153c51118fa9a  ->  Alex Kidd 3 Curse in Miracle World (Homebrew) (SMS)
a9507530c1ddaeeae712f9c3  ->  Alex Kidd in Shinobi World (Hack) (Graphics Restoration) (SMS)
```

**Prova negativa**: revertendo `build_titles` para ler só `title`, dois dos
quatro testes novos reprovam.

## 4. O que esta página NÃO prova

A captura `02` com os títulos corretos **não existe**, e não vai existir até que
uma release com esta correção seja instalada. A release atual carrega o defeito;
capturar a home de novo hoje mostraria os mesmos hashes.

Os demais critérios do item continuam abertos e dependem de interação humana:
navegação por controle, lançamento de um jogo real, acompanhamento de sessão e
retorno ao mesmo contexto. Nenhuma automação de clique ou tecla está disponível
neste host — `computer-use` dá timeout, `xdotool` não enxerga janela Wayland
nativa e `ydotool` exigiria subir o `ydotoold`.

## 5. Nota de privacidade

Todas as capturas desta página usam `spectacle -a`, restrito à janela ativa. Uma
tentativa inicial com `spectacle -f` (tela inteira) capturou conteúdo pessoal do
operador alheio ao projeto; o arquivo foi apagado imediatamente e não chegou ao
repositório.
