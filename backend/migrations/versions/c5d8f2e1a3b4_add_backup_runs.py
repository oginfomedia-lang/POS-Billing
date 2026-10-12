"""add backup_runs table

Revision ID: c5d8f2e1a3b4
Revises: 666ad48a3470
Create Date: 2026-10-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c5d8f2e1a3b4'
down_revision = '666ad48a3470'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'backup_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=200), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('checksum_sha256', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='running'),
        sa.Column('storage_location', sa.String(length=20), nullable=False, server_default='local'),
        sa.Column('cloud_path', sa.String(length=500), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('restore_tested', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('restore_tested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('download_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_backup_runs')),
        sa.UniqueConstraint('filename', name=op.f('uq_backup_runs_filename')),
    )
    op.create_index(op.f('ix_backup_runs_started_at'), 'backup_runs', ['started_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_backup_runs_started_at'), table_name='backup_runs')
    op.drop_table('backup_runs')
