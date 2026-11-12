from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import EXPORT_DIR
from app.db import connect
from app.engines.mask_rules import mask_record
from app.repositories import canonical as canon_repo
from app.repositories import exports as export_repo

EXPORT_FIELDS = ("business_key",) + export_repo.EXPORTABLE_FIELDS


def _export_view(item: dict[str, Any]) -> dict[str, Any]:
    return {k: item[k] for k in EXPORT_FIELDS}


def execute_export(conn, export_dir: Path) -> dict[str, Any]:
    """Run one masked export batch over the current canonical items.

    Reads canonical_items read-only (plaintext master data is never rewritten),
    writes a masked JSONL file plus a per-candidate manifest (export_rows), and
    records a batch whose report numbers all come from the same tables the
    Canonical page and the manifest listing read.
    """
    rules = export_repo.rules_map(conn)
    rules_snapshot = {
        field: {
            "mask_type": r["mask_type"],
            "keep_head": r["keep_head"],
            "keep_tail": r["keep_tail"],
        }
        for field, r in rules.items()
    }
    batch_id = export_repo.create_batch(conn, rules_snapshot)
    try:
        items = canon_repo.list_items(conn)
        exported = 0
        skipped = 0
        failed = 0
        file_lines: list[str] = []

        for item in items:
            key = item["business_key"]
            if not key:
                export_repo.insert_row(
                    conn,
                    batch_id=batch_id,
                    business_key="",
                    disposition="skipped",
                    masked=None,
                    note="empty business_key",
                )
                skipped += 1
                continue
            try:
                masked = mask_record(_export_view(item), rules)
            except Exception as exc:  # noqa: BLE001
                export_repo.insert_row(
                    conn,
                    batch_id=batch_id,
                    business_key=key,
                    disposition="failed",
                    masked=None,
                    note=str(exc),
                )
                failed += 1
                continue
            export_repo.insert_row(
                conn,
                batch_id=batch_id,
                business_key=key,
                disposition="exported",
                masked=masked,
            )
            file_lines.append(json.dumps(masked, ensure_ascii=False))
            exported += 1

        export_dir.mkdir(parents=True, exist_ok=True)
        file_path = export_dir / f"batch_{batch_id}.jsonl"
        file_path.write_text(
            "".join(line + "\n" for line in file_lines), encoding="utf-8"
        )

        candidate = len(items)
        canonical_count = canon_repo.count_items(conn)
        manifest_count = export_repo.count_rows(conn, batch_id)
        report = {
            "canonical_count": canonical_count,
            "candidate_count": candidate,
            "exported_count": exported,
            "skipped_count": skipped,
            "failed_count": failed,
            "manifest_count": manifest_count,
            "reconciled": (
                candidate == exported + skipped + failed
                and candidate == canonical_count
                and manifest_count == candidate
            ),
            "file": file_path.name,
        }
        export_repo.finish_batch(
            conn,
            batch_id,
            status="ok",
            candidate=candidate,
            exported=exported,
            skipped=skipped,
            failed=failed,
            file_path=str(file_path),
            report=report,
        )
        conn.commit()
        return export_repo.get_batch(conn, batch_id)
    except Exception as exc:  # noqa: BLE001
        export_repo.finish_batch(
            conn,
            batch_id,
            status="failed",
            candidate=0,
            exported=0,
            skipped=0,
            failed=0,
            file_path=None,
            report={"error": str(exc)},
        )
        conn.commit()
        raise


def run_export() -> dict[str, Any]:
    conn = connect()
    try:
        return execute_export(conn, EXPORT_DIR)
    finally:
        conn.close()
