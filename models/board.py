"""Deprecated: `Board` was renamed `Journal` when the library/tabs refactor made
a single global board obsolete. Kept as an alias so older imports still resolve.
Prefer `from models.journal import Journal`."""

from models.journal import Journal

Board = Journal
