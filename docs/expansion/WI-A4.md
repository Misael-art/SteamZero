# WI-A4 — Anti-bitrot limitado e estado suspect

## Entrega

- `feat-bitrot-v1` publica saúde agregada, contagens, última execução, amostra
  observada, limites efetivos e jobs ativos;
- o verificador consome o catálogo canônico da emulação e não cria um segundo
  inventário de ROMs;
- a primeira leitura segura estabelece uma baseline SHA-256 local; leituras
  posteriores marcam `suspect` quando divergem, sem reparar, substituir,
  quarentenar ou remover conteúdo do usuário;
- a seleção é determinística, prioriza itens suspeitos/antigos e respeita os
  limites de 8 arquivos, 2 GiB e 20 segundos por execução padrão;
- o Job Manager publica progresso por arquivo, bloqueia durante gameplay e
  honra cancelamento em safepoints;
- CLI, daemon e bridge Desktop expõem status, preview e aplicação;
- a página inicial mostra a saúde da coleção e exige revisão antes do re-hash.

## Segurança e privacidade

- arquivos são abertos como regulares com `O_NOFOLLOW`; symlink, ausência e erro
  de leitura degradam para estado explícito;
- caminhos absolutos nunca são persistidos nem publicados; o estado mantém
  somente o ID opaco do catálogo e um fingerprint SHA-256 do caminho;
- o arquivo de estado é privado, atômico, limitado a 2 MiB, sem symlink e
  validado de forma fail-closed;
- o hash é streaming, limitado por tamanho antes da seleção e interrompível
  entre chunks; uma leitura parcial nunca atualiza a baseline;
- o plano `bitrot.scan` não contém ações sobre ROMs e registra os limites que
  serão revalidados no apply;
- `suspect` é evidência para inspeção, não afirma corrupção nem executa cascata.

## Evidência

- suíte integral instrumentada: 1.425 testes aprovados;
- cobertura total: 85,24% (mínimo 85%); domínio anti-bitrot: 90,00%;
- Ruff, mypy strict em 149 módulos, fronteiras e independência: aprovados;
- testes dedicados cobrem baseline, re-hash, divergência, limites de arquivos e
  bytes, deadline, arquivo ausente, symlink, estado corrompido, validação de
  alvos e não alteração da ROM;
- fuzzing com 64 exemplos prova que o parser do estado falha fechado;
- CLI e JSON-RPC real percorrem status → preview → confirmação → job limitado;
- a bridge HTTP percorre GET, plan e apply por rotas allowlisted;
- oito harnesses QML offscreen passaram, incluindo o preview anti-bitrot em
  949×593 e 1280×800;
- o registry e um golden completo validam `feat-bitrot-v1`.

Estado final: `verified-dev`. Não há alegação de validação em hardware real; a
evidência de UI é exclusivamente offscreen. A4 não fecha a cascata de exclusão
de D9 nem a projeção de DLC/firmware/região de D2/D10; esses destinos permanecem
em A7/A8/A12 conforme o ledger, sem duplicação nesta frente.
