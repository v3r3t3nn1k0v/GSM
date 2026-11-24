"""applications: source, авито-лиды (chat_id, listing), user_id nullable

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "source",
            sa.String(length=8),
            nullable=False,
            server_default="tg",
        ),
    )
    # Лиды с Авито создаются без пользователя бота
    op.alter_column("applications", "user_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("applications", sa.Column("avito_chat_id", sa.String(length=64), nullable=True))
    op.add_column(
        "applications", sa.Column("avito_last_message_id", sa.BigInteger(), nullable=True)
    )
    op.add_column("applications", sa.Column("listing_title", sa.String(length=255), nullable=True))
    op.create_unique_constraint(
        "uq_applications_avito_chat_id", "applications", ["avito_chat_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_applications_avito_chat_id", "applications", type_="unique")
    op.drop_column("applications", "listing_title")
    op.drop_column("applications", "avito_last_message_id")
    op.drop_column("applications", "avito_chat_id")
    op.alter_column("applications", "user_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("applications", "source")
