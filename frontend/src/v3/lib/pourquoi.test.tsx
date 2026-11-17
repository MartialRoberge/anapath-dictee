import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import OngletPourquoi from "../components/OngletPourquoi";
import PanneauRaisonnement, { ORDRE_ONGLETS } from "../components/PanneauRaisonnement";
import OngletAlertes from "../components/OngletAlertes";
import OngletProgression from "../components/OngletProgression";
import { projetPoumon } from "../fixtures/projetPoumon";
import { creerLocal } from "./session";
import { alerteTextes, aRelire, formuleConfiance, passageDictee, preuvesDe, resumeProjet, termesConfiance } from "./pourquoi";
import type { Element } from "../types";
import { projetDemo } from "../fixtures/projetPoumon";
import ConsultationSource, { FicheSource, SourceLien } from "../components/Source";
import { formeExtrait, motFiabilite, normaliserDetail } from "./sources";
import { preuvesTrou } from "./pourquoi";
import { creerLocal as creer, remplirTrou } from "./session";

const local = () => creerLocal(structuredClone(projetPoumon), "texte");
const elt = (id: string) => projetPoumon.elements.find((e) => e.id === id)!;
const rendre = (id: string) => renderToStaticMarkup(<OngletPourquoi local={local()} element={elt(id)} onConsulte={() => {}} />);

describe("vue Pourquoi", () => {
  it("fragments : raison à vérifier, règle en attention avec son calcul, sections dans l'ordre fixe", () => {
    const h = rendre("e2");
    expect(h).toContain("Quatre fragments mesurant de 2 à 4 cm.");
    expect(h).toContain("À vérifier");
    expect(h).toContain("millimètres dictés par erreur");
    expect(h).toContain("20–40 mm &gt; 5 mm (max biopsie bronchique)");
    expect(h).toContain("Conforme");
    const ordre = ["aria-label=\"Dictée\"", "aria-label=\"Règles\"", "aria-label=\"Référentiel\"", "aria-label=\"Modèle\""].map((k) => h.indexOf(k));
    expect(ordre.every((i) => i >= 0)).toBe(true);
    expect([...ordre].sort((a, b) => a - b)).toEqual(ordre);
  });
  it("le passage de la dictée est surligné ; la source du référentiel ouvre la consultation (le lien externe y figure)", () => {
    expect(rendre("e2")).toContain("<mark");
    const h = rendre("e9");
    expect(h).toContain('aria-haspopup="dialog"');
    expect(h).toContain("INCa · Cancer bronchopulmonaire : données minimales");
  });
  it("confiance : somme lisible, repliée par défaut", () => {
    const h = rendre("e2");
    expect(h).toContain("<details");
    expect(h).not.toContain("<details open");
    expect(formuleConfiance(elt("e2"))).toBe("Confiance 0,48 = ancrage dans la dictée 0,75 − taille plausible pour une biopsie bronchique 0,15 − relecteur de fidélité 0,12");
    for (const e of projetPoumon.elements) {
      const t = termesConfiance(e);
      if (t.length) expect(t.reduce((s, x) => s + x.valeur, 0)).toBeCloseTo(e.confiance, 2);
    }
  });
  it("IHC en trois éléments distincts", () => {
    const l = projetPoumon.elements.filter((e) => e.section_id === "s4" && e.type === "liste").map((e) => e.texte);
    expect(l).toHaveLength(3);
    expect(l.join(" ")).toMatch(/TTF1.*CK7.*P40/);
  });
  it("sans sélection : invite et sources du projet", () => {
    const h = renderToStaticMarkup(<OngletPourquoi local={local()} element={null} onConsulte={() => {}} />);
    expect(h).toContain("Cliquez sur une phrase");
    expect(h).toContain("INCa");
  });
});

describe("repli sans preuves (ancien projet)", () => {
  const ancien: Element = { ...elt("e3"), preuves: undefined, a_verifier: undefined };
  it("reconstruit dictée, référentiel et explication depuis sources et explication", () => {
    const p = preuvesDe(ancien);
    expect(p.map((x) => x.categorie)).toEqual(["dictee", "referentiel", "modele"]);
    const h = renderToStaticMarkup(<OngletPourquoi local={local()} element={ancien} onConsulte={() => {}} />);
    expect(h).toContain("Reformulation de ponctuation uniquement");
    expect(h).toContain("OMS 2021");
    expect(h).not.toContain("<details");
    expect(h).toContain("Confiance 0,90");
  });
  it("élément sans aucune information : message neutre", () => {
    const h = renderToStaticMarkup(<OngletPourquoi local={local()} element={{ ...ancien, sources: [], explication: "" }} onConsulte={() => {}} />);
    expect(h).toContain("Aucune justification enregistrée");
  });
  it("alerte ancienne : message et suggestion, sans jargon", () => {
    const t = alerteTextes({ ...projetPoumon.alertes[1], pourquoi: undefined, calcul: undefined, action: undefined });
    expect(t.pourquoi).toBeNull();
    expect(t.action).toBe("Suggestion : 2 à 4 mm");
  });
});

