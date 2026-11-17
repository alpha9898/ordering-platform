"""platform secrets with db-generated session key

Revision ID: 24a4d909b259
Revises: 05f68371735f
Create Date: 2026-11-17 22:59:21.433334

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24a4d909b259'
down_revision: Union[str, Sequence[str], None] = '05f68371735f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_secrets",
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    # 64 hex chars from two v4 UUIDs (gen_random_uuid uses a strong RNG).
    # Generated server-side: nobody ever sees or types this key.
    op.execute(
        "INSERT INTO platform_secrets (key, value) VALUES ('jwt_secret', "
        "replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', ''))"
    )


def downgrade() -> None:
    op.drop_table("platform_secrets")
