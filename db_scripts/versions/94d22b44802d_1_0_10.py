"""1.0.10

Revision ID: 94d22b44802d
Revises: cc7232dfe2b5
Create Date: 2023-01-20 08:10:18.350985

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '94d22b44802d'
down_revision = 'cc7232dfe2b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    try:
        with op.batch_alter_table("RSS_MOVIES") as batch_op:
            batch_op.add_column(sa.Column('FILTER_ORDER', sa.Integer, nullable=True))
    except Exception as e:
        print(str(e))
    try:
        with op.batch_alter_table("RSS_TVS") as batch_op:
            batch_op.add_column(sa.Column('FILTER_ORDER', sa.Integer, nullable=True))
    except Exception as e:
        print(str(e))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    try:
        with op.batch_alter_table("RSS_TVS") as batch_op:
            batch_op.drop_column('FILTER_ORDER')
    except Exception as e:
        print(str(e))
    try:
        with op.batch_alter_table("RSS_MOVIES") as batch_op:
            batch_op.drop_column('FILTER_ORDER')
    except Exception as e:
        print(e)
    # ### end Alembic commands ###