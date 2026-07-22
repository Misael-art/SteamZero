from __future__ import annotations

from dataclasses import dataclass

STEAM_PORTRAIT_SIZE = (600, 900)
STEAM_LANDSCAPE_SIZE = (920, 430)
STEAM_HERO_SIZE = (1920, 620)
STEAM_LOGO_SIZE = (1024, 512)
STEAM_ICON_SIZE = (256, 256)
UI_PREVIEW_SIZE = (128, 128)

STEAM_PORTRAIT = "steam-portrait"
STEAM_LANDSCAPE = "steam-landscape"
STEAM_HERO = "steam-hero"
STEAM_LOGO = "steam-logo"
STEAM_ICON = "steam-icon"
UI_PREVIEW = "ui-preview"

STEAM_PROFILES: dict[str, tuple[int, int, str]] = {
    STEAM_PORTRAIT: (*STEAM_PORTRAIT_SIZE, "steam_portrait"),
    STEAM_LANDSCAPE: (*STEAM_LANDSCAPE_SIZE, "steam_landscape"),
    STEAM_HERO: (*STEAM_HERO_SIZE, "steam_hero"),
    STEAM_LOGO: (*STEAM_LOGO_SIZE, "steam_logo"),
    STEAM_ICON: (*STEAM_ICON_SIZE, "steam_icon"),
    UI_PREVIEW: (*UI_PREVIEW_SIZE, "ui_preview"),
}


@dataclass(frozen=True)
class OptimizerCapability:
    available: bool
    name: str = ""
    version: str = ""
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.available


@dataclass
class OptimizerProfile:
    kind: str
    width: int
    height: int
    label: str

    @property
    def key(self) -> str:
        return self.label

    @staticmethod
    def steam_profiles() -> list[OptimizerProfile]:
        return [
            OptimizerProfile(kind=k, width=w, height=h, label=lb)
            for k, (w, h, lb) in STEAM_PROFILES.items()
        ]

    @staticmethod
    def profile_sizes() -> dict[str, tuple[int, int]]:
        return {
            STEAM_PORTRAIT: STEAM_PORTRAIT_SIZE,
            STEAM_LANDSCAPE: STEAM_LANDSCAPE_SIZE,
            STEAM_HERO: STEAM_HERO_SIZE,
            STEAM_LOGO: STEAM_LOGO_SIZE,
            STEAM_ICON: STEAM_ICON_SIZE,
            UI_PREVIEW: UI_PREVIEW_SIZE,
        }


KIND_TO_STEAM_PROFILES: dict[str, list[str]] = {
    "box2d": [STEAM_PORTRAIT, STEAM_LANDSCAPE],
    "hero": [STEAM_HERO],
    "logo": [STEAM_LOGO],
    "icon": [STEAM_ICON, UI_PREVIEW],
    "screenshot": [STEAM_LANDSCAPE],
}

MASTER_EXTENSIONS: dict[str, str] = {
    "box2d": ".png",
    "hero": ".jpg",
    "logo": ".png",
    "icon": ".png",
    "screenshot": ".png",
}
