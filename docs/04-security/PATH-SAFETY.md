# PATH-SAFETY — segurança de caminhos

## Modelo

Toda operação declara sua(s) **raiz(es) permitida(s)** (ex.: `$ROMS`, staging da operação, config do emulador X). `core.fs` só opera dentro delas.

## Regras normativas

1. **Canonicalização primeiro:** `realpath` (resolvendo symlinks) e comparação por prefixo de componentes (não por string) contra a raiz permitida. Precedente: PhaseZero valida scripts de profile com `realpath -m` + case-prefix (common.sh:754-764) e rejeita `..` e absolutos (748-753).
2. **Symlinks em dados do usuário:** ao percorrer bibliotecas, symlink que aponta para fora da raiz = ignorado + relatado (`E-CONTENT-UNSAFE-PATH`); nunca seguido para escrita. Escrita usa `O_NOFOLLOW`/`openat2(RESOLVE_BENEATH)` quando disponível.
3. **Extração de archives:** cada entrada validada antes de materializar (nome sem `..`, sem absoluto, sem NUL, profundidade e contagem limitadas); destino sempre staging.
4. **Nomes de arquivo gerados** (scraping, renomeação): sanitização para conjunto seguro; NFC-normalização; limites de tamanho; sem controle Unicode bidi.
5. **IDs nunca são paths:** UI/API referem entidades por ID do State Store; o mapeamento ID→path é interno (T-05).
6. **Variáveis de path** (`{XDG_DATA_HOME}`, `{ROMS}`) expandidas por tabela fechada — sem expansão de env arbitrária (corrige a classe de risco do `eval config_file=` do RetroDECK framework.sh:564+).
7. **Mount awareness:** antes de escrever, confirmar que o mountpoint esperado (UUID) está montado — nunca escrever no diretório de mountpoint vazio (FM-06).
8. **Case e colisões:** detecção de colisão case-insensitive ao migrar entre filesystems (ext4→FAT/exFAT de microSD).

## Testes (08-testing)

Vetores obrigatórios: `../../etc/passwd`, absoluto, symlink loop, symlink→`$HOME/.ssh`, nome com NUL/newline/bidi, árvore 10k de profundidade, zip com 1M entradas, hardlink cruzando raiz, mountpoint desaparecendo no meio.
