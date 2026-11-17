import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FeuilleSignalementVue } from "../components/FeuilleSignalement";
import { CATEGORIES_SIGNALEMENT, envoyerSignalement, MESSAGE_DOUBLON, MESSAGE_ENVOYE, VERSION_APP } from "./signalement";

const vue = (p: Partial<Parameters<typeof FeuilleSignalementVue>[0]> = {}) =>
  renderToStaticMarkup(<FeuilleSignalementVue categorie="dysfonctionnement" message="" erreur="" enCours={false} resultat={null} onCategorie={() => {}} onMessage={() => {}} onEnvoyer={() => {}} onFermer={() => {}} {...p} />);

const reponse = (corps: unknown, status = 200) => new Response(JSON.stringify(corps), { status, headers: { "Content-Type": "application/json" } });

describe("feuille Signaler", () => {
  it("propose les quatre catégories en contrôle segmenté, la choisie cochée", () => {
    const h = vue({ categorie: "amelioration" });
    for (const [, l] of CATEGORIES_SIGNALEMENT) expect(h).toContain(l);
    expect(CATEGORIES_SIGNALEMENT.map(([k]) => k)).toEqual(["dysfonctionnement", "erreur_projet", "amelioration", "non_conformite"]);
    expect(h).toMatch(/aria-checked="true"[^>]*>Amélioration/);
    expect(h.match(/role="radio"/g)).toHaveLength(4);
  });
  it("affiche l'avertissement donnée patient et désactive l'envoi d'un message vide", () => {
    const h = vue();
    expect(h).toContain("N&#x27;indiquez aucune donnée patient");
    expect(h).toMatch(/disabled=""[^>]*>Envoyer/);
    expect(vue({ message: "bug" })).not.toMatch(/disabled=""[^>]*>Envoyer/);
  });
  it("affiche le message du serveur (422 donnée patient)", () => {
    expect(vue({ message: "x", erreur: "Votre message semble contenir une date de naissance." })).toContain("Votre message semble contenir une date de naissance.");
  });
  it("confirme l'envoi, et « Déjà signalé, merci » pour un doublon", () => {
    expect(vue({ resultat: { id: "a", doublon_de: null } })).toContain(MESSAGE_ENVOYE);
    const d = vue({ resultat: { id: "a", doublon_de: "a" } });
    expect(d).toContain(MESSAGE_DOUBLON);
    expect(MESSAGE_DOUBLON).toBe("Déjà signalé, merci");
  });
});

describe("envoyerSignalement", () => {
  beforeEach(() => { vi.stubGlobal("localStorage", { getItem: () => "jeton" }); });
  afterEach(() => vi.unstubAllGlobals());

  it("poste projet_id, ecran et version_app avec la catégorie et le message", async () => {
    const f = vi.fn().mockResolvedValue(reponse({ id: "s1", doublon_de: null }));
    vi.stubGlobal("fetch", f);
    const r = await envoyerSignalement({ categorie: "erreur_projet", message: "  Code faux ", projet_id: "p-1", ecran: "projet" });
    expect(r).toEqual({ id: "s1", doublon_de: null });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("/v3/signalements");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer jeton");
    expect(JSON.parse(init.body)).toEqual({ categorie: "erreur_projet", message: "Code faux", projet_id: "p-1", ecran: "projet", version_app: VERSION_APP });
  });
  it("renvoie doublon_de tel quel", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reponse({ id: "s1", doublon_de: "s1" })));
    expect((await envoyerSignalement({ categorie: "amelioration", message: "idée" })).doublon_de).toBe("s1");
  });
  it("lève le message du serveur sur un 422 de donnée patient", async () => {
    const detail = "Votre message semble contenir une date de naissance. Pour protéger les patients, n'écrivez aucune donnée identifiante.";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reponse({ detail }, 422)));
    await expect(envoyerSignalement({ categorie: "dysfonctionnement", message: "né le 01/02/1960" })).rejects.toThrow(detail);
  });
});
