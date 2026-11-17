// Helpers de télémétrie : jamais de texte libre, seulement enums, nombres et ids de champ kb.
import { track } from "../telemetry";
import type { Alerte, Code, Element, SourceRef } from "../types";
import { tranche } from "./session";

export const trackEdition = (el: Element, avant: string, apres: string, modifies: number, projetId: string) =>
  track("element_edite", { type: el.type, statut: el.statut, niveau: el.niveau, tranche: tranche(modifies), longueur_avant: tranche(avant.length), longueur_apres: tranche(apres.length) }, projetId);

export const trackTrou = (el: Element, rempli: boolean, projetId: string) =>
  track(rempli ? "trou_comble" : "trou_ignore", { champ_id: el.champ_id ?? undefined, obligatoire: el.obligatoire }, projetId);

export const trackAlerte = (a: Alerte, resolue: boolean, projetId: string) =>
  track(resolue ? "alerte_resolue" : "alerte_ignoree", { type: a.type, gravite: a.gravite, agent: a.agent }, projetId);

export const trackCode = (type: "code_copie" | "code_modifie", c: Code, projetId: string) =>
  track(type, { systeme: c.systeme, statut: c.statut }, projetId);

export const trackSource = (s: SourceRef, projetId: string) =>
  track("source_consultee", { kind: s.kind, fiabilite: s.fiabilite ?? undefined }, projetId);
