"""Relational teacher plans, schedule versions, proposals, execution and evidence, revision 008.

Additive: creates only missing tables. No data import (see services/workspace_import.import_workspace_plans), no destructive downgrade.
Run against a BACKED-UP or ISOLATED database copy.
"""
from sqlalchemy import inspect

from backend.app.models.teacher_planning import (
    TeacherPlan, TeacherPlanEvidence, TeacherPlanExecution, TeacherPlanProposal, TeacherPlanVersion,
)

revision = '008_plan_tables'
TABLES = [TeacherPlan, TeacherPlanVersion, TeacherPlanProposal, TeacherPlanExecution, TeacherPlanEvidence]


def upgrade(connection):
    existing = set(inspect(connection).get_table_names())
    for model in TABLES:
        if model.__table__.name not in existing:
            model.__table__.create(connection, checkfirst=True)


def downgrade(connection):
    raise RuntimeError('Destructive plan-history downgrade forbidden; restore a backup instead')
