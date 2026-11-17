import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { apiDemo, etudeDemo, retoursDemo, santeDemo, utilisateursDemo, vueEnsembleDemo } from "./demo";
import { EtudeVue } from "./Etude";
import { ListeRetours, Traitement } from "./Retours";
import { SanteVue } from "./Sante";
import { TableUtilisateurs, trierParActivite } from "./Utilisateurs";
import { VueEnsembleVue } from "./VueEnsemble";
import { choisirApi, periodeTelemetrie } from "./api";
import type { RetoursData } from "./types";

const rendre = (n: React.ReactElement) => renderToStaticMarkup(n);

describe("admin : vue d'ensemble", () => {
  it("affiche les KPI avec leur origine et la courbe", () => {
    const h = rendre(<VueEnsembleVue data={vueEnsembleDemo("30j")} recos={[]} />);
    expect(h).toContain("Utilisateurs actifs");
    expect(h).toContain("Ancienne version");
    expect(h).toContain("Étude");
    expect(h).toContain("<svg");
    expect(h).toContain("Activité par jour");
  });
  it("masque les blocs dont l'origine est vide", () => {
    const d = { ...vueEnsembleDemo("7j"), origines: { v3: false, ancienne_version: false, etude: false } };
    const h = rendre(<VueEnsembleVue data={d} recos={[]} />);
    expect(h).not.toContain("Projets générés");
    expect(h).not.toContain("Dossiers d&#x27;étude");
    expect(h).toContain("Aucune activité v3");
  });
  it("la période « tout » se lit sur 90 jours côté télémétrie", () => { expect(periodeTelemetrie("tout")).toBe("90j"); });
});

describe("admin : retours", () => {
  const data: RetoursData = { total: retoursDemo.length, page: 1, items: retoursDemo };
  const liste = (ouvertId: string | null = null) => rendre(<ListeRetours data={data} ouvertId={ouvertId} notes={{}} onBascule={() => {}} onEnregistrer={async () => { throw new Error("x"); }} />);
  it("liste unique : une ligne par retour, sans doublon d'identifiant", () => {
    const h = liste();
    expect(h.match(/<li /g)).toHaveLength(retoursDemo.length);
    expect(new Set(retoursDemo.map((r) => r.id)).size).toBe(retoursDemo.length);
    expect(h).toContain("Le code ADICAP du côlon est faux");
    expect(h).toContain("Ancienne version");
    expect(h).toContain("2 / 5");
  });
  it("seuls les signalements se traitent sur place", () => {
    const h = liste();
    expect(h.match(/aria-expanded/g)).toHaveLength(retoursDemo.filter((r) => r.nature === "signalement").length);
  });
  it("le traitement propose les quatre statuts et une note admin", () => {
    const r = retoursDemo.find((x) => x.nature === "signalement")!;
    const h = rendre(<Traitement r={r} onEnregistrer={apiDemo.majSignalement.bind(null, r.ref)} />);
    for (const s of ["Ouvert", "En cours", "Traité", "Rejeté"]) expect(h).toContain(s);
    expect(h).toContain("Note admin");
  });
  it("vide : message explicite", () => { expect(rendre(<ListeRetours data={{ total: 0, page: 1, items: [] }} ouvertId={null} notes={{}} onBascule={() => {}} onEnregistrer={async () => { throw new Error("x"); }} />)).toContain("Aucun retour"); });
});

describe("admin : utilisateurs", () => {
  it("trie par dernière activité décroissante, sans activité en dernier", () => {
    const t = trierParActivite(utilisateursDemo);
    expect(t[0].id).toBe("u-a");
    expect(t[t.length - 1].derniere_activite).toBeNull();
  });
  it("affiche compteurs par origine et la bascule de valideur", () => {
    const h = rendre(<TableUtilisateurs utilisateurs={utilisateursDemo} onHabilitation={() => {}} />);
    expect(h).toContain("Ancienne version");
    expect(h.match(/role="switch"/g)).toHaveLength(utilisateursDemo.length);
    expect(h).toContain('aria-checked="true"');
    expect(h).toContain("Habilité");
  });
});

describe("admin : étude et santé", () => {
  it("étude : corpus et critères du protocole", () => {
    const h = rendre(<EtudeVue data={etudeDemo} />);
    expect(h).toContain("Critères du protocole");
    expect(h).toContain("Propositions non soutenues par la dictée");
    expect(h).toContain("Données insuffisantes");
    expect(h).toContain("4 / 5");
  });
  it("santé : tables, contrôles « À regarder » avant « OK » avec leur détail", () => {
    const h = rendre(<SanteVue data={santeDemo} />);
    expect(h).toContain("users");
    expect(h).toContain("Comptes de test");
    expect(h.indexOf("À regarder")).toBeLessThan(h.indexOf(">OK<"));
    expect(h).toContain("3 compte(s) de test");
  });
});

describe("admin : démonstration conforme au contrat", () => {
  it("les fixtures ont les clés du contrat", async () => {
    const v = await apiDemo.vueEnsemble("30j");
    expect(Object.keys(v.kpi)).toEqual(expect.arrayContaining(["utilisateurs_actifs", "utilisateurs_total", "projets_v3", "comptes_rendus_anciens", "dossiers_etude", "notes_utile", "notes_a_ameliorer", "signalements_ouverts", "duree_mediane_generation_ms", "modifications_moyennes_par_projet"]));
    expect(v.serie).toHaveLength(30);
    expect(Object.keys(v.origines).sort()).toEqual(["ancienne_version", "etude", "v3"]);
    for (const r of retoursDemo) expect(Object.keys(r).sort()).toEqual(["categorie", "cree_le", "id", "message", "nature", "note_sur_5", "origine", "ref", "sens", "statut", "utilisateur"]);
    expect(Object.keys(utilisateursDemo[0]).sort()).toEqual(["comptes_rendus_anciens", "cree_le", "derniere_activite", "dossiers_etude", "email", "habilite_valideur", "id", "nom", "projets_v3", "role"]);
    expect(santeDemo.controles.map((c) => c.nom)).toEqual(["orphelins", "doublons_comptes", "comptes_de_test", "chaine_audit", "signalements_en_double", "recopie_non_conformites", "tables_jamais_ecrites"]);
  });
  it("filtre les retours par origine, statut et page", async () => {
    const r = await apiDemo.retours({ origine: "v3", categorie: "", statut: "ouvert", page: 1 });
    expect(r.items.every((x) => x.origine === "v3" && x.statut === "ouvert")).toBe(true);
    expect(r.total).toBe(r.items.length);
  });
  it("choisirApi : démonstration ou réelle", () => { expect(choisirApi(true)).toBe(apiDemo); expect(choisirApi(false)).not.toBe(apiDemo); });
});
