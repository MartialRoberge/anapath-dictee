/**
 * Confirmation de la validation : la derniere marche avant l'etat terminal.
 *
 * ------------------------------------------------------------------
 *  CE QU'IL FAIT, ET RIEN DE PLUS
 * ------------------------------------------------------------------
 *
 *  1. il rappelle ce qui reste a juger, et ramene aux propositions concernees ;
 *  2. il dit, en une phrase, ce qui part en base — le texte valide, les
 *     decisions, le temps. Ni identite du patient, ni audio ;
 *  3. il demande confirmation.
 *
 *  POURQUOI IL NE S'OUVRE PAS TOUJOURS
 *  Quand il ne reste rien a juger, ce dialogue n'apprendrait rien au praticien
 *  et lui couterait un clic sur chaque compte rendu de la journee. Le parent ne
 *  l'ouvre donc que si `restantes > 0` ; sinon il valide directement, et la
 *  phrase sur ce qui est enregistre reste visible sous le bouton (cf.
 *  BoutonValider). Une etape de confirmation qui ne protege de rien n'est pas
 *  une securite, c'est un peage.
 *
 *  L'enregistrement part au clic : aucune animation ne s'interpose. On anime
 *  l'affichage, jamais la mesure.
 */

import { useEffect, useRef } from "react";
import { AlertCircle, AlertTriangle, ArrowRight, CheckCircle2, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface DialogueValidationProps {
  ouvert: boolean;
  restantes: number;
  total: number;
  /** L'enregistrement est parti : on verrouille les sorties le temps du trajet. */
  occupe: boolean;
  erreur: string | null;
  /** Referme et amene le praticien aux propositions non jugees. */
  onAllerAuxRestantes: () => void;
  onConfirmer: () => void;
  onFermer: () => void;
}

const TITRE_ID = "dialogue-validation-titre";

export default function DialogueValidation({
  ouvert,
  restantes,
  total,
  occupe,
  erreur,
  onAllerAuxRestantes,
  onConfirmer,
  onFermer,
}: DialogueValidationProps) {
  const panneauRef = useRef<HTMLDivElement>(null);
  const declencheurRef = useRef<HTMLElement | null>(null);

  // Le focus entre dans le panneau a l'ouverture et revient a son point de
  // depart a la fermeture : sans cela, le clavier repart du haut de la page.
  useEffect(() => {
    if (!ouvert) return;
    const precedent = document.activeElement;
    declencheurRef.current =
      precedent instanceof HTMLElement ? precedent : null;
    panneauRef.current?.focus();
    return () => declencheurRef.current?.focus();
  }, [ouvert]);

  // Echap referme, sauf pendant l'enregistrement : fermer a cet instant
  // laisserait croire que l'envoi a ete annule alors qu'il est deja parti.
  useEffect(() => {
    if (!ouvert || occupe) return;
    const surTouche = (e: KeyboardEvent) => {
      if (e.key === "Escape") onFermer();
    };
    window.addEventListener("keydown", surTouche);
    return () => window.removeEventListener("keydown", surTouche);
  }, [ouvert, occupe, onFermer]);

  if (!ouvert) return null;

  const restantesSures = Math.max(0, restantes);

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-foreground/30"
        onClick={() => {
          if (!occupe) onFermer();
        }}
      />
      <div
        ref={panneauRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={TITRE_ID}
        tabIndex={-1}
        className="fixed inset-x-4 top-1/2 z-50 max-h-[90vh] -translate-y-1/2 overflow-y-auto rounded-xl border bg-card p-4 shadow-lg outline-none scrollbar-thin sm:inset-x-auto sm:left-1/2 sm:w-[27rem] sm:-translate-x-1/2"
      >
        <h2
          id={TITRE_ID}
          className="font-heading text-base font-bold tracking-tight text-foreground"
        >
          Valider le compte rendu ?
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          C'est l'acte qui declare votre compte rendu termine et l'enregistre.
        </p>

        {restantesSures > 0 && (
          <div className="mt-3 rounded-lg border border-warning/30 bg-warning/5 p-3">
            <p className="flex items-start gap-2 text-sm font-semibold text-foreground">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
              <span>
                {restantesSures} proposition{restantesSures > 1 ? "s" : ""} sur{" "}
                {total} {restantesSures > 1 ? "ne sont" : "n'est"} pas encore
                jugee{restantesSures > 1 ? "s" : ""}.
              </span>
            </p>
            <p className="mt-1 pl-6 text-xs leading-relaxed text-muted-foreground">
              Valider maintenant les laissera sans reponse. Le compte rendu vous
              attend si vous preferez y retourner.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="ml-6 mt-2 h-8"
              disabled={occupe}
              onClick={() => {
                onAllerAuxRestantes();
                onFermer();
              }}
            >
              <ArrowRight className="h-3.5 w-3.5" />
              Voir les propositions restantes
            </Button>
          </div>
        )}

        {/* Dire ce qui part, et surtout ce qui ne part pas : la confiance dans
            l'enregistrement se gagne ici, pas dans une page de mentions. */}
        <p className="mt-3 flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            <span className="font-semibold text-foreground">
              Ce qui sera enregistre :
            </span>{" "}
            le texte que vous validez, vos decisions sur les propositions et le
            temps passe. Ni identite du patient, ni audio.
          </span>
        </p>

        {erreur && (
          <p
            role="alert"
            className="mt-3 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs font-medium leading-relaxed text-destructive"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{erreur}</span>
          </p>
        )}

        <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-9"
            disabled={occupe}
            onClick={onFermer}
          >
            Continuer a relire
          </Button>
          <Button
            type="button"
            size="sm"
            className="h-9"
            disabled={occupe}
            aria-busy={occupe}
            onClick={onConfirmer}
          >
            {occupe ? (
              <span className="h-3.5 w-3.5 shrink-0 animate-spin-slow rounded-full border-2 border-primary-foreground/40 border-t-primary-foreground" />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
            )}
            {occupe ? "Enregistrement..." : "Valider le compte rendu"}
          </Button>
        </div>
      </div>
    </>
  );
}
