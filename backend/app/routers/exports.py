from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.db import connect
from app.repositories import exports as export_repo
from app.schemas.entities import ExportRuleUpdate
from app.services.export_service import run_export

router = APIRouter(tags=["export"])


@router.get("/export/rules")
def list_rules():
    conn = connect()
    try:
        return export_repo.list_rules(conn)
    finally:
        conn.close()


@router.put("/export/rules/{field}")
def put_rule(field: str, body: ExportRuleUpdate):
    if field not in export_repo.EXPORTABLE_FIELDS:
        raise HTTPException(400, f"unknown exportable field: {field}")
    conn = connect()
    try:
        export_repo.upsert_rule(
            conn, field, body.mask_type, body.keep_head, body.keep_tail
        )
        conn.commit()
        return {
            "field": field,
            "mask_type": body.mask_type,
            "keep_head": body.keep_head,
            "keep_tail": body.keep_tail,
        }
    finally:
        conn.close()


@router.delete("/export/rules/{field}")
def reset_rule(field: str):
    conn = connect()
    try:
        export_repo.delete_rule(conn, field)
        conn.commit()
        return {"field": field, "mask_type": "none"}
    finally:
        conn.close()


@router.post("/export/batches")
def create_batch():
    try:
        return run_export()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@router.get("/export/batches")
def list_batches():
    conn = connect()
    try:
        return export_repo.list_batches(conn)
    finally:
        conn.close()


@router.get("/export/batches/{batch_id}")
def get_batch(batch_id: int):
    conn = connect()
    try:
        batch = export_repo.get_batch(conn, batch_id)
        if not batch:
            raise HTTPException(404, "batch not found")
        return batch
    finally:
        conn.close()


@router.get("/export/batches/{batch_id}/rows")
def get_batch_rows(batch_id: int):
    conn = connect()
    try:
        if not export_repo.get_batch(conn, batch_id):
            raise HTTPException(404, "batch not found")
        return export_repo.list_rows(conn, batch_id)
    finally:
        conn.close()


@router.get("/export/batches/{batch_id}/download")
def download_batch(batch_id: int):
    conn = connect()
    try:
        batch = export_repo.get_batch(conn, batch_id)
    finally:
        conn.close()
    if not batch or not batch.get("file_path"):
        raise HTTPException(404, "export file not found")
    path = Path(batch["file_path"])
    if not path.exists():
        raise HTTPException(404, "export file missing on disk")
    return FileResponse(
        path, media_type="application/x-ndjson", filename=path.name
    )
