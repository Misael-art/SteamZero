# REUSE-POLICY — política de reuso de código (§7)

## Árvore de decisão (por trecho/arquivo candidato a reuso)

```
1. A licença do trecho é conhecida?
   não → NÃO COPIAR. Reimplementar por comportamento (ver §Reimplementação).
2. É compatível com a licença do Unified (Q2)?
   não → NÃO COPIAR. Reimplementar por comportamento.
3. O trecho atende SECURITY-REQUIREMENTS (sem eval, strict, validado)?
   não → não copiar literalmente; usar como referência de comportamento e
         reescrever sob os padrões (com atribuição de derivação se a estrutura
         for preservada).
4. Copiar com: SPDX + atribuição (ATTRIBUTION-PLAN) + testes próprios.
```

## Reimplementação independente (para licença incompatível/incerta)

- Trabalhar a partir de: comportamento observável, formatos de arquivo, requisitos documentados nesta fundação — **não** a partir do código-fonte lado a lado.
- Proibido reproduzir: código, comentários, nomes de variáveis idiossincráticos, estrutura exclusiva do original.
- Registrar no PR: "implementação independente da capacidade X (referência de comportamento: <projeto>)".
- Quando a semelhança for inevitável por natureza do problema (ex.: paths padrão do ES-DE), documentar que deriva do **formato público**, não do código.

## Casos já classificados

| Fonte | Classificação |
|---|---|
| PhaseZero `linux/` (transação, envelope, guards) | reuso condicionado a Q3 (titular licenciar); caso contrário, reimplementar — a fundação já captura o comportamento |
| EmuDeck templates `configs/` e estrutura `roms/` | derivação GPL (se Q2=GPL) — maior valor de reuso direto |
| EmuDeck scripts de instalação | NÃO copiar (não atendem requisitos); comportamento capturado na CAPABILITY-MATRIX |
| RetroDECK framework.sh | NÃO copiar (eval); conceitos capturados em CONFIGURATION-SCHEMAS |
| RetroDECK modelo components (manifest/recipe) | conceito (não-copyrightável como ideia) — schema próprio novo |
| LinuxToys libs | conceito de detecção de distro; reimplementar em Python (formato diferente por natureza) |
