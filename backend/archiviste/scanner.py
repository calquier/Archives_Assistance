"""Parcours des dossiers et mise à jour incrémentale de l'index.

Le scan ne fait que lire : aucun fichier n'est déplacé, renommé ni supprimé.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .arborescence import a_descendant_inclus, est_inclus
from .config import DOSSIERS_IGNORES, EXTENSIONS_TEXTE, TAILLE_MAX_EXTRACTION
from .extraction import date_du_document, extraire_texte


@dataclass
class BilanScan:
    vus: int = 0
    ajoutes: int = 0
    modifies: int = 0
    retires: int = 0
    erreurs: int = 0


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloc)
    return h.hexdigest()


def rubrique_de(relatif: Path, racine: Path) -> str:
    """Rubrique = nom de la racine + premier niveau de dossier (ex. ESPACE PRO/[2] Missions)."""
    parties = relatif.parts
    if len(parties) > 1:
        return f"{racine.name}/{parties[0]}"
    return racine.name


def fichiers(racine: Path, choix: dict[str, bool] | None = None):
    """Fichiers des branches sélectionnées (toutes si aucun choix)."""
    choix = choix or {}
    for dossier, sous_dossiers, noms in os.walk(racine):
        sous_dossiers[:] = [
            d for d in sous_dossiers
            if d not in DOSSIERS_IGNORES
            and (est_inclus(os.path.join(dossier, d), choix) or a_descendant_inclus(os.path.join(dossier, d), choix))
        ]
        if not est_inclus(dossier, choix):
            continue
        for nom in noms:
            yield Path(dossier) / nom


def scanner(conn: sqlite3.Connection, racines: list[Path], choix: dict[str, bool] | None = None) -> BilanScan:
    """Met l'index à jour. Les fichiers des branches non sélectionnées en sortent."""
    bilan = BilanScan()
    debut = time.time()
    scan_id = conn.execute("INSERT INTO scans(debut) VALUES (?)", (debut,)).lastrowid
    connus = {
        r["chemin"]: (r["taille"], r["modifie_le"])
        for r in conn.execute("SELECT chemin, taille, modifie_le FROM documents")
    }
    vus: set[str] = set()

    for racine in racines:
        racine = racine.resolve()
        if not racine.is_dir():
            bilan.erreurs += 1
            continue
        for chemin in fichiers(racine, choix):
            try:
                st = chemin.stat()
            except OSError:
                bilan.erreurs += 1
                continue
            cle = str(chemin)
            vus.add(cle)
            bilan.vus += 1
            precedent = connus.get(cle)
            if precedent == (st.st_size, st.st_mtime):
                continue
            try:
                _indexer(conn, chemin, racine, st)
            except OSError:
                bilan.erreurs += 1
                continue
            if precedent is None:
                bilan.ajoutes += 1
            else:
                bilan.modifies += 1
            if (bilan.ajoutes + bilan.modifies) % 200 == 0:
                conn.commit()

    # Les fichiers disparus des racines scannées sortent de l'index.
    racines_txt = [str(r.resolve()) for r in racines]
    for cle in set(connus) - vus:
        if any(cle.startswith(r) for r in racines_txt):
            conn.execute("DELETE FROM documents WHERE chemin = ?", (cle,))
            bilan.retires += 1

    conn.execute(
        "UPDATE scans SET fin=?, vus=?, ajoutes=?, modifies=?, retires=?, erreurs=? WHERE id=?",
        (time.time(), bilan.vus, bilan.ajoutes, bilan.modifies, bilan.retires, bilan.erreurs, scan_id),
    )
    conn.commit()
    return bilan


def _indexer(conn: sqlite3.Connection, chemin: Path, racine: Path, st: os.stat_result) -> None:
    relatif = chemin.relative_to(racine)
    ext = chemin.suffix.lower()
    texte = ""
    if ext in EXTENSIONS_TEXTE and st.st_size <= TAILLE_MAX_EXTRACTION:
        texte = extraire_texte(chemin)
    date_doc, source = date_du_document(chemin.name, texte, st.st_mtime)
    valeurs = dict(
        chemin=str(chemin),
        racine=str(racine),
        relatif=str(relatif),
        nom=chemin.name,
        extension=ext,
        taille=st.st_size,
        modifie_le=st.st_mtime,
        sha256=empreinte(chemin),
        date_doc=date_doc,
        date_source=source,
        rubrique=rubrique_de(relatif, racine),
        texte=texte,
        vu_le=time.time(),
    )
    colonnes = ", ".join(valeurs)
    marques = ", ".join(f":{k}" for k in valeurs)
    maj = ", ".join(f"{k}=excluded.{k}" for k in valeurs if k != "chemin")
    conn.execute(
        f"INSERT INTO documents ({colonnes}) VALUES ({marques}) "
        f"ON CONFLICT(chemin) DO UPDATE SET {maj}",
        valeurs,
    )
