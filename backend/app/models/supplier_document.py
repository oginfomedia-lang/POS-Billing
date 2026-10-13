"""SupplierDocument: file attachments for suppliers, POs, GRNs, invoices, payments."""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import DocumentEntityType


class SupplierDocument(TimestampMixin, db.Model):
    __tablename__ = "supplier_documents"

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(
        db.Enum(DocumentEntityType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    document_label = db.Column(db.String(200), nullable=True)
    original_filename = db.Column(db.String(500), nullable=False)
    stored_filename = db.Column(db.String(500), nullable=False, unique=True)
    file_size = db.Column(db.Integer, nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    uploaded_by = db.relationship("User")

    def __repr__(self) -> str:
        return f"<SupplierDocument {self.id} {self.original_filename}>"
