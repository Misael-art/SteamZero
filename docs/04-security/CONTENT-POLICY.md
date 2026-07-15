# CONTENT-POLICY — política de conteúdo: `local-owned-dump-only`

## Enunciado

A plataforma **organiza, valida e protege** conteúdo que o usuário já possui legalmente. Ela **nunca obtém** conteúdo protegido.

## O sistema NUNCA (proibições absolutas, sem flag de override)

- Procura ROMs/BIOS/keys/firmware protegido em fontes externas.
- Baixa qualquer um desses, de qualquer origem, inclusive "abandonware".
- Sugere, lista ou linka fontes não autorizadas (nem em mensagens de erro, nem em docs de usuário).
- Integra provedores de conteúdo ilegal ou "stores" de ROMs.
- Contorna DRM, criptografia ou verificação de assinatura de console.
- Registra conteúdo de keys em logs, relatórios ou bundles (SR-14).
- Copia conteúdo protegido para qualquer artefato de diagnóstico.

## O sistema PODE

- Importar conteúdo fornecido localmente pelo usuário (pendrive, pasta, rede local dele).
- Validar estrutura e integridade (hashes contra bancos de referência de **hashes**, que não contêm o conteúdo — precedentes: EmuDeck `checkBIOS.sh`, RetroDECK BIOS checker e `config/retrodeck/reference_lists/`).
- Identificar arquivos ausentes ("falta BIOS X para o emulador Y") com ação "importar arquivo local".
- Exibir hashes e metadados; organizar; criar links seguros entre stores e emuladores.
- Alertar incompatibilidades (região/versão/emulador).
- **Orientar o usuário a produzir seus próprios dumps** (guias de dumping do hardware que ele possui), sem links para conteúdo.

## Aplicação técnica

- Não existe código de rede nos módulos Content/Library exceto consulta a bancos de hashes/metadados (dat-files) versionados com o produto.
- Mensagens do ERROR-CATALOG sobre conteúdo ausente têm texto fixo auditado (sem interpolação de sugestões).
- Scraping de mídia usa identificação por hash/nome, e os provedores configurados são de **metadados/arte**, com licença registrada (F-MD-01).

## Revisão

Qualquer feature nova que toque conteúdo passa por checklist desta política no PR (gate de CI com checklist obrigatório).
