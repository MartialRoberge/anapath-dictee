/**
 * Le bouton qui termine le compte rendu.
 *
 * ------------------------------------------------------------------
 *  POURQUOI IL NE DIT PAS "SAUVEGARDER"
 * ------------------------------------------------------------------
 *
 *  "Sauvegarder" ne distingue pas un brouillon d'un compte rendu fini. Le
 *  praticien cliquait sans savoir s'il rangeait un brouillon ou s'il declarait
 *  son travail termine, et le texte valide n'arrivait jamais en base. Ce bouton
 *  nomme l'acte : valider. C'est le SEUL bouton primaire de l'ecran ; s'il y en
 *  a deux, le praticien en choisit un au hasard.
 *
 *  POURQUOI IL RESTE CLIQUABLE QUAND IL RESTE DES PROPOSITIONS
 *  Un bouton grise sans explication ressemble a une panne, pas a une
 *  protection. On laisse cliquer : le compte des restantes est annonce ici
 *  AVANT le clic, et le dialogue de validation dit lesquelles et y ramene.
 *  Le seul cas de desactivation est l'enregistrement en cours, et il est
 *  explique par le libelle du bouton lui-meme.
 *
 * ------------------------------------------------------------------
 *  CABLAGE ATTENDU
 * ------------------------------------------------------------------
 *
 *  Ce composant ne connait pas le dialogue : c'est le parent qui arbitre.
 *
 *    onValider={() => (restantes > 0 ? ouvrirDialogue() : validerMaintenant())}
 *
 *  S'il ne reste rien a juger, la confirmation n'apprendrait rien au praticien
 *  et lui volerait un clic : on lui epargne l'etape. C'est pour cela que la
 *  phrase sur ce qui est enregistre est affichee ici en permanence, et pas
 *  seulement dans le dialogue — l'honnetete ne doit pas dependre d'une etape
 *  qu'on peut sauter.
 */

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { EtatParcours } from "./BarreEtat";

export interface BoutonValiderProps {
  etat: EtatParcours;
  restantes: number;
  /** Un enregistrement est deja parti : on empeche le double envoi. */
  occupe: boolean;
  onValider: () => void;
}

export default function BoutonValider({
  etat,
  restantes,
  occupe,
  onValider,
}: BoutonValiderProps) {
  // Etat terminal : l'acte a eu lieu, il n'y a plus d'action a proposer. On
  // laisse une marque a l'endroit exact ou le praticien a clique plutot que de
  // faire disparaitre le bouton, ce qui donnerait l'impression d'un bug.
  if (etat === "valide") {
    return (
      <div className="inline-flex items-center gap-2 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm font-semibold text-success">
        <CheckCircle2 className="h-4 w-4 shrink-0" />
        Compte rendu valide
      </div>
    );
  }

  const restantesSures = Math.max(0, restantes);

  return (
    <div className="flex flex-col gap-1.5 sm:items-end">
      <Button
        type="button"
        size="lg"
        className="h-11 w-full text-sm font-semibold sm:w-auto"
        disabled={occupe}
        aria-busy={occupe}
        onClick={onValider}
      >
        {occupe ? (
          <span className="h-4 w-4 shrink-0 animate-spin-slow rounded-full border-2 border-primary-foreground/40 border-t-primary-foreground" />
        ) : (
          <CheckCircle2 className="h-4 w-4 shrink-0" />
        )}
        {occupe ? "Enregistrement..." : "Valider le compte rendu"}
      </Button>

      {/* Ce qui reste a juger se dit avant le clic, pas a la place du clic. */}
      {restantesSures > 0 && !occupe && (
        <span className="inline-flex items-start gap-1.5 text-xs text-warning sm:justify-end">
          <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
          <span>
            Il reste {restantesSures} proposition{restantesSures > 1 ? "s" : ""} a
            juger.
          </span>
        </span>
      )}

      <p className="max-w-[22rem] text-[0.7rem] leading-relaxed text-muted-foreground sm:text-right">
        Enregistre le texte que vous validez, vos decisions et le temps passe.
        Ni identite du patient, ni audio.
      </p>
    </div>
  );
}
