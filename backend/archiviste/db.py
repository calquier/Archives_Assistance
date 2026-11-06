"""Index SQLite : table des documents + recherche plein texte FTS5."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    chemin      TEXT NOT NULL UNIQUE,
    racine      TEXT NOT NULL,
    relatif     TEXT NOT NULL,
    nom         TEXT NOT NULL,
    extension   TEXT NOT NULL,
    taille      INTEGER NOT NULL,
    modifie_le  REAL NOT NULL,
    sha256      TEXT,
    date_doc    TEXT,
    date_source TEXT,
    rubrique    TEXT,
    texte       TEXT NOT NULL DEFAULT '',
    vu_le       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_sha ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_documents_date ON documents(date_doc);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    nom, relatif, texte,
    content='documents', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, nom, relatif, texte)
    VALUES (new.id, new.nom, new.relatif, new.texte);
END;
CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, nom, relatif, texte)
    VALUES ('delete', old.id, old.nom, old.relatif, old.texte);
END;
CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, nom, relatif, texte)
    VALUES ('delete', old.id, old.nom, old.relatif, old.texte);
    INSERT INTO documents_fts(rowid, nom, relatif, texte)
    VALUES (new.id, new.nom, new.relatif, new.texte);
END;

-- Décisions de l'utilisateur sur les propositions (renommage, corbeille).
-- Une proposition refusée n'est plus présentée tant que le fichier ne change pas.
CREATE TABLE IF NOT EXISTS decisions (
    cle         TEXT PRIMARY KEY,
    statut      TEXT NOT NULL CHECK (statut IN ('acceptee', 'refusee')),
    decide_le   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scans (
    id          INTEGER PRIMARY KEY,
    debut       REAL NOT NULL,
    fin         REAL,
    vus         INTEGER DEFAULT 0,
    ajoutes     INTEGER DEFAULT 0,
    modifies    INTEGER DEFAULT 0,
    retires     INTEGER DEFAULT 0,
    erreurs     INTEGER DEFAULT 0
);
"""


def connecter(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn
