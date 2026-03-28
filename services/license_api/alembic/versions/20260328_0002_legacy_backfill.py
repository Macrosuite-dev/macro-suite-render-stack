"""legacy schema backfill"""

from alembic import op
import sqlalchemy as sa


revision = "20260328_0002"
down_revision = "20260327_0001"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return table_name in set(sa.inspect(bind).get_table_names())


def _has_index(bind, table_name: str, index_name: str) -> bool:
    return index_name in {item["name"] for item in sa.inspect(bind).get_indexes(table_name)}


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return column_name in {item["name"] for item in sa.inspect(bind).get_columns(table_name)}


def _ensure_column(bind, table_name: str, column: sa.Column) -> None:
    if not _has_column(bind, table_name, column.name):
        op.add_column(table_name, column)


def _drop_legacy_status_checks(bind) -> None:
    for item in sa.inspect(bind).get_check_constraints("licenses"):
        name = item.get("name")
        sqltext = str(item.get("sqltext") or "").lower()
        if name and name != "ck_licenses_status_allowed" and "status" in sqltext:
            op.drop_constraint(name, "licenses", type_="check")


def _ensure_status_check(bind) -> None:
    names = {item.get("name") for item in sa.inspect(bind).get_check_constraints("licenses")}
    if "ck_licenses_status_allowed" not in names:
        op.create_check_constraint(
            "ck_licenses_status_allowed",
            "licenses",
            "status in ('active','disabled','banned','revoked','suspended')",
        )


def upgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "licenses"):
        if not _has_column(bind, "licenses", "license_key_hash") and _has_column(bind, "licenses", "license_key"):
            op.alter_column("licenses", "license_key", new_column_name="license_key_hash")
        if not _has_column(bind, "licenses", "expires_at") and _has_column(bind, "licenses", "expiration_date"):
            op.alter_column("licenses", "expiration_date", new_column_name="expires_at")
        _ensure_column(bind, "licenses", sa.Column("customer_name", sa.String(length=255), nullable=True))
        _ensure_column(bind, "licenses", sa.Column("customer_email", sa.String(length=255), nullable=True))
        _ensure_column(bind, "licenses", sa.Column("notes", sa.Text(), nullable=True))
        _ensure_column(bind, "licenses", sa.Column("license_key_plain", sa.String(length=32), nullable=True))
        _ensure_column(bind, "licenses", sa.Column("license_key_suffix", sa.String(length=4), nullable=True))
        _ensure_column(bind, "licenses", sa.Column("status", sa.String(length=20), nullable=False, server_default="active"))
        _ensure_column(bind, "licenses", sa.Column("max_devices", sa.Integer(), nullable=False, server_default="1"))
        _ensure_column(bind, "licenses", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        _ensure_column(bind, "licenses", sa.Column("disabled_reason", sa.String(length=255), nullable=True))
        _ensure_column(bind, "licenses", sa.Column("banned_reason", sa.String(length=255), nullable=True))
        _ensure_column(
            bind,
            "licenses",
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        _ensure_column(
            bind,
            "licenses",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        if _has_column(bind, "licenses", "flagged_reason"):
            op.execute(
                sa.text(
                    "UPDATE licenses "
                    "SET disabled_reason = COALESCE(disabled_reason, flagged_reason) "
                    "WHERE flagged_reason IS NOT NULL AND status = 'suspended'"
                )
            )
            op.execute(
                sa.text(
                    "UPDATE licenses "
                    "SET banned_reason = COALESCE(banned_reason, flagged_reason) "
                    "WHERE flagged_reason IS NOT NULL AND status = 'revoked'"
                )
            )
        _drop_legacy_status_checks(bind)
        _ensure_status_check(bind)
        if not _has_index(bind, "licenses", "ix_licenses_customer_name"):
            op.create_index("ix_licenses_customer_name", "licenses", ["customer_name"], unique=False)
        if not _has_index(bind, "licenses", "ix_licenses_license_key_hash"):
            op.create_index("ix_licenses_license_key_hash", "licenses", ["license_key_hash"], unique=False)
        if not _has_index(bind, "licenses", "ix_licenses_license_key_plain"):
            op.create_index("ix_licenses_license_key_plain", "licenses", ["license_key_plain"], unique=False)
        if not _has_index(bind, "licenses", "ix_licenses_status"):
            op.create_index("ix_licenses_status", "licenses", ["status"], unique=False)

    if _has_table(bind, "activations"):
        _ensure_column(bind, "activations", sa.Column("device_id", sa.String(length=128), nullable=False))
        _ensure_column(bind, "activations", sa.Column("device_name", sa.String(length=255), nullable=False))
        _ensure_column(bind, "activations", sa.Column("device_fingerprint", sa.String(length=64), nullable=True))
        _ensure_column(bind, "activations", sa.Column("ip_address", sa.String(length=64), nullable=True))
        _ensure_column(
            bind,
            "activations",
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        _ensure_column(bind, "activations", sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True))
        _ensure_column(bind, "activations", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        if not _has_index(bind, "activations", "ix_activations_device_id"):
            op.create_index("ix_activations_device_id", "activations", ["device_id"], unique=False)
        if not _has_index(bind, "activations", "ix_activations_license_id"):
            op.create_index("ix_activations_license_id", "activations", ["license_id"], unique=False)

    if not _has_table(bind, "audit_logs"):
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
    elif _has_table(bind, "audit_logs"):
        _ensure_column(bind, "audit_logs", sa.Column("actor", sa.String(length=255), nullable=False, server_default="system"))
        _ensure_column(bind, "audit_logs", sa.Column("action", sa.String(length=100), nullable=False, server_default="legacy"))
        _ensure_column(bind, "audit_logs", sa.Column("license_id", sa.Integer(), nullable=True))
        _ensure_column(bind, "audit_logs", sa.Column("license_key_suffix", sa.String(length=4), nullable=True))
        _ensure_column(bind, "audit_logs", sa.Column("ip_address", sa.String(length=64), nullable=True))
        _ensure_column(bind, "audit_logs", sa.Column("detail", sa.Text(), nullable=True))
        _ensure_column(
            bind,
            "audit_logs",
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    if _has_table(bind, "audit_logs"):
        if not _has_index(bind, "audit_logs", "ix_audit_logs_action"):
            op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
        if not _has_index(bind, "audit_logs", "ix_audit_logs_created_at"):
            op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    pass
