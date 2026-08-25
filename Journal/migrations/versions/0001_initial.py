from alembic import op
import sqlalchemy as sa
revision="0001_initial"; down_revision=None; branch_labels=None; depends_on=None
def upgrade():
 op.create_table("journal_users",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("username",sa.String(80),nullable=False),sa.Column("password_hash",sa.String(512),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False)); op.create_index("ix_journal_users_username","journal_users",["username"],unique=True)
 op.create_table("journal_entries",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("user_id",sa.Integer(),sa.ForeignKey("journal_users.id",ondelete="CASCADE"),nullable=False),sa.Column("title",sa.String(120),nullable=False),sa.Column("entry_date",sa.Date(),nullable=False),sa.Column("content",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False)); op.create_index("ix_journal_entries_user_id","journal_entries",["user_id"])
 op.create_table("journal_sessions",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("user_id",sa.Integer(),sa.ForeignKey("journal_users.id",ondelete="CASCADE"),nullable=False),sa.Column("token_hash",sa.String(64),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False)); op.create_index("ix_journal_sessions_user_id","journal_sessions",["user_id"]); op.create_index("ix_journal_sessions_token_hash","journal_sessions",["token_hash"],unique=True); op.create_index("ix_journal_sessions_expires_at","journal_sessions",["expires_at"])
def downgrade():
 op.drop_table("journal_sessions"); op.drop_table("journal_entries"); op.drop_table("journal_users")
