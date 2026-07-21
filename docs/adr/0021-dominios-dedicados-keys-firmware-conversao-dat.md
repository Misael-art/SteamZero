# ADR-0021 — Domínios dedicados para keys, firmware, conversão, conteúdo compartilhado e DAT

**Status:** aceito

## Contexto

O backend de emulação de Nintendo Switch exige capacidades que não pertencem ao ciclo de
vida de um emulador: importar/validar keys e firmware, converter ROMs (NSZ), casar hashes
contra um índice DAT, deduplicar conteúdo comum (cache/mods/DLC) e migrar saves. O contrato
de emulador (`adapter-v1`) tem um enum FECHADO de capacidades
(`detect,status,install,update,configure,verify,repair,uninstall,backup,restore`) que a UI e
o engine tratam como estáveis.

Abrir esse enum para acomodar `import-keys`, `convert`, `share-content` etc. acoplaria
responsabilidades heterogêneas ao adapter de emulador, quebraria o contrato estável que a UI
consome e misturaria segredos (keys/firmware) com o fluxo de instalação.

## Decisão

1. **O enum de capacidades de emulador permanece fechado e inalterado.** Nenhuma capacidade
   nova é adicionada ao `adapter-v1`.
2. **Keys, firmware, conversão, conteúdo compartilhado, DAT, saves e shader cache são
   domínios/adapters dedicados**, cada um com seu schema, store e contrato próprios:
   - `keys-db-v1`, `firmware-db-v1` — bancos de hashes/metadados, **nunca conteúdo**.
   - `tool-manifest-v1` — ferramentas de conversão com fonte pinada + hash.
   - `dat-index-v1` — índice de nome canônico por hash, **importação local**, nunca
     redistribuído até validação jurídica (G7).
3. **O adapter de emulador apenas DECLARA seus pré-requisitos** via campos aditivos e
   opcionais `requiresKeys`/`requiresFirmware`. A satisfação desses requisitos é
   responsabilidade dos domínios dedicados, não do engine de instalação.
4. **Compatibilidade retroativa:** `adapter-v1` mantém `schemaVersion: 1`. Os campos novos
   são opcionais; os três manifestos existentes (dolphin/duckstation/retroarch) continuam
   válidos sem alteração. A invariante `requiresKeys.platform ∈ platforms` é verificada no
   loader.
5. **Segredos** (keys/firmware) herdam SR-14: nomes e hashes completos nunca vão para
   log/state/argv em claro. O produto valida o que o usuário já possui; nunca obtém, sugere
   ou baixa keys/firmware/ROMs.

## Consequências

A UI continua consumindo um contrato de emulador estável; capacidades novas evoluem em
contratos próprios, versionados independentemente. Um emulador de Switch é modelado como
"emulador que declara `requiresKeys`/`requiresFirmware`", enquanto a lógica de keys vive num
domínio testável isoladamente. O custo é mais superfícies de contrato — aceitável frente ao
risco de acoplar segredos e conversão ao ciclo de vida de instalação.
