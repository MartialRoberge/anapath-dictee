/**
 * Le dossier instrumente, du cote du praticien.
 *
 * Un seul hook porte le cycle de vie complet d'un cas : ouverture de la session
 * puis du dossier, propositions a valider, decisions prises, cloture, export,
 * abandon. Regrouper le tout evite qu'un ecran clot un dossier dont un autre
 * detient encore les propositions.
 *
 * Aucune de ces fonctions ne leve : une panne reseau au milieu d'une etude ne
 * doit pas faire disparaitre le compte-rendu sous les yeux du praticien. Elles
 * renvoient null et renseignent `erreur`, que l'ecran montre comme il l'entend.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import {
  type ResultatCloture,
  abandonnerDossier,
  cloreDossier,
  cloreSession,
  deciderProposition,
  grilleDe,
  marquerExport,
  ouvrirDossier,
  ouvrirSession,
  type CauseErreur,
  type ClotureDossier,
  type Decision,
  type DossierOuvert,
  type MotifAbandon,
  type OuvertureDossier,
  type PropositionAffichee,
  type ResultatDecision,
} from "@/services/etude";

/** L'ouverture d'un dossier : la session est l'affaire du hook, pas de l'ecran. */
export type EntreeDossier = Omit<OuvertureDossier, "session_id">;

/** Ce qu'on retient d'une decision, une fois le serveur d'accord. */
export interface DecisionPrise {
  decision: Decision;
  valeur_retenue: string | null;
  latence_ms: number | null;
  /** Decision trop rapide pour avoir ete lue : signalee, jamais rejetee. */
  hative: boolean;
}

export interface OptionsDecision {
  valeur_retenue?: string | null;
  /** style | precision | erreur_fond — seule `erreur_fond` impute une erreur. */
  nature_correction?: string | null;
  cause_erreur?: CauseErreur | null;
  justif_ouverte?: boolean;
  justif_duree_ms?: number | null;
}

export interface EtudeDossier {
  sessionId: string | null;
  dossierId: string | null;
  propositions: PropositionAffichee[];
  /** Indexe par identifiant de proposition : l'ecran sait ce qui est fait. */
  decisions: Readonly<Record<string, DecisionPrise>>;
  restantes: number;
  toutesDecidees: boolean;
  /** Premiere proposition encore a decider, pour un bouton « suivante ». */
  prochaine: PropositionAffichee | null;
  /** Le dossier produit trop peu a valider pour etre exploitable. */
  sousExtraction: boolean;
  clos: boolean;
  abandonne: boolean;
  /** Un appel reseau est en cours : de quoi desactiver les commandes. */
  occupe: boolean;
  erreur: string | null;
  ouvrir: (entree: EntreeDossier) => Promise<DossierOuvert | null>;
  decider: (
    proposition: PropositionAffichee,
    decision: Decision,
    options?: OptionsDecision,
  ) => Promise<ResultatDecision | null>;
  clore: (corps: ClotureDossier) => Promise<ResultatCloture | null>;
  exporter: () => Promise<boolean>;
  abandonner: (motif: MotifAbandon) => Promise<boolean>;
  terminerSession: () => Promise<boolean>;
}

function messageErreur(erreur: unknown): string {
  return erreur instanceof Error ? erreur.message : "Erreur inconnue";
}

