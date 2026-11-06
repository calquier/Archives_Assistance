from datetime import date
from pathlib import Path

import docx
import pytest
from fastapi.testclient import TestClient

from archiviste.api import creer_app
from archiviste.config import Config
from archiviste.db import connecter
from archiviste.doublons import groupes_doublons
from archiviste.extraction import date_dans_nom, date_dans_texte
from archiviste.nommage import appliquer_convention, est_conforme
from archiviste.propositions import decider, propositions_corbeille, propositions_renommage
from archiviste.recherche import analyser, chercher
from archiviste.scanner import scanner


def ecrire(chemin: Path, contenu: str | bytes) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(contenu, bytes):
        chemin.write_bytes(contenu)
    else:
        chemin.write_text(contenu, encoding="utf-8")
    return chemin


@pytest.fixture
def arbo(tmp_path: Path) -> Path:
    pro = tmp_path / "ESPACE PRO"
    perso = tmp_path / "ESPACE PERSO"
    ecrire(pro / "[2] Missions" / "ACME" / "Stocks Composants et PF_Lyon_280225 v2.txt",
           "Etat des stocks composants Lyon")
    ecrire(pro / "[2] Missions" / "ACME" / "Stocks Composants et PF_Lyon_280225 v1.txt",
           "Etat des stocks composants Lyon (ancien)")
    ecrire(pro / "[3] Produit" / "Mailing externe produit v2.txt", "Mailing produit")
    ecrire(perso / "ESPACE PRO" / "[3] Produit" / "Mailing externe produit v2.txt", "Mailing produit")
    ecrire(perso / "Crozet" / "Albatros.jpg", b"\xff\xd8photo-albatros")
    ecrire(perso / "Crozet" / "Albatros - Copie.jpg", b"\xff\xd8photo-albatros")
    ecrire(pro / "[8] Fonds" / "[1] Archives R4-DESKTOP-6E47TO4" / "Note R4.txt", "note fonds R4")
    ecrire(pro / "[8] Fonds" / "[1] Archives R4" / "Note R4.txt", "note fonds R4")
    ecrire(pro / "[4] Outils de gestion" / "~$modele.docx", "verrou office")
    ecrire(perso / "Assurances" / "Bail Rue des Lilas.txt", "Bail signé le 12 mars 2019 avenue Rue des Lilas")
    ecrire(perso / "Assurances" / "Bail Rue des Lilas - Copie.txt", "Bail signé le 12 mars 2019 avenue Rue des Lilas")
    d = docx.Document()
    d.add_paragraph("Contrat d'assurance habitation ASSUREUR, émis le 03/04/2023")
    (perso / "Assurances" / "Assureur").mkdir(parents=True)
    d.save(perso / "Assurances" / "Assureur" / "contrat habitation.docx")
    ecrire(pro / "[7] Python" / "script.py", "print('x')")
    ecrire(pro / "node_modules" / "ignore.txt", "ignoré")
    return tmp_path


@pytest.fixture
def conn(arbo: Path, tmp_path: Path):
    c = connecter(tmp_path / "index.sqlite3")
    scanner(c, [arbo / "ESPACE PRO", arbo / "ESPACE PERSO"])
    return c


def test_dates():
    assert date_dans_nom("Stocks_Lyon_280225 v2.xlsx") == date(2025, 2, 28)
    assert date_dans_nom("2024-08-12_avis.pdf") == date(2024, 8, 12)
    assert date_dans_nom("Résultats du test CetSI v10.01.2017.pdf") == date(2017, 1, 10)
    assert date_dans_texte("Paris, le 1er août 2025. Objet : bail") == date(2025, 8, 1)
    assert date_dans_texte("rien ici") is None


def test_scan_incremental_et_ignores(arbo, tmp_path):
    c = connecter(tmp_path / "i2.sqlite3")
    racines = [arbo / "ESPACE PRO", arbo / "ESPACE PERSO"]
    b1 = scanner(c, racines)
    assert b1.ajoutes == b1.vus and b1.erreurs == 0
    assert not c.execute("SELECT 1 FROM documents WHERE relatif LIKE '%node_modules%'").fetchone()
    b2 = scanner(c, racines)
    assert b2.ajoutes == 0 and b2.modifies == 0
    (arbo / "ESPACE PRO" / "[3] Produit" / "Mailing externe produit v2.txt").unlink()
    assert scanner(c, racines).retires == 1


