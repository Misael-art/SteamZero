# 2. Invariantes do framework

Estas regras complementam, mas não substituem, a governança do repositório.

## 2.1 Fronteiras permanentes

1. Domínio, biblioteca, transações e adapters não dependem de um tema concreto.
2. O tema não cria ações, rotas HTTP, comandos, URIs ou permissões.
3. O QML não lê pacotes externos diretamente; recebe um tema resolvido e validado.
4. Temas externos são dados não confiáveis.
5. O primeiro marco rejeita QML, JavaScript, Python, binários, shaders e links externos.
6. Nenhum caminho absoluto, `..`, symlink ou arquivo fora da raiz do pacote é aceito.
7. O tema padrão nativo é obrigatório, imutável pelo usuário e sempre elegível a fallback.
8. Alto contraste substitui os tokens de contraste relevantes.
9. Movimento reduzido força duração zero, mesmo que o tema declare animações.
10. O tema não pode reduzir alvo interativo abaixo de 48 px nem ocultar foco.
11. O tema não pode modificar texto operacional, código de erro ou estado do backend.
12. Instalar, ativar e remover são operações explícitas, observáveis e reversíveis.
13. O backend e a CLI permanecem operantes sem Qt e sem qualquer tema externo.
14. Ausência de diretório de temas externos é estado normal, não erro.
15. Compatibilidade é recusada por versão de contrato, não “tentada” silenciosamente.

## 2.2 Níveis de confiança

| Origem | Confiança | Capacidades |
|---|---|---|
| `builtin` | empacotada e revisada com o SteamZero | tokens e assets declarativos |
| `user` | conteúdo local não confiável | o mesmo subconjunto declarativo |

No primeiro marco não existe nível “plugin” ou “tema executável”. Qualquer proposta para
scripts, shaders ou componentes QML exige ADR de sandbox, threat model, processo isolado e
testes de fuga antes de entrar no roadmap.

## 2.3 Precedência de valores

Da maior para a menor prioridade:

1. invariantes de segurança e acessibilidade;
2. preferências do host e perfil responsivo;
3. tokens do tema ativo;
4. tema base declarado em `extends`;
5. tema `org.steamzero.default`;
6. constantes seguras compiladas.

## 2.4 Garantias de estado

- A seleção persistida contém apenas `themeId`, `themeVersion` e revisão.
- O tema resolvido contém valores finais; QML não resolve herança.
- Preview fica apenas em memória e expira ao fechar/cancelar.
- Ativação revalida o pacote imediatamente antes de aplicar.
- Remoção do tema ativo exige primeiro selecionar o padrão no mesmo plano ou é recusada.
- Falha na verificação pós-apply restaura a preferência anterior.

## 2.5 Decisões que exigem ADR

- execução de código fornecido por tema;
- download, assinatura e cadeia de confiança remota;
- mudança do toolkit ou suporte ao Game Mode;
- armazenamento de temas em banco;
- novo formato principal de manifesto;
- introdução de dependência estrutural.