export function useEtudeDossier(): EtudeDossier {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [dossierId, setDossierId] = useState<string | null>(null);
  const [propositions, setPropositions] = useState<PropositionAffichee[]>([]);
  const [decisions, setDecisions] = useState<Record<string, DecisionPrise>>({});
  const [sousExtraction, setSousExtraction] = useState(false);
  const [clos, setClos] = useState(false);
  const [abandonne, setAbandonne] = useState(false);
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  // La session survit a plusieurs dossiers : la lire dans une ref evite qu'une
  // ouverture rapide en cree une seconde avant que l'etat ne soit rendu.
  const sessionRef = useRef<string | null>(null);

  const assurerSession = useCallback(async (): Promise<string> => {
    if (sessionRef.current !== null) return sessionRef.current;
    const id = await ouvrirSession();
    sessionRef.current = id;
    setSessionId(id);
    return id;
  }, []);

  const ouvrir = useCallback(
    async (entree: EntreeDossier): Promise<DossierOuvert | null> => {
      setOccupe(true);
      setErreur(null);
      try {
        const session = await assurerSession();
        const ouvert = await ouvrirDossier({ ...entree, session_id: session });
        setDossierId(ouvert.dossier_id);
        setPropositions(ouvert.propositions);
        setSousExtraction(ouvert.sous_extraction);
        setDecisions({});
        setClos(false);
        setAbandonne(false);
        return ouvert;
      } catch (e) {
        setErreur(messageErreur(e));
        return null;
      } finally {
        setOccupe(false);
      }
    },
    [assurerSession],
  );

  const decider = useCallback(
    async (
      proposition: PropositionAffichee,
      decision: Decision,
      options: OptionsDecision = {},
    ): Promise<ResultatDecision | null> => {
      // Garde-fou local avant le reseau : les trois grilles sont distinctes et
      // le serveur refuse en 400 une decision hors grille. Autant le dire tout
      // de suite et sans faire attendre le praticien.
      if (!grilleDe(proposition.type).includes(decision)) {
        setErreur(
          `Décision « ${decision} » hors de la grille « ${proposition.type} ».`,
        );
        return null;
      }

      setErreur(null);
      try {
        const resultat = await deciderProposition(proposition.id, {
          decision,
          ...options,
        });
        setDecisions((precedentes) => ({
          ...precedentes,
          [proposition.id]: {
            decision,
            valeur_retenue: options.valeur_retenue ?? null,
            latence_ms: resultat.latence_ms,
            hative: resultat.hative,
          },
        }));
        return resultat;
      } catch (e) {
        setErreur(messageErreur(e));
        return null;
      }
    },
    [],
  );

  const clore = useCallback(
    async (corps: ClotureDossier): Promise<ResultatCloture | null> => {
      if (dossierId === null) return null;
      setOccupe(true);
      setErreur(null);
      try {
        const reponse = await cloreDossier(dossierId, corps);
        setClos(true);
        return reponse;
      } catch (e) {
        setErreur(messageErreur(e));
        return null;
      } finally {
        setOccupe(false);
      }
    },
    [dossierId],
  );

  const exporter = useCallback(async (): Promise<boolean> => {
    if (dossierId === null) return false;
    try {
      await marquerExport(dossierId);
      return true;
    } catch (e) {
      // L'horodatage de sortie est une mesure, pas une condition : il ne doit
      // jamais empecher le compte-rendu de partir.
      setErreur(messageErreur(e));
      return false;
    }
  }, [dossierId]);

  const abandonner = useCallback(
    async (motif: MotifAbandon): Promise<boolean> => {
      if (dossierId === null) return false;
      setOccupe(true);
      setErreur(null);
      try {
        await abandonnerDossier(dossierId, motif);
        setAbandonne(true);
        return true;
      } catch (e) {
        setErreur(messageErreur(e));
        return false;
      } finally {
        setOccupe(false);
      }
    },
    [dossierId],
  );

  const terminerSession = useCallback(async (): Promise<boolean> => {
    const session = sessionRef.current;
    if (session === null) return false;
    try {
      await cloreSession(session);
      sessionRef.current = null;
      setSessionId(null);
      return true;
    } catch (e) {
      setErreur(messageErreur(e));
      return false;
    }
  }, []);

  const prochaine = useMemo(
    () => propositions.find((p) => decisions[p.id] === undefined) ?? null,
    [propositions, decisions],
  );

  const restantes = propositions.length - Object.keys(decisions).length;

  return {
    sessionId,
    dossierId,
    propositions,
    decisions,
    restantes,
    toutesDecidees: propositions.length > 0 && restantes === 0,
    prochaine,
    sousExtraction,
    clos,
    abandonne,
    occupe,
    erreur,
    ouvrir,
    decider,
    clore,
    exporter,
    abandonner,
    terminerSession,
  };
}
