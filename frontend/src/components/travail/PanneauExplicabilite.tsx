import { useMemo } from "react";
import { CheckCircle2, CircleDot, FileText, Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Bloc, Trou } from "@/lib/blocsTexte";

/**
 * Analyse MARC : POURQUOI, et rien d'autre.
 *
 * Ce panneau est PUREMENT CONSULTATIF. Il ne porte aucun bouton qui decide —
 * pas un seul. Tout se tranche dans le compte rendu, sur la phrase concernee.
 *
 * Ce panneau portait les boutons, et c'etait le defaut central de l'interface :
 * on lisait une phrase a droite, on la jugeait a gauche, et on tenait les deux
 * en tete pendant l'aller-retour. C'est pendant cet aller-retour qu'on accepte
 * sans relire.
 *
 * ON DIT LE POURQUOI, JAMAIS LA MECANIQUE. Aucun « relecteur », aucun
 * « litteraliste », aucun decompte de voix. Personne n'a a savoir comment MARC
 * est construit pour s'en servir ; ce qu'on veut savoir, c'est pourquoi cette
 * phrase est la et sur quoi elle s'appuie.
 *
 * LES CITATIONS NE SONT JAMAIS REFORMULEES. Ce qui s'affiche est le passage de
 * la dictee, tel qu'il a ete transcrit. Le reecrire, meme pour le rendre plus
 * clair, reviendrait a GENERER l'explication d'une decision au lieu de la
 * CONSTATER — ce ne serait plus de l'explicabilite, mais une seconde production
 * du modele qu'on demanderait au praticien de croire.
 */

interface PanneauExplicabiliteProps {
  blocs: readonly Bloc[];
  /** Le bloc dont on regarde l'explication, ou null. */
  selection: string | null;
  /** Le trou dont on regarde l'explication, quand c'est un trou. */
  trouSelectionne: Trou | null;
  /** Identifiant de bloc -> decision enregistree. */
  decisions: Readonly<Record<string, string>>;
  transcription: string | null;
  /** Verifications deterministes passees sur le document, en lecture seule. */
  verifies: readonly { libelle: string }[];
  /** Les codes retenus, une fois tranches. Un code non encore juge n'apparait
   *  PAS ici : l'afficher le ferait passer pour acquis. */
  codes: readonly { position: string; code: string; libelle: string }[];
  onEclairer: (blocId: string | null) => void;
  onAllerAuBloc: (blocId: string) => void;
  className?: string;
  style?: React.CSSProperties;
}

export default function PanneauExplicabilite({
  blocs,
  selection,
  trouSelectionne,
  decisions,
  transcription,
  verifies,
  codes,
  onEclairer,
  onAllerAuBloc,
  className,
  style,
}: PanneauExplicabiliteProps) {
  const bloc = useMemo(
    () => blocs.find((b) => b.id === selection) ?? null,
    [blocs, selection],
  );

  const reste = useMemo(() => {
    const aDecider = blocs.filter(
      (b) => b.point !== null && decisions[b.id] === undefined,
    );
    const trous = blocs.flatMap((b) => b.trous.map((t) => ({ bloc: b, trou: t })));
    return { aDecider, trous };
  }, [blocs, decisions]);

  return (
    <aside
      style={style}
      className={cn(
        "flex min-w-0 shrink-0 flex-col overflow-hidden rounded-xl border bg-card/40",
        className,
      )}
    >
      <header className="shrink-0 border-b px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-[0.09em] text-muted-foreground">
          Analyse MARC
        </h2>
        <p className="mt-0.5 text-[0.68rem] leading-relaxed text-muted-foreground">
          Pourquoi chaque élément est là. Tout se décide dans le compte rendu.
        </p>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
        <Checklist reste={reste} onAllerAuBloc={onAllerAuBloc} onEclairer={onEclairer} />

        <section className="border-t px-3 py-2.5">
          <h3 className="text-[0.62rem] font-semibold uppercase tracking-[0.09em] text-muted-foreground">
            Pourquoi
          </h3>
          {bloc === null ? (
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
              Cliquez « Pourquoi ? » sur une phrase du compte rendu, ou un champ
              à compléter, pour voir ce sur quoi il s'appuie.
            </p>
          ) : (
            <Explication bloc={bloc} trou={trouSelectionne} />
          )}
        </section>

        <Verifications verifies={verifies} />
        <Codes codes={codes} />
        <Dictee transcription={transcription} />
      </div>
    </aside>
  );
}

/* ------------------------------------------------------------------ */

