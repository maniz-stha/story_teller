import sqlite3
from pathlib import Path


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        sql = (Path(__file__).parent / "migrations" / "0001.sql").read_text()
        conn.executescript("BEGIN IMMEDIATE;\n" + sql + "\nPRAGMA user_version=1;\nCOMMIT;")
        version = 1
    if version == 1:
        sql = (Path(__file__).parent / "migrations" / "0002.sql").read_text()
        conn.executescript("BEGIN IMMEDIATE;\n" + sql + "\nPRAGMA user_version=2;\nCOMMIT;")
        version = 2
    if version == 2:
        sql = (Path(__file__).parent / "migrations" / "0003.sql").read_text()
        conn.executescript("BEGIN IMMEDIATE;\n" + sql + "\nPRAGMA user_version=3;\nCOMMIT;")
    elif version != 3:
        raise RuntimeError(f"Unsupported database version: {version}")


def resolve_artifact(root: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Artifact path must stay inside data root")
    resolved_root = root.resolve()
    resolved = (resolved_root / path).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("Artifact path must stay inside data root")
    return resolved
