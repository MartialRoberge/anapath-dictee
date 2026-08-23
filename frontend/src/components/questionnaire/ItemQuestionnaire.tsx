import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ItemQuestionnaire as ItemQuestionnaireApi } from "@/services/etude";
import { Textarea } from "@/components/ui/textarea";

/* ------------------------------------------------------------------ */
/*  Contrat d'item — miroir de GET /etude/questionnaires/{nom}         */
/* ------------------------------------------------------------------ */

export type TypeItem =
  | "likert_5"
  | "echelle_10"
  | "choix_unique"
  | "choix_multiple"
  | "texte_libre"
  | "nombre"
  | "oui_non"
  | "classement";

/**
 * Un item tel que le backend le sert. Aucun libelle n'est recopie ici : le
 * depouillement doit pouvoir associer une reponse a un libelle exact des mois
 * plus tard, et un libelle duplique dans un composant derive au premier
 * remaniement.
 */
/**
 * Un item, tel que le backend le sert.
 *
 * Le type vient de services/etude.ts, seul miroir du serveur : le redeclarer
 * ici laisserait un champ renomme cote serveur passer inapercu — et c'est
 * exactement ce qui vient d'arriver avec les ancres d'echelle.
 *
 * `inverse` est volontairement sans effet a l'affichage : l'inversion se fait a
 * la cotation. Retourner l'echelle ici l'inverserait deux fois.
 */
export type ItemDefinition = ItemQuestionnaireApi;

/* ------------------------------------------------------------------ */
/*  Encodage des valeurs                                               */
/* ------------------------------------------------------------------ */

/** Choix multiple : la valeur reste lisible telle quelle au depouillement, et
 *  une selection unique reste comparable a son libelle — c'est ce dont depend
 *  la regle depend_de. */
const SEP_MULTIPLE = " | ";

/** Le classement encode un ORDRE, la fleche le dit sans convention a retenir. */
const SEP_CLASSEMENT = " > ";

/* Les ancres d'echelle viennent du BACKEND, item par item, exactement comme
 * les libelles. Une constante ici les appliquerait a toutes les echelles a cinq
 * points — or elles ne mesurent pas la meme chose. Les items par cas sont des
 * AFFIRMATIONS, qu'on cote en accord. Le PDQI-9 cote un DEGRE de qualite : le
 * coter en accord change la question posee, et un PDQI-9 sur des ancres
 * d'accord ne se compare pas plus a la litterature qu'un F-SUS retraduit. Un
 * item formule en question ("faites-vous confiance a ... ?") n'appelle pas
 * davantage "tout a fait d'accord" comme reponse. */

const POINTS_LIKERT = 5;
const POINTS_ECHELLE = 10;

/** Champ de saisie : meme vocabulaire visuel que la primitive Textarea. */
const CLASSES_CHAMP =
  "rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

/* ------------------------------------------------------------------ */
/*  PastilleChoix — une option cliquable, pilotee par un vrai input     */
/* ------------------------------------------------------------------ */

interface PastilleChoixProps {
  /** Nom du groupe : les fleches du clavier naviguent entre les radios. */
  nom: string;
  multiple?: boolean;
  coche: boolean;
  libelle: string;
  onSelect: () => void;
}

function PastilleChoix({
  nom,
  multiple = false,
  coche,
  libelle,
  onSelect,
}: PastilleChoixProps) {
  return (
    <label className="min-w-0 cursor-pointer">
      <input
        type={multiple ? "checkbox" : "radio"}
        name={nom}
        checked={coche}
        onChange={onSelect}
        className="peer sr-only"
      />
      <span
        className={cn(
          "flex min-h-[2.5rem] items-center justify-center gap-1.5 rounded-md border px-3 py-1.5 text-center text-sm font-medium transition-colors",
          "peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2",
          coche
            ? "border-primary bg-primary text-primary-foreground"
            : "border-input bg-background text-foreground hover:bg-accent hover:text-accent-foreground",
        )}
      >
        {multiple && coche && <Check className="h-3.5 w-3.5 shrink-0" />}
        <span className="min-w-0 break-words">{libelle}</span>
      </span>
    </label>
  );
}

/* ------------------------------------------------------------------ */
/*  Echelles numerotees                                                */
/* ------------------------------------------------------------------ */

interface EchelleProps {
  nom: string;
  points: number;
  valeur: string;
  onChange: (valeur: string) => void;
}

/** Les deux extremites, toujours visibles : une rangee de ronds anonymes ne
 *  s'interprete pas, et un survol ne se lit pas au clavier. */
function Ancres({ basse, haute }: { basse: string; haute: string }) {
  if (!basse && !haute) return null;
  return (
    <div className="flex items-baseline justify-between gap-3 text-[0.7rem] leading-tight text-muted-foreground">
      <span className="min-w-0">{basse}</span>
      <span className="min-w-0 text-right">{haute}</span>
    </div>
  );
}