function Checklist({
  reste,
  onAllerAuBloc,
  onEclairer,
}: {
  reste: { aDecider: Bloc[]; trous: { bloc: Bloc; trou: Trou }[] };
  onAllerAuBloc: (blocId: string) => void;
  onEclairer: (blocId: string) => void;
}) {
  const total = reste.aDecider.length + reste.trous.length;

  return (
    <section className="px-3 py-2.5">
      <h3 className="text-[0.62rem] font-semibold uppercase tracking-[0.09em] text-muted-foreground">
        Reste à voir
      </h3>
      {total === 0 ? (
        <p className="mt-1.5 text-xs text-muted-foreground">
          Rien en attente. Le compte rendu reste modifiable.
        </p>
      ) : (
        <ul className="mt-1.5 space-y-1">
          {reste.aDecider.map((bloc) => (
            <li key={bloc.id}>
              <button
                type="button"
                onClick={() => {
                  onEclairer(bloc.id);
                  onAllerAuBloc(bloc.id);
                }}
                className="flex w-full items-start gap-1.5 rounded px-1 py-0.5 text-left text-xs hover:bg-accent"
              >
                <CircleDot
                  className={cn(
                    "mt-0.5 h-3 w-3 shrink-0",
                    bloc.nature === "verifier" ? "text-rose-500" : "text-sky-500",
                  )}
                />
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {bloc.texte.trim()}
                </span>
              </button>
            </li>
          ))}
          {reste.trous.map(({ bloc, trou }) => (
            <li key={`${bloc.id}:${trou.debut}`}>
              <button
                type="button"
                onClick={() => {
                  onEclairer(bloc.id);
                  onAllerAuBloc(bloc.id);
                }}
                className="flex w-full items-start gap-1.5 rounded px-1 py-0.5 text-left text-xs hover:bg-accent"
              >
                <CircleDot className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  À compléter : {trou.champ}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Explication({ bloc, trou }: { bloc: Bloc; trou: Trou | null }) {
  // Un trou selectionne prime sur son bloc : c'est de LUI qu'on veut savoir
  // pourquoi il est demande.
  if (trou !== null) {
    return (
      <div className="mt-1.5 space-y-2">
        <p className="text-xs font-medium text-foreground">{trou.champ}</p>
        {trou.declencheur !== null && (
          <div>
            <p className="text-[0.62rem] uppercase tracking-wide text-muted-foreground">
              Parce que vous avez dit
            </p>
            <blockquote className="mt-1 flex gap-1.5 rounded-md border-l-2 border-amber-500/60 bg-amber-500/10 px-2 py-1.5">
              <Quote className="mt-0.5 h-3 w-3 shrink-0 opacity-50" />
              <span className="text-xs italic leading-relaxed">
                {trou.declencheur}
              </span>
            </blockquote>
          </div>
        )}
        {trou.raison !== null && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            {trou.raison}
          </p>
        )}
        {trou.options.length > 0 && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            Les valeurs proposées sont les seules possibles pour ce champ. Vous
            pouvez en écrire une autre.
          </p>
        )}
      </div>
    );
  }

  const point = bloc.point;
  return (
    <div className="mt-1.5 space-y-2">
      <p className="text-xs leading-relaxed text-foreground">{bloc.texte.trim()}</p>

      {bloc.nature === "verifier" ? (
        <div className="rounded-md bg-rose-500/10 px-2 py-1.5">
          <p className="text-xs leading-relaxed text-rose-800 dark:text-rose-200">
            Aucun passage de votre dictée ne correspond à cette phrase. MARC l'a
            écrite en interprétant le reste — à vous de dire si l'interprétation
            tient.
          </p>
        </div>
      ) : point?.citation ? (
        <div>
          <p className="text-[0.62rem] uppercase tracking-wide text-muted-foreground">
            S'appuie sur
          </p>
          <blockquote className="mt-1 flex gap-1.5 rounded-md border-l-2 border-sky-500/60 bg-sky-500/10 px-2 py-1.5">
            <Quote className="mt-0.5 h-3 w-3 shrink-0 opacity-50" />
            <span className="text-xs italic leading-relaxed">{point.citation}</span>
          </blockquote>
        </div>
      ) : (
        <p className="text-xs leading-relaxed text-muted-foreground">
          Ce passage reprend ce que vous avez dicté.
        </p>
      )}

      {point !== null && point.pourquoi.length > 0 && (
        <ul className="space-y-1">
          {point.pourquoi.map((raison, rang) => (
            <li
              key={`${rang}-${raison.slice(0, 20)}`}
              className="rounded-md bg-muted/60 px-2 py-1.5 text-xs leading-relaxed"
            >
              {raison}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Verifications({ verifies }: { verifies: readonly { libelle: string }[] }) {
  if (verifies.length === 0) return null;
  return (
    <section className="border-t px-3 py-2.5">
      <h3 className="text-[0.62rem] font-semibold uppercase tracking-[0.09em] text-muted-foreground">
        Vérifié sur le document
      </h3>
      <ul className="mt-1.5 space-y-1">
        {verifies.map((verifie) => (
          <li
            key={verifie.libelle}
            className="flex items-start gap-1.5 text-xs leading-relaxed text-muted-foreground"
          >
            <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-emerald-600" />
            {verifie.libelle}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Codes({
  codes,
}: {
  codes: readonly { position: string; code: string; libelle: string }[];
}) {
  if (codes.length === 0) return null;
  return (
    <section className="border-t px-3 py-2.5">
      <h3 className="text-[0.62rem] font-semibold uppercase tracking-[0.09em] text-muted-foreground">
        Codification retenue
      </h3>
      <ul className="mt-1.5 space-y-1">
        {codes.map((code) => (
          <li key={`${code.position}:${code.code}`} className="text-xs">
            <span className="font-mono font-medium text-foreground">{code.code}</span>
            {code.libelle && (
              <span className="text-muted-foreground"> · {code.libelle}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Dictee({ transcription }: { transcription: string | null }) {
  if (transcription === null || transcription.trim() === "") return null;
  return (
    <section className="border-t px-3 py-2.5">
      <h3 className="flex items-center gap-1.5 text-[0.62rem] font-semibold uppercase tracking-[0.09em] text-muted-foreground">
        <FileText className="h-3 w-3" />
        Votre dictée
      </h3>
      <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
        {transcription}
      </p>
    </section>
  );
}
