# PLUGIN-MODEL — extensibilidade além dos adapters embutidos

## Postura v1 (conservadora — ver NON-GOALS N6, ADR-0007)

- **Não há loja de plugins nem carregamento automático de diretório.** Carregar "qualquer arquivo encontrado numa pasta" é proibido pelos princípios de segurança (§5.1 do prompt mestre).
- Extensibilidade v1 = **adapters declarativos** (dados, não código): um `adapter.json` + templates pode ser adicionado pelo usuário avançado em `$XDG_DATA_HOME/steamzero/adapters.d/`, mas:
  - hooks de código de terceiros **não são carregados** no v1 (apenas manifestos 100% declarativos);
  - manifesto de terceiro roda com badge "não verificado" e exige confirmação explícita na primeira utilização;
  - fontes de download do manifesto de terceiro exigem sha256 — sem exceção.

## Evolução v2 (condicionada a ADR futuro)

- Plugins com código assinados (chave do projeto ou de autor registrado), sandbox de execução (subprocess com seccomp/landlock ou WASM), API de capacidade explícita e permissões declaradas no manifesto (`needs: [network, config-write:duckstation]`).
- QAM/Decky permanece **adapter opcional da nossa UI**, nunca hospedeiro de lógica (ver 07-ui-ux/QAM-INTEGRATION.md).

## Anti-modelos observados (por que esta postura)

- RetroDECK Configurator despacha nomes de função shell vindos de JSON (`command.zenity` → nome de função global) — funcional, mas equivale a "executar função arbitrária recebida por string" se o JSON for adulterado dentro do sandbox.
- EmuDeck chama funções por convenção de nome construído (`RunFunc.sh`, `"$emuName"_install`) — mesma classe de risco + impossibilita análise estática.
- O Unified só despacha **ações registradas em código** com schema; dados externos jamais escolhem o símbolo a executar.
