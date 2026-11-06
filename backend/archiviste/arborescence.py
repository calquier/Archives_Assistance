"""Arborescence des dossiers à archiver et sélection des branches.

L'exploration ne lit que les métadonnées (nom, taille) : elle n'ouvre aucun
fichier, et ne télécharge donc pas les fichiers OneDrive « en ligne seulement ».

La sélection est un ensemble de choix explicites {dossier: inclus/exclu}.
Un dossier sans choix explicite hérite du choix de son parent le plus proche ;
par défaut, tout est inclus.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .config import DOSSIERS_IGNORES


def explorer(racine: Path) -> dict:
    """Nœud {nom, chemin, fichiers, taille, enfants} avec totaux cumulés par branche."""
    noeud = {"nom": racine.name or str(racine), "chemin": str(racine), "fichiers": 0, "taille": 0, "enfants": []}
    try:
        entrees = list(os.scandir(racine))
    except OSError:
        noeud["erreur"] = True
        return noeud
    for e in entrees:
        try:
            if e.is_dir(follow_symlinks=False):
                if e.name in DOSSIERS_IGNORES:
                    continue
                enfant = explorer(Path(e.path))
                noeud["enfants"].append(enfant)
                noeud["fichiers"] += enfant["fichiers"]
                noeud["taille"] += enfant["taille"]
            elif e.is_file(follow_symlinks=False):
                noeud["fichiers"] += 1
                noeud["taille"] += e.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    noeud["enfants"].sort(key=lambda n: n["nom"].lower())
    return noeud


def lire_choix(conn: sqlite3.Connection) -> dict[str, bool]:
    return {r["chemin"]: bool(r["inclus"]) for r in conn.execute("SELECT chemin, inclus FROM selection")}


def enregistrer_choix(conn: sqlite3.Connection, choix: dict[str, bool]) -> None:
    conn.execute("DELETE FROM selection")
    conn.executemany(
        "INSERT INTO selection(chemin, inclus) VALUES (?, ?)",
        [(chemin, int(bool(v))) for chemin, v in choix.items()],
    )
    conn.commit()


def est_inclus(dossier: str, choix: dict[str, bool]) -> bool:
    """Choix du dossier, sinon de son ancêtre le plus proche ; inclus par défaut."""
    p = Path(dossier)
    for candidat in (p, *p.parents):
        cle = str(candidat)
        if cle in choix:
            return choix[cle]
    return True


def a_descendant_inclus(dossier: str, choix: dict[str, bool]) -> bool:
    prefixe = dossier.rstrip("\\/") + os.sep
    return any(v and c.startswith(prefixe) for c, v in choix.items())
