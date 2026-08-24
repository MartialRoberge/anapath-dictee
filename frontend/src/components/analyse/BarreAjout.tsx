import { useState } from "react";
import { Mic, Square, CornerDownLeft, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * La barre flottante : ajouter quelque chose sans repartir de zero.
 *
 * Aujourd'hui, un praticien qui veut completer son compte rendu doit REDICTER
 * l'ensemble. C'est la chose la moins ergonomique de l'outil, et la plus simple
 * a corriger : une ligne ou l'on ecrit, ou l'on dicte, et le compte rendu
 * s'enrichit.
 *
 * Ce qui est ajoute ici passe par le meme chemin que le reste — le college le
 * juge, il devient un point a traiter s'il y a doute. Un ajout n'est pas un
 * passe-droit : il est verifie comme le reste, sinon il suffirait de dicter une
 * phrase pour contourner tous les garde-fous.
 *
 * Flottante et discrete : elle accompagne le travail, elle ne le commande pas.
 */

/** Un ajout deja verse au contexte, du plus recent au plus ancien. */
export interface AjoutContexte {
  id: string;
  texte: string;
  /** Dicte a la voix, ou tape au clavier. La distinction se mesure. */
  voix: boolean;
  a: number;
}

interface BarreAjoutProps {
  /** Envoie le texte a ajouter. Rejette si l'ajout echoue. */
  onAjouter: (texte: string, voix: boolean) => Promise<void>;
  /**
   * Demarre l'enregistrement. ABSENT tant que la dictee d'appoint n'est pas
   * disponible : le bouton disparait alors, plutot que de promettre une
   * fonction qui echouerait au clic.
   *
   * DEUX CALLBACKS ET NON UNE, parce qu'une seule ne pouvait pas s'arreter.
   * Le contrat precedent etait `onDicter(): Promise<string>` — demarrer et
   * resoudre quand c'est fini — sans aucun moyen de dire "c'est fini". Le
   * bouton affichait bien un carre « Arreter la dictee », mais le clic
   * retombait sur une garde `if (dictee) return` et ne faisait rien. On
   * demarrait une dictee qu'on ne pouvait plus arreter.
   */
  onDicterDebut?: () => Promise<void>;
  /** Arrete l'enregistrement et rend le texte transcrit. */
  onDicterFin?: () => Promise<string>;
  occupe: boolean;
  /**
   * CE QUI A DEJA ETE AJOUTE. Sans cet historique, le praticien qui vient de
   * dicter une precision ne voit plus nulle part ce qu'il a ajoute : le texte
   * a change quelque part dans le compte rendu, et il doit le retrouver a
   * l'oeil pour verifier que la transcription l'a bien compris.
   */
  historique: readonly AjoutContexte[];
  className?: string;
}

export default function BarreAjout({
  onAjouter,
  onDicterDebut,
  onDicterFin,
  occupe,
  historique,
  className,
}: BarreAjoutProps) {
  const [texte, setTexte] = useState("");
  const [dictee, setDictee] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  // Un texte insere par la dictee reste marque comme tel meme si le praticien
  // le retouche avant d'envoyer : il vient bien de la voix.
  const [venaitDeLaVoix, setVenaitDeLaVoix] = useState(false);

  async function envoyer() {
    const contenu = texte.trim();
    if (!contenu || occupe) return;
    setErreur(null);
    try {
      await onAjouter(contenu, venaitDeLaVoix);
      setTexte("");
      setVenaitDeLaVoix(false);
    } catch (e) {
      // On NE VIDE PAS le champ en cas d'echec : le praticien perdrait ce
      // qu'il vient d'ecrire, et c'est le meilleur moyen de lui faire
      // abandonner la fonction.
      setErreur(e instanceof Error ? e.message : "L'ajout n'a pas abouti.");
    }
  }

  const [transcrit, setTranscrit] = useState(false);

  async function basculerDictee() {
    if (occupe || !onDicterDebut || !onDicterFin || transcrit) return;
    setErreur(null);

    if (!dictee) {
      try {
        await onDicterDebut();
        setDictee(true);
      } catch (e) {
        setErreur(
          e instanceof Error ? e.message : "Le micro n'a pas pu démarrer.",
        );
      }
      return;
    }

    // Deuxieme clic : on arrete, on transcrit, on INSERE dans le champ plutot
    // que d'envoyer directement — le praticien relit ce que la transcription a
    // compris avant que ca parte.
    setDictee(false);
    setTranscrit(true);
    try {
      const texteDicte = await onDicterFin();
      if (texteDicte.trim()) {
        setTexte((actuel) =>
          actuel ? `${actuel} ${texteDicte}` : texteDicte,
        );
        setVenaitDeLaVoix(true);
      }
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "La dictée n'a pas abouti.");
    } finally {
      setTranscrit(false);
    }
  }

  return (
    <div className={cn("pointer-events-none flex justify-center px-4", className)}>
      <div className="pointer-events-auto w-full max-w-2xl">
        {historique.length > 0 && (
          <ol className="mb-1.5 space-y-1">
            {/* Les trois derniers seulement : la barre flotte au-dessus du
                compte rendu, et un historique qui grandit finirait par le
                masquer. Le reste vit dans la dictee, a gauche. */}
            {historique.slice(0, 3).map((ajout) => (
              <li
                key={ajout.id}
                className="flex items-start gap-1.5 rounded-md bg-card/90 px-2.5 py-1 text-xs shadow-sm backdrop-blur"
              >
                {ajout.voix ? (
                  <Mic className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                ) : (
                  <CornerDownLeft className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                )}
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {ajout.texte}
                </span>
              </li>
            ))}
          </ol>
        )}
        {erreur && (
          <p
            role="alert"
            className="mb-1.5 rounded-md bg-destructive/10 px-3 py-1.5 text-xs text-destructive"
          >
            {erreur}
          </p>
        )}
        <div className="flex items-end gap-1.5 rounded-xl border bg-card/95 p-1.5 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-card/80">
          {onDicterDebut && onDicterFin && (
          <button
            type="button"
            onClick={basculerDictee}
            disabled={occupe || transcrit}
            aria-label={
              transcrit
                ? "Transcription en cours"
                : dictee
                  ? "Arrêter la dictée"
                  : "Ajouter à la voix"
            }
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors",
              "ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              "disabled:opacity-50",
              dictee
                ? "bg-destructive text-destructive-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            {transcrit ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : dictee ? (
              <Square className="h-4 w-4" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
          </button>
          )}

          <textarea
            value={texte}
            onChange={(e) => setTexte(e.target.value)}
            onKeyDown={(e) => {
              // Entrée envoie, Maj+Entrée passe a la ligne : c'est la
              // convention que tout le monde connait deja.
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void envoyer();
              }
            }}
            rows={1}
            placeholder="Ajouter une précision, une mesure, un résultat…"
            className="max-h-32 min-h-[2.25rem] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-snug text-foreground placeholder:text-muted-foreground focus-visible:outline-none"
          />

          <button
            type="button"
            onClick={() => void envoyer()}
            disabled={occupe || texte.trim().length === 0}
            aria-label="Ajouter au compte rendu"
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-colors",
              "ring-offset-background hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              "disabled:opacity-40",
            )}
          >
            {occupe ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CornerDownLeft className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
