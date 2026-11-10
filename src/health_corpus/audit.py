"""Audit log writer — must run inside the same transaction as the data write."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

Operation = Literal["INSERT", "UPDATE", "DELETE"]


def write_audit_in_txn(
    conn: psycopg.Connection,
    *,
    audit_id: UUID,
    actor: str,
    operation: Operation,
    entity_kind: str,
    entity_id: UUID,
    before: dict | None,
    after: dict | None,
) -> None:
    """Insert an audit row on the open connection (no commit)."""
    conn.execute(
        """
        INSERT INTO writes_audit
            (id, actor, operation, entity_kind, entity_id, before, after)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            audit_id,
            actor,
            operation,
            entity_kind,
            entity_id,
            Jsonb(before) if before is not None else None,
            Jsonb(after) if after is not None else None,
        ),
    )
