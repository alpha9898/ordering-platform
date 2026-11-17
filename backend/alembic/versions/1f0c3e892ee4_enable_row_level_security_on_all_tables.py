"""enable row level security on all tables

Revision ID: 1f0c3e892ee4
Revises: 24a4d909b259
Create Date: 2026-11-17 23:01:33.792386

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f0c3e892ee4'
down_revision: Union[str, Sequence[str], None] = '24a4d909b259'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    "restaurants", "users", "categories", "items", "item_variants", "addons", "category_addons",
    "customers", "delivery_zones", "conversations", "messages", "orders", "order_items",
    "order_item_addons", "order_status_events", "order_counters", "settings", "rate_hits",
    "platform_secrets", "alembic_version",
]


def upgrade() -> None:
    # On Supabase, tables in "public" are reachable through the auto-generated
    # REST API with the public anon key. RLS with no policies denies that path
    # entirely; the app connects as the table owner, which bypasses RLS.
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
