"""enable RLS on remaining public tables

Defense-in-depth hardening. Enabling row level security with no policy makes a table
deny-by-default for any role that is NOT a BYPASSRLS/superuser role — i.e. for the Supabase
anon/PostgREST path or any future least-privilege application role. The current backend
connects with a BYPASSRLS role, so it is unaffected by this change; the intent is purely to
close the door for any non-backend access path rather than to alter app behavior.

NOTE: This does not by itself make RLS meaningful for the application. For that, the app must
connect with a non-BYPASSRLS role and explicit policies must be written per table. See the
security audit notes. This migration is the safe first step and can be applied independently.

Revision ID: b2e8f4a1c6d0
Revises: a1f7c2d9e4b0
Create Date: 2026-09-04 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b2e8f4a1c6d0'
down_revision: Union[str, Sequence[str], None] = 'a1f7c2d9e4b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# alembic_version is deliberately excluded: it is owned by the migration tooling, not the app.
_TABLES = ("vouchers", "promos", "promo_products", "pending_registrations", "rate_limit_counters")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
