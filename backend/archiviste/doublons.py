"""Groupes de doublons exacts (même empreinte SHA-256)."""

from __future__ import annotations

import re
import sqlite3

_RE_COPIE = re.compile(r"( - Copie| - Copy|\(\d+\)|-DESKTOP-|-LAPTOP-)", re.IGNORECASE)


def _rang_reference(doc: dict) -> tuple:
    """Plus petit = meilleur candidat à garder : pas une copie, chemin court, plus récent."""
    return (bool(_RE_COPIE.search(doc["relatif"])), len(doc["relatif"]), -doc["modifie_le"])


def groupes_doublons(conn: sqlite3.Connection, taille_min: int = 1) -> list[dict]:
    lignes = conn.execute(
        """
        SELECT id, chemin, relatif, nom, taille, modifie_le, sha256, rubrique, racine
        FROM documents
        WHERE sha256 IN (
            SELECT sha256 FROM documents
            WHERE taille >= ? GROUP BY sha256 HAVING COUNT(*) > 1
        )
        ORDER BY sha256
        """,
        (taille_min,),
    ).fetchall()
    par_empreinte: dict[str, list[dict]] = {}
    for ligne in lignes:
        par_empreinte.setdefault(ligne["sha256"], []).append(dict(ligne))

    groupes = []
    for sha, docs in par_empreinte.items():
        docs.sort(key=_rang_reference)
        reference, *copies = docs
        groupes.append(
            {
                "sha256": sha,
                "taille": reference["taille"],
                "recuperable": reference["taille"] * len(copies),
                "reference": reference,
                "copies": copies,
            }
        )
    groupes.sort(key=lambda g: -g["recuperable"])
    return groupes
