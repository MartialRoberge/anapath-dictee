import { CheckCircle2 } from "lucide-react";
import Questionnaire from "./Questionnaire";

interface QuestionnaireParCasProps {
  /** Requis, contrairement au questionnaire generique : une reponse « sur ce
   *  cas » qui n'est rattachee a aucun dossier n'est pas exploitable. */
  dossierId: string;
  onTermine: () => void;
  onIndisponible?: (raison: string) => void;
}

/**
 * Le questionnaire pose juste apres la validation d'un cas.
 *
 * Il est pose a chaud et jamais en fin de session : un jugement retrospectif
 * global est peu fiable, alors que le souvenir du cas qu'on vient de relire
 * l'est. Ce composant ne fait que poser ce cadre — la mecanique (items,
 * dependances, obligatoires, envoi) reste celle du questionnaire generique.
 */
export default function QuestionnaireParCas({
  dossierId,
  onTermine,
  onIndisponible,
}: QuestionnaireParCasProps) {
  // Plus large que la colonne de lecture d'un compte-rendu : chaque libelle qui
  // tient sur une ligne, c'est une rangee de moins, et les 40 secondes
  // annoncees restent tenables sans defilement.
  return (
    <section className="mx-auto w-full max-w-[1100px] overflow-hidden rounded-xl border bg-card shadow-sm">
      <header className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5 border-b px-4 py-2.5">
        <span className="flex h-4 w-4 shrink-0 translate-y-0.5 items-center justify-center text-success">
          <CheckCircle2 className="h-4 w-4" />
        </span>
        <span className="text-sm font-semibold">Cas valide</span>
        <span className="min-w-0 text-xs text-muted-foreground">
          Pendant que le cas est encore frais.
        </span>
      </header>

      <div className="p-3.5">
        <Questionnaire
          nom="par_cas"
          dossierId={dossierId}
          onTermine={onTermine}
          onIndisponible={onIndisponible}
        />
      </div>
    </section>
  );
}
