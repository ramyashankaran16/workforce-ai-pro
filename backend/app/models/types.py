"""
Portable column types.

JSONType renders as JSONB on PostgreSQL (indexable, faster containment queries)
and as plain JSON everywhere else, so the models stay database-agnostic.
"""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JSONType = JSON().with_variant(JSONB, "postgresql")
