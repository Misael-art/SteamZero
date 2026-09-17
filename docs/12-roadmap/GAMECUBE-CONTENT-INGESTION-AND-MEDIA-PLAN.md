# Plano GameCube — ingestão, multi-disc, mídia e otimização RVZ

## Objetivo

Permitir que o usuário escolha uma pasta, arquivo, unidade removível ou compartilhamento e o SteamZero descubra jogos GameCube sem renomeação, conversão manual ou conhecimento dos formatos de dump.

O catálogo deve apresentar:

```text
Título do jogo - Edição [GAME_ID]
```

Internamente, cada entrada deve preservar `systemId=gamecube`, Game ID, região, edição, disco, formato, origem, hashes, controles e histórico de conversão.

## Separação do Wii

GameCube e Wii continuam usando o mesmo runtime Dolphin, mas não podem compartilhar identidade de catálogo:

```text
platformId: nintendo-console
adapterId: dolphin
systemId: gamecube
```

O `systemId` deve ser resolvido pelo cabeçalho e metadados internos. Extensão ou nome externo não são suficientes. Isso impede que mídia, capa, controles e launch profile do Wii sejam atribuídos a GameCube.

O manifesto e adapter atuais são compartilhados: [manifesto Nintendo Console](../../../src/steamzero/platform_manifests/11-nintendo-console.platform.json) e [adapter Dolphin](../../../src/steamzero/adapters/manifests/dolphin.adapter.json).

## Formatos

O Dolphin documenta suporte a GCM/ISO, GCZ, CISO, WIA e RVZ. [FAQ oficial do Dolphin](https://tv.dolphin-emu.org/docs/faq/)

O resolver deve reconhecer:

```text
iso/gcm
rvz
gcz
ciso
wia
dol
elf
```

`DOL` e `ELF` devem ser classificados como homebrew/executável quando não houver metadados de jogo comercial. WBFS, NFS, WAD, WiiWare, Virtual Console e NAND title pertencem a fluxos Wii e não devem virar GameCube sem identificação interna comprovada.

## Identidade

```text
gameGroupId: gamecube:<canonical-work-id>
mediaId: gamecube:<discId>:<region>:<mediaType>
sourceId: fingerprint + volume/share + relative path
```

Ordem de identificação:

1. Game ID interno do disco;
2. região;
3. metadados do volume;
4. número do disco;
5. hash e estrutura;
6. nome normalizado como fallback confirmado.

Variantes regionais, edições e fontes com hashes diferentes não podem ser mescladas silenciosamente.

## Multi-disc

Jogos com dois discos devem formar um único conjunto lógico:

```text
gameGroupId
├── Disc 1
│   ├── discId
│   ├── hash
│   └── activePath
└── Disc 2
    ├── discId
    ├── hash
    └── activePath
```

A associação usa identidade interna, número do disco, hash, vínculo explícito e nome normalizado apenas como fallback. Não criar dois jogos porque os nomes diferem.

O sistema não deve gerar `.m3u` automaticamente sem prova de que o fluxo Dolphin exige esse descritor. A troca de disco deve ficar no contrato do adapter e no launch/session controller.

## RVZ opt-in

RVZ é o formato recomendado para economia de espaço, mas a conversão nunca é automática. A fonte original continua ativa por padrão.

Antes da conversão, o usuário escolhe explicitamente:

```text
Otimizar para RVZ
```

O plano mostra:

```text
sourceBytes
estimatedRvzBytes
temporaryBytes
savedBytes
estimatedTime
conversionProfile
```

Fluxo:

```text
ISO/GCM ativa
→ usuário opta por RVZ
→ reservar e calcular staging
→ converter em background
→ validar leitura, metadados e integridade
→ registrar variante RVZ
→ oferecer “Usar RVZ”
→ ativar somente após verify e confirmação
```

Regras:

- não converter durante o scan;
- manter a origem lançável durante o job;
- limitar CPU e I/O;
- pausar durante jogo ativo;
- permitir pausa, cancelamento e retomada;
- remover somente staging incompleto em falha;
- ativar RVZ somente após verify;
- permitir rollback;
- nunca apagar ISO automaticamente;
- remoção posterior da origem é outra operação explícita.

Registro:

```text
sourceFormat
derivedFormat: rvz
originalHash
rvzHash
originalBytes
rvzBytes
temporaryBytes
savedBytes
conversionTool
conversionProfile
lossiness
state: planned | running | paused | verified | active | failed | rolled-back
```

O usuário deve entender a diferença entre RVZ, CISO e GCZ antes de converter. O produto não deve afirmar que todas as conversões são equivalentes.

## Requisitos e controles

Jogos GameCube em disco não devem exigir firmware ou BIOS genérica para aparecer como prontos. IPL, quando necessária para um fluxo específico, deve ser requisito pontual.

Fontes auxiliares não são jogos:

```text
memory card
GCI save
save state
shader cache
configuration
```

Perfis de controle devem reconhecer:

```text
GameCube controller
WaveBird
bongos
microphone
dance mat
steering wheel
GBA Link
standard gamepad fallback
```

Periférico ausente gera aviso acionável, sem ocultar o jogo.

## Armazenamento e mídia

```text
volumeOrShareIdentity
relativePath
contentFingerprint
lastKnownPath
mountHints
```

Hardlink/reflink somente no mesmo filesystem. Imagens grandes devem ser referenciadas, não duplicadas por padrão.

Busca de mídia:

1. `systemId=gamecube + discId`;
2. região e edição;
3. número do disco;
4. título canônico;
5. aliases;
6. nome externo como fallback.

GameCube nunca deve receber arte de Wii por similaridade textual baixa.

## Fluxo e estados

```text
scan
→ identificar GameCube/Wii
→ ler Game ID e região
→ classificar formato
→ agrupar multi-disc
→ resolver mídia e controles
→ oferecer RVZ opt-in
→ plan
→ apply
→ verify
→ publish catalog
→ launch preflight Dolphin
```

Estados:

```text
discovered
classified
identified
multi-disc-grouped
rvz-opt-in-available
conversion-running
conversion-paused
conversion-failed
controller-missing
media-pending
missing-source
invalid-source
verified
ready
needs-review
unsupported
```

## Fases

1. **Contrato e fixtures** — GameCube/Wii, formatos, homebrew e multi-disc.
2. **Resolver seguro** — Game ID, região, fontes e classificação.
3. **Conversão RVZ opt-in** — job de baixa prioridade, espaço, pausa, cancelamento, verify e rollback.
4. **Catálogo e mídia** — `systemId=gamecube`, identidade estável e fallback.
5. **Controles e preflight** — periféricos e lançamento Dolphin.
6. **Validação física** — imagem GameCube, conversão RVZ opt-in e multi-disc quando disponível.

## Critérios de aceite

- Wii e GameCube compartilham Dolphin, mas não identidade, mídia ou controles.
- ISO/GCM, RVZ, GCZ, CISO e WIA são classificados pelo conteúdo real.
- DOL/ELF sem identidade comercial não viram jogos falsos.
- Multi-disc forma um único conjunto lógico.
- RVZ é recomendado, mas sempre opt-in.
- Conversão RVZ não bloqueia interface nem jogo em execução.
- Fonte original permanece ativa até verify e confirmação.
- Falha, cancelamento e rollback não danificam a origem.
- BIOS não é exigida genericamente para jogos GameCube.
- SD, USB e rede sobrevivem à mudança do ponto de montagem.
- Mídia usa `systemId=gamecube` e Game ID antes do nome.
- Nenhum arquivo de tema, launcher, Wii, PS3, PS4 ou Vita é alterado.

