// Pourquoi : pour l'élément sélectionné, ce qui justifie la phrase, toujours dans le même ordre
// (Dictée, Règles, Référentiel, Modèle). Sans sélection : sources citées par le projet.
import { formuleConfiance, nombre, parCategorie, passageDictee, preuvesDe, preuvesTrou, TITRES_TROU, VERDICT, verdictAmbre } from "../lib/pourquoi";
import { etatTrou, texteElement, type ProjetLocal } from "../lib/session";
import type { Element, Preuve, SourceRef } from "../types";
import OngletSources from "./OngletSources";
import { SourceLien } from "./Source";

const NIVEAU = { haute: "confiance haute", moyenne: "confiance moyenne", basse: "confiance basse" } as const;
const STATUT = { dicte: "Dicté tel quel", reformule: "Reformulé", normalise: "Normalisé", a_completer: "À compléter" } as const;

interface Props {
  local: ProjetLocal;
  element: Element | null;
  onConsulte: (s: SourceRef) => void;
  /** Remplir un trou depuis les valeurs proposées. */
  onRemplir?: (el: Element, valeur: string) => void;
}

function Dictee({ p, dictee, element }: { p: Preuve; dictee: string; element: Element }) {
  const src = p.source ?? element.sources.find((s) => s.kind === "dictee" && s.debut != null);
  const passage = src ? passageDictee(dictee, src) : null;
  return (
    <li className="space-y-1">
      <p className="text-[13.5px] font-medium leading-snug">{p.titre}</p>
      {p.detail && <p className="text-[13px] leading-relaxed text-[var(--mute)]">{p.detail}</p>}
      {passage ? (
        <p className="rounded-lg bg-[var(--paper)] px-3 py-2.5 text-[12.5px] leading-[1.7] text-[var(--mute)]" aria-label="Passage dans la dictée corrigée">
          {passage.avant}<mark className="rounded-[3px] bg-[var(--mark)] px-px text-[var(--ink)]">{passage.cite}</mark>{passage.apres}
        </p>
      ) : (
        src?.extrait && !p.detail.includes(src.extrait) && <blockquote className="text-[12.5px] italic text-[var(--mute)]">« {src.extrait} »</blockquote>
      )}
    </li>
  );
}

function Regle({ p }: { p: Preuve }) {
  const ambre = verdictAmbre(p.verdict);
  return (
    <li className="space-y-1">
      <p className="flex items-baseline gap-3 text-[13.5px] leading-snug">
        <span className="flex-1 font-medium">{p.titre}</span>
        {VERDICT[p.verdict] && <span className={`flex-none text-[12px] font-medium ${ambre ? "rounded bg-[var(--amber-soft)] px-1.5 py-px text-[var(--amber)]" : "text-[var(--mute)]"}`}>{VERDICT[p.verdict]}</span>}
      </p>
      {p.detail && <p className="text-[13px] leading-relaxed text-[var(--mute)]">{p.detail}</p>}
      {p.calcul && <p className="num text-[12.5px] text-[var(--ink)]">{p.calcul}</p>}
    </li>
  );
}

function Referentiel({ p, onConsulte }: { p: Preuve; onConsulte: Props["onConsulte"] }) {
  const s = p.source;
  return (
    <li className="space-y-1">
      {s ? <SourceLien source={s} onConsulte={onConsulte} /> : <p className="text-[13.5px] font-medium leading-snug">{p.titre}</p>}
      {p.detail && <p className="text-[13px] leading-relaxed text-[var(--mute)]">{p.detail}</p>}
    </li>
  );
}

/** Trou, Dictée : « non mentionné » et les termes cherchés (dans `calcul`). */
function DicteeTrou({ p }: { p: Preuve }) {
  const termes = p.calcul ? p.calcul.replace(/^\s*\d+\s+mentions?\s+trouv[ée]+s?\s+pour\s*:\s*/i, "") : null;
  const cherches = termes ? (/cherch/i.test(termes) ? termes : `Termes cherchés : ${termes}`) : null;
  return (
    <li className="space-y-1">
      <p className="text-[13.5px] font-medium leading-snug">{p.titre}</p>
      {p.detail && <p className="text-[13px] leading-relaxed text-[var(--mute)]">{p.detail}</p>}
      {cherches && <p className="text-[12.5px] leading-relaxed text-[var(--mute)]">{cherches}</p>}
    </li>
  );
}

