# Plano Wii — ingestão, NAND, controles e otimização RVZ

## Objetivo

Permitir que o usuário escolha uma pasta, arquivo, unidade removível ou compartilhamento e o SteamZero descubra jogos Wii automaticamente, sem renomeação, conversão manual ou conhecimento de diferenças entre ISO, WBFS, WAD, NAND e RVZ.

O catálogo deve apresentar:

```text
Título do jogo - Edição [GAME_ID]
```

O sistema deve preservar internamente `systemId=wii`, disc ID/title ID, região, edição, formato, origem, hashes, controles e estado de conversão.

## Situação atual

Wii e GameCube estão agrupados no manifesto `nintendo-console` e usam o Dolphin. Isso é correto para o runtime, mas insuficiente para identidade, mídia, controles e conteúdo Wii. O manifesto declara ISO/GCM, WBFS, RVZ, CISO e GCZ, mas ainda não fecha WIA, NFS, WAD, NAND title, separação explícita por `systemId` e a política de RVZ opt-in.

O adapter Dolphin comprova o componente, não a ingestão automática nem a prova física de um jogo Wii real.

## Contrato Dolphin

O Dolphin documenta suporte a GCM/ISO, GCZ, CISO, WBFS, WIA, NFS e RVZ. Também recomenda RVZ para economizar espaço: [FAQ oficial do Dolphin](https://tv.dolphin-emu.org/docs/faq/).

O Dolphin possui caminhos distintos para boot de disco, WAD e títulos instalados na NAND. [Boot.cpp oficial](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/Boot/Boot.cpp)

## Separação Wii/GameCube

O runtime permanece compartilhado:

```text
adapterId: dolphin
platformId: nintendo-console
```

Mas cada registro deve carregar:

```text
systemId: wii | gamecube
```

O `systemId` deve ser resolvido por cabeçalho/metadados internos, não somente pela extensão. Isso evita mídia, controles e launch profiles errados.

## Identidade e fontes

```text
gameGroupId: wii:<canonical-work-id>
mediaId: wii:<discId/titleId>:<region>:<mediaType>
sourceId: fingerprint + volume/share + relative path
```

Fontes reconhecidas:

- ISO/GCM: imagem de disco;
- RVZ: imagem comprimida gerenciada;
- WBFS, CISO, GCZ e WIA: variantes de imagem, com política própria;
- NFS: conteúdo Wii específico, validado pelo adapter;
- WAD: canal, WiiWare ou Virtual Console instalável;
- NAND title: conteúdo já instalado em NAND gerenciada;
- saves, SD card, cache e shaders: dados auxiliares, não jogos.

WAD não pode ser tratado como ISO renomeada. A identidade deve vir do TMD/title ID e do conteúdo validado.

## RVZ opt-in

RVZ é a otimização recomendada para economia de espaço, mas nunca deve ser conversão automática. A fonte original continua ativa por padrão.

O usuário escolhe explicitamente:

```text
Otimizar para RVZ
```

Antes do apply, o plano mostra:

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
fonte original ativa
→ usuário opta por RVZ
→ calcular espaço e staging
→ converter em background
→ validar leitura, metadados e integridade
→ registrar variante RVZ
→ oferecer “Usar RVZ”
→ tornar RVZ ativa somente após confirmação/verify
```

Regras obrigatórias:

- fonte original nunca é apagada automaticamente;
- a origem continua lançável enquanto a conversão ocorre;
- conversão não bloqueia catálogo, tema ou jogo em execução;
- CPU e I/O devem ser limitados;
- o job pausa durante lançamento e jogo ativo;
- o usuário pode pausar, cancelar e retomar;
- falha preserva origem e remove apenas staging incompleto;
- RVZ só vira fonte ativa após verify;
- rollback restaura a fonte anterior;
- remoção da origem é ação posterior, explícita e reversível quando possível.

O modelo deve registrar:

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

WBFS e CISO não devem ser tratados como equivalentes ao RVZ. A interface deve explicar diferenças de compressão e preservação antes de oferecer qualquer conversão.

## WAD e NAND

O fluxo de WAD é separado:

```text
validar WAD
→ ler TMD/title ID/região
→ verificar espaço da NAND gerenciada
→ planejar instalação
→ instalar atomicamente no perfil Dolphin
→ verificar título instalado
→ publicar no catálogo
```

Nunca substituir uma NAND inteira automaticamente. A instalação deve tocar somente títulos gerenciados pelo SteamZero e preservar WAD original.

Estados:

```text
wad-discovered
wad-invalid
nand-target-missing
nand-installed
nand-conflict
nand-needs-review
```

BIOS não deve ser requisito genérico para todo jogo Wii. Jogos em disco devem aparecer como prontos quando a fonte e o Dolphin estiverem prontos; canais ou títulos NAND podem exigir requisitos específicos.

## Controles

O registro deve declarar requisitos de controle quando conhecidos:

```text
Wii Remote
Wii Remote + Nunchuk
Classic Controller
GameCube controller
Balance Board
Wii Wheel
guitarra
bateria
microfone
MotionPlus
```

Ausência de periférico deve gerar aviso acionável, não remover o jogo do catálogo.

## Armazenamento e mídia

```text
volumeOrShareIdentity
relativePath
contentFingerprint
lastKnownPath
mountHints
```

Hardlink/reflink só no mesmo filesystem. ISO, WBFS e RVZ grandes devem ser referenciados, não duplicados por padrão.

Busca de mídia:

1. `systemId=wii + discId/titleId`;
2. região e edição;
3. WAD title ID;
4. título canônico;
5. aliases;
6. nome externo como fallback.

Nunca usar arte de GameCube para Wii por semelhança textual.

## Fluxo completo

```text
scan
→ identificar Wii/GameCube
→ ler disc ID ou WAD/TMD
→ classificar formato
→ associar conversões e conteúdo NAND
→ resolver mídia e controles
→ plan
→ apply
→ verify
→ publish catalog
→ launch preflight
```

## Estados

```text
discovered
classified
identified
rvz-opt-in-available
conversion-running
conversion-paused
conversion-failed
wad-ready
nand-missing
nand-conflict
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

1. **Contrato e fixtures** — Wii/GameCube, formatos de imagem, WAD, NAND e controles.
2. **Resolver seguro** — IDs internos, regiões, formatos e fontes auxiliares.
3. **Conversão RVZ opt-in** — job de baixa prioridade, espaço, pausa, cancelamento, verify e rollback.
4. **WAD/NAND** — instalação limitada, ownership e recuperação.
5. **Catálogo e mídia** — `systemId=wii`, identidade estável e fallback.
6. **Validação física** — jogo em imagem, conversão RVZ opt-in e título WAD/NAND quando disponível.

## Critérios de aceite

- Wii e GameCube compartilham Dolphin, mas não identidade, mídia ou controles.
- ISO, RVZ, WBFS, CISO, GCZ, WIA, NFS e WAD são classificados pelo conteúdo real.
- RVZ é recomendado, mas sempre opt-in.
- Conversão RVZ não bloqueia a interface nem o lançamento de jogos.
- Fonte original permanece ativa até verify e confirmação.
- Falha, cancelamento e rollback não danificam a origem.
- WAD e NAND não são tratados como ISO nem como arquivos comuns.
- BIOS não é exigida genericamente para jogos Wii em disco.
- SD, USB e rede sobrevivem à mudança do ponto de montagem.
- O plano exibe espaço temporário, tamanho final e economia prevista.
- Mídia usa `systemId=wii` e ID interno antes do nome.
- Nenhum arquivo de tema, launcher, PS3, PS4 ou Vita é alterado.

