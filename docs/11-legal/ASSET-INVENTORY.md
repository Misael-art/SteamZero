# ASSET-INVENTORY — inventário fino de assets (G7) — **PREPARATÓRIO**

> **Status (2026-08-10):** rascunho sobre `origin/main@39bd325`. **Não fecha G7.**
> Regenerar com hashes novos sobre o tip final pós–code freeze M10 (árvore
> M10+M11), em commit próprio, antes de qualquer integração como closure.
> Branch de origem: `codex/docs-g7-g32-m14` (preservar; não reescrever).

Inventário **item a item** dos assets binários (e SVG) rastreados no repositório
SteamZero **nessa base**, com origem, licença, hash SHA-256 e se podem ser
redistribuídos com o produto. Complementa `THIRD-PARTY-NOTICES.md` e
`src/steamzero/ui/assets/ATTRIBUTION.md`.

**Escopo:** somente o que está no tree do SteamZero. Assets dos projetos de
referência (EmuDeck / RetroDECK / LinuxToys / PhaseZero) **não** são
redistribuídos; ver §Pendências.

**Regra ADR-0019:** este inventário é documentação legal. Não reintroduz nomes
de projetos de referência em código, UI, units ou paths de runtime.

**Base deste inventário:** commit `39bd325` (`origin/main` no momento do
rascunho). Hashes recalculados localmente em 2026-08-10.

## Legenda

| Campo | Significado |
|---|---|
| Redistribuível | Pode ir no wheel/release do produto com a licença do SteamZero + avisos |
| Fixture-only | Só testes; não acompanha o produto instalado |
| Evidência | Captura operacional/documental; não é asset de produto |
| Marca de terceiros | Nome/logo permanece do titular; uso apenas identificativo |

---

## 1. Ícones de UI empacotados (`src/steamzero/ui/assets/`)

Fonte de atribuição humana: `src/steamzero/ui/assets/ATTRIBUTION.md`.

### 1.1 Derivados BigIcons Papient (GPL-3.0)

