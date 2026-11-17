// Pilote une génération (nouveau projet ou itération) : consomme le flux SSE et expose l'état réel.
import { useCallback, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import type { Element, Projet, ProjetEvent, TraceStep } from "../types";

export type Lanceur = (onEvent: (e: ProjetEvent) => void, signal: AbortSignal) => Promise<void>;

export interface EtatGeneration {
  phase: "inactif" | "en_cours" | "erreur";
  mode: "nouveau" | "iteration";
  /** Première étape reçue ? Avant : on est encore en train d'envoyer / d'attendre le serveur. */
  etapes: TraceStep[];
  partiel: Element[];
  erreur?: { message: string; recuperable: boolean };
  debut: number;
  /** Dictée en cours de traitement (texte) pour l'afficher au centre pendant la génération. */
  dictee?: string;
  audio: boolean;
}

const INACTIF: EtatGeneration = { phase: "inactif", mode: "nouveau", etapes: [], partiel: [], debut: 0, audio: false };

export function mettreAJourEtapes(etapes: TraceStep[], s: TraceStep): TraceStep[] {
  const i = etapes.findIndex((x) => x.id === s.id);
  if (i === -1) return [...etapes, s];
  const copie = [...etapes];
  copie[i] = s;
  return copie;
}

interface Options {
  onProjet: (p: Projet, dureeMs: number, mode: "nouveau" | "iteration") => void;
  onNonAutorise: () => void;
}

export function useGeneration({ onProjet, onNonAutorise }: Options) {
  const [etat, setEtat] = useState<EtatGeneration>(INACTIF);
  const ctrl = useRef<AbortController | null>(null);
  const derniere = useRef<{ fn: Lanceur; meta: Pick<EtatGeneration, "mode" | "dictee" | "audio"> } | null>(null);

  const executer = useCallback(async (fn: Lanceur, meta: Pick<EtatGeneration, "mode" | "dictee" | "audio">) => {
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    derniere.current = { fn, meta };
    const debut = performance.now();
    setEtat({ ...INACTIF, ...meta, phase: "en_cours", debut: Date.now() });
    let recu = false;
    try {
      await fn((e) => {
        if (c.signal.aborted) return;
        if (e.event === "step") setEtat((s) => ({ ...s, etapes: mettreAJourEtapes(s.etapes, e.data) }));
        else if (e.event === "partial") setEtat((s) => ({ ...s, partiel: e.data.elements }));
        else if (e.event === "projet") {
          recu = true;
          setEtat(INACTIF);
          onProjet(e.data, Math.round(performance.now() - debut), meta.mode);
        } else if (e.event === "error") {
          recu = true;
          setEtat((s) => ({ ...s, phase: "erreur", erreur: e.data }));
        }
      }, c.signal);
      if (!recu && !c.signal.aborted) {
        setEtat((s) => ({ ...s, phase: "erreur", erreur: { message: "Le flux s'est interrompu avant la fin. Réessayez.", recuperable: true } }));
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      if (err instanceof ApiError && err.status === 401) {
        onNonAutorise();
        return;
      }
      const message = err instanceof Error ? err.message : "Erreur inattendue.";
      setEtat((s) => ({ ...s, phase: "erreur", erreur: { message, recuperable: !(err instanceof ApiError) || err.recuperable } }));
    }
  }, [onProjet, onNonAutorise]);

  const annuler = useCallback(() => {
    ctrl.current?.abort();
    setEtat(INACTIF);
  }, []);

  const reessayer = useCallback(() => {
    const d = derniere.current;
    if (d) void executer(d.fn, d.meta);
  }, [executer]);

  return { etat, executer, annuler, reessayer };
}
