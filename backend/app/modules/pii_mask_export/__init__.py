"""pii_mask_export — implemented.

Mask sensitive canonical fields per configurable rules, then export a batch
(file + manifest) whose counts reconcile with the canonical list.

- masking engine: app/engines/mask_rules.py
- batch orchestration + reconcile: app/services/export_service.py
- persistence: app/repositories/exports.py (export_rules / export_batches / export_rows)
- API: app/routers/exports.py
- UI: frontend/src/pages/Exports.vue
"""
