# WI-F1 — Fundação `core.net`

## Entrega

- cliente HTTP centralizado com HTTPS obrigatório, validação de userinfo,
  allowlist por host e validação do destino final de redirects;
- timeouts, limites por `Content-Length` e corpo recebido, retry exponencial com
  jitter limitado, rate limit por token bucket e cancelamento thread-safe;
- download streaming publicado atomicamente por `core.fs`, sem arquivo parcial;
- transport e respostas fake determinísticos, sem rede;
- migração de todos os consumidores HTTP existentes para `core.net`;
- regra `BND-NET` impede novos clientes HTTP fora da fronteira;
- oito falhas `E-NET-*` registradas com textos fixos e detalhes variáveis.

O TLS usa o contexto verificado padrão do Python/host, com validação de hostname
e CAs. HTTP sem TLS só pode ser habilitado explicitamente para loopback local.

## Evidência

- testes focados de rede, consumidores e fronteiras: 138 aprovados;
- suíte integral: 1265 aprovados em 79,42 s;
- Ruff: aprovado;
- mypy strict: aprovado em 138 arquivos;
- independência e fronteiras: aprovadas, zero violações;
- cobertura limpa: 85,32%;
- `git diff --check`: aprovado.

Estado final: `verified-dev`. Nenhuma conexão real, credencial ou conteúdo
pessoal foi usado; não há alegação `verified-hw`.