describe("panneau et onglets", () => {
  const props = (element: Element | null) => ({
    onglet: "pourquoi" as const, onOnglet: () => {}, local: local(), generation: { phase: "inactif", etapes: [] } as never, etapes: [], element,
    alerteActive: null, correctionActive: null, onAlerte: () => {}, onDecider: () => {}, onCorrectionActive: () => {}, onDecision: () => {},
    onCopieCode: () => {}, onModifierCode: () => {}, onConsulte: () => {}, onNotifier: () => {}, onDocument: () => {},
  });
  it("rôle tabpanel relié à l'onglet actif, ordre des onglets stable", () => {
    const h = renderToStaticMarkup(<PanneauRaisonnement {...props(elt("e2"))} />);
    expect(h).toContain('role="tabpanel"');
    expect(h).toContain('aria-labelledby="tab-pourquoi"');
    expect(h).toContain('tabindex="0"');
    expect(ORDRE_ONGLETS).toEqual(["pourquoi", "alertes", "codes", "dictee", "progression"]);
    expect(h.indexOf("Pourquoi")).toBeLessThan(h.indexOf("Progression"));
    expect(h).toContain('aria-keyshortcuts="Alt+1"');
  });
  it("alertes : pourquoi, calcul et action, sans nom d'agent ni type brut", () => {
    const h = renderToStaticMarkup(<OngletAlertes alertes={projetPoumon.alertes} decisions={{}} active={null} onActiver={() => {}} onDecider={() => {}} />);
    expect(h).toContain("20–40 mm &gt; 5 mm");
    expect(h).toContain("À faire");
    expect(h).not.toContain("Vérificateur d&#x27;unités");
    expect(h).not.toContain("Vérificateur de complétude");
    expect(h).not.toMatch(/Incohérence|phonetique|Phonétique/);
  });
  it("un seul signe de marge : soulignement ambre sur les phrases à relire", () => {
    expect(aRelire(elt("e2"))).toBe(true);
    expect(aRelire(elt("e1"))).toBe(false);
    expect(aRelire(elt("e9"))).toBe(false);
  });
});

describe("progression en langage clair", () => {
  it("résumé", () => {
    const t = resumeProjet(projetPoumon).map((l) => l.texte);
    expect(t).toContain("Organe identifié : poumon, biopsie");
    expect(t).toContain("4 termes corrigés à l'écoute");
    expect(t.some((x) => /^8 règles vérifiées, 2 à revoir$/.test(x))).toBe(true);
    expect(t).toContain("2 champs obligatoires manquants");
    expect(t).toContain("Codes SNOMED CT, CIM-O3, ADICAP proposés");
  });
  it("détails techniques repliés, résumé visible", () => {
    const h = renderToStaticMarkup(<OngletProgression etapes={projetPoumon.trace} projet={projetPoumon} generation={{ phase: "inactif", etapes: [] } as never} alertesOuvertes={4} onOnglet={() => {}} onDocument={() => {}} />);
    expect(h).toContain("Ce qui a été fait");
    expect(h).toContain("Détails techniques");
    expect(h.indexOf("Ce qui a été fait")).toBeLessThan(h.indexOf("Détails techniques"));
  });
  it("passage de dictée : bornes invalides refusées", () => {
    expect(passageDictee("abc", { debut: 2, fin: 9 })).toBeNull();
    expect(passageDictee("un deux trois", { debut: 3, fin: 7 })?.cite).toBe("deux");
  });
});

