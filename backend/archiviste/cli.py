"""Ligne de commande : archiviste scanner | chercher | doublons | plan | serveur"""

from __future__ import annotations

import argparse
import sys

from .config import Config
from .db import connecter


def _mo(octets: int) -> str:
    return f"{octets / 1e6:.1f} Mo"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="archiviste", description="Index, recherche et rangement des archives.")
    sous = p.add_subparsers(dest="commande", required=True)
    sous.add_parser("scanner", help="Met à jour l'index (lecture seule)")
    c = sous.add_parser("chercher", help="Recherche par mots-clés, rubrique, dates")
    c.add_argument("requete", nargs="+")
    c.add_argument("--date", action="store_true", help="Trier par date du document")
    sous.add_parser("doublons", help="Liste les groupes de doublons")
    sous.add_parser("plan", help="Propositions de renommage et de corbeille")
    s = sous.add_parser("serveur", help="Lance l'interface web")
    s.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)

    config = Config.depuis_env()

    if a.commande == "serveur":
        import uvicorn

        from .api import creer_app

        print(f"Archiviste : http://127.0.0.1:{a.port}")
        uvicorn.run(creer_app(config), host="127.0.0.1", port=a.port)
        return 0

    conn = connecter(config.db_path)

    if a.commande == "scanner":
        from .scanner import scanner

        if not config.racines:
            print("Renseignez ARCHIVISTE_RACINES (dossiers séparés par ;).", file=sys.stderr)
            return 2
        b = scanner(conn, config.racines)
        print(f"{b.vus} fichiers vus, {b.ajoutes} ajoutés, {b.modifies} modifiés, {b.retires} retirés, {b.erreurs} erreurs")
    elif a.commande == "chercher":
        from .recherche import chercher

        for r in chercher(conn, " ".join(a.requete), tri="date" if a.date else "pertinence"):
            print(f"{r['date_doc']}  {r['relatif']}")
            if r["extrait"]:
                print(f"            {r['extrait']}")
    elif a.commande == "doublons":
        from .doublons import groupes_doublons

        for g in groupes_doublons(conn):
            print(f"[{_mo(g['recuperable'])}] garder : {g['reference']['relatif']}")
            for copie in g["copies"]:
                print(f"    copie : {copie['relatif']}")
    elif a.commande == "plan":
        from .propositions import propositions_corbeille, propositions_renommage

        print("== Renommage")
        for r in propositions_renommage(conn):
            print(f"{r['document']['relatif']}\n    -> {r['nouveau_nom']}")
        print("== Corbeille")
        for r in propositions_corbeille(conn):
            print(f"[{r['motif']}] {r['document']['relatif']} : {r['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
