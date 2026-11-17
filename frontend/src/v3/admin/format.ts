// Mise en forme des dates et durées de l'administration (fuseau d'affichage : celui du navigateur ; l'API est en UTC).
export const dateHeure = (iso: string | null): string =>
  iso ? new Date(iso).toLocaleString("fr-FR", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
export const dateCourte = (iso: string | null): string => (iso ? new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }) : "—");
export const jourCourt = (jour: string): string => new Date(`${jour}T00:00:00Z`).toLocaleDateString("fr-FR", { day: "numeric", month: "short", timeZone: "UTC" });

/** « il y a 3 j » : repère rapide pour la dernière activité ; la date exacte reste en infobulle. */
export function ilYa(iso: string | null, maintenant = Date.now()): string {
  if (!iso) return "Jamais";
  const s = Math.max(0, (maintenant - new Date(iso).getTime()) / 1000);
  if (s < 3600) return `il y a ${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  if (s < 86400 * 60) return `il y a ${Math.round(s / 86400)} j`;
  return dateCourte(iso);
}

export const duree = (ms: number | null): string =>
  ms == null ? "n/d" : ms >= 60_000 ? `${Math.floor(ms / 60_000)} min ${String(Math.round((ms % 60_000) / 1000)).padStart(2, "0")} s` : `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
export const pct = (v: number | null): string => (v == null ? "n/d" : `${Math.round(v * 1000) / 10} %`.replace(".", ","));
export const nombre = (v: number | null | undefined, d = 0): string => (v == null ? "n/d" : v.toLocaleString("fr-FR", { maximumFractionDigits: d }));

export const ORIGINES = { v3: "v3", ancienne_version: "Ancienne version", etude: "Étude" } as const;
export const STATUTS = { ouvert: "Ouvert", en_cours: "En cours", traite: "Traité", rejete: "Rejeté" } as const;
export const CATEGORIES: Record<string, string> = {
  dysfonctionnement: "Dysfonctionnement", erreur_projet: "Erreur dans le projet", amelioration: "Amélioration", non_conformite: "Non-conformité qualité",
  commentaire_validation: "Commentaire de validation", questionnaire_par_cas: "Questionnaire par cas", questionnaire_fin_etude: "Questionnaire de fin d'étude",
};
export const NATURES = { signalement: "Signalement", note: "Note rapide", avis: "Avis" } as const;
