"""add cloud_upload_attempts, restore_records, replication_snapshots

Revision ID: f4a1b2c3d5e6
Revises: 0681aa0e55cb
Create Date: 2026-10-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f4a1b2c3d5e6'
down_revision = '0681aa0e55cb'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cloud_upload_attempts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('backup_run_id', sa.Integer(), sa.ForeignKey('backup_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False, server_default='s3'),
        sa.Column('bucket', sa.String(200), nullable=True),
        sa.Column('key', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('bytes_uploaded', sa.BigInteger(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_cloud_upload_attempts_backup_run_id', 'cloud_upload_attempts', ['backup_run_id'])

    op.create_table(
        'restore_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('backup_run_id', sa.Integer(), sa.ForeignKey('backup_runs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('target_db', sa.String(200), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('triggered_by_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('safety_backup_path', sa.String(1000), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_restore_records_backup_run_id', 'restore_records', ['backup_run_id'])

    op.create_table(
        'replication_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('primary_host', sa.String(200), nullable=True),
        sa.Column('standby_host', sa.String(200), nullable=True),
        sa.Column('lag_bytes', sa.BigInteger(), nullable=True),
        sa.Column('lag_seconds', sa.Float(), nullable=True),
        sa.Column('is_healthy', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('wal_lsn', sa.String(50), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('replication_snapshots')
    op.drop_index('ix_restore_records_backup_run_id', table_name='restore_records')
    op.drop_table('restore_records')
    op.drop_index('ix_cloud_upload_attempts_backup_run_id', table_name='cloud_upload_attempts')
    op.drop_table('cloud_upload_attempts')
