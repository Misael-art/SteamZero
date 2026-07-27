# 5. Pacotes, assets e segurança

## 5.1 Formatos de entrada

O primeiro marco deve aceitar um diretório local. Suporte a arquivo compactado só entra
na mesma entrega se reutilizar extração segura já existente ou vier acompanhado de testes
de traversal, symlink, limites e decompression bomb. Caso contrário, fica para um commit
posterior.

Layout:

```text
org.example.ocean/
├── theme.json
├── LICENSE
└── assets/
    ├── background.webp
    └── logo.svg
```

Arquivos inesperados são rejeitados, não ignorados. Isso inclui QML, JS, executáveis,
bibliotecas, sockets, devices e FIFOs.

## 5.2 Limites iniciais

Valores devem ser constantes nomeadas e cobertas por teste:

| Recurso | Limite inicial |
|---|---:|
| `theme.json` | 256 KiB |
| quantidade de arquivos | 128 |
| tamanho total descompactado | 64 MiB |
| asset individual | 16 MiB |
| dimensão raster | 8192 × 8192 |
| profundidade de diretório | 4 |
| profundidade de herança | 2 |
| temas catalogados | 100 |

Se benchmarks justificarem números diferentes, atualizar a especificação e os testes
no mesmo commit.

## 5.3 Validação de caminho

- Abrir a raiz e descendentes sem seguir symlinks.
- Rejeitar caminho absoluto, componente vazio, `.` e `..`.
- Comparar o caminho resolvido com a raiz antes de publicar.
- Validar tipo com metadados do descritor, não apenas pelo sufixo.
- Nunca aceitar URL como asset.
- Não reutilizar nome de arquivo como comando ou argumento de shell.

## 5.4 Sanitização

Raster:

- decodificar com Pillow;
- validar formato real, dimensões e limite de pixels;
- não confiar apenas em MIME ou extensão;
- fechar o arquivo mesmo em erro.

SVG:

- usar parser sem resolução de entidades externas;
- rejeitar scripts, eventos `on*`, `foreignObject`, CSS/URLs externas e referências
  fora do próprio documento;
- preferir rasterização no staging quando a sanitização confiável não puder ser provada.

Fontes:

- adiar por padrão;
- se habilitadas, limitar formatos e tamanho, validar a tabela do arquivo e registrar
  licença; nunca tornar a inicialização dependente da fonte.

## 5.5 Instalação e remoção

Instalação:

1. planejar origem, destino, bytes e riscos;
2. copiar para staging privado;
3. validar manifesto e todos os assets;
4. calcular digest determinístico;
5. recusar colisão de ID/versão sem ação explícita de atualização;
6. publicar atomicamente;
7. reler e verificar o pacote publicado;
8. registrar operação sem dados pessoais de caminho além do necessário.

Remoção:

- builtin é irremovível;
- tema ativo não é removido isoladamente;
- o plano lista exatamente o diretório gerenciado;
- arquivo estranho ou ownership ambíguo bloqueia remoção;
- rollback restaura o pacote quando tecnicamente possível.

## 5.6 Licença e autoria

Manifesto exige licença em identificador SPDX ou valor `LicenseRef-*`. O gerenciador
mostra autor e licença. Assets criados para temas nativos do projeto seguem a licença
do repositório, salvo atribuição explícita.

## 5.7 Assinatura e distribuição

Assinatura criptográfica, catálogo remoto, download e atualização automática não fazem
parte do primeiro marco. O digest local prova integridade entre staging e publicação,
mas não autoria. Não chamar um pacote de “verificado” sem uma cadeia de confiança futura.
