# Plano de cobertura de conteúdo real

Este plano consolida a frente de catálogo para plataformas cujo suporte está
declarado, mas cuja classificação, requisitos e execução ainda precisam de
prova em conteúdo real. A fonte para capacidades declaradas continua sendo os
manifestos e `CAPABILITY-MATRIX.md`; os itens de estado e os relatórios de
certificação registram o que foi de fato verificado.

## Estado declarado hoje

| Plataforma | Runtime declarado | Formatos e política do manifesto | Estado relevante |
|---|---|---|---|
| Nintendo 3DS | Azahar primário; RetroArch fallback | `.3ds`/`.cci`/`.zcci`, `.cxi`/`.zcxi`, `.app`, `.3dsx`, `.axf`, `.elf`; contêiner nativo; auxiliares associados por Title ID | Controles declarados; overview, requisitos, gráficos e mídia permanecem `planned` |
| Wii U | Cemu primário | `.wud`/`.wux`, `.wua`, `.rpx`, `.wuhb`, `.elf`; extração declarada para contêineres; auxiliares associados por Title ID | Perfil de GamePad declarado; overview, requisitos, gráficos e mídia permanecem `planned` |

Essas entradas provam somente o contrato declarativo. Elas não provam que um
arquivo foi corretamente classificado, que chaves/firmware estão válidos, que
um jogo inicia ou que uma jornada foi observada em hardware. Não promover os
estados `planned` com base em manifestos, fixtures ou mera presença de processo.

## Sequência de entrega

1. **Inventário do contrato:** validar extensões, contêineres, conteúdo
   auxiliar, identidade e limite entre arquivo de jogo, update/DLC e material
   do sistema contra os manifestos atuais. Não criar formatos por analogia.
2. **Classificação:** adicionar fixtures pequenas e sintéticas ou dumps
   próprios do operador, fora do repositório. Testar extensões, cabeçalhos,
   arquivos truncados, nomes ambíguos e falso positivo. Resultado ambíguo deve
   permanecer `needs-review`; classificar nunca deve mover nem reescrever a
   origem.
3. **Identidade e associação:** definir como Title ID e metadados verificáveis
   ligam base, update e DLC. Recusar associação quando identidade, plataforma
   ou propriedade do conjunto não confere; não fundir conteúdo homônimo.
4. **Requisitos locais:** enumerar requisitos reais por runtime e região a
   partir de fontes primárias dos projetos correspondentes. Verificar arquivos
   fornecidos pelo usuário localmente, comparar hashes quando houver banco
   confiável, não baixar conteúdo protegido e nunca expor chaves, firmware ou
   caminhos sensíveis em logs.
5. **Preflight e prontidão:** distinguir runtime ausente, requisito ausente,
   formato incompatível, conteúdo incompleto e falha de acesso. A prontidão
   deve falhar antes do spawn quando um requisito declarado faltar e indicar
   ação local segura sem sugerir aquisição de conteúdo protegido.
6. **Mídia e controles:** aceitar a política de arte e metadados já existente;
   não incluir logos ou dumps sem licença. Para 3DS, tratar orientação e duas
   telas como opções explícitas. Para Wii U, tratar GamePad, toque, movimento e
   microfone como capabilities separadas; nenhuma delas se torna pronta só por
   existir um perfil declarativo.
7. **Prova em máquina real:** em instalação identificada, usar apenas conteúdo
   próprio/licenciado; registrar versão do runtime, hashes redigidos, estado
   anterior/posterior, launch, gameplay, retorno e recuperação. Separar prova
   de scanner, readiness, launch e experiência completa.

## Critérios para promover estado

- O manifesto continua validado pelo schema e pela matriz gerada; um novo
  formato só entra com contrato do runtime e fixture que cubra classificação.
- Testes exercitam conteúdo válido, incompleto, malformado, duplicado e
  associação errada entre base/update/DLC, sem modificar a origem.
- Requisitos de sistema são enumerados por evidência primária e checados sem
  vazamento de segredos; ausência ou incompatibilidade bloqueia antes do spawn.
- Verificação de instalação, teste de `--help` e processo vivo não são chamados
  de launch funcional. Cada claim de hardware aponta para relatório físico
  reproduzível.
- `implementation`, `integration`, `verification`, `operation` e
  `distribution` do catálogo são atualizados separadamente; um resultado em
  uma dimensão não promove as demais.

## Fronteiras conhecidas

- 3DS e Wii U têm entradas declarativas, mas seus campos centrais permanecem
  planejados nos manifestos. A tabela de capacidade não certifica conteúdo real.
- O plano não cria requirements, scanners, adaptadores ou suporte de mídia por
  suposição. Cada mudança de código exige revisão independente dos contratos e
  dos gates do componente responsável.
- Os branches 045, 050 e 054 continham sobreposição de roadmap e referências a
  planos/agentes separados que não existem na main. Este documento mantém uma
  única direção verificável e não reanima esses documentos ausentes.
