"""Add persistent image attachments to journal entries."""

from alembic import op
import sqlalchemy as sa


revision = "0002_entry_images"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "journal_entry_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entry_id",
            sa.Integer(),
            sa.ForeignKey("journal_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_journal_entry_images_entry_id",
        "journal_entry_images",
        ["entry_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_journal_entry_images_entry_id",
        table_name="journal_entry_images",
    )
    op.drop_table("journal_entry_images")