describe("vue d'un trou", () => {
  const ki67 = projetDemo.elements.find((e) => e.id === "e12")!;
  const rendreTrou = (el: Element, onRemplir?: (e: Element, v: string) => void, l = creer(structuredClone(projetDemo), "texte")) =>
    renderToStaticMarkup(<OngletPourquoi local={l} element={el} onConsulte={() => {}} onRemplir={onRemplir} />);
  it("champ, statut, raison, puis Dictée, Pourquoi c'est demandé, Référentiel ; jamais de Modèle ni de Confiance basse", () => {
    const h = rendreTrou(ki67, () => {});
    expect(h).toContain("Ki67 (% de cellules tumorales)");
    expect(h).toContain("À compléter");
    expect(h).toContain("Ki67 n&#x27;est pas dicté");
    expect(h).toContain("Ki67 n&#x27;est pas mentionné dans la dictée");
    expect(h).toContain("Termes cherchés : ki67, ki-67, mib1");
    expect(h).toContain("Exigé pour : poumon · biopsie · carcinome infiltrant");
    expect(h).toContain("Bible de la pathologiste · Biopsies thoraciques");
    const ordre = ["aria-label=\"Dictée\"", "aria-label=\"Pourquoi c&#x27;est demandé\"", "aria-label=\"Référentiel\""].map((k) => h.indexOf(k));
    expect(ordre.every((i) => i >= 0)).toBe(true);
    expect([...ordre].sort((a, b) => a - b)).toEqual(ordre);
    expect(h).not.toContain("Modèle");
    expect(h).not.toMatch(/Confiance basse|confiance basse/);
    expect(h).not.toContain("<details");
  });
  it("même un modèle fourni par erreur n'apparaît pas pour un trou", () => {
    const h = rendreTrou({ ...ki67, preuves: [...ki67.preuves!, { categorie: "modele", verdict: "info", titre: "Confiance basse : exigence issue de", detail: "" }] });
    expect(h).not.toContain("Modèle");
    expect(h).not.toContain("Confiance basse");
  });
  it("options cliquables seulement si on peut remplir ; la valeur retenue est marquée ; statut rempli", () => {
    expect(rendreTrou(ki67)).not.toContain("Valeurs proposées");
    const h = rendreTrou(ki67, () => {});
    expect(h).toContain("Valeurs proposées");
    expect(h).toContain("10 à 30 %");
    const l = remplirTrou(creer(structuredClone(projetDemo), "texte"), "e12", "10 à 30 %");
    const r = rendreTrou(ki67, () => {}, l);
    expect(r).toContain("Rempli : 10 à 30 %");
    expect(r).toMatch(/aria-pressed="true"[^>]*>10 à 30 %/);
  });
  it("repli sans preuves : Non dicté et Exigé par la source, sans « Confiance basse »", () => {
    const sans: Element = { ...ki67, preuves: undefined };
    expect(preuvesTrou(sans).map((p) => p.categorie)).toEqual(["dictee", "regle"]);
    const h = rendreTrou(sans);
    expect(h).toContain("Non dicté");
    expect(h).toContain("Exigé par");
    expect(h).toContain("Bible de la pathologiste · Biopsies thoraciques");
    expect(h).not.toMatch(/Modèle|onfiance basse/);
    const sansSource = rendreTrou({ ...sans, sources: [] });
    expect(sansSource).toContain("Non dicté");
    expect(sansSource).not.toContain("Exigé par");
  });
});

describe("sources lisibles et cliquables", () => {
  const longue = { kind: "kb" as const, ref: "x", libelle: "Société française de pathologie · Recommandations sur les biopsies thoraciques et médiastinales", fiabilite: "B" as const, extrait: "Fiche 12, page 4" };
  it("titre entier, sans troncature ni points de suspension ; extrait en petit ; fiabilité en mots, pas de lettre seule", () => {
    const h = renderToStaticMarkup(<SourceLien source={longue} onConsulte={() => {}} />);
    expect(h).toContain(longue.libelle);
    expect(h).not.toContain("line-clamp");
    expect(h).not.toContain("truncate");
    expect(h).not.toContain("…");
    expect(h).toContain("Fiche 12, page 4");
    expect(h).toContain("Pathologiste référente");
    expect(h).not.toMatch(/>B</);
    expect(h).toContain("<button");
  });
  it("fiabilité A à D en mots", () => {
    expect(["A", "B", "C", "D"].map(motFiabilite)).toEqual(["Référentiel officiel", "Pathologiste référente", "Synthèse MARC à valider", "Non validé"]);
    expect(motFiabilite(null)).toBeNull();
  });
  it("extrait : citation entre guillemets ou localisation", () => {
    expect(formeExtrait({ kind: "kb", extrait: "Les fragments biopsiques se décrivent en millimètres." })).toEqual({ type: "citation", texte: "Les fragments biopsiques se décrivent en millimètres." });
    expect(formeExtrait({ kind: "kb", extrait: "Chapitre Adénocarcinome" })?.type).toBe("localisation");
    expect(formeExtrait({ kind: "kb", extrait: "« déjà cité »" })).toEqual({ type: "citation", texte: "déjà cité" });
    const h = renderToStaticMarkup(<SourceLien source={{ ...longue, extrait: "Les fragments se décrivent en millimètres." }} onConsulte={() => {}} />);
    expect(h).toContain("« Les fragments se décrivent en millimètres. »");
  });
  it("sources dans À vérifier : titre entier et fiabilité en mots, sans la lettre", () => {
    const h = renderToStaticMarkup(<OngletAlertes alertes={projetPoumon.alertes} decisions={{}} active={null} onActiver={() => {}} onDecider={() => {}} onConsulte={() => {}} />);
    expect(h).toContain("INCa · Cancer bronchopulmonaire : données minimales");
    expect(h).toContain("Référentiel officiel");
  });
  it("lecture défensive de la fiche : clés alternatives, valeurs inattendues ignorées", () => {
    const f = normaliserDetail({ libelle: "T", resume: "D", organisme: "E", date_publication: 2021, fiabilite: "Z", url: "javascript:alert(1)", regles: ["R1", { id: "R2" }], champs: [{ libelle: "Ki67" }, 3] });
    expect(f).toMatchObject({ titre: "T", description: "D", editeur: "E", date: "2021", fiabilite: undefined, url: undefined });
    expect(f.cite_par.map((c) => c.libelle)).toEqual(["Ki67", "R1", "R2"]);
    expect(f.cite_par).toHaveLength(3);
    expect(normaliserDetail(null).cite_par).toEqual([]);
    expect(normaliserDetail("n'importe quoi").titre).toBeUndefined();
  });
});

