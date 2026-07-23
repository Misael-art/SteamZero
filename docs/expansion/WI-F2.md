# WI-F2 — Fundação `core.crypto`

## Entrega

- digests canônicos SHA-256, SHA-512 e BLAKE2b para bytes e arquivos regulares;
- leitura streaming sem seguir symlink e comparação constante de checksums;
- assinatura destacada limitada e verificação por `SignatureVerifierPort`;
- verifier HMAC-SHA256 com resolver de chave injetado para envelopes locais;
- envelope v1 autenticado, com nonce, digest, tag, parser estrito e limites;
- consumidores de supply-chain (`AdapterEngine`, registry e LSFG) migrados;
- funções de hash legadas de `core.fs` delegam à fundação canônica.

O envelope garante integridade e autenticidade, não confidencialidade. Payloads
continuam visíveis e não podem conter segredos. As chaves não são persistidas
por este módulo: devem chegar de `SecretStorePort` no ponto de composição.

## Segurança e testes

- testes property-based cobrem roundtrip binário e parser de bytes arbitrários;
- symlinks, arquivos não regulares, base64, schema, tamanhos, alteração de
  payload/tag, chave ausente e algoritmos não permitidos falham fechados;
- nenhum teste usa chave, credencial ou conteúdo pessoal real.

## Evidência

- testes focados: 69 aprovados;
- suíte integral: 1278 aprovados em 81,23 s;
- Ruff: aprovado;
- mypy strict: aprovado em 139 arquivos;
- independência e fronteiras: aprovadas, zero violações;
- cobertura limpa: 85,36%;
- `git diff --check`: aprovado.

Estado final: `verified-dev`, sem alegação de validação física.
