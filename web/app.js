/* Archiviste : interface web. Même organisation que la Console personnelle :
   rail de modules à gauche, bandeau, onglets, colonne de lecture. */
(function(){
  "use strict";

  var S = {arbre:null, choix:{}, ouverts:{}, exploration:false,
    mod:"accueil", sub:{}, etat:null, q:"", tri:"pertinence", resultats:null, doublons:null, renommage:null, corbeille:null, busy:false};

  /* ---------- Utilitaires ---------- */
  function esc(s){ return String(s == null ? "" : s).replace(/[&<>"']/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]; }); }
  var NF = new Intl.NumberFormat("fr-FR");
  function n(x){ return NF.format(x || 0); }
  function fichiersTxt(x){ return n(x) + (x > 1 ? " fichiers" : " fichier"); }
  function taille(o){ if (!o) return "0 Mo"; if (o < 1e6) return Math.max(1, Math.round(o / 1e3)) + " Ko"; if (o >= 1e9) return (o / 1e9).toFixed(1).replace(".", ",") + " Go"; return (o / 1e6).toFixed(1).replace(".", ",") + " Mo"; }
  function dateFr(k){ var p = String(k || "").split("-"); return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : (k || ""); }
  function quand(ts){ return ts ? new Date(ts * 1000).toLocaleString("fr-FR", {day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit"}) : "jamais"; }
  /* Indicateur animé. Le décalage d'animation suit l'horloge pour que la rotation
     reste fluide quand l'écran est redessiné (toutes les 1,5 s pendant un inventaire). */
  function spinner(){ return '<span class="spinner" aria-hidden="true" style="animation-delay:-' + (Date.now() % 800) + 'ms"></span>'; }
  function attente(texte){ return '<p class="loading" role="status">' + spinner() + esc(texte) + '</p>'; }
  var toastTimer;
  function toast(msg){ var el = document.getElementById("toast"); el.textContent = msg; el.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(function(){ el.hidden = true; }, 5000); }

  function api(path, opts){
    return fetch(path, opts).then(function(r){
      return r.json().then(function(j){ if (!r.ok) throw new Error(j.detail || ("Erreur " + r.status)); return j; });
    });
  }
  function post(path, body){ return api(path, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body || {})}); }

  /* ---------- Icônes (traits 24 × 24, même style que la console) ---------- */
  var ICONS = {
    accueil:'<path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z"/>',
    dossiers:'<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/><path d="M8 13h8M8 16h5"/>',
    recherche:'<circle cx="10.5" cy="10.5" r="6"/><path d="m15 15 5.5 5.5"/>',
    doublons:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>',
    propositions:'<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/><path d="m9 14 2 2 4-4"/>',
    reglages:'<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2.2"/><circle cx="9" cy="17" r="2.2"/>'
  };
  function icon(k){ return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICONS[k] + '</svg>'; }

  /* ---------- Modules ---------- */
  var MODS = [
    {id:"accueil", name:"Accueil", cat:null},
    {id:"dossiers", name:"Dossiers à classer", cat:"Archives"},
    {id:"recherche", name:"Recherche", cat:"Archives"},
    {id:"doublons", name:"Doublons", cat:"Archives", badge:function(){ return S.etat && S.etat.doublons.groupes; }},
    {id:"propositions", name:"Propositions", cat:"Rangement",
      badge:function(){ return (S.classement ? S.classement.propositions.length : 0) + (S.renommage ? S.renommage.length : 0) + (S.corbeille ? S.corbeille.length : 0) || null; },
      tabs:function(){ return [["classement", "Classement", S.classement ? S.classement.propositions.length : null], ["renommage", "Renommage", S.renommage ? S.renommage.length : null], ["corbeille", "Corbeille", S.corbeille ? S.corbeille.length : null]]; }},
    {id:"reglages", name:"Réglages", cat:"admin"}
  ];
  function mod(id){ return MODS.filter(function(m){ return m.id === id; })[0] || MODS[0]; }

  function go(id, sub){
    S.mod = mod(id).id; if (sub) S.sub[S.mod] = sub;
    try { history.replaceState(null, "", "#" + S.mod); } catch(e){}
    charger(S.mod); render(); window.scrollTo(0, 0);
  }

  /* ---------- Chargements ---------- */
  function chargerEtat(){
    return api("/api/etat").then(function(e){ S.etat = e; render(); if (e.scan_en_cours) setTimeout(chargerEtat, 1500); })
      .catch(function(err){ toast(err.message); });
  }
  function charger(id){
    if (id === "dossiers" && !S.arbre) chargerArbre();
    if (id === "doublons") api("/api/doublons").then(function(r){ S.doublons = r.groupes; render(); });
    if (id === "propositions"){
      api("/api/propositions/classement").then(function(r){ S.classement = r; render(); });
      api("/api/propositions/renommage").then(function(r){ S.renommage = r.propositions; render(); });
      api("/api/propositions/corbeille").then(function(r){ S.corbeille = r.propositions; render(); });
    }
  }
  function chercher(){
    S.busy = true; render();
    api("/api/recherche?q=" + encodeURIComponent(S.q) + "&tri=" + S.tri).then(function(r){ S.resultats = r.resultats; S.busy = false; render(); })
      .catch(function(err){ S.busy = false; toast(err.message); render(); });
  }

  /* ---------- Rendu ---------- */
  function renderRail(){
    var item = function(m){
      var b = m.badge ? m.badge() : null;
      return '<button class="nav-item" data-act="nav" data-mod="' + m.id + '"' + (S.mod === m.id ? ' aria-current="page"' : '') + '>' + icon(m.id) +
        '<span>' + esc(m.name) + '</span>' + (b ? '<span class="nav-badge">' + esc(n(b)) + '</span>' : '') + '</button>';
    };
    var html = '<button class="brand" data-act="nav" data-mod="accueil"><span class="brand-mark">AR</span><span class="brand-name"><b>Archiviste</b><small>archives</small></span></button>';
    html += item(MODS[0]);
    var cats = [];
    MODS.forEach(function(m){ if (m.cat && m.cat !== "admin" && cats.indexOf(m.cat) < 0) cats.push(m.cat); });
    cats.forEach(function(c){
      html += '<p class="nav-cat">' + esc(c) + '</p>' + MODS.filter(function(m){ return m.cat === c; }).map(item).join("");
    });
    html += '<span class="rail-sep"></span>' + MODS.filter(function(m){ return m.cat === "admin"; }).map(item).join("");
    var d = S.etat && S.etat.dernier_scan;
    html += '<p class="rail-note">' + (S.etat && S.etat.scan_en_cours ? spinner() + "Inventaire en cours · " + esc(n(S.etat.documents)) + " documents" : "Dernier inventaire : " + esc(quand(d && d.fin))) + '</p>';
    document.getElementById("rail").innerHTML = html;
  }

  function bandHtml(kicker, title, meta, actions){
    return '<div style="min-width:0"><p class="kicker">' + esc(kicker) + '</p><h1>' + esc(title) + '</h1>' +
      (meta ? '<p class="band-meta">' + esc(meta) + '</p>' : '') + '</div>' + (actions ? '<div class="band-actions">' + actions + '</div>' : '');
  }
  function boutonScan(){
    var en = S.etat && S.etat.scan_en_cours;
    return '<button class="btn gold" data-act="scan"' + (en ? " disabled" : "") + '>' + (en ? spinner() + "Inventaire en cours…" : "Préparer l'inventaire") + '</button>';
  }

  function renderTabs(m){
    var nav = document.getElementById("tabsnav"), tabs = m.tabs ? m.tabs() : null;
    nav.hidden = !tabs;
    if (!tabs) return;
    var cur = S.sub[m.id] || tabs[0][0];
    document.getElementById("tabs").innerHTML = tabs.map(function(t){
      return '<button class="tab" role="tab" data-act="tab" data-tab="' + t[0] + '" aria-selected="' + (cur === t[0]) + '">' + esc(t[1]) + (t[2] != null ? '<span class="n">' + n(t[2]) + '</span>' : '') + '</button>';
    }).join("");
  }

  function render(){
    var m = mod(S.mod), band = "", main = "";
    var e = S.etat;
    renderRail(); renderTabs(m);
    if (!e){ document.getElementById("main").innerHTML = attente("Chargement…"); return; }
    if (m.id === "accueil"){
      band = bandHtml("Archiviste", "Vos archives", n(e.documents) + " documents indexés · " + taille(e.taille), boutonScan());
      main = vueAccueil(e);
    } else if (m.id === "dossiers"){
      var tot = totaux();
      band = bandHtml("Inventaire", "Dossiers à classer",
        S.arbre ? "Sélection : " + n(tot.sf) + " fichiers · " + taille(tot.st) + " sur " + n(tot.f) + " fichiers · " + taille(tot.t) : "Choisissez les branches à inventorier",
        S.arbre ? boutonLancer() : "");
      main = vueDossiers();
    } else if (m.id === "recherche"){
      band = bandHtml("Archives", "Recherche", "Mots-clés, rubriques et dates dans " + n(e.documents) + " documents");
      main = vueRecherche();
    } else if (m.id === "doublons"){
      band = bandHtml("Archives", "Doublons", n(e.doublons.groupes) + " groupes · " + taille(e.doublons.recuperable) + " récupérables");
      main = vueDoublons();
    } else if (m.id === "propositions"){
      band = bandHtml("Rangement", "Propositions", "Rien n'est modifié tant que vous n'avez pas validé.");
      var onglet = S.sub.propositions || "classement";
      main = onglet === "classement" ? vueClassement() : onglet === "renommage" ? vueRenommage() : vueCorbeille();
    } else {
      band = bandHtml("Administration", "Réglages", "Dossiers indexés et syntaxe de recherche");
      main = vueReglages(e);
    }
    document.getElementById("band").innerHTML = band;
    var el = document.getElementById("main"), actif = document.activeElement, focusQ = actif && actif.id === "q";
    el.innerHTML = main;
    Array.prototype.forEach.call(el.querySelectorAll('input[data-mixte]'), function(c){ c.indeterminate = true; });
    if (focusQ){ var q = document.getElementById("q"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  }

  function vueAccueil(e){
    if (!e.racines.length) return '<div class="empty"><b>Aucun dossier à indexer.</b> Renseignez ARCHIVISTE_RACINES dans le fichier .env, puis relancez l\'Archiviste.</div>';
    var d = e.dernier_scan;
    var h = '<section class="tiles">' +
      '<div class="tile" style="--edge:var(--gold)"><b>' + n(e.documents) + '</b><span>documents indexés</span></div>' +
      '<div class="tile"><b>' + taille(e.taille) + '</b><span>volume total</span></div>' +
      '<div class="tile" style="--edge:var(--p2)"><b>' + n(e.doublons.groupes) + '</b><span>groupes de doublons</span></div>' +
      '<div class="tile" style="--edge:var(--ok)"><b>' + taille(e.doublons.recuperable) + '</b><span>récupérables</span></div></section>';
    if (e.scan_en_cours) h += '<div class="callout loading" role="status">' + spinner() + '<span>Inventaire en cours : ' + n(e.documents) + ' documents lus jusqu\'ici. Cela peut prendre plusieurs minutes ; vous pouvez continuer à utiliser l\'app.</span></div>';
    if (e.erreur_scan) h += '<div class="callout">Le dernier scan a échoué : ' + esc(e.erreur_scan) + '</div>';
    if (d) h += '<p class="muted" style="margin:0">Dernier inventaire le ' + esc(quand(d.fin)) + ' : ' + n(d.vus) + ' fichiers vus, ' + n(d.ajoutes) + ' ajoutés, ' + n(d.modifies) + ' modifiés, ' + n(d.retires) + ' retirés' + (d.erreurs ? ', ' + n(d.erreurs) + ' erreurs' : '') + '.</p>';
    if (!e.documents && !e.scan_en_cours) return h + '<div class="empty"><b>L\'index est vide.</b> Cliquez sur « Préparer l\'inventaire » pour choisir les dossiers à classer, puis lancez l\'inventaire : l\'Archiviste lit vos dossiers sans rien modifier.</div>';
    h += '<section><h2>Rubriques<small>' + n(e.rubriques.length) + '</small></h2><div class="scroll"><table><thead><tr><th>Rubrique</th><th class="num">Documents</th><th class="num">Volume</th></tr></thead><tbody>' +
      e.rubriques.map(function(r){ return '<tr><td><button class="btn sm" style="border:0;padding:0;background:none;text-align:left" data-act="rubrique" data-r="' + esc(r.rubrique) + '">' + esc(r.rubrique) + '</button></td><td class="num">' + n(r.n) + '</td><td class="num">' + taille(r.taille) + '</td></tr>'; }).join("") +
      '</tbody></table></div></section>';
    return h;
  }

  function snippet(s){ return esc(s).replace(/\[/g, "<mark>").replace(/\]/g, "</mark>"); }
  function chemin(r){ var racine = String(r.racine || "").split(/[\\/]/).pop(); var dossier = String(r.relatif || "").split(/[\\/]/).slice(0, -1).join(" / "); return racine + (dossier ? " / " + dossier : ""); }
  function ligneDoc(r, extra, actions){
    return '<b>' + esc(r.nom) + '</b><span class="meta">' + esc(chemin(r)) + '</span>' + (extra || "") +
      '</div><div class="actions">' + (actions || "") + '<button class="btn sm" data-act="ouvrir" data-id="' + r.id + '">Ouvrir</button><button class="btn sm" data-act="dossier" data-id="' + r.id + '">Dossier</button>';
  }

  function vueRecherche(){
    var h = '<form class="toolbar" data-act="chercher"><input id="q" class="input grow" type="search" placeholder="ex. assurance habitation depuis:2023-01-01" value="' + esc(S.q) + '" autocomplete="off">' +
      '<select class="input" id="tri"><option value="pertinence"' + (S.tri === "pertinence" ? " selected" : "") + '>Pertinence</option><option value="date"' + (S.tri === "date" ? " selected" : "") + '>Date</option></select>' +
      '<button class="btn primary" type="submit">Chercher</button></form>' +
      '<p class="muted" style="margin:-12px 0 0;font-size:.88rem">Filtres : <code>rubrique:Missions</code> <code>ext:pdf</code> <code>depuis:2023-01-01</code> <code>jusqua:2024-12-31</code> <code>-mot</code> <code>"expression exacte"</code></p>';
    if (S.busy) return h + attente("Recherche en cours…");
    if (!S.resultats) return h;
    if (!S.resultats.length) return h + '<div class="empty"><b>Aucun document trouvé.</b> Essayez moins de mots ou retirez un filtre.</div>';
    h += '<h2>Résultats<small>' + n(S.resultats.length) + (S.resultats.length >= 100 ? " premiers" : "") + '</small></h2><ul class="alist">' +
      S.resultats.map(function(r){
        var date = '<span class="meta">' + esc(dateFr(r.date_doc)) + (r.date_source === "fichier" ? ' <span class="chip">date du fichier</span>' : '') + '</span>';
        return '<li class="arow"><div>' + ligneDoc(r, date + (r.extrait ? '<span class="snip">' + snippet(r.extrait) + '</span>' : '')) + '</div></li>';
      }).join("") + '</ul>';
    return h;
  }

  function vueDoublons(){
    if (!S.doublons) return attente("Recherche des doublons…");
    if (!S.doublons.length) return '<div class="empty"><b>Aucun doublon.</b></div>';
    return '<p class="muted" style="margin:0">Pour chaque groupe, l\'exemplaire en gras est celui à garder ; les copies sont proposées à la corbeille dans Propositions.</p>' +
      S.doublons.map(function(g){
        return '<div class="group"><span class="ref">' + esc(g.reference.relatif) + '</span><span class="meta muted">' + esc(g.reference.rubrique) + ' · ' + taille(g.taille) + ' par exemplaire · ' + taille(g.recuperable) + ' récupérables</span><ul>' +
          g.copies.map(function(c){ return '<li>' + esc(chemin(c)) + ' / ' + esc(c.nom) + '</li>'; }).join("") + '</ul></div>';
      }).join("");
  }

  function boutonsDecision(p){
    if (p.statut === "acceptee") return '<span class="chip gold">Validée</span><button class="btn sm" data-act="decider" data-cle="' + p.cle + '" data-st="annuler">Annuler</button>';
    return '<button class="btn sm ok" data-act="decider" data-cle="' + p.cle + '" data-st="acceptee">Valider</button><button class="btn sm ko" data-act="decider" data-cle="' + p.cle + '" data-st="refusee">Refuser</button>';
  }
  var bandeauPlan = '<div class="callout">Valider une proposition l\'inscrit au plan de rangement ; l\'application des changements validés (classement, renommage, corbeille OneDrive) arrive à l\'étape suivante, avec un journal pour revenir en arrière. Une proposition refusée n\'est plus présentée.</div>';

  function vueRenommage(){
    if (!S.renommage) return attente("Préparation des propositions…");
    if (!S.renommage.length) return '<div class="empty"><b>Tous les fichiers suivent déjà la convention.</b></div>';
    return bandeauPlan + '<p class="muted" style="margin:0">Convention : <code>AAAA-MM-JJ_Type_Tiers_Précision_vNN.ext</code>. Une puce « date à vérifier » signale une date prise sur le fichier faute de date dans le document.</p><ul class="alist">' +
      S.renommage.map(function(p){
        var d = p.document;
        return '<li class="arow" data-st="' + p.statut + '"><div>' + ligneDoc(d, '<span class="new">→ ' + esc(p.nouveau_nom) + '</span>' + (p.a_verifier ? ' <span class="chip warn">date à vérifier</span>' : ''), boutonsDecision(p)) + '</div></li>';
      }).join("") + '</ul>';
  }

  /* Classement : regroupé par rubrique cible (« ESPACE PERSO / [3] Banque… »). */
  function rubriqueDe(cible){ return cible.split("/").slice(0, 2).join(" / "); }
  function ligneClassement(p){
    var dossier = p.portee === "dossier";
    var titre = dossier ? p.source.split("/").pop() : p.source.split("/").pop();
    var info = '<span class="meta">' + (dossier ? "Dossier · " : "Fichier · ") + esc(fichiersTxt(p.fichiers)) + ' · ' + taille(p.taille) +
      (p.fusion ? ' · <span class="chip gold">fusion avec un dossier existant</span>' : '') +
      (p.confiance < 0.7 ? ' · <span class="chip warn">à vérifier</span>' : '') +
      (p.doublons ? ' · <span class="chip warn">' + (p.portee === "fichier" && p.fichiers === 1 ? "doublon" : n(p.doublons) + (p.doublons > 1 ? " doublons" : " doublon")) + '</span>' : '') + '</span>' +
      (p.doublons_exemples && p.doublons_exemples.length ? '<span class="meta">Même contenu déjà dans : ' + p.doublons_exemples.map(function(c){ return esc(c.split("/").join(" / ")); }).join(" ; ") + (p.doublons > p.doublons_exemples.length ? " …" : "") + '</span>' : '') +
      '<span class="meta">De : ' + esc(p.source.split("/").join(" / ")) + '</span>' +
      '<span class="new">→ ' + esc(p.cible.split("/").join(" / ")) + '</span>' +
      (p.motif ? '<span class="meta">' + esc(p.motif) + '</span>' : '');
    var actions = boutonsDecision(p) + (p.document ? '<button class="btn sm" data-act="ouvrir" data-id="' + p.document.id + '">Ouvrir</button>' : '');
    return '<li class="arow" data-st="' + p.statut + '"><div><b>' + esc(titre) + '</b>' + info + '</div><div class="actions">' + actions + '</div></li>';
  }
  function vueClassement(){
    var c = S.classement;
    if (!c) return attente("Préparation des propositions de classement…");
    if (!c.plan_present) return '<div class="empty"><b>Aucun plan de classement.</b> Le fichier plan_classement.json, qui décrit vos rubriques, n\'est pas encore installé sur ce poste.</div>';
    if (!c.propositions.length) return '<div class="empty"><b>Tout est rangé selon le plan.</b> Aucune proposition de classement.</div>';
    var groupes = {}, ordre = [];
    c.propositions.forEach(function(p){ var g = rubriqueDe(p.cible); if (!groupes[g]){ groupes[g] = []; ordre.push(g); } groupes[g].push(p); });
    ordre.sort();
    var nd = c.propositions.filter(function(p){ return p.portee === "dossier"; }).length;
    var nb = c.propositions.reduce(function(t, p){ return t + (p.doublons || 0); }, 0);
    return bandeauPlan + '<p class="muted" style="margin:0">' + n(nd) + ' dossiers et ' + n(c.propositions.length - nd) + ' fichiers isolés à ranger, regroupés par rubrique cible. Les noms et le contenu des fichiers ne changent pas.' +
      (nb ? ' <b>' + n(nb) + ' fichiers concernés ont un exemplaire identique ailleurs</b> (doublons potentiels, signalés en orange).' : '') + '</p>' +
      ordre.map(function(g){
        return '<section><h2>' + esc(g) + '<small>' + n(groupes[g].length) + '</small></h2><ul class="alist">' + groupes[g].map(ligneClassement).join("") + '</ul></section>';
      }).join("");
  }

  var MOTIFS = {technique:"Fichier technique", copie:"Copie", conflit:"Conflit OneDrive", doublon:"Doublon", version:"Version antérieure"};
  function vueCorbeille(){
    if (!S.corbeille) return attente("Préparation des propositions…");
    if (!S.corbeille.length) return '<div class="empty"><b>Aucune proposition de corbeille.</b></div>';
    return bandeauPlan + '<p class="muted" style="margin:0">Les pièces d\'identité, impôts, contrats, baux, bulletins, factures, statuts et PV ne sont jamais proposés.</p><ul class="alist">' +
      S.corbeille.map(function(p){
        var d = p.document;
        var extra = '<span class="meta"><span class="chip">' + esc(MOTIFS[p.motif] || p.motif) + '</span> ' + esc(p.detail) + ' · ' + taille(d.taille) + '</span>' +
          (p.reference ? '<span class="meta">Exemplaire gardé : ' + esc(chemin(p.reference) + " / " + p.reference.nom) + '</span>' : '');
        return '<li class="arow" data-st="' + p.statut + '"><div>' + ligneDoc(d, extra, boutonsDecision(p)) + '</div></li>';
      }).join("") + '</ul>';
  }

  function vueReglages(e){
    return '<section class="panel"><h3>Dossiers indexés</h3>' +
      (e.racines.length ? '<ul style="margin:0;padding-left:18px">' + e.racines.map(function(r){ return '<li><code>' + esc(r) + '</code></li>'; }).join("") + '</ul>' : '<p>Aucun.</p>') +
      '<p class="muted">Pour en changer, modifiez <code>ARCHIVISTE_RACINES</code> dans le fichier <code>.env</code> (chemins séparés par <code>;</code>) puis relancez l\'Archiviste.</p></section>' +
      '<section class="panel"><h3>Mise à jour automatique</h3><p>Le script <code>scripts\\installer-tache.ps1</code> crée une tâche Windows qui met l\'index à jour chaque dimanche à 20 h. Le scan ne modifie aucun fichier.</p></section>' +
      '<section class="panel"><h3>Syntaxe de recherche</h3><div class="scroll"><table><tbody>' +
      [["facture orange", "tous les mots (début de mot, accents ignorés)"], ['"lettre de mission"', "expression exacte"], ["-brouillon", "exclure un mot"], ["rubrique:Missions", "dans une rubrique"], ["ext:pdf", "par type de fichier"], ["depuis:2023-01-01 jusqua:2024-12-31", "par date du document"]]
        .map(function(r){ return '<tr><td><code>' + esc(r[0]) + '</code></td><td>' + esc(r[1]) + '</td></tr>'; }).join("") +
      '</tbody></table></div></section>';
  }

  /* ---------- Dossiers à classer ---------- */
  function chargerArbre(){
    if (S.exploration) return;
    S.exploration = true; render();
    api("/api/arborescence").then(function(r){
      S.arbre = r.racines; S.choix = r.choix || {}; S.exploration = false;
      r.racines.forEach(function(x){ if (S.ouverts[x.chemin] === undefined) S.ouverts[x.chemin] = true; });
      render();
    }).catch(function(err){ S.exploration = false; toast(err.message); render(); });
  }
  /* Choix effectif : celui du dossier, sinon celui hérité du parent ; tout est inclus par défaut. */
  function eff(noeud, herite){ return Object.prototype.hasOwnProperty.call(S.choix, noeud.chemin) ? S.choix[noeud.chemin] : herite; }
  /* Fichiers et taille sélectionnés dans une branche, et si elle est partiellement cochée. */
  function stats(noeud, herite){
    var e = eff(noeud, herite), sf = 0, st = 0, ef = 0, et = 0, mixte = false;
    noeud.enfants.forEach(function(c){
      var x = stats(c, e); sf += x.sf; st += x.st; ef += c.fichiers; et += c.taille;
      if (x.mixte || x.inclus !== e) mixte = true;
    });
    if (e){ sf += noeud.fichiers - ef; st += noeud.taille - et; }
    return {inclus: e, sf: sf, st: st, mixte: mixte};
  }
  function totaux(){
    var r = {sf:0, st:0, f:0, t:0};
    (S.arbre || []).forEach(function(x){ var k = stats(x, true); r.sf += k.sf; r.st += k.st; r.f += x.fichiers; r.t += x.taille; });
    return r;
  }
  function trouver(chemin, liste, herite){
    for (var i = 0; i < liste.length; i++){
      var x = liste[i], e = eff(x, herite);
      if (x.chemin === chemin) return {noeud: x, herite: herite};
      var r = trouver(chemin, x.enfants, e); if (r) return r;
    }
    return null;
  }
  function basculer(chemin){
    var f = trouver(chemin, S.arbre, true); if (!f) return;
    var st = stats(f.noeud, f.herite), cible = st.mixte ? true : !st.inclus;
    // La branche entière suit le nouveau choix : on retire les choix de ses sous-dossiers.
    var prefixe = chemin.replace(/[\\/]+$/, "");
    Object.keys(S.choix).forEach(function(k){ if (k.length > prefixe.length && k.indexOf(prefixe) === 0 && /[\\/]/.test(k.charAt(prefixe.length))) delete S.choix[k]; });
    if (cible === f.herite) delete S.choix[chemin]; else S.choix[chemin] = cible;
    sauverChoix(); render();
  }
  function sauverChoix(){
    if (S.etat && S.etat.scan_en_cours) return;
    api("/api/selection", {method:"PUT", headers:{"Content-Type":"application/json"}, body: JSON.stringify({choix: S.choix})}).catch(function(){});
  }
  function boutonLancer(){
    var en = S.etat && S.etat.scan_en_cours;
    return '<button class="btn gold" data-act="lancer"' + (en ? " disabled" : "") + '>' + (en ? spinner() + "Inventaire en cours…" : "Lancer l'inventaire") + '</button>';
  }
  function lignesArbre(liste, herite, niveau, out){
    liste.forEach(function(x){
      var s = stats(x, herite), ouvert = !!S.ouverts[x.chemin], aEnfants = x.enfants.length > 0;
      out.push('<li class="tnode' + (s.inclus || s.mixte ? '' : ' off') + '" style="--niv:' + niveau + '">' +
        (aEnfants ? '<button class="tcaret" data-act="noeud" data-k="' + esc(x.chemin) + '" aria-expanded="' + ouvert + '" aria-label="' + (ouvert ? "Replier " : "Déplier ") + esc(x.nom) + '">' + (ouvert ? "▾" : "▸") + '</button>' : '<span class="tcaret"></span>') +
        '<label><input type="checkbox" data-chk="' + esc(x.chemin) + '"' + (s.inclus && !s.mixte ? " checked" : "") + (s.mixte ? ' data-mixte="1"' : "") + (S.etat && S.etat.scan_en_cours ? " disabled" : "") + '>' +
        '<span class="tname">' + esc(x.nom) + '</span></label>' +
        '<span class="tnum">' + fichiersTxt(x.fichiers) + '</span><span class="tnum">' + taille(x.taille) + '</span>' +
        (s.mixte ? '<span class="tsel">' + n(s.sf) + ' cochés</span>' : '<span class="tsel"></span>') + '</li>');
      if (aEnfants && ouvert) lignesArbre(x.enfants, s.inclus, niveau + 1, out);
    });
    return out;
  }
  function vueDossiers(){
    if (S.exploration || !S.arbre) return attente("Exploration des dossiers… (nombre de fichiers et taille, sans ouvrir les fichiers)");
    if (!S.arbre.length) return '<div class="empty"><b>Aucun dossier à analyser.</b> Vérifiez les dossiers dans Réglages.</div>';
    var h = '<div class="callout">Cochez les branches à classer, puis cliquez sur « Lancer l\'inventaire ». Les branches décochées ne sont pas lues, et leurs documents sortent de l\'index. Le choix est gardé pour les prochains inventaires.</div>';
    if (S.etat && S.etat.scan_en_cours) h += '<div class="callout loading" role="status">' + spinner() + '<span>Un inventaire est en cours : la sélection pourra être modifiée à la fin.</span></div>';
    h += '<div class="toolbar"><button class="btn sm" data-act="tout" data-v="1">Tout cocher</button><button class="btn sm" data-act="tout" data-v="0">Tout décocher</button><span class="grow"></span><button class="btn sm" data-act="rafraichir-arbre">Actualiser</button></div>';
    h += '<ul class="tree" aria-label="Dossiers">' + lignesArbre(S.arbre, true, 0, []).join("") + '</ul>';
    return h;
  }

  /* ---------- Événements ---------- */
  document.addEventListener("click", function(ev){
    var t = ev.target.closest("[data-act]"); if (!t || t.tagName === "FORM") return;
    var a = t.getAttribute("data-act");
    if (a === "nav") go(t.getAttribute("data-mod"));
    else if (a === "tab"){ S.sub[S.mod] = t.getAttribute("data-tab"); render(); }
    else if (a === "rafraichir-arbre"){ S.arbre = null; chargerArbre(); }
    else if (a === "noeud"){ var k = t.getAttribute("data-k"); S.ouverts[k] = !S.ouverts[k]; render(); }
    else if (a === "tout"){ S.choix = {}; if (t.getAttribute("data-v") === "0") S.arbre.forEach(function(r){ S.choix[r.chemin] = false; }); sauverChoix(); render(); }
    else if (a === "lancer"){
      api("/api/selection", {method:"PUT", headers:{"Content-Type":"application/json"}, body: JSON.stringify({choix: S.choix})})
        .then(function(){ return post("/api/scan"); })
        .then(function(r){ toast(r.lance ? "Inventaire lancé sur les dossiers cochés." : r.raison); go("accueil"); chargerEtat(); })
        .catch(function(err){ toast(err.message); });
    }
    else if (a === "scan"){ go("dossiers"); }
    else if (a === "scan-direct"){
      post("/api/scan").then(function(r){ toast(r.lance ? "Inventaire lancé : l'index se met à jour." : r.raison); chargerEtat(); }).catch(function(err){ toast(err.message); });
    }
    else if (a === "rubrique"){ S.q = 'rubrique:"' + t.getAttribute("data-r").replace(/"/g, "") + '"'; S.tri = "date"; go("recherche"); chercher(); }
    else if (a === "ouvrir" || a === "dossier"){
      post("/api/ouvrir/" + t.getAttribute("data-id") + (a === "dossier" ? "?dossier=true" : "")).catch(function(err){ toast(err.message); });
    }
    else if (a === "decider"){
      var cle = t.getAttribute("data-cle"), st = t.getAttribute("data-st");
      post("/api/propositions/" + cle, {statut: st}).then(function(){
        [S.classement && S.classement.propositions, S.renommage, S.corbeille].forEach(function(list){
          if (!list) return;
          for (var i = 0; i < list.length; i++) if (list[i].cle === cle){
            if (st === "refusee") list.splice(i, 1); else list[i].statut = st === "annuler" ? "proposee" : st;
            break;
          }
        });
        render();
      }).catch(function(err){ toast(err.message); });
    }
  });
  document.addEventListener("change", function(ev){
    var k = ev.target.getAttribute && ev.target.getAttribute("data-chk");
    if (k != null) basculer(k);
  });
  document.addEventListener("submit", function(ev){
    if (ev.target.getAttribute("data-act") !== "chercher") return;
    ev.preventDefault();
    S.q = document.getElementById("q").value.trim();
    S.tri = document.getElementById("tri").value;
    chercher();
  });

  window.addEventListener("hashchange", function(){ var k = (location.hash || "").slice(1); if (k && k !== S.mod && mod(k).id === k) go(k); });

  /* ---------- Démarrage ---------- */
  var h = (location.hash || "").slice(1);
  if (h && mod(h).id === h) S.mod = h;
  chargerEtat().then(function(){ charger(S.mod); api("/api/propositions/classement").then(function(r){ S.classement = r; render(); }); api("/api/propositions/renommage").then(function(r){ S.renommage = r.propositions; render(); }); api("/api/propositions/corbeille").then(function(r){ S.corbeille = r.propositions; render(); }); });
  render();
})();
