# 9. Critérios de qualidade e aceite

## 9.1 Contrato

- manifesto válido é aceito de forma determinística;
- chaves desconhecidas são recusadas;
- versão incompatível é claramente classificada;
- herança tem limite, ciclo é rejeitado e defaults são completos;
- o schema está presente no pacote Python instalado.

## 9.2 Segurança

- não há execução/import de QML, JS, Python, shader ou binário externo;
- traversal, caminho absoluto, symlink e arquivo especial são recusados;
- imagem é validada pelo conteúdo e pelos limites;
- SVG não acessa rede, arquivo ou código;
- rotas não aceitam destino arbitrário;
- pacote inválido não derruba startup nem catálogo;
- tema externo não altera ação, texto de erro ou foco.

## 9.3 Transação

- preview não persiste;
- ativação exige plano e confirmação;
- preferência é escrita atomicamente;
- falha de verify restaura estado anterior;
- aplicar duas vezes é idempotente ou recusa stale plan de forma estruturada;
- remover tema ativo é recusado ou inclui fallback no mesmo plano;
- builtin nunca é removido.

## 9.4 UI e acessibilidade

- 100% do gerenciador é navegável por D-pad, A e B;
- modal prende foco e o devolve à origem;
- alvo interativo permanece ≥ 48 px;
- foco é sempre visível;
- alto contraste atinge ≥ 7:1 em texto essencial;
- cor não é o único canal de estado;
- redução de movimento força duração zero;
- escala/layout não quebra em 949×593 e 1280×800;
- cancelar preview restaura aparência e foco;
- QML não emite warning ou erro.

## 9.5 Regressão visual

O tema `org.steamzero.default` deve reproduzir a aparência anterior. A prova mínima é:

- catálogo de tokens equivalente aos valores atuais;
- capturas offscreen comparáveis das seções principais;
- revisão do diff visual;
- nenhuma nova cor literal fora do módulo de tema, salvo fixture/teste ou exceção
  documentada.

## 9.6 Desempenho

Metas iniciais, a medir no hardware disponível:

- catálogo de 100 temas sem bloquear a thread QML;
- troca de preview sem reconstruir o backend;
- nenhuma decodificação repetida do mesmo asset a cada refresh;
- startup com fallback não depende de rede;
- limites impedem consumo de memória descontrolado.

Uma meta de FPS físico não pode ser marcada verde por teste offscreen.

## 9.7 Matriz mínima de testes

| Caso | Unit | Integração | QML |
|---|:---:|:---:|:---:|
| builtin padrão | ✓ | ✓ | ✓ |
| builtin alternativo | ✓ | ✓ | ✓ |
| pacote externo válido | ✓ | ✓ | ✓ |
| pacote incompatível | ✓ | ✓ | — |
| manifesto corrompido | ✓ | ✓ | fallback |
| traversal/symlink/código | ✓ | ✓ | — |
| preview/cancel | ✓ | ✓ | ✓ |
| apply/rollback | ✓ | ✓ | ✓ |
| alto contraste | ✓ | — | ✓ |
| movimento reduzido | ✓ | — | ✓ |
| remoção do ativo | ✓ | ✓ | feedback |

## 9.8 Definição de pronto

Uma etapa só está pronta quando:

- seus testes focados passam;
- os quatro gates passam após a etapa;
- o diff respeita o escopo;
- erros têm códigos/feedback estruturado;
- documentação e contrato acompanham a mudança;
- nada foi instalado no host;
- limitações físicas são declaradas como pendentes.
