# AURA mídia rica — promoção bloqueada

Data: 2026-09-16  
Item: `SZ-AURA-RICH-MEDIA-PROJECTION`  
Commit de origem: `a5f3ed144f3d44adbf89f4979268e4ec58e35193`  
Release candidata: `2.0.0rc1-a5f3ed144f3d`  
CI do `main`: `35108255871`

## Resultado

O bundle foi preparado e verificado pelo fluxo governado. Duas tentativas do
comando `release_host.py install` ficaram aguardando autenticação interativa
do `pkexec` e foram encerradas sem ativação. A release efetivamente ativa
permaneceu `2.0.0rc1-0bd3942a0d41`.

As verificações read-only após o encerramento confirmaram serviço convergido,
`state audit` limpo, nenhum staging/backup/journal órfão e nenhum reinício do
KDE. Não há PNG de entrega nesta evidência: o apply não chegou a ocorrer, logo
a captura física de fanart e a medição pós-release continuam abertas.

Próxima ação: repetir o mesmo fluxo governado quando o operador puder concluir
a autenticação do polkit; depois aplicar uma mídia `fanart` real pela rota
autorizada, verificar a separação da capa e capturar a janela instalada.
