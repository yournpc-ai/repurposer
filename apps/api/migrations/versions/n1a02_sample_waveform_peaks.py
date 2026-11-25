"""Store measured waveform peaks for recorded sound effects."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "n1a02_sample_waveform_peaks"
down_revision = "n1a01_sound_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sound_effects", sa.Column("waveform_peaks", JSONB, nullable=False, server_default="[]"))
    # Frozen measurements identify the bundled recordings by their original bytes.
    op.execute("""
        UPDATE sound_effects AS s SET waveform_peaks = m.peaks
        FROM (VALUES
            ('3d1f75a723cb43f34906f9d88cbe804e0ac1f9e02ac4c79a08efa080f6fcda0c',
             '[0.192, 1.0, 0.998, 0.741, 0.513, 0.35, 0.394, 0.247, 0.242, 0.281, 0.165, 0.195, 0.156, 0.154, 0.114, 0.081, 0.079, 0.074, 0.079, 0.061, 0.051, 0.034, 0.033, 0.043, 0.037, 0.03, 0.022, 0.015, 0.008, 0.007, 0.004, 0.003]'::jsonb),
            ('98fb5887400b1405176f171d9c8f796f5425c1c0e7979c13ac3b947bca61aa5b',
             '[1.0, 0.555, 0.352, 0.253, 0.233, 0.196, 0.19, 0.189, 0.156, 0.13, 0.108, 0.092, 0.081, 0.061, 0.066, 0.066, 0.046, 0.041, 0.041, 0.037, 0.027, 0.024, 0.021, 0.017, 0.01, 0.009, 0.006, 0.005, 0.005, 0.004, 0.004, 0.002]'::jsonb),
            ('43bfa8dde4a8553802b826518aff7246f510037e563009166b93584be626dba2',
             '[0.154, 1.0, 0.431, 0.46, 0.252, 0.187, 0.133, 0.136, 0.113, 0.114, 0.052, 0.059, 0.056, 0.04, 0.05, 0.033, 0.021, 0.015, 0.016, 0.011, 0.012, 0.013, 0.01, 0.01, 0.005, 0.007, 0.005, 0.004, 0.003, 0.004, 0.003, 0.001]'::jsonb)
        ) AS m(sha256, peaks)
        WHERE s.engine_kind = 'sample' AND s.content_sha256 = m.sha256
    """)


def downgrade() -> None:
    op.drop_column("sound_effects", "waveform_peaks")
