# LSFG-VK — aquisição, propriedade e rollback

## Escopo

O SteamZero prepara somente a camada Vulkan livre LSFG-VK em escopo do usuário. O
Lossless Scaling (Steam App 993090) é proprietário, precisa ser obtido pelo usuário na
Steam e nunca é baixado, copiado ou redistribuído pelo projeto.

## Fonte pinada

| Campo | Valor |
|---|---|
| Projeto | `PancakeTAS/lsfg-vk` |
| Release | `1.0.0` |
| Asset | `lsfg-vk_noui.zip` |
| SHA-256 do asset | `af5ee1626d9543349245520689da107c3ebc5ef3755086441fbb854173b8e096` |
| SHA-256 da biblioteca | `de4954bcce6904b62b6c48f1525c7fd78b4c2d7f9a959edf621528d9363ebbfd` |

A URL é fixa e allowlisted. Redirecionamentos só são aceitos pelo cliente HTTP depois
da requisição ao asset exato; o conteúdo continua obrigado a corresponder aos dois hashes.

## Gates antes da escrita

1. Host `x86_64`/`amd64`.
2. Manifesto Steam do App 993090 com `installdir` simples e `Lossless.dll` regular no
   diretório correspondente.
3. Download limitado a 2 MiB e SHA-256 do archive exato.
4. ZIP com exatamente `lib/liblsfg-vk.so` e
   `share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json`.
5. Entradas sem symlink e limitadas a 2 MiB; biblioteca validada por hash.
6. Manifesto JSON com a camada `VK_LAYER_LS_frame_generation`; `library_path`
   normalizado para o destino absoluto em `~/.local`.
7. Revisão do plano e `confirmToken` válido.

## Aplicação e recuperação

As duas escritas passam por `core.transaction` com garantia G-FULL. O smoke test relê o
manifesto e recalcula o hash da biblioteca antes do commit. Falha em qualquer etapa aciona
rollback automático; a sessão também expõe **Desfazer** para a última operação. O journal
transacional permanece a fonte de recuperação após interrupção de processo.

## Limite atual

A instalação da camada está implementada. O launcher/reconciliador que injeta a política
LSFG e comprova o estado observado por jogo pertence ao restante de M11; até lá, os
perfis são registrados como `desired`, nunca como aplicados.
