import { useState } from "react";
import { Check, Pencil, X, ChevronDown, Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ActionPoint, PointATraiter } from "@/lib/pointsATraiter";

/**
 * Un point a traiter, et les trois gestes qui le font disparaitre.
 *
 * TOUJOURS LA MEME FORME, quelle que soit l'origine du point. Une proposition
 * du college, un champ obligatoire absent, un code ADICAP, une incoherence : le
 * praticien voit la meme carte, au meme endroit, avec les memes verbes. C'est
 * ce qui permet d'enchainer sans reapprendre a chaque fois.
 *
 * Le POURQUOI est replie par defaut. Ouvert, il noierait la decision ; absent,
 * il rendrait le point arbitraire. Son ouverture est un evenement remonte au
 * parent, parce que l'etude mesure si la justification change l'avis — c'est LA
 * mesure d'explicabilite, et elle n'existe pas sans ce signal.
 */

/**
 * Les trois natures d'une correction, demandees UNIQUEMENT sur une correction
 * de restitution.
 *
 * C'est la question qui separe "le systeme s'est trompe" de "j'ecris
 * autrement". Sans elle, une reformulation de confort et une erreur clinique
 * comptent pareil, et le taux publie melange deux choses sans rapport — un
 * outil dont 40 % des propositions sont reecrites en style maison passerait
 * pour un outil a 40 % d'erreurs.
 *
 * Elle ne se pose pas sur un code : un code ADICAP corrige n'a pas de "nature"
 * au sens clinique, il est juste ou faux.
 */
const NATURES: { valeur: string; libelle: string; aide: string }[] = [
  {
    valeur: "style",
    libelle: "J'écris autrement",
    aide: "Le fond était juste, je reformule",
  },
  {
    valeur: "precision",
    libelle: "J'ajoute une précision",
    aide: "Juste mais incomplet",
  },
  {
    valeur: "erreur_fond",
    libelle: "C'était faux",
    aide: "Le système s'est trompé sur le fond",
  },
];

interface PointCarteProps {
  point: PointATraiter;
  actif: boolean;
  occupe: boolean;
  onDecider: (action: ActionPoint, valeur?: string, nature?: string) => void;
  onSurvol: (point: PointATraiter | null) => void;
  onOuvrirPourquoi: (point: PointATraiter) => void;
}

const ICONE = {
  accepter: Check,
  modifier: Pencil,
  ecarter: X,
} as const;

/** La gravite se lit au liseré, sans avoir a lire le texte. */
const LISERE: Record<PointATraiter["gravite"], string> = {
  haute: "border-l-[3px] border-l-destructive",
  moyenne: "border-l-[3px] border-l-warning",
  basse: "border-l-[3px] border-l-border",
};

const TON: Record<string, string> = {
  accepter: "bg-primary text-primary-foreground hover:bg-primary/90",
  modifier: "border border-input bg-background hover:bg-accent",
  ecarter: "border border-input bg-background hover:bg-accent",
};

