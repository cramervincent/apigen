"""Initial migration - create benchmark_reports table

Revision ID: d9aa93d703e0
Revises: 
Create Date: 2025-05-27 13:17:29.098888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9aa93d703e0'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('benchmark_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('report_uuid', sa.String(), nullable=True),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('client_a_property_id', sa.String(), nullable=True),
    sa.Column('benchmark_property_ids_json', sa.Text(), nullable=True),
    sa.Column('property_ids_used', sa.Text(), nullable=True),
    sa.Column('metrics_used', sa.Text(), nullable=True),
    sa.Column('dimensions_used', sa.Text(), nullable=True),
    sa.Column('benchmark_data_json', sa.Text(), nullable=True),
    sa.Column('generated_by_email', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_benchmark_reports_generated_by_email'), 'benchmark_reports', ['generated_by_email'], unique=False)
    op.create_index(op.f('ix_benchmark_reports_id'), 'benchmark_reports', ['id'], unique=False)
    op.create_index(op.f('ix_benchmark_reports_report_uuid'), 'benchmark_reports', ['report_uuid'], unique=True)
    op.create_index(op.f('ix_benchmark_reports_title'), 'benchmark_reports', ['title'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_benchmark_reports_title'), table_name='benchmark_reports')
    op.drop_index(op.f('ix_benchmark_reports_report_uuid'), table_name='benchmark_reports')
    op.drop_index(op.f('ix_benchmark_reports_id'), table_name='benchmark_reports')
    op.drop_index(op.f('ix_benchmark_reports_generated_by_email'), table_name='benchmark_reports')
    op.drop_table('benchmark_reports')
    # ### end Alembic commands ###
