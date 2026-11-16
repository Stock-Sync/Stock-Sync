"""guard: refuse to start with orders that have no tenant

Revision ID: e4b7c2d9f1a3
Revises: c8e2f4a91b73
Create Date: 2026-11-07 10:00:00.000000

The sales database has no way to recover the original tenant of a row created
before tenancy existed. Instead of silently assigning an empty tenant (which
would hide those sales from every user), this migration fails loudly and asks
the operator to either reset the test data (Plano 1) or backfill ``tenant_id``
manually before running ``alembic upgrade head`` again.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b7c2d9f1a3"
down_revision: str | None = "c8e2f4a91b73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


GUARD_MESSAGE = (
    "A tabela 'order' contém linhas com tenant_id nulo ou vazio. "
    "O sales-service não sabe qual era o tenant original dessas vendas e não "
    "faz backfill automático. Resete os dados de negócio (Plano 1) ou "
    "preencha tenant_id manualmente antes de executar 'alembic upgrade head'."
)


def upgrade() -> None:
    bind = op.get_bind()
    invalid = bind.execute(
        sa.text(
            'SELECT COUNT(*) FROM "order" '
            "WHERE tenant_id IS NULL OR tenant_id = ''"
        )
    ).scalar_one()
    if invalid:
        raise RuntimeError(f"{GUARD_MESSAGE} ({invalid} linha(s) inválida(s))")


def downgrade() -> None:
    # The guard is a data check, not a schema change.
    pass