export default function PointCarte({
  point,
  actif,
  occupe,
  onDecider,
  onSurvol,
  onOuvrirPourquoi,
}: PointCarteProps) {
  const [pourquoiOuvert, setPourquoiOuvert] = useState(false);
  const [saisie, setSaisie] = useState<ActionPoint | null>(null);
  const [valeur, setValeur] = useState(point.valeur ?? point.detail);
  const [nature, setNature] = useState<string | null>(null);

  // La nature ne se demande que sur une correction de restitution : ailleurs
  // elle n'a pas de sens, et un geste sans objet fait abandonner la fonction.
  const natureRequise =
    saisie?.decision === "corrige" && point.origine === "proposition";

  function basculerPourquoi() {
    const ouvre = !pourquoiOuvert;
    setPourquoiOuvert(ouvre);
    // Seule l'OUVERTURE est un signal : refermer ne dit rien de plus.
    if (ouvre) onOuvrirPourquoi(point);
  }

  function lancer(action: ActionPoint) {
    if (action.saisie && saisie?.decision !== action.decision) {
      setSaisie(action);
      return;
    }
    onDecider(action, action.saisie ? valeur : undefined, nature ?? undefined);
    setSaisie(null);
    setNature(null);
  }

  return (
    <article
      onMouseEnter={() => onSurvol(point)}
      onMouseLeave={() => onSurvol(null)}
      onFocus={() => onSurvol(point)}
      onBlur={() => onSurvol(null)}
      className={cn(
        "rounded-lg bg-card shadow-sm transition-shadow",
        LISERE[point.gravite],
        actif && "ring-2 ring-primary/40",
      )}
    >
      <div className="px-3 py-2.5">
        <p className="text-[0.68rem] font-medium uppercase tracking-wide text-muted-foreground">
          {point.titre}
        </p>
        <p className="mt-1 text-sm leading-snug text-foreground">{point.detail}</p>

        {/* Le decompte des voix remplace un score de confiance : "deux
            relecteurs sur trois" se verifie, un 0,73 ne se verifie pas. */}
        {point.voix && (
          <p className="mt-1.5 text-xs text-muted-foreground">
            {point.voix.pour} relecteur{point.voix.pour > 1 ? "s" : ""} sur{" "}
            {point.voix.total}{" "}
            {point.voix.pour > 1 ? "ont retrouvé" : "a retrouvé"} ce passage dans
            votre dictée
          </p>
        )}

        {point.empan === null && point.origine === "proposition" && (
          <p className="mt-1.5 rounded bg-destructive/10 px-2 py-1 text-xs text-destructive">
            Aucun passage de votre dictée ne soutient cette phrase.
          </p>
        )}
      </div>

      {saisie && (
        <div className="border-t px-3 py-2">
          <textarea
            autoFocus
            value={valeur}
            onChange={(e) => setValeur(e.target.value)}
            rows={3}
            className="w-full resize-y rounded-md border border-input bg-background px-2.5 py-1.5 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            placeholder={
              point.origine === "champ_manquant"
                ? "Saisissez la valeur…"
                : "Votre formulation…"
            }
          />
        </div>
      )}

      {natureRequise && (
        <div className="border-t px-3 py-2">
          <p className="mb-1.5 text-xs text-muted-foreground">
            Pourquoi corrigez-vous&nbsp;?
          </p>
          <div className="flex flex-wrap gap-1.5">
            {NATURES.map((choix) => (
              <button
                key={choix.valeur}
                type="button"
                title={choix.aide}
                onClick={() => setNature(choix.valeur)}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
                  "ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  nature === choix.valeur
                    ? "bg-primary text-primary-foreground"
                    : "border border-input bg-background hover:bg-accent",
                )}
              >
                {choix.libelle}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 border-t px-3 py-2">
        {point.actions.map((action) => {
          const Icone = ICONE[action.verbe];
          const enSaisie = saisie?.decision === action.decision;
          return (
            <button
              key={action.decision + action.libelle}
              type="button"
              disabled={occupe}
              onClick={() => lancer(action)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
                "ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                "disabled:opacity-50",
                TON[action.verbe],
              )}
            >
              <Icone className="h-3.5 w-3.5" />
              {enSaisie ? "Enregistrer" : action.libelle}
            </button>
          );
        })}
      </div>

      {point.pourquoi.length > 0 && (
        <div className="border-t">
          <button
            type="button"
            onClick={basculerPourquoi}
            aria-expanded={pourquoiOuvert}
            className="flex w-full items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform motion-reduce:transition-none",
                pourquoiOuvert && "rotate-180",
              )}
            />
            Pourquoi
          </button>
          {pourquoiOuvert && (
            <div className="space-y-1.5 px-3 pb-2.5">
              {point.pourquoi.map((raison, index) => (
                <p key={index} className="text-xs leading-relaxed text-muted-foreground">
                  {raison}
                </p>
              ))}
              {point.citation && (
                <p className="flex gap-1.5 rounded bg-muted/60 px-2 py-1.5 text-xs italic text-foreground">
                  <Quote className="mt-0.5 h-3 w-3 shrink-0 opacity-60" />
                  {point.citation}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </article>
  );
}
