from app.db import connect

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS sources(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    format TEXT NOT NULL,
    fixture_path TEXT NOT NULL,
    watermark_ts TEXT,
    lookback_seconds INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    note TEXT
);
CREATE TABLE IF NOT EXISTS runs(
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    parsed_count INTEGER NOT NULL,
    upserted_count INTEGER NOT NULL,
    conflict_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staging_rows(
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    business_key TEXT NOT NULL,
    event_ts TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    disposition TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canonical_items(
    id INTEGER PRIMARY KEY,
    business_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    category TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    event_ts TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conflicts(
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    business_key TEXT NOT NULL,
    existing_payload TEXT NOT NULL,
    incoming_payload TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS export_rules(
    field TEXT PRIMARY KEY,
    mask_type TEXT NOT NULL,
    keep_head INTEGER NOT NULL DEFAULT 0,
    keep_tail INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS export_batches(
    id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    candidate_count INTEGER NOT NULL,
    exported_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    rules_json TEXT NOT NULL,
    file_path TEXT,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS export_rows(
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    business_key TEXT NOT NULL,
    disposition TEXT NOT NULL,
    masked_json TEXT,
    note TEXT
);
"""

DEFAULT_EXPORT_RULES = [
    # 标题：保留前后各 2 字符，中间打码
    ("title", "keep_edges", 2, 2),
    # 价格：外发时置空
    ("price", "blank", 0, 0),
]


def init_db():
    conn = connect()
    conn.executescript(SCHEMA_SQL)
    if conn.execute("SELECT COUNT(*) c FROM sources").fetchone()["c"] == 0:
        conn.executemany(
            """
            INSERT INTO sources(name, format, fixture_path, watermark_ts, lookback_seconds, enabled, note)
            VALUES (?,?,?,?,?,?,?)
            """,
            [
                (
                    "Alpha Catalog",
                    "json",
                    "alpha_catalog.json",
                    None,
                    0,
                    1,
                    "clean：三件独立货号，首跑应全部 upsert",
                ),
                (
                    "Beta Offers",
                    "jsonl",
                    "beta_offers.jsonl",
                    None,
                    0,
                    1,
                    "dirty：SKU-1001 与 Alpha 同键异价→冲突；另含独立货号",
                ),
                (
                    "Gamma Shelf",
                    "xml",
                    "gamma_shelf.xml",
                    None,
                    0,
                    1,
                    "xml 源：两件独立货号",
                ),
            ],
        )
        conn.execute("INSERT INTO settings(key, value) VALUES ('project_label', 'Feedstitch')")
        conn.execute("INSERT INTO settings(key, value) VALUES ('default_mode', 'incremental')")
        conn.commit()
    if conn.execute("SELECT COUNT(*) c FROM export_rules").fetchone()["c"] == 0:
        conn.executemany(
            """
            INSERT INTO export_rules(field, mask_type, keep_head, keep_tail, updated_at)
            VALUES (?,?,?,?,datetime('now'))
            """,
            DEFAULT_EXPORT_RULES,
        )
        conn.commit()
    conn.close()
