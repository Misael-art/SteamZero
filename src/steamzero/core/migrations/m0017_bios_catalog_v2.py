# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""State for catalog-backed BIOS objects and their managed projections."""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    statements = (
        """
        CREATE TABLE bios_object (
          sha256 TEXT PRIMARY KEY,
          size INTEGER NOT NULL,
          state TEXT NOT NULL CHECK (state IN ('present','missing','corrupt')),
          last_validated TEXT NOT NULL,
          operation_id TEXT REFERENCES operation(id)
        );
        """,
        """
        CREATE TABLE bios_identity (
          id TEXT PRIMARY KEY,
          platform_id TEXT NOT NULL REFERENCES platform(id),
          canonical_name TEXT NOT NULL,
          catalog_hash TEXT NOT NULL,
          required INTEGER NOT NULL CHECK (required IN (0,1)),
          UNIQUE(platform_id, canonical_name)
        );
        """,
        """
        CREATE TABLE bios_variant (
          identity_id TEXT NOT NULL REFERENCES bios_identity(id),
          sha256 TEXT NOT NULL REFERENCES bios_object(sha256),
          size INTEGER NOT NULL,
          PRIMARY KEY(identity_id, sha256)
        );
        """,
        """
        CREATE TABLE bios_projection (
          id TEXT PRIMARY KEY,
          identity_id TEXT NOT NULL REFERENCES bios_identity(id),
          consumer_id TEXT,
          relpath TEXT NOT NULL,
          projection_mode TEXT NOT NULL CHECK (projection_mode IN
            ('canonical-symlink','symlink','read-only-store','bind-mount','materialized-copy')),
          technical_reason TEXT,
          status TEXT NOT NULL CHECK (status IN ('present','missing','corrupt')),
          last_validated TEXT NOT NULL,
          operation_id TEXT REFERENCES operation(id),
          UNIQUE(identity_id, consumer_id, relpath)
        );
        """,
    )
    for statement in statements:
        if statement.strip():
            conn.execute(statement)
