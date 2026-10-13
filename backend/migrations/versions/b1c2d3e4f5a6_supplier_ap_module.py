"""Supplier AP module: supplier_products, supplier_invoices, supplier_payments,
supplier_documents; add opening_balance to suppliers; add shipping/approval
columns to purchase_orders; add accepted/rejected/batch columns to
goods_receipt_items; extend purchasestatus enum.

Revision ID: b1c2d3e4f5a6
Revises: f4a1b2c3d5e6
Create Date: 2026-10-12 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b1c2d3e4f5a6'
down_revision = 'f4a1b2c3d5e6'
branch_labels = None
depends_on = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _col_exists(conn, table, column):
    r = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
    ), {"t": table, "c": column}).fetchone()
    return r is not None


def _table_exists(conn, name):
    r = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t"
    ), {"t": name}).fetchone()
    return r is not None


def _fk_exists(conn, name):
    r = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE constraint_type='FOREIGN KEY' AND constraint_name=:n"
    ), {"n": name}).fetchone()
    return r is not None


def _index_exists(conn, name):
    r = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname=:n"
    ), {"n": name}).fetchone()
    return r is not None


def upgrade():
    conn = op.get_bind()

    # ── Extend purchasestatus enum ────────────────────────────────────────────
    for val in ('pending_approval', 'approved', 'closed'):
        conn.execute(
            sa.text(f"ALTER TYPE purchasestatus ADD VALUE IF NOT EXISTS '{val}'")
        )

    # ── New enum types (IF NOT EXISTS = idempotent on re-run) ────────────────
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE supplierinvoicestatus AS ENUM "
        "    ('unpaid','partially_paid','paid','cancelled'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    ))
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE invoiceverificationstatus AS ENUM "
        "    ('pending','verified','disputed'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    ))
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE supplierpaymenttype AS ENUM "
        "    ('payment','advance','credit_note','debit_note'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    ))
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE supplierpaymentmethod AS ENUM "
        "    ('cash','bank_transfer','upi','cheque','other'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    ))
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE documententitytype AS ENUM "
        "    ('supplier','purchase_order','goods_receipt',"
        "     'supplier_invoice','supplier_payment'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    ))

    # ── suppliers: add opening_balance ────────────────────────────────────────
    if not _col_exists(conn, 'suppliers', 'opening_balance'):
        op.add_column('suppliers',
            sa.Column('opening_balance', sa.Numeric(12, 2), nullable=False, server_default='0'))

    # ── purchase_orders: add new columns ─────────────────────────────────────
    po_cols = [
        ('shipping_charges', sa.Column('shipping_charges', sa.Numeric(12, 2), nullable=False, server_default='0')),
        ('other_charges',    sa.Column('other_charges',    sa.Numeric(12, 2), nullable=False, server_default='0')),
        ('shipping_address', sa.Column('shipping_address', sa.Text(),         nullable=True)),
        ('approved_at',      sa.Column('approved_at',      sa.DateTime(timezone=True), nullable=True)),
        ('approved_by_id',   sa.Column('approved_by_id',   sa.Integer(),      nullable=True)),
        ('closed_at',        sa.Column('closed_at',        sa.DateTime(timezone=True), nullable=True)),
        ('closed_by_id',     sa.Column('closed_by_id',     sa.Integer(),      nullable=True)),
    ]
    for col_name, col_def in po_cols:
        if not _col_exists(conn, 'purchase_orders', col_name):
            op.add_column('purchase_orders', col_def)

    if not _fk_exists(conn, 'fk_purchase_orders_approved_by_id_users'):
        op.create_foreign_key(
            'fk_purchase_orders_approved_by_id_users',
            'purchase_orders', 'users', ['approved_by_id'], ['id'],
        )
    if not _fk_exists(conn, 'fk_purchase_orders_closed_by_id_users'):
        op.create_foreign_key(
            'fk_purchase_orders_closed_by_id_users',
            'purchase_orders', 'users', ['closed_by_id'], ['id'],
        )

    # ── goods_receipt_items: add quality/batch columns ───────────────────────
    gri_cols = [
        ('qty_accepted', sa.Column('qty_accepted', sa.Numeric(12, 3), nullable=True)),
        ('qty_rejected', sa.Column('qty_rejected', sa.Numeric(12, 3), nullable=False, server_default='0')),
        ('qty_damaged',  sa.Column('qty_damaged',  sa.Numeric(12, 3), nullable=False, server_default='0')),
        ('batch_number', sa.Column('batch_number', sa.String(100),    nullable=True)),
        ('mfg_date',     sa.Column('mfg_date',     sa.Date(),         nullable=True)),
        ('remarks',      sa.Column('remarks',      sa.Text(),         nullable=True)),
    ]
    for col_name, col_def in gri_cols:
        if not _col_exists(conn, 'goods_receipt_items', col_name):
            op.add_column('goods_receipt_items', col_def)

    # ── supplier_products ────────────────────────────────────────────────────
    if not _table_exists(conn, 'supplier_products'):
        op.create_table(
            'supplier_products',
            sa.Column('id',                    sa.Integer(),      nullable=False),
            sa.Column('supplier_id',           sa.Integer(),      nullable=False),
            sa.Column('product_id',            sa.Integer(),      nullable=False),
            sa.Column('supplier_product_code', sa.String(100),    nullable=True),
            sa.Column('purchase_price',        sa.Numeric(12, 2), nullable=True),
            sa.Column('last_purchase_price',   sa.Numeric(12, 2), nullable=True),
            sa.Column('min_order_qty',         sa.Numeric(12, 3), nullable=True),
            sa.Column('lead_time_days',        sa.Integer(),      nullable=True),
            sa.Column('is_preferred',          sa.Boolean(),      nullable=False, server_default='false'),
            sa.Column('notes',                 sa.Text(),         nullable=True),
            sa.Column('is_active',             sa.Boolean(),      nullable=False, server_default='true'),
            sa.Column('created_at',            sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at',            sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='CASCADE',
                                    name='fk_supplier_products_supplier_id_suppliers'),
            sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE',
                                    name='fk_supplier_products_product_id_products'),
            sa.PrimaryKeyConstraint('id', name='pk_supplier_products'),
            sa.UniqueConstraint('supplier_id', 'product_id', name='uq_supplier_products_supplier_product'),
        )
    if not _index_exists(conn, 'ix_supplier_products_supplier_id'):
        op.create_index('ix_supplier_products_supplier_id', 'supplier_products', ['supplier_id'])
    if not _index_exists(conn, 'ix_supplier_products_product_id'):
        op.create_index('ix_supplier_products_product_id',  'supplier_products', ['product_id'])

    # ── supplier_invoices ────────────────────────────────────────────────────
    if not _table_exists(conn, 'supplier_invoices'):
        op.create_table(
            'supplier_invoices',
            sa.Column('id',                  sa.Integer(),      nullable=False),
            sa.Column('supplier_id',         sa.Integer(),      nullable=False),
            sa.Column('purchase_order_id',   sa.Integer(),      nullable=True),
            sa.Column('store_id',            sa.Integer(),      nullable=True),
            sa.Column('invoice_number',      sa.String(100),    nullable=False),
            sa.Column('invoice_date',        sa.Date(),         nullable=False),
            sa.Column('due_date',            sa.Date(),         nullable=True),
            sa.Column('subtotal',            sa.Numeric(12, 2), nullable=False, server_default='0'),
            sa.Column('tax_amount',          sa.Numeric(12, 2), nullable=False, server_default='0'),
            sa.Column('other_charges',       sa.Numeric(12, 2), nullable=False, server_default='0'),
            sa.Column('grand_total',         sa.Numeric(12, 2), nullable=False, server_default='0'),
            sa.Column('amount_paid',         sa.Numeric(12, 2), nullable=False, server_default='0'),
            sa.Column('payment_status',
                      sa.Enum('unpaid', 'partially_paid', 'paid', 'cancelled',
                               name='supplierinvoicestatus', create_type=False),
                      nullable=False, server_default='unpaid'),
            sa.Column('verification_status',
                      sa.Enum('pending', 'verified', 'disputed',
                               name='invoiceverificationstatus', create_type=False),
                      nullable=False, server_default='pending'),
            sa.Column('notes',               sa.Text(),         nullable=True),
            sa.Column('created_by_id',       sa.Integer(),      nullable=True),
            sa.Column('created_at',          sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at',          sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['supplier_id'],       ['suppliers.id'],
                                    name='fk_supplier_invoices_supplier_id_suppliers'),
            sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'],
                                    name='fk_supplier_invoices_po_id_purchase_orders'),
            sa.ForeignKeyConstraint(['store_id'],          ['stores.id'],
                                    name='fk_supplier_invoices_store_id_stores'),
            sa.ForeignKeyConstraint(['created_by_id'],     ['users.id'],
                                    name='fk_supplier_invoices_created_by_id_users'),
            sa.PrimaryKeyConstraint('id', name='pk_supplier_invoices'),
            sa.UniqueConstraint('supplier_id', 'invoice_number',
                                name='uq_supplier_invoices_supplier_invoice_number'),
        )
    if not _index_exists(conn, 'ix_supplier_invoices_supplier_id'):
        op.create_index('ix_supplier_invoices_supplier_id', 'supplier_invoices', ['supplier_id'])
    if not _index_exists(conn, 'ix_supplier_invoices_purchase_order_id'):
        op.create_index('ix_supplier_invoices_purchase_order_id', 'supplier_invoices', ['purchase_order_id'])
    if not _index_exists(conn, 'ix_supplier_invoices_payment_status'):
        op.create_index('ix_supplier_invoices_payment_status', 'supplier_invoices', ['payment_status'])

    # ── supplier_invoice_grns ────────────────────────────────────────────────
    if not _table_exists(conn, 'supplier_invoice_grns'):
        op.create_table(
            'supplier_invoice_grns',
            sa.Column('id',                  sa.Integer(), nullable=False),
            sa.Column('supplier_invoice_id', sa.Integer(), nullable=False),
            sa.Column('goods_receipt_id',    sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['supplier_invoice_id'], ['supplier_invoices.id'],
                                    ondelete='CASCADE', name='fk_supplier_invoice_grns_invoice_id'),
            sa.ForeignKeyConstraint(['goods_receipt_id'], ['goods_receipts.id'],
                                    name='fk_supplier_invoice_grns_grn_id'),
            sa.PrimaryKeyConstraint('id', name='pk_supplier_invoice_grns'),
            sa.UniqueConstraint('supplier_invoice_id', 'goods_receipt_id',
                                name='uq_supplier_invoice_grns'),
        )
    if not _index_exists(conn, 'ix_supplier_invoice_grns_invoice_id'):
        op.create_index('ix_supplier_invoice_grns_invoice_id', 'supplier_invoice_grns', ['supplier_invoice_id'])

    # ── supplier_payments ────────────────────────────────────────────────────
    if not _table_exists(conn, 'supplier_payments'):
        op.create_table(
            'supplier_payments',
            sa.Column('id',               sa.Integer(),      nullable=False),
            sa.Column('supplier_id',      sa.Integer(),      nullable=False),
            sa.Column('store_id',         sa.Integer(),      nullable=True),
            sa.Column('payment_date',     sa.Date(),         nullable=False),
            sa.Column('amount',           sa.Numeric(12, 2), nullable=False),
            sa.Column('payment_type',
                      sa.Enum('payment', 'advance', 'credit_note', 'debit_note',
                               name='supplierpaymenttype', create_type=False),
                      nullable=False, server_default='payment'),
            sa.Column('payment_method',
                      sa.Enum('cash', 'bank_transfer', 'upi', 'cheque', 'other',
                               name='supplierpaymentmethod', create_type=False),
                      nullable=False, server_default='bank_transfer'),
            sa.Column('reference_number', sa.String(100),    nullable=True),
            sa.Column('bank_account',     sa.String(200),    nullable=True),
            sa.Column('notes',            sa.Text(),         nullable=True),
            sa.Column('is_voided',        sa.Boolean(),      nullable=False, server_default='false'),
            sa.Column('voided_at',        sa.DateTime(timezone=True), nullable=True),
            sa.Column('voided_by_id',     sa.Integer(),      nullable=True),
            sa.Column('created_by_id',    sa.Integer(),      nullable=True),
            sa.Column('created_at',       sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at',       sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['supplier_id'],   ['suppliers.id'],
                                    name='fk_supplier_payments_supplier_id_suppliers'),
            sa.ForeignKeyConstraint(['store_id'],      ['stores.id'],
                                    name='fk_supplier_payments_store_id_stores'),
            sa.ForeignKeyConstraint(['created_by_id'], ['users.id'],
                                    name='fk_supplier_payments_created_by_id_users'),
            sa.ForeignKeyConstraint(['voided_by_id'],  ['users.id'],
                                    name='fk_supplier_payments_voided_by_id_users'),
            sa.PrimaryKeyConstraint('id', name='pk_supplier_payments'),
        )
    if not _index_exists(conn, 'ix_supplier_payments_supplier_id'):
        op.create_index('ix_supplier_payments_supplier_id', 'supplier_payments', ['supplier_id'])

    # ── supplier_payment_allocations ─────────────────────────────────────────
    if not _table_exists(conn, 'supplier_payment_allocations'):
        op.create_table(
            'supplier_payment_allocations',
            sa.Column('id',               sa.Integer(),      nullable=False),
            sa.Column('payment_id',       sa.Integer(),      nullable=False),
            sa.Column('invoice_id',       sa.Integer(),      nullable=False),
            sa.Column('allocated_amount', sa.Numeric(12, 2), nullable=False),
            sa.ForeignKeyConstraint(['payment_id'], ['supplier_payments.id'],
                                    ondelete='CASCADE',
                                    name='fk_supplier_payment_allocations_payment_id'),
            sa.ForeignKeyConstraint(['invoice_id'], ['supplier_invoices.id'],
                                    name='fk_supplier_payment_allocations_invoice_id'),
            sa.PrimaryKeyConstraint('id', name='pk_supplier_payment_allocations'),
            sa.UniqueConstraint('payment_id', 'invoice_id', name='uq_supplier_payment_allocations'),
        )
    if not _index_exists(conn, 'ix_supplier_payment_allocations_payment_id'):
        op.create_index('ix_supplier_payment_allocations_payment_id',
                        'supplier_payment_allocations', ['payment_id'])
    if not _index_exists(conn, 'ix_supplier_payment_allocations_invoice_id'):
        op.create_index('ix_supplier_payment_allocations_invoice_id',
                        'supplier_payment_allocations', ['invoice_id'])

    # ── supplier_documents ───────────────────────────────────────────────────
    if not _table_exists(conn, 'supplier_documents'):
        op.create_table(
            'supplier_documents',
            sa.Column('id',                sa.Integer(),   nullable=False),
            sa.Column('entity_type',
                      sa.Enum('supplier', 'purchase_order', 'goods_receipt',
                               'supplier_invoice', 'supplier_payment',
                               name='documententitytype', create_type=False),
                      nullable=False),
            sa.Column('entity_id',         sa.Integer(),   nullable=False),
            sa.Column('document_label',    sa.String(200), nullable=True),
            sa.Column('original_filename', sa.String(500), nullable=False),
            sa.Column('stored_filename',   sa.String(500), nullable=False),
            sa.Column('file_size',         sa.Integer(),   nullable=True),
            sa.Column('mime_type',         sa.String(100), nullable=True),
            sa.Column('uploaded_by_id',    sa.Integer(),   nullable=True),
            sa.Column('created_at',        sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at',        sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'],
                                    name='fk_supplier_documents_uploaded_by_id_users'),
            sa.PrimaryKeyConstraint('id', name='pk_supplier_documents'),
            sa.UniqueConstraint('stored_filename', name='uq_supplier_documents_stored_filename'),
        )
    if not _index_exists(conn, 'ix_supplier_documents_entity_type_id'):
        op.create_index('ix_supplier_documents_entity_type_id',
                        'supplier_documents', ['entity_type', 'entity_id'])


def downgrade():
    conn = op.get_bind()

    if _index_exists(conn, 'ix_supplier_documents_entity_type_id'):
        op.drop_index('ix_supplier_documents_entity_type_id', table_name='supplier_documents')
    if _table_exists(conn, 'supplier_documents'):
        op.drop_table('supplier_documents')
    conn.execute(sa.text("DROP TYPE IF EXISTS documententitytype"))

    if _index_exists(conn, 'ix_supplier_payment_allocations_invoice_id'):
        op.drop_index('ix_supplier_payment_allocations_invoice_id',
                      table_name='supplier_payment_allocations')
    if _index_exists(conn, 'ix_supplier_payment_allocations_payment_id'):
        op.drop_index('ix_supplier_payment_allocations_payment_id',
                      table_name='supplier_payment_allocations')
    if _table_exists(conn, 'supplier_payment_allocations'):
        op.drop_table('supplier_payment_allocations')

    if _index_exists(conn, 'ix_supplier_payments_supplier_id'):
        op.drop_index('ix_supplier_payments_supplier_id', table_name='supplier_payments')
    if _table_exists(conn, 'supplier_payments'):
        op.drop_table('supplier_payments')
    conn.execute(sa.text("DROP TYPE IF EXISTS supplierpaymentmethod"))
    conn.execute(sa.text("DROP TYPE IF EXISTS supplierpaymenttype"))

    if _index_exists(conn, 'ix_supplier_invoice_grns_invoice_id'):
        op.drop_index('ix_supplier_invoice_grns_invoice_id', table_name='supplier_invoice_grns')
    if _table_exists(conn, 'supplier_invoice_grns'):
        op.drop_table('supplier_invoice_grns')

    if _index_exists(conn, 'ix_supplier_invoices_payment_status'):
        op.drop_index('ix_supplier_invoices_payment_status', table_name='supplier_invoices')
    if _index_exists(conn, 'ix_supplier_invoices_purchase_order_id'):
        op.drop_index('ix_supplier_invoices_purchase_order_id', table_name='supplier_invoices')
    if _index_exists(conn, 'ix_supplier_invoices_supplier_id'):
        op.drop_index('ix_supplier_invoices_supplier_id', table_name='supplier_invoices')
    if _table_exists(conn, 'supplier_invoices'):
        op.drop_table('supplier_invoices')
    conn.execute(sa.text("DROP TYPE IF EXISTS invoiceverificationstatus"))
    conn.execute(sa.text("DROP TYPE IF EXISTS supplierinvoicestatus"))

    if _index_exists(conn, 'ix_supplier_products_product_id'):
        op.drop_index('ix_supplier_products_product_id', table_name='supplier_products')
    if _index_exists(conn, 'ix_supplier_products_supplier_id'):
        op.drop_index('ix_supplier_products_supplier_id', table_name='supplier_products')
    if _table_exists(conn, 'supplier_products'):
        op.drop_table('supplier_products')

    for col in ('remarks', 'mfg_date', 'batch_number', 'qty_damaged', 'qty_rejected', 'qty_accepted'):
        if _col_exists(conn, 'goods_receipt_items', col):
            op.drop_column('goods_receipt_items', col)

    if _fk_exists(conn, 'fk_purchase_orders_closed_by_id_users'):
        op.drop_constraint('fk_purchase_orders_closed_by_id_users',
                           'purchase_orders', type_='foreignkey')
    if _fk_exists(conn, 'fk_purchase_orders_approved_by_id_users'):
        op.drop_constraint('fk_purchase_orders_approved_by_id_users',
                           'purchase_orders', type_='foreignkey')
    for col in ('closed_by_id', 'closed_at', 'approved_by_id', 'approved_at',
                'shipping_address', 'other_charges', 'shipping_charges'):
        if _col_exists(conn, 'purchase_orders', col):
            op.drop_column('purchase_orders', col)

    if _col_exists(conn, 'suppliers', 'opening_balance'):
        op.drop_column('suppliers', 'opening_balance')
