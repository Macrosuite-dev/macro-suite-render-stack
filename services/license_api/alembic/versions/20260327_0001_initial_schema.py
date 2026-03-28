"""initial schema"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "licenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("license_key_hash", sa.String(length=128), nullable=False),
        sa.Column("license_key_plain", sa.String(length=32), nullable=False),
        sa.Column("license_key_suffix", sa.String(length=4), nullable=False),
        sa.Column("product", sa.String(length=100), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("max_devices", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_reason", sa.String(length=255), nullable=True),
        sa.Column("banned_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("license_key_hash"),
        sa.UniqueConstraint("license_key_plain"),
    )
    op.create_index("ix_licenses_customer_name", "licenses", ["customer_name"], unique=False)
    op.create_index("ix_licenses_license_key_hash", "licenses", ["license_key_hash"], unique=False)
    op.create_index("ix_licenses_license_key_plain", "licenses", ["license_key_plain"], unique=False)
    op.create_index("ix_licenses_status", "licenses", ["status"], unique=False)

    op.create_table(
        "activations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("license_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=False),
        sa.Column("device_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["license_id"], ["licenses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("license_id", "device_id", name="uq_activations_license_device"),
    )
    op.create_index("ix_activations_device_id", "activations", ["device_id"], unique=False)
    op.create_index("ix_activations_license_id", "activations", ["license_id"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("license_id", sa.Integer(), nullable=True),
        sa.Column("license_key_suffix", sa.String(length=4), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["license_id"], ["licenses.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_activations_license_id", table_name="activations")
    op.drop_index("ix_activations_device_id", table_name="activations")
    op.drop_table("activations")
    op.drop_index("ix_licenses_status", table_name="licenses")
    op.drop_index("ix_licenses_license_key_plain", table_name="licenses")
    op.drop_index("ix_licenses_license_key_hash", table_name="licenses")
    op.drop_index("ix_licenses_customer_name", table_name="licenses")
    op.drop_table("licenses")
