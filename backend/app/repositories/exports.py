from __future__ import annotations

import json
import sqlite3
from typing import Any

# Canonical fields eligible for masking rules. business_key stays plaintext so
# the export manifest can always be reconciled against the canonical list.
EXPORTABLE_FIELDS = ("title", "price", "category", "event_ts", "source_revision")


def list_rules(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT field, mask_type, keep_head, keep_tail, updated_at FROM export_rules"
    ).fetchall()
    configured = {r["field"]: dict(r) for r in rows}
    out = []
    for field in EXPORTABLE_FIELDS:
        out.append(
            configured.get(field)
            or {
                "field": field,
                "mask_type": "none",
                "keep_head": 0,
                "keep_tail": 0,
                "updated_at": None,
            }
        )
    return out


def rules_map(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {r["field"]: r for r in list_rules(conn)}


def upsert_rule(
    conn: sqlite3.Connection,
    field: str,
    mask_type: str,
    keep_head: int,
    keep_tail: int,
) -> None:
    conn.execute(
        """
        INSERT INTO export_rules(field, mask_type, keep_head, keep_tail, updated_at)
        VALUES (?,?,?,?,datetime('now'))
        ON CONFLICT(field) DO UPDATE SET
            mask_type=excluded.mask_type,
            keep_head=excluded.keep_head,
            keep_tail=excluded.keep_tail,
            updated_at=datetime('now')
        """,
        (field, mask_type, keep_head, keep_tail),
    )


def delete_rule(conn: sqlite3.Connection, field: str) -> None:
    conn.execute("DELETE FROM export_rules WHERE field=?", (field,))


def create_batch(conn: sqlite3.Connection, rules_snapshot: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO export_batches(
            status, candidate_count, exported_count, skipped_count, failed_count,
            rules_json, file_path, report_json, created_at
        ) VALUES ('running', 0, 0, 0, 0, ?, NULL, '{}', datetime('now'))
        """,
        (json.dumps(rules_snapshot, ensure_ascii=False),),
    )
    return int(cur.lastrowid)


def finish_batch(
    conn: sqlite3.Connection,
    batch_id: int,
    *,
    status: str,
    candidate: int,
    exported: int,
    skipped: int,
    failed: int,
    file_path: str | None,
    report: dict[str, Any],
) -> None:
    conn.execute(
        """
        UPDATE export_batches SET status=?, candidate_count=?, exported_count=?,
            skipped_count=?, failed_count=?, file_path=?, report_json=? WHERE id=?
        """,
        (
            status,
            candidate,
            exported,
            skipped,
            failed,
            file_path,
            json.dumps(report, ensure_ascii=False),
            batch_id,
        ),
    )


def insert_row(
    conn: sqlite3.Connection,
    *,
    batch_id: int,
    business_key: str,
    disposition: str,
    masked: dict[str, Any] | None,
    note: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO export_rows(batch_id, business_key, disposition, masked_json, note)
        VALUES (?,?,?,?,?)
        """,
        (
            batch_id,
            business_key,
            disposition,
            json.dumps(masked, ensure_ascii=False) if masked is not None else None,
            note,
        ),
    )


def _decode_batch(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["rules"] = json.loads(d.pop("rules_json") or "{}")
    d["report"] = json.loads(d.pop("report_json") or "{}")
    return d


def list_batches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, status, candidate_count, exported_count, skipped_count, failed_count,
               rules_json, file_path, report_json, created_at
        FROM export_batches ORDER BY id DESC
        """
    ).fetchall()
    return [_decode_batch(r) for r in rows]


def get_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, status, candidate_count, exported_count, skipped_count, failed_count,
               rules_json, file_path, report_json, created_at
        FROM export_batches WHERE id = ?
        """,
        (batch_id,),
    ).fetchone()
    return _decode_batch(row) if row else None


def list_rows(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, batch_id, business_key, disposition, masked_json, note
        FROM export_rows WHERE batch_id = ? ORDER BY id
        """,
        (batch_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        masked_json = d.pop("masked_json")
        d["masked"] = json.loads(masked_json) if masked_json else None
        out.append(d)
    return out


def count_rows(conn: sqlite3.Connection, batch_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) c FROM export_rows WHERE batch_id = ?", (batch_id,)
        ).fetchone()["c"]
    )
