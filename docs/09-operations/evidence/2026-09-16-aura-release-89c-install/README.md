# Tentativa de instalação governada da release `89c23730`

O CI principal do merge `89c237308fb648c84af22a15b1c4326d534f998a`
(`35061166953`) terminou verde. O bundle foi preparado e verificado como
`2.0.0rc1-89c237308fb6`, com rollback conhecido
`2.0.0rc1-3c4b563242a9`.

Com a autorização desta thread, o comando `release_host.py install` foi
executado com o token exato `INSTALAR-2.0.0rc1-89c237308fb6`. O fluxo ficou
aguardando autenticação do polkit sem apresentar saída; após aproximadamente
um minuto não havia processo `bigsudo`, `install_host.py` ou helper polkit
visível. O wrapper foi interrompido, sem comando privilegiado alternativo.

A inspeção read-only posterior confirmou release ativa
`2.0.0rc1-3c4b563242a9`, serviço e socket ativos, zero staging/backups/journals
órfãos, zero operações pendentes e zero jobs stale. O KDE não foi reiniciado.
Esta tentativa não constitui instalação nem prova física da candidata.
