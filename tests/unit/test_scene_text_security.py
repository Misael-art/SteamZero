# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato fechado para texto StyledText."""

from steamzero.domain.scene_text_security import sanitize_styled_text


def test_allowlisted_tags_survive_without_attributes() -> None:
    assert sanitize_styled_text("<b>bold</b> <i>italic</i><u>under</u><br>") == (
        "<b>bold</b> <i>italic</i><u>under</u><br>",
        False,
    )


def test_unsafe_tags_and_attributes_are_removed_but_text_survives() -> None:
    sanitized, changed = sanitize_styled_text(
        '<a href="https://example.test"><b onclick="bad()">go</b></a><img src="file:///etc/passwd">'
    )
    assert changed is True
    assert sanitized == "go"


def test_literal_markup_is_escaped() -> None:
    sanitized, changed = sanitize_styled_text("5 < 6 & 7 > 3")
    assert changed is False
    assert sanitized == "5 &lt; 6 &amp; 7 &gt; 3"


def test_safe_entities_are_preserved_without_false_degradation() -> None:
    assert sanitize_styled_text("<b>&lt;tag&gt; &amp; &#x3c;</b>") == (
        "<b>&lt;tag&gt; &amp; &#x3c;</b>",
        False,
    )


def test_script_and_comments_cannot_cross_the_boundary() -> None:
    sanitized, changed = sanitize_styled_text("before<script>alert(1)</script><!-- x -->after")
    assert changed is True
    assert sanitized == "beforealert(1)after"


def test_unbalanced_allowlisted_markup_is_closed_deterministically() -> None:
    assert sanitize_styled_text("<b><i>text</b>") == ("<b><i>text</i></b>", True)
