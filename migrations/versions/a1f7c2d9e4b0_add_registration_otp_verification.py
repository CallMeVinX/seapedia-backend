"""add registration otp verification

Adds the staging table for unverified sign-ups, a generic rate-limit counter, and the
alias-collapsed email column that makes one mailbox map to exactly one account.

Revision ID: a1f7c2d9e4b0
Revises: c0de3cf274b7
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1f7c2d9e4b0'
down_revision: Union[str, Sequence[str], None] = 'c0de3cf274b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirrors app.core.email_rules.canonicalize_email so that rows backfilled here compare equal
# to values the application computes at runtime. If the two ever drift, existing users stop
# matching on login, so the two implementations must be changed together.
CANONICALIZE_SQL = """
    CASE
        WHEN split_part(lower(email), '@', 2) IN ('gmail.com', 'googlemail.com')
            THEN replace(split_part(split_part(lower(email), '@', 1), '+', 1), '.', '')
                 || '@gmail.com'
        ELSE split_part(split_part(lower(email), '@', 1), '+', 1)
             || '@' || split_part(lower(email), '@', 2)
    END
"""


def upgrade() -> None:
    """Upgrade schema."""

    # --- users: canonical address + verification timestamp ---------------------
    op.add_column('users', sa.Column('email_canonical', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))

    op.execute(f"UPDATE users SET email_canonical = {CANONICALIZE_SQL}")

    # Accounts that predate this feature are grandfathered as verified. Leaving them unverified
    # would lock out the entire existing user base the moment a verification gate is enforced.
    op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")

    # Fail loudly rather than letting the UNIQUE index blow up with an opaque error: if two
    # existing accounts collapse to the same mailbox, that is real data requiring a decision.
    op.execute("""
        DO $$
        DECLARE
            duplicates text;
        BEGIN
            SELECT string_agg(email_canonical, ', ') INTO duplicates
            FROM (
                SELECT email_canonical FROM users
                GROUP BY email_canonical HAVING count(*) > 1
            ) d;

            IF duplicates IS NOT NULL THEN
                RAISE EXCEPTION
                    'Cannot add UNIQUE(email_canonical): these mailboxes already hold multiple accounts: %. Merge or remove the duplicates, then re-run this migration.',
                    duplicates;
            END IF;
        END $$;
    """)

    op.alter_column('users', 'email_canonical', nullable=False)
    op.create_index(op.f('ix_users_email_canonical'), 'users', ['email_canonical'], unique=True)

    # --- pending_registrations -------------------------------------------------
    op.create_table(
        'pending_registrations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('email_canonical', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=150), nullable=False),
        sa.Column('roles', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('resend_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('request_ip', postgresql.INET(), nullable=True),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # UNIQUE rather than a plain index: it is the conflict target of the UPSERT that lets a
    # user restart an unverified signup without stacking duplicate pending rows.
    op.create_index(
        op.f('ix_pending_registrations_email_canonical'),
        'pending_registrations', ['email_canonical'], unique=True,
    )
    # Supports the opportunistic purge of abandoned attempts.
    op.create_index('ix_pending_registrations_expires_at', 'pending_registrations', ['expires_at'])

    # --- rate_limit_counters ---------------------------------------------------
    op.create_table(
        'rate_limit_counters',
        sa.Column('key', sa.String(length=200), nullable=False),
        sa.Column('count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_index('ix_rate_limit_counters_window_start', 'rate_limit_counters', ['window_start'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_rate_limit_counters_window_start', table_name='rate_limit_counters')
    op.drop_table('rate_limit_counters')

    op.drop_index('ix_pending_registrations_expires_at', table_name='pending_registrations')
    op.drop_index(op.f('ix_pending_registrations_email_canonical'), table_name='pending_registrations')
    op.drop_table('pending_registrations')

    op.drop_index(op.f('ix_users_email_canonical'), table_name='users')
    op.drop_column('users', 'email_verified_at')
    op.drop_column('users', 'email_canonical')
