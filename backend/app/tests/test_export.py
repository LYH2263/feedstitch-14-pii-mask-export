import json
import sqlite3

import pytest

from app.engines.mask_rules import mask_record, mask_value
from app.repositories import canonical as canon_repo
from app.repositories import exports as export_repo
from app.seed import SCHEMA_SQL
from app.services.export_service import execute_export


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA_SQL)
    yield c
    c.close()


def _item(key, title, price, category="c", rev=1):
    return {
        "business_key": key,
        "title": title,
        "price": price,
        "category": category,
        "event_ts": "2026-11-01T10:00:00Z",
        "source_revision": rev,
        "payload": {},
    }


def _seed_canonical(conn):
    canon_repo.upsert_item(conn, _item("SKU-1001", "Oak Desk Lamp", 129.0), 1)
    canon_repo.upsert_item(conn, _item("SKU-1002", "Walnut Shelf", 249.5), 1)
    conn.commit()


# --- mask engine -----------------------------------------------------------


def test_keep_edges_masks_middle():
    assert mask_value("Oak Desk Lamp", "keep_edges", 2, 2) == "Oa*********mp"
    assert mask_value("Oak Desk Lamp", "keep_edges", 0, 0) == "*************"


def test_keep_edges_short_string_fully_masked():
    assert mask_value("abc", "keep_edges", 2, 2) == "***"


def test_blank_and_hash():
    assert mask_value(129.0, "blank") == ""
    hashed = mask_value(129.0, "hash")
    assert hashed.startswith("sha256:") and len(hashed) == len("sha256:") + 12
    assert mask_value(129.0, "hash") == hashed  # deterministic


def test_none_passthrough_and_invalid_type():
    assert mask_value("x", "none") == "x"
    with pytest.raises(ValueError):
        mask_value("x", "bogus")


def test_mask_record_applies_per_field_rules():
    rules = {
        "title": {"mask_type": "keep_edges", "keep_head": 1, "keep_tail": 1},
        "price": {"mask_type": "blank", "keep_head": 0, "keep_tail": 0},
    }
    out = mask_record({"business_key": "SKU-1", "title": "Lamp", "price": 9.5}, rules)
    assert out == {"business_key": "SKU-1", "title": "L**p", "price": ""}


# --- export service --------------------------------------------------------


def test_export_reconciles_and_masks(conn, tmp_path):
    _seed_canonical(conn)
    export_repo.upsert_rule(conn, "title", "keep_edges", 2, 2)
    export_repo.upsert_rule(conn, "price", "blank", 0, 0)
    conn.commit()

    batch = execute_export(conn, tmp_path)

    assert batch["status"] == "ok"
    assert batch["candidate_count"] == 2
    assert batch["exported_count"] == 2
    assert batch["skipped_count"] == 0
    assert batch["failed_count"] == 0
    report = batch["report"]
    assert report["canonical_count"] == 2
    assert report["manifest_count"] == 2
    assert report["reconciled"] is True

    rows = export_repo.list_rows(conn, batch["id"])
    assert len(rows) == 2
    by_key = {r["business_key"]: r for r in rows}
    assert by_key["SKU-1001"]["masked"]["title"] == "Oa*********mp"
    assert by_key["SKU-1001"]["masked"]["price"] == ""
    assert by_key["SKU-1001"]["masked"]["business_key"] == "SKU-1001"

    # export file exists and matches exported rows
    lines = (tmp_path / f"batch_{batch['id']}.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["title"] == "Oa*********mp"

    # plaintext master data untouched by the export
    assert canon_repo.get_by_key(conn, "SKU-1001")["title"] == "Oak Desk Lamp"
    assert canon_repo.get_by_key(conn, "SKU-1001")["price"] == 129.0


def test_rule_change_applies_to_next_export_only(conn, tmp_path):
    _seed_canonical(conn)
    export_repo.upsert_rule(conn, "price", "blank", 0, 0)
    conn.commit()
    first = execute_export(conn, tmp_path)

    export_repo.upsert_rule(conn, "price", "hash", 0, 0)
    conn.commit()
    second = execute_export(conn, tmp_path)

    first_rows = {r["business_key"]: r for r in export_repo.list_rows(conn, first["id"])}
    second_rows = {r["business_key"]: r for r in export_repo.list_rows(conn, second["id"])}
    assert first_rows["SKU-1001"]["masked"]["price"] == ""
    assert second_rows["SKU-1001"]["masked"]["price"].startswith("sha256:")
    # batch 1 keeps its own rules snapshot for audit
    assert first["rules"]["price"]["mask_type"] == "blank"
    assert second["rules"]["price"]["mask_type"] == "hash"


def test_export_empty_canonical_reconciles(conn, tmp_path):
    batch = execute_export(conn, tmp_path)
    assert batch["status"] == "ok"
    assert batch["candidate_count"] == 0
    assert batch["report"]["reconciled"] is True
    assert (tmp_path / f"batch_{batch['id']}.jsonl").read_text(encoding="utf-8") == ""