/** Trou, Pourquoi c'est demandé : la condition, et la source si elle est seule à l'exiger. */
function ExigeTrou({ p, onConsulte }: { p: Preuve; onConsulte: Props["onConsulte"] }) {
  return (
    <li className="space-y-1">
      <p className="text-[13.5px] font-medium leading-snug">{p.titre}</p>
      {p.detail && <p className="text-[13px] leading-relaxed text-[var(--mute)]">{p.detail}</p>}
      {p.source && <SourceLien source={p.source} onConsulte={onConsulte} />}
    </li>
  );
}

function Modele({ p }: { p: Preuve }) {
  return (
    <li className="space-y-1">
      <p className="text-[13.5px] font-medium leading-snug">{p.titre}</p>
      {p.detail && <p className="text-[13px] leading-relaxed text-[var(--mute)]">{p.detail}</p>}
    </li>
  );
}

export default function OngletPourquoi({ local, element, onConsulte, onRemplir }: Props) {
  if (!element) {
    return (
      <div>
        <p className="px-5 pt-5 text-[13.5px] leading-relaxed text-[var(--mute)]">Cliquez sur une phrase du projet pour voir pourquoi elle est là : ce qui a été dicté, les règles appliquées, le référentiel cité.</p>
        <p className="label px-5 pt-6">Sources citées dans le projet</p>
        <OngletSources projet={local.projet} onConsulte={onConsulte} />
      </div>
    );
  }
  const trou = element.type === "trou";
  const groupes = trou ? parCategorie(preuvesTrou(element), TITRES_TROU) : parCategorie(preuvesDe(element));
  const formule = trou ? null : formuleConfiance(element);
  const etat = trou ? etatTrou(local, element) : null;
  const valeur = trou ? local.fills[element.id] : null;
  return (
    <div className="space-y-6 px-5 py-5" key={element.id}>
      <section className="enter" aria-label="Phrase sélectionnée">
        <p className="text-[15px] font-medium leading-snug">{texteElement(local, element)}</p>
        <p className="mt-1.5 text-[12.5px] text-[var(--mute)]">
          {trou ? (etat === "rempli" ? `Rempli : ${valeur}` : etat === "ignore" ? "Ignoré" : "À compléter") : STATUT[element.statut]}
          {!trou && <> · {NIVEAU[element.niveau]} <span className="num">({Math.round(element.confiance * 100)} %)</span></>}
        </p>
        {element.a_verifier && (
          <p className="mt-3 rounded-lg bg-[var(--amber-soft)] px-3 py-2.5 text-[13.5px] leading-snug text-[var(--ink)]">
            <span className="mr-1.5 font-semibold text-[var(--amber)]">À vérifier</span>{element.a_verifier}
          </p>
        )}
      </section>

      {groupes.length === 0 && <p className="text-[13px] leading-relaxed text-[var(--faint)]">Aucune justification enregistrée pour cet élément.</p>}
      {groupes.map((g) => (
        <section key={g.cle} className="enter" aria-label={g.titre}>
          <h3 className="label mb-2.5">{g.titre}</h3>
          <ul className="space-y-3.5">
            {g.preuves.map((p, i) =>
              g.cle === "dictee" ? (trou ? <DicteeTrou key={i} p={p} /> : <Dictee key={i} p={p} dictee={local.projet.dictee.corrigee} element={element} />)
              : g.cle === "regle" ? (trou ? <ExigeTrou key={i} p={p} onConsulte={onConsulte} /> : <Regle key={i} p={p} />)
              : g.cle === "referentiel" ? <Referentiel key={i} p={p} onConsulte={onConsulte} />
              : <Modele key={i} p={p} />)}
          </ul>
        </section>
      ))}

      {trou && onRemplir && element.options.length > 0 && (
        <section className="enter" aria-label="Valeurs proposées">
          <h3 className="label mb-2.5">Valeurs proposées</h3>
          <div className="flex flex-wrap gap-1.5">
            {element.options.map((o) => (
              <button key={o} type="button" className="btn btn-sm" aria-pressed={etat === "rempli" && valeur === o} onClick={() => onRemplir(element, o)}>{o}</button>
            ))}
          </div>
        </section>
      )}

      {formule && (
        <details className="group border-t border-[var(--line)] pt-3">
          <summary className="cursor-pointer text-[12px] text-[var(--faint)] hover:text-[var(--ink)]">Comment la confiance est calculée</summary>
          <p className="num mt-2 text-[12.5px] leading-relaxed text-[var(--mute)]">{formule}</p>
        </details>
      )}
      {!formule && !trou && <p className="num border-t border-[var(--line)] pt-3 text-[12px] text-[var(--faint)]">Confiance {nombre(element.confiance)}</p>}
    </div>
  );
}
