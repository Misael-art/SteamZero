# WI-A3 — Tags, favoritos e coleções inteligentes

## Entrega

- `feat-collection-v1` publica tags, favoritos, atribuições e coleções
  inteligentes em um documento local versionado;
- referências canônicas unem jogos Steam, emulação, cloud e ports sem depender
  de caminhos pessoais;
- regras inteligentes suportam `all`/`any` sobre origem, plataforma, tag e
  favorito, com limites explícitos de tamanho e complexidade;
- o catálogo do Desktop projeta favoritos e tags sobre jogos recentes e calcula
  os membros de cada coleção;
- CLI, daemon e bridge Desktop expõem listagem, preview e aplicação;
- a página inicial oferece favoritos e um resumo das coleções, enquanto o
  gerenciador permite criar tags e coleções sem executar mutações diretamente.

## Segurança e rollback

- toda mutação percorre `plan → preview → confirmToken → apply → verify` usando
  o executor transacional comum;
- o plano fixa ação, revisão e fingerprint; concorrência, token incorreto e
  ownership divergente são recusados antes da escrita;
- o documento rejeita symlink, conteúdo acima de 1 MiB, IDs inseguros,
  referências fora do allowlist, cores inválidas e regras excessivas;
- remoção de tag limpa atribuições e coleções dependentes na mesma transação;
- unset e delete são idempotentes;
- cada operação entra em `feat-operation-history-v1` e o rollback contextual
  restaura o estado anterior com verificação observável.

## Evidência

- suíte integral instrumentada: 1.416 testes aprovados;
- cobertura total: 85,18% (mínimo 85%); domínio de coleções: 86,15%;
- Ruff, mypy strict em 148 módulos, fronteiras e independência: aprovados;
- testes dedicados cobrem tags, favoritos, regras `all`/`any`, cascata,
  idempotência, corrupção, symlink, ownership, CLI e rollback;
- JSON-RPC real e bridge HTTP percorrem listagem → preview → confirmação →
  aplicação, e o histórico desfaz a operação;
- oito harnesses QML offscreen passaram, incluindo o gerenciador em 949×593 e
  1280×800;
- o teste golden do registry valida `feat-collection-v1`.

Estado final: `verified-dev`. Não há alegação de validação em hardware real; a
evidência de UI é exclusivamente offscreen.
