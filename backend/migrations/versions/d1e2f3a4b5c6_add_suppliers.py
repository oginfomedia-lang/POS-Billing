"""Add suppliers table and supplier_id FK on products.

Revision ID: d1e2f3a4b5c6
Revises: c5d8f2e1a3b4
Create Date: 2026-10-09 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd1e2f3a4b5c6'
down_revision = 'c5d8f2e1a3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'suppliers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_code', sa.String(50), nullable=False),
        sa.Column('company_name', sa.String(200), nullable=False),
        sa.Column('contact_person', sa.String(100), nullable=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('alt_phone', sa.String(20), nullable=True),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('gstin', sa.String(15), nullable=True),
        sa.Column('pan', sa.String(10), nullable=True),
        sa.Column('billing_address', sa.Text(), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('state', sa.String(100), nullable=True),
        sa.Column('pincode', sa.String(10), nullable=True),
        sa.Column('country', sa.String(100), nullable=False, server_default='India'),
        sa.Column(
            'payment_terms',
            sa.Enum('immediate', 'net_7', 'net_15', 'net_30', name='paymentterms'),
            nullable=False,
            server_default='net_30',
        ),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_suppliers')),
        sa.UniqueConstraint('supplier_code', name=op.f('uq_suppliers_supplier_code')),
    )
    op.create_index(op.f('ix_suppliers_company_name'), 'suppliers', ['company_name'])

    op.add_column('products', sa.Column('supplier_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f('fk_products_supplier_id_suppliers'),
        'products', 'suppliers',
        ['supplier_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint(op.f('fk_products_supplier_id_suppliers'), 'products', type_='foreignkey')
    op.drop_column('products', 'supplier_id')
    op.drop_index(op.f('ix_suppliers_company_name'), table_name='suppliers')
    op.drop_table('suppliers')
    op.execute("DROP TYPE IF EXISTS paymentterms")
