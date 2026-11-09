"""Configuration de l'Archiviste.

Les dossiers à indexer et l'emplacement de l'index se règlent par variables
d'environnement (ou un fichier .env chargé par le lanceur) :

- ARCHIVISTE_RACINES : chemins séparés par « ; » (ex. ESPACE PERSO;ESPACE PRO;Downloads)
- ARCHIVISTE_DB      : chemin du fichier SQLite de l'index
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DB = Path.home() / ".archiviste" / "index.sqlite3"

# Dossiers jamais parcourus (code, caches, outils).
DOSSIERS_IGNORES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".vscode",
    ".idea", "$RECYCLE.BIN", "System Volume Information",
}

# Extensions dont le texte est extrait pour la recherche plein texte.
EXTENSIONS_TEXTE = {
    ".txt", ".md", ".csv", ".pdf", ".docx", ".xlsx", ".xlsm", ".pptx", ".eml",
}

# Taille maximale lue pour l'extraction de texte (au-delà, seul le nom est indexé).
TAILLE_MAX_EXTRACTION = 40 * 1024 * 1024
# Texte conservé par document dans l'index.
TEXTE_MAX = 200_000


@dataclass
class Config:
    racines: list[Path] = field(default_factory=list)
    db_path: Path = DEFAULT_DB

    @classmethod
    def depuis_env(cls) -> "Config":
        brut = os.environ.get("ARCHIVISTE_RACINES", "")
        racines = [Path(p.strip()).expanduser() for p in brut.split(";") if p.strip()]
        db = Path(os.environ.get("ARCHIVISTE_DB", str(DEFAULT_DB))).expanduser()
        return cls(racines=racines, db_path=db)
