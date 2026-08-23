import { useEffect, useRef } from "react";
import { Mic, Square, CornerDownLeft, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Le quai de dictee : le micro, en bas a gauche, au meme pixel du debut a la
 * fin.
 *
 * « Ajouter une precision, du coup on ne peut pas dicter. C'est dommage, on
 * perd un peu ce cote dictee. Je l'aurais bien mis en bas a gauche, moi. »
 *
 * Le proprietaire ne se trompe pas et ce n'est pas une impression : App.tsx
 * monte BarreAjout sans lui passer onDicter, et le bouton micro etait
 * conditionne par la presence de ce callback. Il n'existait litteralement pas.
 *
 * TROIS REGLES QUI NE SE NEGOCIENT PAS
 *
 * 1. LE MEME OBJET AVANT ET APRES. Le quai est identique dans les deux etats
 *    du rail : avant generation il lance la dictee initiale, apres il ajoute
 *    une precision. Meme rond, meme place, meme geste. Rien a rechercher.
 *
 * 2. LA VOIX REMPLIT LE CHAMP, ELLE N'ENVOIE PAS. Ce qui est transcrit
 *    s'ecrit dans le champ ; le praticien relit, corrige au clavier s'il le
 *    faut, puis appuie sur Entree. Une dictee qui part toute seule dans le
 *    compte rendu est une dictee qu'on n'ose plus utiliser.
 *
 * 3. PARTOUT OU L'ON PEUT TAPER, ON PEUT DICTER. C'est ce qui rend l'outil
 *    utilisable debout entre deux lames.
 *
 * Pas de cadre : un filet en haut, un champ au fond legerement teinte pour
 * dire qu'on peut y ecrire. Ni bordure arrondie, ni ombre, ni fond de carte —
 * le quai est un socle, pas une bulle posee sur le rail.
 */

interface QuaiDicteeProps {
  /** Maintien en cours : le micro pulse et la minuterie remplace l'aide. */
  enregistrement: boolean;
  /** Secondes ecoulees, fournies par le parent qui possede l'enregistreur. */
  duree: number;
  onDicterDebut: () => void;
  onDicterFin: () => void;
  /**
   * Ce que la voix a ecrit, relisible et modifiable. Le parent y depose la
   * transcription : le quai ne la publie jamais de lui-meme.
   */
  texte: string;
  onTexteChange: (texte: string) => void;
  /** Entree, ou le bouton d'envoi. Le champ n'est vide qu'en cas de succes. */
  onEnvoyer: (texte: string) => Promise<void>;
  /** Un aller-retour moteur est en cours : on ne part pas deux fois. */
  occupe: boolean;
  placeholder: string;
  erreur: string | null;
  /** Compact : socle bas des petites largeurs, ou lame repliee. */
  compact?: boolean;
  className?: string;
}

function minutes(secondes: number): string {
  const m = Math.floor(secondes / 60).toString().padStart(2, "0");
  const s = (secondes % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export default function QuaiDictee({
  enregistrement,
  duree,
  onDicterDebut,
  onDicterFin,
  texte,
  onTexteChange,
  onEnvoyer,
  occupe,
  placeholder,
  erreur,
  compact = false,
  className,
}: QuaiDicteeProps) {
  const champ = useRef<HTMLTextAreaElement>(null);

  // Le champ grandit avec le texte au lieu d'ouvrir sa propre glissiere : une
  // barre de defilement sur trois lignes de texte est exactement ce que le
  // proprietaire appelle « des glissieres partout sur les cotes ».
  useEffect(() => {
    const noeud = champ.current;
    if (!noeud) return;
    noeud.style.height = "auto";
    noeud.style.height = `${Math.min(noeud.scrollHeight, 120)}px`;
  }, [texte]);

  async function envoyer() {
    const contenu = texte.trim();
    if (!contenu || occupe) return;
    // On NE VIDE PAS le champ avant d'avoir la confirmation : perdre ce qu'on
    // vient de dicter est le meilleur moyen de ne plus jamais s'en servir.
    await onEnvoyer(contenu);
  }

  const tailleMicro = compact ? "h-11 w-11" : "h-14 w-14";

  return (
    <div className={cn("border-t px-3 py-3", className)}>
      {erreur && (
        <p role="alert" className="mb-2 text-xs font-medium text-destructive">
          {erreur}
        </p>
      )}

      <div className="flex items-end gap-2">
        <button
          type="button"
          onPointerDown={(e) => {
            e.preventDefault();
            onDicterDebut();
          }}
          onPointerUp={onDicterFin}
          onPointerLeave={() => enregistrement && onDicterFin()}
          onPointerCancel={onDicterFin}
          disabled={occupe}
          aria-pressed={enregistrement}
          aria-label={enregistrement ? "Relâcher pour transcrire" : "Maintenir pour dicter"}
          className={cn(
            "flex shrink-0 select-none items-center justify-center rounded-full transition-colors",
            "ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            "disabled:opacity-40",
            tailleMicro,
            enregistrement
              ? "bg-destructive text-destructive-foreground ring-2 ring-destructive/40"
              : "bg-primary/10 text-primary hover:bg-primary/20",
          )}
        >
          {enregistrement ? (
            <Square className="h-5 w-5" />
          ) : (
            <Mic className={compact ? "h-5 w-5" : "h-6 w-6"} />
          )}
        </button>

        <div className="flex min-w-0 flex-1 items-end gap-1.5 rounded-lg bg-muted px-2 py-1">
          <textarea
            ref={champ}
            rows={1}
            value={texte}
            onChange={(e) => onTexteChange(e.target.value)}
            onKeyDown={(e) => {
              // Entree envoie, Maj+Entree passe a la ligne : la convention que
              // tout le monde connait deja.
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void envoyer();
              }
            }}
            placeholder={enregistrement ? minutes(duree) : placeholder}
            // 16 px sous sm : en dessous, Safari iOS zoome a la mise au point.
            className={cn(
              "min-w-0 flex-1 resize-none bg-transparent py-1.5 text-base leading-snug sm:text-sm",
              "text-foreground placeholder:text-muted-foreground focus-visible:outline-none",
              enregistrement && "placeholder:font-semibold placeholder:tabular-nums placeholder:text-destructive",
            )}
          />
          <button
            type="button"
            onClick={() => void envoyer()}
            disabled={occupe || texte.trim().length === 0}
            aria-label="Ajouter au compte rendu"
            className={cn(
              "mb-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
              "text-muted-foreground transition-colors hover:text-foreground",
              "ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              "disabled:opacity-30",
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
