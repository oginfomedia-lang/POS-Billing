"""Add purchase_orders, purchase_order_items, goods_receipts, goods_receipt_items tables.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-10-09 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('po_number', sa.String(40), nullable=False),
        sa.Column('supplier_id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=False),
        sa.Column('expected_delivery_date', sa.Date(), nullable=True),
        sa.Column('reference_number', sa.String(100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('internal_remarks', sa.Text(), nullable=True),
        sa.Column('subtotal', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('discount_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('tax_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('grand_total', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column(
            'status',
            sa.Enum('draft', 'ordered', 'partially_received', 'received', 'cancelled',
                    name='purchasestatus'),
            nullable=False,
            server_default='draft',
        ),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('ordered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ordered_by_id', sa.Integer(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_purchase_orders_supplier_id_suppliers')),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], name=op.f('fk_purchase_orders_store_id_stores')),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_purchase_orders_created_by_id_users')),
        sa.ForeignKeyConstraint(['ordered_by_id'], ['users.id'], name=op.f('fk_purchase_orders_ordered_by_id_users')),
        sa.ForeignKeyConstraint(['cancelled_by_id'], ['users.id'], name=op.f('fk_purchase_orders_cancelled_by_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_orders')),
        sa.UniqueConstraint('po_number', name=op.f('uq_purchase_orders_po_number')),
    )
    op.create_index(op.f('ix_purchase_orders_po_number'), 'purchase_orders', ['po_number'])
    op.create_index(op.f('ix_purchase_orders_status'), 'purchase_orders', ['status'])

    op.create_table(
        'purchase_order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_order_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('product_name', sa.String(200), nullable=False),
        sa.Column('product_sku', sa.String(50), nullable=True),
        sa.Column('ordered_qty', sa.Numeric(12, 3), nullable=False),
        sa.Column('received_qty', sa.Numeric(12, 3), nullable=False, server_default='0'),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('discount_percent', sa.Numeric(5, 2), nullable=False, server_default='0'),
        sa.Column('tax_rate', sa.Numeric(5, 2), nullable=False, server_default='0'),
        sa.Column('line_discount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('tax_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('line_total', sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'],
                                name=op.f('fk_purchase_order_items_purchase_order_id_purchase_orders'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'],
                                name=op.f('fk_purchase_order_items_product_id_products')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_order_items')),
    )
    op.create_index(op.f('ix_purchase_order_items_purchase_order_id'), 'purchase_order_items', ['purchase_order_id'])

    op.create_table(
        'goods_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_order_id', sa.Integer(), nullable=False),
        sa.Column('receipt_number', sa.String(40), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_by_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'],
                                name=op.f('fk_goods_receipts_purchase_order_id_purchase_orders')),
        sa.ForeignKeyConstraint(['received_by_id'], ['users.id'],
                                name=op.f('fk_goods_receipts_received_by_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_goods_receipts')),
        sa.UniqueConstraint('receipt_number', name=op.f('uq_goods_receipts_receipt_number')),
    )
    op.create_index(op.f('ix_goods_receipts_purchase_order_id'), 'goods_receipts', ['purchase_order_id'])

    op.create_table(
        'goods_receipt_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('goods_receipt_id', sa.Integer(), nullable=False),
        sa.Column('purchase_order_item_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('qty_received', sa.Numeric(12, 3), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['goods_receipt_id'], ['goods_receipts.id'],
                                name=op.f('fk_goods_receipt_items_goods_receipt_id_goods_receipts'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['purchase_order_item_id'], ['purchase_order_items.id'],
                                name=op.f('fk_goods_receipt_items_purchase_order_item_id_purchase_order_items')),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'],
                                name=op.f('fk_goods_receipt_items_product_id_products')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_goods_receipt_items')),
    )
    op.create_index(op.f('ix_goods_receipt_items_goods_receipt_id'), 'goods_receipt_items', ['goods_receipt_id'])


def downgrade():
    op.drop_index(op.f('ix_goods_receipt_items_goods_receipt_id'), table_name='goods_receipt_items')
    op.drop_table('goods_receipt_items')

    op.drop_index(op.f('ix_goods_receipts_purchase_order_id'), table_name='goods_receipts')
    op.drop_table('goods_receipts')

    op.drop_index(op.f('ix_purchase_order_items_purchase_order_id'), table_name='purchase_order_items')
    op.drop_table('purchase_order_items')

    op.drop_index(op.f('ix_purchase_orders_status'), table_name='purchase_orders')
    op.drop_index(op.f('ix_purchase_orders_po_number'), table_name='purchase_orders')
    op.drop_table('purchase_orders')

    op.execute("DROP TYPE IF EXISTS purchasestatus")
