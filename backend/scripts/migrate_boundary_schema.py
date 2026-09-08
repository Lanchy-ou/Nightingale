"""Additive, repeatable upgrade. Does not rewrite clinical or derived data."""
from app.db import engine
from app.db import migrate_boundary_schema

if __name__ == "__main__":
    migrate_boundary_schema(engine)
