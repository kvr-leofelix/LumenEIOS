"""Additive teaching-mode and independent-learning allocation fields, revision 009.

Existing rows receive INDEPENDENT / zero as neutral values. No classification, allocation,
approval, schedule or execution history is rewritten. Never run against a protected database.
"""
import hashlib

from sqlalchemy import inspect, text

revision = "009_topic_default_modes"


def upgrade(connection):
    inspector = inspect(connection)
    if "teacher_topic_configs" not in inspector.get_table_names():
        return
    have = {c["name"] for c in inspector.get_columns("teacher_topic_configs")}
    if "teaching_mode" not in have:
        connection.execute(text("ALTER TABLE teacher_topic_configs ADD COLUMN teaching_mode VARCHAR(16) NOT NULL DEFAULT 'INDEPENDENT'"))
    if "independent_periods" not in have:
        connection.execute(text("ALTER TABLE teacher_topic_configs ADD COLUMN independent_periods INTEGER NOT NULL DEFAULT 0"))
    # Backfill only machine-generated demo defaults. Teacher customizations and approved imports stay untouched.
    rows = connection.execute(text(
        "SELECT id, topic_key, non_core_periods FROM teacher_topic_configs WHERE origin='demo_default'"
    )).fetchall()
    for row in rows:
        value = int(hashlib.sha256(("teaching-mode:" + row.topic_key).encode("utf-8")).hexdigest(), 16) % 3
        mode = "SHARED" if value == 0 else "INDEPENDENT"
        independent = int(row.non_core_periods) // 2 if mode == "INDEPENDENT" else 0
        connection.execute(text(
            "UPDATE teacher_topic_configs SET teaching_mode=:mode, independent_periods=:independent WHERE id=:id AND origin='demo_default'"
        ), {"mode": mode, "independent": independent, "id": row.id})


def downgrade(connection):
    raise RuntimeError("Destructive planning-config downgrade forbidden; restore a backup instead")
