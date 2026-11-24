"""applications: avito_last_message_id -> строка (id сообщений Авито — hex)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "applications",
        "avito_last_message_id",
        existing_type=sa.BigInteger(),
        type_=sa.String(length=64),
        postgresql_using="avito_last_message_id::varchar",
    )


def downgrade() -> None:
    op.alter_column(
        "applications",
        "avito_last_message_id",
        existing_type=sa.String(length=64),
        type_=sa.BigInteger(),
        postgresql_using="avito_last_message_id::bigint",
    )