describe("consultation d'une source", () => {
  it("avant réponse : titre, extrait et fiabilité du SourceRef restent affichés", () => {
    const s = projetDemo.elements.find((e) => e.id === "e9")!.sources[0];
    const h = renderToStaticMarkup(<ConsultationSource source={s} onFermer={() => {}} />);
    expect(h).toContain('role="dialog"');
    expect(h).toContain('aria-modal="true"');
    expect(h).toContain(s.libelle);
    expect(h).toContain("Le statut PD-L1");
    expect(h).toContain("Référentiel officiel");
  });
  it("repli si la consultation échoue : le SourceRef reste lisible, message sobre, lien externe conservé", () => {
    const s = projetDemo.elements.find((e) => e.id === "e9")!.sources[0];
    const h = renderToStaticMarkup(<FicheSource source={s} etat={{ phase: "indisponible" }} onFermer={() => {}} />);
    expect(h).toContain(s.libelle);
    expect(h).toContain("fiche détaillée n&#x27;est pas disponible");
    expect(h).toContain("Référentiel officiel");
    expect(h).toContain(`href="${s.url}"`);
    expect(h).not.toContain("Cité par");
  });
  it("fiche reçue : éditeur, version, fiabilité expliquée, liste des champs qui citent la source", () => {
    const s = projetDemo.elements.find((e) => e.id === "e9")!.sources[0];
    const fiche = normaliserDetail({ titre: s.libelle, description: "Données minimales.", editeur: "INCa", version: "2011", fiabilite: "A", cite_par: [{ libelle: "PD-L1", type: "champ" }] });
    const h = renderToStaticMarkup(<FicheSource source={s} etat={{ phase: "ok", fiche }} onFermer={() => {}} />);
    expect(h).toContain("INCa");
    expect(h).toContain("2011");
    expect(h).toContain("Référentiel officiel publié");
    expect(h).toContain("Cité par");
    expect(h).toContain("PD-L1");
  });
  it("consulterSource : une erreur réseau ou HTTP est propagée (l'interface retombe sur le SourceRef)", async () => {
    const { consulterSource } = await import("./api");
    const orig = globalThis.fetch;
    const ls = (globalThis as { localStorage?: unknown }).localStorage;
    (globalThis as { localStorage?: unknown }).localStorage = { getItem: () => null };
    try {
      globalThis.fetch = (async () => new Response("{}", { status: 404 })) as typeof fetch;
      await expect(consulterSource("inconnue")).rejects.toThrow();
      globalThis.fetch = (async () => new Response(JSON.stringify({ libelle: "Titre", editeur: "Org" }), { status: 200 })) as typeof fetch;
      expect(await consulterSource("ok")).toMatchObject({ titre: "Titre", editeur: "Org" });
    } finally {
      globalThis.fetch = orig;
      (globalThis as { localStorage?: unknown }).localStorage = ls;
    }
  });
  it("source sans fiche (dictée, agent) : pas d'appel, informations du SourceRef seulement", () => {
    const h = renderToStaticMarkup(<ConsultationSource source={{ kind: "agent", ref: "correcteur", libelle: "Correcteur phonétique" }} onFermer={() => {}} />);
    expect(h).toContain("Correcteur phonétique");
    expect(h).not.toContain("Chargement");
  });
});