Tema [BigIcons Papient](https://github.com/biglinux/bigicons-papient), GPL-3.0,
versão `26.05.05-0223` (distribuição BigLinux). Derivados no SteamZero:

| arquivo | sha256 | bytes | redistribuível |
|---|---|---:|---|
| `dolphin-emu.svg` | `f2ab757b5f65233d936a45855bd0171191add3a2366ccb4df1f046c8af3f460e` | 4252 | sim (GPL-3.0) |
| `duckstation.svg` | `2b5b53465015d05d779cbdb234df8b5f7c7fccaee50e4cbb3281c0a7b31c98da` | 3686 | sim (GPL-3.0) |
| `retroarch.svg` | `dfabf54e28f01133659c8607887b23cf7b7d15dd088c5ce66fa13a32abc1ca78` | 1136 | sim (GPL-3.0) |
| `steam.svg` | `3d6f80eea3007176ac15184ca9223092e9b5a2ded6d6f5f6bc0783b93f7c88d7` | 2056 | sim (GPL-3.0) + marca Valve |

### 1.2 Originais SteamZero (GPL-3.0-or-later)

Fallbacks geométricos / marca própria; **não** reproduzem artwork oficial de
terceiros. Nomes de produtos nas marcas dos titulares.

| arquivo | sha256 | bytes | notas |
|---|---|---:|---|
| `steamzero-mark.png` | `e530c0d3c6ef766527529643875d2955e45cab7e12837bc588298674a9f80e59` | 249110 | marca original 2026-07-16 |
| `switch.svg` | `36125d6f60d5b9ce8fb47a29343864ac028a58cda71948ceae347c73aa4e213c` | 663 | fallback plataforma |
| `nintendo-console.svg` | `abf55ff7d95a71557a962f0f9c57e15cc3561418facda5d80a8729deaafb1796` | 660 | fallback geométrico |
| `nintendo-handheld.svg` | `9413332bc59ccbf249b17bcff278d7f0fe9b6ce98d3469396890c23e7b700c23` | 621 | fallback geométrico |
| `nes-famicom.svg` | `b503b328198515aa48f29af962d3f3800b31d2c30b7b7436be11d55dd615c710` | 682 | fallback geométrico |
| `snes.svg` | `c61ebdab4478cd145aafcf8b0c6606a3c446efb7788767f8be07521d7b3c4400` | 630 | fallback geométrico |
| `mega-drive.svg` | `7581a780433d8cdf2bbe6eebe8dbee47e88724e7bfc39fffffcecb754ee6c180` | 680 | fallback geométrico |
| `arcade.svg` | `e2c9364fbe233a952d27999c4954ad85008422b9f70510dba05a40fe325b3563` | 630 | fallback geométrico |
| `dreamcast.svg` | `c14495cadd84adf8bc8c84567039459afd73fe5cc07f9ab97d51697dd7588a8e` | 525 | fallback geométrico |
| `nintendo-ds.svg` | `f68f4913aada9610ac11acd3110fe7b1ff9b9e66f6143cab325c5489042fe171` | 621 | fallback geométrico |
| `nintendo-3ds.svg` | `1c5c1b9da04d8bce0b52bb511bf2f92ff01f0972c681f8dd187c00dc506e59f1` | 592 | fallback geométrico |
| `playstation.svg` | `f1b64d5a1f3026faa2c586d06bc115fb836c2fdefe68fb71635c6799ed7097d2` | 578 | fallback geométrico |
| `playstation-2.svg` | `6bc4596f5961e1d72f50a7896db6bb0c990970448ae29ea639609ac74ce6363f` | 545 | fallback geométrico |
| `playstation-3.svg` | `689aca5178b96700afd4df9b897863a8805c1ce76e0f44709f351eada54aaed5` | 578 | fallback geométrico |
| `playstation-portable.svg` | `5388c0d384f0621a3a99462020d3b0da6adfc7d4b554961b4d4fe4f43c560a43` | 604 | fallback geométrico |
| `wii-u.svg` | `3acfe4c01c231392148c1b3e56260ce021439f907be344d9ad10896272906413` | 607 | fallback geométrico |
| `xbox.svg` | `2be9b4f3a6c03652767f1bf97c76b7b8f6f852438435f4f9c17d3ccf8db9678a` | 487 | fallback geométrico |
| `xbox-360.svg` | `a42475f4e4d2f17805642bed344232f8d4d74a51772a79c7508409f0224800e2` | 541 | fallback geométrico |
| `geforce-now.svg` | `a540eb8568d46c71cf4852fa13cf7d6a7bf4483ff6420cc671fab153d61a0737` | 594 | fallback geométrico |
| `xbox-cloud-gaming.svg` | `dd03cdbe031253bf370e86a9e515c8647c712a714b0f4fd2dcf80b0466f8ee35` | 541 | fallback geométrico |
| `amazon-luna.svg` | `b1edcde37a8498e923a1636eee2ffef9083d3ab8cfea53e422cd3f0580f7356d` | 608 | fallback geométrico |

### 1.3 Ícones oficiais de emuladores (upstream GPL)

| arquivo | sha256 | bytes | origem | licença | redistribuível |
|---|---|---:|---|---|---|
| `eden.svg` | `5eb45a25fadc62fc35d123b4fe19462b0e7ffffed7dd3f14920e5432b3859769` | 13467 | `eden-emu/eden` → `dist/dev.eden_emu.eden.svg` | GPL-3.0-or-later (projeto) | sim, com atribuição |
| `citron.svg` | `82ff2410c4c061b78de449b69c9051dfb0ddf995b71fe43cbfb6c3ffb9c4fa67` | 11817 | `citron-neo/emulator` → `dist/citron.svg` | GPL-3.0-or-later (projeto) | sim, com atribuição |
| `ryubing.png` | `5c0d69d820bc05376a7ac370ccf8bb9d16f93c17f58dbf7601569498deb0041e` | 8134 | `Ryubing/Assets` → `RyujinxApp_64.png` | conforme repositório de assets Ryubing (uso identificativo do produto) | sim **apenas** como identificação do emulador; marcas permanecem dos titulares |

---

## 2. Fontes de teste — Liberation Sans 2.1.5

Já inventariadas em `THIRD-PARTY-NOTICES.md`. Resumo:

| arquivo | sha256 | uso |
|---|---|---|
| `LiberationSans-Regular.ttf` | `76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8` | fixture-only, OFL-1.1-RFN |
| `LiberationSans-Bold.ttf` | `788abee4c806d660e8aee46689dd8540cd4bb98da03dcc9d171ce3efd99a9173` | fixture-only |
| `LiberationSans-Italic.ttf` | `e5bae5c4cde31f22142753855f4f8fb86da6ff39955ed3c0a11248b0d16948b0` | fixture-only |
| `LiberationSans-BoldItalic.ttf` | `698da70fc191cc5f33ad4d6d3fe830fe4624b898ea2e3169955928b7c491f1ee` | fixture-only |

Local: `tests/fixtures/fonts/liberation-sans-2.1.5/`. **Não** acompanha o produto.

---

## 3. Fixtures de mídia de cena (geradas para teste)

Arquivos sintéticos em `tests/fixtures/scene-media/` (covers de 1 KiB-class).
Autoria: SteamZero; GPL-3.0-or-later; **fixture-only**.

| arquivo | sha256 |
|---|---|
| `cover-01.png` | `6f028f64d28691d528184d809a7c0995098e3c5f93022f4abffb2eab073086a5` |
| `cover-02.png` | `c51109a9677fdb988aa5d65775065cb4c5f7816adf9bfa4943992c6692483143` |
| `cover-03.png` | `c060c0e721b6e6177b4b20da01af1fefa1d0560877d0e7812ad0b17ed070eb20` |
| `cover-04.png` | `1377c7afd78f2795cb5651204c51652d1d149b1e5de9ecb2311a7e52a6acf96b` |
| `cover-05.png` | `af0107948130cc600012e9491abece36c3db979206613b1deaa28f2373273df0` |
| `cover-06.png` | `68a929001564f04adf244979a6fa8497c69a3eaea1c780b2a5b25ed0c6f30610` |
| `cover-fallback.png` | `670a5c65d316ded2fa37d6397280ba0ec32c927677ffaefeda1a73833ad25cd7` |

---

## 4. Baselines visuais (golden)

Capturas geradas pelos harnesses QML do próprio SteamZero sob fontconfig isolado
(ver fechamento G14). Autoria: SteamZero; GPL-3.0-or-later; **fixture-only**
(não são arte de produto).

### 4.1 `tests/qml/golden/`

| arquivo | sha256 |
|---|---|
| `text-baseline.png` | `c06854d9498a9f373122204dd0bd94e718a43d9ab4cd92897835bc56e4b47edd` |
| `text-bold-italic.png` | `1955f109b42910b005b874a4430b13bd0b8e00f4313d804c68f4d90c6ccf4493` |
| `text-bold.png` | `e4976a7bc5bf51e023a878e0b1a68c6ee2b957cad27783c1e87ba98e0a2f1ea6` |
| `text-bottom.png` | `f8720b042083430c66ae6d60168d2ccde613143c474806379acb395ab9c94ee9` |
| `text-centered.png` | `19876ba055b94b54cadf3f6e061e3247864303d5f7060d2c8e80c2073b22afb2` |
| `text-implicit-width.png` | `c06854d9498a9f373122204dd0bd94e718a43d9ab4cd92897835bc56e4b47edd` |
| `text-italic.png` | `672a9b921967f723b7d8d06cba2fccd00eebffb4d133cc32a183fb6f8dee7ad1` |
| `text-portuguese-accents.png` | `32d0bf9bc2208e163104ea1a974f66c3e2b6ba068bf33bc208ca2321d9faadd2` |
| `text-right.png` | `9adb9904a29d064395c01f984f6e47c141c708cfb6ea3734af999c6f4739ea1b` |
| `text-translucent.png` | `321f79dcf08742720bd4c3964e803565106a9d092103d57de4dc0ab204f559e0` |

### 4.2 `src/steamzero/ui/qml/golden/`

Baselines de layout/navegação (screenshots da UI SteamZero). Mesma autoria e
licença; fixture de regressão visual.

| arquivo | sha256 |
|---|---|
| `deck-accessibility-150-1280x800.png` | `f1cda158d15d571086524b75e73378fe169b84bffb76c4f438ecde4f68d413a4` |
| `deck-accessibility-menu-1280x800.png` | `da7562a8c5925bdb08b747ed48f81963dbabb0adaa9ac639e530ce6105576720` |
| `deck-alert-compact-1280x800.png` | `6c55a826732c8a6bb8f3769c852a02a2890d7f64e188344dbc70bd5a94c9f7dd` |
| `deck-alert-expanded-1280x800.png` | `459311f3cf5ba5d6ca73ae1fb8008b34ba4780bb2569596be1818d93f797721a` |
| `deck-emulator-drawer-1280x800.png` | `00bfc8efe3418498330cc04cde9e7b90cfae6670a0a98e0e6a14a8231446591a` |
| `deck-emulators-data-1280x800.png` | `8f1c6a1ccbb24331220dc32913b6f8c35b7767de36683979e9867ac306c9b1f6` |
| `deck-emulators-empty-1280x800.png` | `4d2e47ae564217b971e71a78e3ce265afb8bb454087d4d4b40e11a2193c36120` |
| `deck-error-feedback-1280x800.png` | `cb7617aec163438cab0e7f645bf8a5571f44c3dd238abe5c7b2320f296f65987` |
| `deck-high-contrast-1280x800.png` | `4b90f86a1280f52fda9b31f51b40285fe6a70b3725274308a3ca5650d95751d7` |
| `deck-loading-1280x800.png` | `6eb8ec89d0917a568f15f9513d179358adc4ae1d453b913ba66e3fd0c46bfc77` |
| `deck-navigation-icons-1280x800.png` | `a1688fbb7a93dcfd38d774c777d632c95e7447b23f56716714b8104626ed673c` |
| `deck-overview-1280x800.png` | `a1688fbb7a93dcfd38d774c777d632c95e7447b23f56716714b8104626ed673c` |
| `deck-section-menu-1280x800.png` | `b30e7e1a9ae77bafb0f541a2f30d91fc25a9bf355664bd78ffc568bfe8cdc97b` |
| `desktop-4k-overview-3840x2160.png` | `f095efde9a75b8966e83fe30ce819e41036ac7a5cae3c05d9d5f063b80cb7510` |
| `fullhd-profiles-1920x1080.png` | `0edf0fe48e4dd10849d0d9b28f61251f83c109aec203d94dc30732aa38b6a8bc` |
| `fullhd-steam-1920x1080.png` | `4a9927f5afd6856455f1fbb9c0d4c3ef464fc00f02b54d1e11f5d435e1da68ad` |
| `fullhd-sync-data-1920x1080.png` | `f04774cf5c586222ade7ac3fe33ed4c61a68deef22586097851b8b83bfcc94cc` |
| `fullhd-system-conflict-1920x1080.png` | `b8aba43836e5d0e037c36e0627c58241eebde5408933681a45cb3dc81518513f` |
| `tv-4k-overview-3840x2160.png` | `477db718be53d850ce1807f0f7824d65d46718a17f463b998332aa48977fae0f` |
| `ultrawide-sync-empty-2560x1080.png` | `6785f04bae68a1b678acf9a87fe6e46220e201ec5ca9e12cace5d89f65f3098a` |

---

## 5. Evidências operacionais (não-produto)

`docs/09-operations/evidence/2026-07-22-handheld-p7/*.png` — capturas de
validação física handheld. Autoria SteamZero; **evidência documental**; não
empacotadas no runtime.

| arquivo | sha256 |
|---|---|
| `dock-2560x1080.png` | `e3a260aa80d69a167455d99ab3cd6605985f302959e6faf14869017379672f50` |
| `internal-1280x800-contrast-retest.png` | `8ac933a5a00bff754312d4c5080611ca6441d7b62dcbccc3098d815bb6795462` |
| `internal-1280x800.png` | `6d10df216da9a5a86a5dcfa2abdef3fed5fba88a292cdb59a4c1a75b610381f9` |

---

## 6. O que **não** está no repositório (e continua proibido sem inventário)

| categoria | status | ação |
|---|---|---|
| Ícones/artes/sons dos quatro projetos de referência | **não presentes** no tree SteamZero | não redistribuir; se no futuro for desejado, inventário item a item **antes** de copiar |
| `other_licenses.txt` do RetroDECK | aplicável só se algo for derivado | revisar só se houver derivação concreta |
| Bancos de hashes No-Intro / Redump | **não embarcados** | verificar termos antes de qualquer redistribuição; preferir gerar de fonte com termos claros |
| Templates de controle / Steam Input de terceiros | **não inventariados como assets de referência** | perfis SteamZero próprios ou gerados; não copiar packs sem licença |
| Artwork oficial de fabricantes (Nintendo, Sony, Microsoft, …) | **não copiado** (fallbacks geométricos) | manter política |

---

## 7. Contagem

| classe | quantidade inventariada |
|---|---:|
| UI assets empacotados | 28 |
| Fontes fixture | 4 |
| Scene-media fixture | 7 |
| Golden tests/qml | 10 |
| Golden ui/qml | 20 |
| Evidência operacional | 3 |
| **Total com hash** | **72** |

## 8. Critério de manutenção

1. Todo asset binário novo no repo **deve** ganhar linha neste inventário + aviso
   em `THIRD-PARTY-NOTICES.md` no mesmo PR.
2. Preferir originais geométricos / próprios a copiar artwork de terceiros.
3. Ícones oficiais de emuladores só com licença compatível (GPL-3.0-or-later ou
   equivalente documentada) e uso identificativo.
4. Releases futuras: SBOM + este inventário alimentam o `THIRD-PARTY-NOTICES`
   gerado (ver plano M14).
