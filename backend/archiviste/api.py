"""API web de l'Archiviste et service de l'interface (dossier web/)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Config
from .db import connecter
from .doublons import groupes_doublons
from .propositions import decider, propositions_corbeille, propositions_renommage
from .recherche import chercher
from .scanner import scanner

WEB = Path(__file__).resolve().parent.parent.parent / "web"


class Decision(BaseModel):
    statut: str  # acceptee | refusee | annuler


def creer_app(config: Config | None = None) -> FastAPI:
    config = config or Config.depuis_env()
    conn = connecter(config.db_path)
    verrou = threading.Lock()
    etat_scan: dict = {"en_cours": False, "dernier": None, "erreur": None}

    app = FastAPI(title="Archiviste", version="0.1.0")

    def _scanner():
        try:
            with verrou:
                bilan = scanner(conn, config.racines)
            etat_scan["dernier"] = {**bilan.__dict__, "fin": time.time()}
            etat_scan["erreur"] = None
        except Exception as e:  # remonté à l'interface
            etat_scan["erreur"] = str(e)
        finally:
            etat_scan["en_cours"] = False

    @app.get("/api/etat")
    def etat():
        with verrou:
            n, taille = conn.execute("SELECT COUNT(*), COALESCE(SUM(taille), 0) FROM documents").fetchone()
            rubriques = [
                dict(r) for r in conn.execute(
                    "SELECT rubrique, COUNT(*) AS n, SUM(taille) AS taille FROM documents "
                    "GROUP BY rubrique ORDER BY rubrique"
                )
            ]
            dernier = conn.execute("SELECT * FROM scans WHERE fin IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
            groupes = groupes_doublons(conn)
        return {
            "racines": [str(r) for r in config.racines],
            "documents": n,
            "taille": taille,
            "rubriques": rubriques,
            "dernier_scan": dict(dernier) if dernier else None,
            "scan_en_cours": etat_scan["en_cours"],
            "erreur_scan": etat_scan["erreur"],
            "doublons": {"groupes": len(groupes), "recuperable": sum(g["recuperable"] for g in groupes)},
        }

    @app.post("/api/scan")
    def lancer_scan():
        if not config.racines:
            raise HTTPException(400, "Aucun dossier à indexer : renseignez ARCHIVISTE_RACINES.")
        if etat_scan["en_cours"]:
            return {"lance": False, "raison": "Un scan est déjà en cours."}
        etat_scan["en_cours"] = True
        threading.Thread(target=_scanner, daemon=True).start()
        return {"lance": True}

    @app.get("/api/recherche")
    def recherche(q: str = "", tri: str = "pertinence", limite: int = 100):
        with verrou:
            return {"requete": q, "resultats": chercher(conn, q, min(limite, 500), tri)}

    @app.get("/api/doublons")
    def doublons():
        with verrou:
            return {"groupes": groupes_doublons(conn)}

    @app.get("/api/propositions/renommage")
    def renommage():
        with verrou:
            return {"propositions": propositions_renommage(conn)}

    @app.get("/api/propositions/corbeille")
    def corbeille():
        with verrou:
            return {"propositions": propositions_corbeille(conn)}

    @app.post("/api/propositions/{cle}")
    def decision(cle: str, d: Decision):
        if d.statut not in {"acceptee", "refusee", "annuler"}:
            raise HTTPException(400, "Statut inconnu.")
        with verrou:
            decider(conn, cle, d.statut)
        return {"cle": cle, "statut": d.statut}

    @app.post("/api/ouvrir/{doc_id}")
    def ouvrir(doc_id: int, dossier: bool = False):
        """Ouvre le fichier (ou son dossier) sur ce poste. Lecture seule."""
        with verrou:
            row = conn.execute("SELECT chemin FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row or not Path(row["chemin"]).exists():
            raise HTTPException(404, "Fichier introuvable.")
        cible = Path(row["chemin"])
        if sys.platform.startswith("win"):
            if dossier:
                subprocess.Popen(["explorer", "/select,", str(cible)])
            else:
                os.startfile(str(cible))  # type: ignore[attr-defined]
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(cible.parent if dossier else cible)])
        return {"ouvert": str(cible)}

    if WEB.is_dir():
        app.mount("/static", StaticFiles(directory=WEB), name="static")

        @app.get("/")
        def accueil():
            return FileResponse(WEB / "index.html")

    return app
