"""${message}"""
revision = "${up_revision}"
down_revision = ${repr(down_revision)}
from alembic import op
import sqlalchemy as sa
${upgrades if upgrades else "def upgrade(): pass"}
${downgrades if downgrades else "def downgrade(): pass"}
