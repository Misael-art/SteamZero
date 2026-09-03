# Catálogo de temas ES-DE na release instalada — 2026-09-03

Validação funcional do ciclo completo **na release efetivamente ativada no
host**, não em teste.

## Release

| | |
|---|---|
| Release ativa | `2.0.0rc1-e571577faeda` |
| Commit de origem | `e571577faedac20dbb718d66982b7f70666a4c62` |
| Release anterior (rollback) | `2.0.0rc1-8a6bb071b8ba` |
| CI | run `33755674759`, `success` |
| Fluxo | `release_host.py update`, com lock, journal e reversão automática |
| Instalada em | 2026-09-03T12:57:16Z |

`doctor`: todos os checks `pass`, exceto o `boot.direct: unknown` — warn
**pré-existente**, causado por falta de permissão para inspecionar a
configuração de boot, e presente antes desta mudança.

## Ciclo exercido na release instalada

Todas as chamadas via `/opt/steamzero/current/venv/bin/python`, ou seja, contra
o código instalado.

**Contrato.** As cinco ações estão publicadas: `theme.catalog.list`,
`theme.catalog.install`, `theme.catalog.rollback`, `theme.catalog.uninstall`,
`theme.store.gc`.

**Listagem.** Os 5 temas curados com licença, e os 4 excluídos com o motivo
("não declara licença").

**Instalação real** de `org.esde.xmb-menu` a partir do commit fixado:

```
instalado em 67s
  tema: org.esde.xmb-menu afe3b7b61cb2 | licenca: CC-BY-NC-SA-2.0
  creditos: ['anthonycaccese', 'InitialDin (XML original)']
  assets: 596 | ativado: False
  aquisicao: files=596 bytesIngested=69324695
             bytesRepeatedInPackage=358272 bytesSharedWithInstalled=0
```

A cadeia de atribuição sobrevive até o manifesto instalado, que é o que a
licença CC-BY-NC-SA exige. `ativado: False` é deliberado: instalar não troca a
aparência da central.

**Estado após instalar.** `installed=True`, `upToDate=True`, store com 474
blobs e 66,1 MB — 596 arquivos em 474 blobs, porque o pacote repete 358 KB
internamente.

**Coleta com o tema instalado:** `orphans=0`. O GC não toca em nada que tenha
dono.

**Remoção:** `assetsPreserved: True`, e os **474 blobs continuam no disco**. É
a propriedade central do desenho — remover um tema nunca invalida asset que
outro ainda referencia.

**Coleta após a remoção:** 474 órfãos, 66,1 MB. Prévia primeiro (`dryRun:
True`), e só com `apply` o espaço volta. Store final: 0 blobs, 0 bytes.

## O que esta evidência NÃO prova

- **Não há captura PNG**, porque **não há tela**. As rotas estão publicadas no
  contrato e funcionam, mas nenhuma superfície QML as consome ainda: não existe
  um ecrã de temas para fotografar. Chamar isso de "entregue ao usuário" seria
  falso.
- Nenhuma cena ES-DE foi **renderizada**. A cobertura de 95% medida antes é de
  compilação, e um tema instalado ainda não vira aparência.
- Nada foi medido em desempenho, FPS ou memória.

## Reprodução

```bash
/opt/steamzero/current/venv/bin/python - <<'PY'
from steamzero.adapters.desktop_dashboard import DesktopDashboard
d = DesktopDashboard()
print(d.theme_catalog_list())
print(d.theme_catalog_install("org.esde.xmb-menu"))
print(d.theme_store_gc())            # prévia
print(d.theme_catalog_uninstall("org.esde.xmb-menu"))
print(d.theme_store_gc(apply=True))  # recupera o espaço
PY
```