def test_recherche(conn):
    r = chercher(conn, "assurance habitation")
    assert [x["nom"] for x in r] == ["contrat habitation.docx"]
    assert r[0]["date_doc"] == "2023-04-03" and r[0]["date_source"] == "contenu"
    assert chercher(conn, "stock depuis:2025-01-01 rubrique:Missions")
    assert not chercher(conn, "stock jusqua:2024-12-31")
    assert len(chercher(conn, "stocks -ancien")) == 1
    assert chercher(conn, "albatros ext:jpg")
    q = analyser('"lettre de mission" -brouillon depuis:2023-01-01')
    assert analyser('rubrique:"ESPACE PRO/[2] Missions" stock').rubrique == "ESPACE PRO/[2] Missions"
    assert chercher(conn, 'rubrique:"ESPACE PRO/[2] Missions"')
    assert q.mots == ["lettre de mission"] and q.exclus == ["brouillon"] and q.depuis == "2023-01-01"


def test_doublons(conn):
    groupes = groupes_doublons(conn)
    refs = {g["reference"]["nom"] for g in groupes}
    assert "Albatros.jpg" in refs and "Bail Rue des Lilas.txt" in refs
    r4 = next(g for g in groupes if g["reference"]["nom"] == "Note R4.txt")
    assert "DESKTOP" not in r4["reference"]["relatif"]


def test_convention():
    nom = appliquer_convention(
        "Stocks Composants et PF_Lyon_280225 v2.xlsx",
        "[2] Missions/ACME/[3] DATABOOK/Stocks Composants et PF_Lyon_280225 v2.xlsx",
        "2025-02-28", ".xlsx",
    )
    assert nom == "2025-02-28_Etat_ACME_Stocks-Composants-PF-Lyon_v02.xlsx"
    assert est_conforme(nom)
    assert len(nom) <= 80


def test_corbeille(conn):
    props = {p["document"]["nom"]: p for p in propositions_corbeille(conn)}
    assert props["Albatros - Copie.jpg"]["motif"] == "copie"
    assert props["~$modele.docx"]["motif"] == "technique"
    assert props["Stocks Composants et PF_Lyon_280225 v1.txt"]["motif"] == "version"
    conflit = [p for p in props.values() if "DESKTOP" in p["document"]["relatif"]]
    assert conflit and conflit[0]["motif"] == "conflit"
    # Un bail est protégé, même en double.
    assert not any("Bail" in n for n in props)
    assert "Stocks Composants et PF_Lyon_280225 v2.txt" not in props


def test_renommage_et_decisions(conn):
    props = propositions_renommage(conn)
    noms = {p["document"]["nom"] for p in props}
    assert "script.py" not in noms
    assert "Albatros - Copie.jpg" not in noms and "Albatros.jpg" in noms
    p = next(p for p in props if p["document"]["nom"] == "contrat habitation.docx")
    assert p["nouveau_nom"] == "2023-04-03_Contrat_Assureur_Habitation.docx"
    decider(conn, p["cle"], "refusee")
    assert all(x["cle"] != p["cle"] for x in propositions_renommage(conn))
    decider(conn, p["cle"], "annuler")
    assert any(x["cle"] == p["cle"] for x in propositions_renommage(conn))


def test_api(arbo, tmp_path):
    cfg = Config(racines=[arbo / "ESPACE PRO", arbo / "ESPACE PERSO"], db_path=tmp_path / "api.sqlite3")
    client = TestClient(creer_app(cfg))
    assert client.post("/api/scan").json()["lance"]
    import time
    for _ in range(100):
        if not client.get("/api/etat").json()["scan_en_cours"]:
            break
        time.sleep(0.05)
    etat = client.get("/api/etat").json()
    assert etat["documents"] > 10 and etat["doublons"]["groupes"] >= 3
    assert client.get("/api/recherche", params={"q": "habitation"}).json()["resultats"]
    cle = client.get("/api/propositions/corbeille").json()["propositions"][0]["cle"]
    assert client.post(f"/api/propositions/{cle}", json={"statut": "acceptee"}).status_code == 200
    assert client.post(f"/api/propositions/{cle}", json={"statut": "n'importe"}).status_code == 400
    assert client.get("/").status_code == 200


def test_interface_reste_disponible_pendant_inventaire(arbo, tmp_path, monkeypatch):
    """Pendant un inventaire long, /api/etat répond et voit le compte progresser."""
    import threading
    import time

    import archiviste.api as api_mod
    from archiviste.scanner import scanner as vrai_scanner

    feu = threading.Event()

    def scanner_lent(conn, racines):
        bilan = vrai_scanner(conn, racines)
        feu.wait(5)
        return bilan

    monkeypatch.setattr(api_mod, "scanner", scanner_lent)
    cfg = Config(racines=[arbo / "ESPACE PRO"], db_path=tmp_path / "lent.sqlite3")
    client = TestClient(creer_app(cfg))
    assert client.post("/api/scan").json()["lance"]
    time.sleep(0.3)
    debut = time.time()
    etat = client.get("/api/etat").json()
    assert time.time() - debut < 2
    assert etat["scan_en_cours"] and etat["documents"] > 0
    assert client.get("/").headers["cache-control"] == "no-cache"
    feu.set()
