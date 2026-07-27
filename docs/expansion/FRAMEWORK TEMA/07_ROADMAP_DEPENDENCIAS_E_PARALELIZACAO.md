# 7. Roadmap implementável

Cada item abaixo termina em commit próprio e nos quatro gates obrigatórios. O agente não
deve começar uma réplica ampla de cores no QML antes de o contrato e o resolver estarem
testados.

## WI-T0 — Decisão e contrato

Entregas:

- ADR do framework declarativo e da proibição de código externo;
- `theme-manifest-v1.schema.json`;
- exemplos válidos/inválidos;
- testes de contrato e empacotamento do schema.

Aceite: schema fechado, limites documentados, compatibilidade e tokens obrigatórios
provados por teste.

## WI-T1 — Modelo puro e temas builtin

Entregas:

- tipos imutáveis para manifesto, tokens, assets e tema resolvido;
- resolução de defaults e herança;
- `org.steamzero.default`;
- um segundo builtin de referência;
- testes determinísticos de merge, ciclo, versão e fallback.

Aceite: o tema padrão resolvido reproduz os valores atuais de `Main.qml`.

## WI-T2 — Catálogo e fronteira de segurança

Entregas:

- descoberta via `importlib.resources` e XDG;
- validação de diretório, arquivos, limites, imagens e SVG;
- estados `available`, `invalid` e `incompatible`;
- fixtures maliciosas sintéticas.

Aceite: path traversal, symlink, arquivo especial, URL, código e excesso de limites são
recusados sem impedir os temas válidos.

## WI-T3 — Preferência e operações transacionais

Entregas:

- path XDG da preferência;
- `theme-preference-v1.schema.json`;
- leitura segura com fallback;
- preview em memória;
- plan/apply/verify/rollback de instalar, ativar e remover;
- idempotência e recuperação de preferência corrompida.

Aceite: kill/falha entre etapas nunca deixa a central sem tema elegível.

## WI-T4 — Projeção e bridge Desktop

Entregas:

- `dashboard.theme`;
- contratos/rotas allowlisted;
- erros estruturados;
- testes HTTP de autenticação, esquema, concorrência e falha degradada.

Aceite: nenhuma rota recebe path de destino arbitrário e QML não lê filesystem externo.

## WI-T5 — Runtime de tokens QML

Entregas:

- `Theme.qml`/`qmldir`;
- aplicação do resolved theme;
- migração dos hexadecimais e medidas temáveis;
- overrides de alto contraste e movimento reduzido;
- harness offscreen para padrão, builtin alternativo, externo, fallback e preview.

Aceite: tema padrão preserva o visual; `qml6` não emite warnings; foco e 48 px continuam
válidos em 949×593, 1280×800 e monitor.

## WI-T6 — Gerenciador visual

Entregas:

- seção/cartão de temas na UI atual;
- lista com origem, versão, licença, compatibilidade e estado;
- preview, cancelar, aplicar, instalar local e remover;
- confirmação transacional e feedback de erro;
- navegação completa por controle.

Aceite: nenhum fluxo comum exige terminal; fechar/cancelar preview restaura o tema ativo e
o foco de origem.

## WI-T7 — Hardening e documentação

Entregas:

- testes de carga/limites e startup com pacote corrompido;
- atualização de docs de UI, segurança, API, teste e operação;
- apêndice único em `docs/WORKLOG.md`;
- checklist físico do operador.

Aceite: todos os gates verdes e nenhuma alegação de teste físico sem evidência.

## Dependências

```text
T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7
```

T1 pode preparar fixtures visuais em paralelo com T2, mas alterações compartilhadas em
Dashboard/Main ficam nos marcos T4/T5 para minimizar conflitos.

## Itens futuros

- pacotes compactados;
- fontes externas;
- assinatura e catálogo remoto;
- atualização automática;
- editor visual;
- Game Mode;
- extensões executáveis em processo isolado.

Cada item futuro requer nova especificação e não deve ser antecipado “por conveniência”.