function EchelleNumerique({ nom, points, valeur, onChange }: EchelleProps) {
  return (
    <div
      className={cn(
        "grid gap-1.5",
        points > POINTS_LIKERT ? "grid-cols-5 sm:grid-cols-10" : "grid-cols-5",
      )}
    >
      {Array.from({ length: points }, (_, index) => String(index + 1)).map(
        (point) => (
          <PastilleChoix
            key={point}
            nom={nom}
            coche={valeur === point}
            libelle={point}
            onSelect={() => onChange(point)}
          />
        ),
      )}
    </div>
  );
}

interface LikertProps {
  nom: string;
  /** Options hors echelle servies par le backend (ex. « Non applicable »). */
  options: string[];
  ancreBasse: string;
  ancreHaute: string;
  valeur: string;
  onChange: (valeur: string) => void;
}

function EchelleLikert({
  nom,
  options,
  ancreBasse,
  ancreHaute,
  valeur,
  onChange,
}: LikertProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Ancres basse={ancreBasse} haute={ancreHaute} />
      <EchelleNumerique
        nom={nom}
        points={POINTS_LIKERT}
        valeur={valeur}
        onChange={onChange}
      />
      {options.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {options.map((option) => (
            <PastilleChoix
              key={option}
              nom={nom}
              coche={valeur === option}
              libelle={option}
              onSelect={() => onChange(option)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Listes d'options (choix unique, oui/non, choix multiple)           */
/* ------------------------------------------------------------------ */

interface ListeOptionsProps {
  nom: string;
  options: string[];
  valeur: string;
  onChange: (valeur: string) => void;
  multiple: boolean;
}

function ListeOptions({
  nom,
  options,
  valeur,
  onChange,
  multiple,
}: ListeOptionsProps) {
  const choisies = multiple ? valeur.split(SEP_MULTIPLE).filter(Boolean) : [];

  const basculer = (option: string) => {
    if (!multiple) {
      onChange(option);
      return;
    }
    const retenues = new Set(choisies);
    if (!retenues.delete(option)) retenues.add(option);
    // On reprend l'ordre du backend plutot que l'ordre des clics : deux
    // praticiens qui cochent la meme chose ecrivent alors la meme valeur.
    onChange(options.filter((o) => retenues.has(o)).join(SEP_MULTIPLE));
  };

  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => (
        <PastilleChoix
          key={option}
          nom={nom}
          multiple={multiple}
          coche={multiple ? choisies.includes(option) : valeur === option}
          libelle={option}
          onSelect={() => basculer(option)}
        />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Classement                                                         */
/* ------------------------------------------------------------------ */

interface ClassementProps {
  options: string[];
  valeur: string;
  onChange: (valeur: string) => void;
}

function Classement({ options, valeur, onChange }: ClassementProps) {
  const ordre = valeur ? valeur.split(SEP_CLASSEMENT) : [];

  const basculer = (option: string) => {
    const suivant = ordre.includes(option)
      ? ordre.filter((o) => o !== option)
      : [...ordre, option];
    onChange(suivant.join(SEP_CLASSEMENT));
  };

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-xs text-muted-foreground">
        Cliquez dans votre ordre de priorite ; recliquez pour retirer.
      </p>
      {options.map((option) => {
        const rang = ordre.indexOf(option);
        const classe = rang >= 0;
        return (
          <button
            key={option}
            type="button"
            onClick={() => basculer(option)}
            className={cn(
              "flex min-h-[2.5rem] items-center gap-2.5 rounded-md border px-3 py-1.5 text-left text-sm font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              classe
                ? "border-primary/40 bg-primary/5 text-foreground"
                : "border-input bg-background hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <span
              className={cn(
                "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                classe
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {classe ? rang + 1 : "-"}
            </span>
            <span className="min-w-0 break-words">{option}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Controle — un rendu par type d'item                                */
/* ------------------------------------------------------------------ */

interface ControleProps {
  item: ItemDefinition;
  nom: string;
  idChamp: string;
  valeur: string;
  onChange: (valeur: string) => void;
  dense: boolean;
}

function Controle({
  item,
  nom,
  idChamp,
  valeur,
  onChange,
  dense,
}: ControleProps) {
  switch (item.type) {
    case "likert_5":
      return (
        <EchelleLikert
          nom={nom}
          options={item.options}
          ancreBasse={item.ancre_basse}
          ancreHaute={item.ancre_haute}
          valeur={valeur}
          onChange={onChange}
        />
      );
    case "echelle_10":
      return (
        <div className="flex flex-col gap-1.5">
          {/* Sans ancres, deux praticiens cotent une charge de travail en sens
              inverse et rien ne le revele au depouillement. */}
          <Ancres basse={item.ancre_basse} haute={item.ancre_haute} />
          <EchelleNumerique
            nom={nom}
            points={POINTS_ECHELLE}
            valeur={valeur}
            onChange={onChange}
          />
        </div>
      );
    case "choix_unique":
    case "oui_non":
      return (
        <ListeOptions
          nom={nom}
          options={item.options}
          valeur={valeur}
          onChange={onChange}
          multiple={false}
        />
      );
    case "choix_multiple":
      return (
        <ListeOptions
          nom={nom}
          options={item.options}
          valeur={valeur}
          onChange={onChange}
          multiple
        />
      );
    case "classement":
      return (
        <Classement
          options={item.options}
          valeur={valeur}
          onChange={onChange}
        />
      );
    case "nombre":
      return (
        <input
          id={idChamp}
          type="number"
          inputMode="numeric"
          min={0}
          value={valeur}
          onChange={(e) => onChange(e.target.value)}
          className={cn(CLASSES_CHAMP, "h-10 w-full max-w-[9rem]")}
        />
      );
    case "texte_libre":
      return (
        <Textarea
          id={idChamp}
          value={valeur}
          onChange={(e) => onChange(e.target.value)}
          className={cn(
            "resize-y",
            dense ? "min-h-[3.25rem]" : "min-h-[5rem]",
          )}
        />
      );
  }
}

/* ------------------------------------------------------------------ */
/*  ItemQuestionnaire                                                  */
/* ------------------------------------------------------------------ */

interface ItemQuestionnaireProps {
  item: ItemDefinition;
  valeur: string;
  onChange: (valeur: string) => void;
  /** Ancre DOM stable : permet d'amener le praticien sur un oubli. */
  ancreId: string;
  /** Obligatoire reste vide apres une tentative d'envoi. */
  manquant?: boolean;
  /** Version resserree (questionnaire par cas : tout tient sans defilement). */
  dense?: boolean;
  /** Poids visuel supplementaire (mesure qu'aucune telemetrie ne produit). */
  accentue?: boolean;
  className?: string;
}

export default function ItemQuestionnaire({
  item,
  valeur,
  onChange,
  ancreId,
  manquant = false,
  dense = false,
  accentue = false,
  className,
}: ItemQuestionnaireProps) {
  const idLibelle = `${ancreId}-libelle`;
  const idChamp = `${ancreId}-champ`;
  const champLibre = item.type === "texte_libre" || item.type === "nombre";
  // Une question fermee a deux options tient sur la meme ligne que son libelle :
  // une ligne gagnee par item, c'est ce qui fait tenir le questionnaire par cas
  // dans un ecran sans defilement.
  const enLigne = item.type === "oui_non";

  const roleGroupe = champLibre
    ? undefined
    : item.type === "choix_multiple"
      ? "group"
      : "radiogroup";

  const classesLibelle = cn(
    "text-sm leading-snug text-foreground break-words",
    accentue ? "font-semibold" : "font-medium",
    enLigne ? "min-w-0 flex-1" : "block",
  );

  const libelle = (
    <>
      {item.libelle}
      {item.obligatoire && (
        <>
          <span aria-hidden="true" className="ml-1 text-destructive">
            *
          </span>
          <span className="sr-only"> (reponse obligatoire)</span>
        </>
      )}
    </>
  );

  return (
    <div
      id={ancreId}
      className={cn(
        "min-w-0 rounded-lg border transition-colors",
        dense ? "p-2.5" : "p-3.5",
        enLigne && "flex flex-wrap items-center justify-between gap-x-4 gap-y-2",
        manquant
          ? "border-destructive/40 bg-destructive/5"
          : accentue
            ? "border-primary/30 bg-primary/5"
            : "border-border/70 bg-card",
        className,
      )}
    >
      {champLibre ? (
        <label id={idLibelle} htmlFor={idChamp} className={classesLibelle}>
          {libelle}
        </label>
      ) : (
        <p id={idLibelle} className={classesLibelle}>
          {libelle}
        </p>
      )}

      <div
        className={cn(
          "min-w-0",
          enLigne ? "shrink-0" : dense ? "mt-1.5" : "mt-2",
        )}
        role={roleGroupe}
        aria-labelledby={champLibre ? undefined : idLibelle}
      >
        <Controle
          item={item}
          nom={ancreId}
          idChamp={idChamp}
          valeur={valeur}
          onChange={onChange}
          dense={dense}
        />
      </div>

      {manquant && (
        <p
          className={cn(
            "text-xs font-medium text-destructive",
            enLigne ? "basis-full" : "mt-1.5",
          )}
        >
          Reponse attendue.
        </p>
      )}
    </div>
  );
}
