"""Additive, repeatable upgrade. Does not rewrite clinical or derived data."""
from app.db import engine
from app.schema_migrations import migrate_boundary_schema

if __name__ == "__main__":
    migrate_boundary_schema(engine)
