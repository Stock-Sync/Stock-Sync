"""add dedupe_key and listings_sync_run

Revision ID: c4d8e2f1a9b3
Revises: 
Create Date: 2026-10-23 19:55:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4d8e2f1a9b3'
down_revision: str | None = '8e0edf439e6a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('syncevent', sa.Column('dedupe_key', sa.String(length=200), nullable=True))
    op.create_index(op.f('ix_syncevent_dedupe_key'), 'syncevent', ['dedupe_key'], unique=True)
    op.create_table(
        'listingssyncrun',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('items_found', sa.Integer(), nullable=False),
        sa.Column('items_upserted', sa.Integer(), nullable=False),
        sa.Column('mappings_created', sa.Integer(), nullable=False),
        sa.Column('error_summary', sa.String(length=2000), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_listingssyncrun_status'), 'listingssyncrun', ['status'], unique=False)
    op.create_index(op.f('ix_listingssyncrun_tenant_id'), 'listingssyncrun', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_listingssyncrun_tenant_id'), table_name='listingssyncrun')
    op.drop_index(op.f('ix_listingssyncrun_status'), table_name='listingssyncrun')
    op.drop_table('listingssyncrun')
    op.drop_index(op.f('ix_syncevent_dedupe_key'), table_name='syncevent')
    op.drop_column('syncevent', 'dedupe_key')
