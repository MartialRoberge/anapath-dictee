// Vue projet à trois zones : document au centre, raisonnement à droite, actions en bas du centre.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EtatGeneration } from "../hooks/useGeneration";
import { exporterDocx, telecharger } from "../lib/api";
import { copierProjet, copierTexte } from "../lib/copy";
import * as S from "../lib/session";
import { cleAlt, declencher } from "../lib/raccourcis";
import { focaliserTrou } from "../lib/format";
import { trackAlerte, trackCode, trackEdition, trackSource, trackTrou } from "../lib/track";
import { track } from "../telemetry";
import type { Alerte, Code, Correction, Element, SourceRef } from "../types";
import ConsultationSource from "./Source";
import BandeauService from "./BandeauService";
import BandeauAlerte from "./BandeauAlerte";
import BarreActions, { Feedback } from "./BarreActions";
import FeuilleSignalement from "./FeuilleSignalement";
import type { CategorieSignalement } from "../lib/signalement";
import Document from "./Document";
import EtatCentre from "./EtatCentre";
import { useMedia, useTelephone } from "../hooks/useTelephone";
import PanneauRaisonnement, { ORDRE_ONGLETS, type NomOnglet } from "./PanneauRaisonnement";

interface Props {
  local: S.ProjetLocal | null;
  setLocal: (f: (l: S.ProjetLocal) => S.ProjetLocal) => void;
  generation: EtatGeneration;
  onReessayer: () => void;
  onAnnuler: () => void;
  onNouveau: () => void;
  onCompleter: (texte: string) => void;
  onNotifier: (m: string) => void;
}

const generationActive = (g: EtatGeneration) => g.phase !== "inactif";

export default function ProjetVue({ local, setLocal, generation, onReessayer, onAnnuler, onNouveau, onCompleter, onNotifier }: Props) {
  const [signalement, setSignalement] = useState<CategorieSignalement | null>(null);
  const [onglet, setOnglet] = useState<NomOnglet>(() => (local && !generationActive(generation) && S.alertesOuvertes(local).length ? "alertes" : "progression"));
  const [selection, setSelection] = useState<string | null>(null);
  const [alerteActive, setAlerteActive] = useState<string | null>(null);
  const [correctionActive, setCorrectionActive] = useState<string | null>(null);
  const [exportEnCours, setExportEnCours] = useState(false);
  const [tiroir, setTiroir] = useState(false);
  const [sourceOuverte, setSourceOuverte] = useState<SourceRef | null>(null);
  const focusFait = useRef(false);
  const occupe = generation.phase !== "inactif";
  const precedente = useRef(generation.phase);
  const centre = useRef<HTMLDivElement>(null);
  const tel = useTelephone();
  const paysage = useMedia("(max-height: 500px) and (max-width: 940px)");

  // Pendant le traitement : Progression ; à la fin : « À vérifier » s'il reste des points.
  useEffect(() => {
    if (generation.phase === "en_cours" && precedente.current !== "en_cours") setOnglet("progression");
    if (precedente.current === "en_cours" && generation.phase === "inactif" && local) setOnglet(S.alertesOuvertes(local).length ? "alertes" : "progression");
    precedente.current = generation.phase;
  }, [generation.phase, local]);

  const element = useMemo(() => local?.projet.elements.find((e) => e.id === selection) ?? null, [local, selection]);
  const surlignes = useMemo(() => local?.projet.alertes.find((a) => a.id === alerteActive)?.element_ids ?? [], [local, alerteActive]);
  const etapes = occupe || !local ? generation.etapes : local.projet.trace;
  const maj = useCallback((f: (l: S.ProjetLocal) => S.ProjetLocal) => setLocal(f), [setLocal]);

  // Sélectionner une phrase ouvre « Pourquoi », sauf si la dictée est déjà ouverte (elle y surligne le passage de l'élément).
  const choisir = (id: string | null) => {
    setSelection(id);
    if (id && onglet !== "dictee") setOnglet("pourquoi");
  };

  const defiler = (id: string) =>
    document.querySelector(`[data-eid="${id}"]`)?.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });

  const activerAlerte = (a: Alerte) => {
    const deja = alerteActive === a.id;
    setAlerteActive(deja ? null : a.id);
    if (!deja && a.element_ids[0]) defiler(a.element_ids[0]);
  };

  const RANG = { bloquant: 0, attention: 1, info: 2 } as const;
  const ordreAlertes = useMemo(() => (local ? S.alertesOuvertes(local).slice().sort((a, b) => RANG[a.gravite] - RANG[b.gravite]) : []), [local]);
  const nTrous = local ? S.trousOuverts(local) : 0;
  const alerte = local?.projet.alertes.find((a) => a.id === alerteActive) ?? null;
  const alerteOuverte = alerte && local && !local.alertes[alerte.id] ? alerte : null;

  const decider = (a: Alerte, d: S.DecisionAlerte | null) => {
    if (!local) return;
    maj((l) => S.decider(l, a.id, d));
    if (d) {
      trackAlerte(a, d === "resolue", local.projet.id);
      // Enchaînement : après un traitement, le point suivant devient actif (un geste par point).
      const reste = ordreAlertes.filter((x) => x.id !== a.id);
      const apres = reste.find((x) => RANG[x.gravite] >= RANG[a.gravite]) ?? reste[0] ?? null;
      setAlerteActive(apres ? apres.id : null);
      if (apres?.element_ids[0]) defiler(apres.element_ids[0]);
    }
  };
  const copier = async () => {
    if (!local) return;
    const ok = await copierProjet(local);
    const t = S.trousOuverts(local);
    onNotifier(ok ? `Projet copié, mise en forme Word incluse${t ? ` · ${t} trou${t > 1 ? "s" : ""} à compléter` : ""}` : "Copie impossible : autorisez le presse-papiers.");
    if (ok) track("export", { format: "copie", trous_ouverts: t, alertes_ouvertes: S.alertesOuvertes(local).length }, local.projet.id);
  };
  const exporter = async () => {
    if (!local || exportEnCours || occupe) return;
    setExportEnCours(true);
    try {
      telecharger(await exporterDocx(local), "projet-compte-rendu.docx");
      track("export", { format: "docx", trous_ouverts: S.trousOuverts(local), alertes_ouvertes: S.alertesOuvertes(local).length }, local.projet.id);
      onNotifier("Fichier DOCX exporté");
    } catch (e) {
      onNotifier(e instanceof Error ? e.message : "Export impossible.");
    } finally {
      setExportEnCours(false);
    }
  };

  // Au premier affichage d'un projet prêt : le focus va au premier trou ouvert (Tab enchaîne ensuite).
  useEffect(() => {
    if (!local || occupe || focusFait.current) return;
    focusFait.current = true;
    const id = S.trouSuivant(local, null, 1);
    if (id) requestAnimationFrame(() => focaliserTrou(id));
  }, [local, occupe]);

  // Raccourcis du projet (Alt + touche physique). Voir lib/raccourcis.ts.
  const sc = useRef({ ordreAlertes, alerteOuverte, decider, copier, exporter, activerAlerte });
  sc.current = { ordreAlertes, alerteOuverte, decider, copier, exporter, activerAlerte };
  useEffect(() => {
    if (!local) return;
    const noms = ORDRE_ONGLETS;
    const f = (e: KeyboardEvent) => {
      const k = cleAlt(e);
      if (!k) { if (e.key === "Escape") setTiroir(false); return; }
      const c = sc.current;
      if (k === "ArrowDown" || k === "ArrowUp") {
        if (!c.ordreAlertes.length) return;
        e.preventDefault();
        const i = c.alerteOuverte ? c.ordreAlertes.findIndex((a) => a.id === c.alerteOuverte!.id) : -1;
        const n = c.ordreAlertes.length;
        const suiv = c.ordreAlertes[k === "ArrowDown" ? (i + 1) % n : (i - 1 + n) % n];
        setOnglet("alertes");
        setAlerteActive(suiv.id);
        if (suiv.element_ids[0]) defiler(suiv.element_ids[0]);
      } else if (k === "KeyR" || k === "KeyI") {
        e.preventDefault();
        const a = c.alerteOuverte ?? c.ordreAlertes[0];
        if (a) c.decider(a, k === "KeyR" ? "resolue" : "ignoree");
      } else if (/^Digit[1-5]$/.test(k)) { e.preventDefault(); setOnglet(noms[Number(k.slice(5)) - 1]); setTiroir(true); }
      else if (k === "KeyC") { e.preventDefault(); void c.copier(); }
      else if (k === "KeyX") { e.preventDefault(); void c.exporter(); }
      else if (k === "KeyV") { e.preventDefault(); declencher("valider"); }
      else if (k === "KeyM") { e.preventDefault(); declencher("completer"); }
    };
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [local]);

  if (!local || (occupe && generation.mode === "nouveau")) {
    return (
      <>
        <div className="scroll min-h-0 overflow-y-auto px-8 pb-10"><EtatCentre etat={generation} onReessayer={onReessayer} onAnnuler={onAnnuler} onNouveau={onNouveau} /></div>
        <div className="tiroir-d min-h-0" data-ouvert={tiroir}>
          <PanneauRaisonnement {...vide} onglet={onglet} onOnglet={setOnglet} local={null} generation={generation} etapes={etapes} element={null}
            alerteActive={null} correctionActive={null} onNotifier={onNotifier} onFermer={() => setTiroir(false)} />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="flex min-h-0 min-w-0 flex-col" ref={centre}>
        {tel && paysage ? null : tel ? (
          <div className="flex items-center gap-3 border-b-[0.5px] border-[var(--line)] py-1 pl-4 pr-2">
            <p className="num min-w-0 flex-1 text-[13px] text-[var(--mute)]" role="status">
              {nTrous > 0 ? <b className="font-semibold text-[var(--amber)]">{nTrous} à compléter</b> : "Aucun trou"}
              <span aria-hidden> · </span>
              {ordreAlertes.length > 0 ? <b className="font-semibold text-[var(--ink)]">{ordreAlertes.length} à vérifier</b> : "rien à vérifier"}
            </p>
            <button type="button" className="btn btn-ghost shrink-0" aria-expanded={tiroir} aria-controls="panneau-raisonnement" onClick={() => setTiroir(true)}>Raisonnement</button>
          </div>
        ) : (
        <div className="flex items-center gap-3 border-b-[0.5px] border-[var(--line)] px-4 py-2 min-[1180px]:hidden">
          <button type="button" className="btn btn-sm" aria-expanded={tiroir} aria-controls="panneau-raisonnement" onClick={() => setTiroir(true)}>
            Raisonnement <span className="num text-[var(--faint)]">{ordreAlertes.length > 0 ? `· ${ordreAlertes.length} à vérifier` : "· pourquoi, codes, dictée"}</span>
          </button>
        </div>
        )}
        <div className="scroll doc-defile min-h-0 flex-1 overflow-y-auto px-6 py-6" onClick={(e) => { if (e.target === e.currentTarget) choisir(null); }}>
          <div className="mx-auto max-w-[800px]">
            {occupe && generation.mode === "iteration" && (
              <p role="status" className="enter carte mb-4 px-4 py-3 text-[15px] text-[var(--mute)]">
                Intégration du complément en cours… Le projet reste modifiable.
                <button type="button" className="ml-3 underline underline-offset-2 hover:text-[var(--ink)]" onClick={onAnnuler}>Annuler</button>
              </p>
            )}
            {generation.phase === "erreur" && (
              <p role="alert" className="mb-4 rounded-xl bg-[var(--red-soft)] px-4 py-3 text-[15px] text-[var(--red)]">
                {generation.erreur?.message} <button type="button" className="ml-2 underline underline-offset-2" onClick={onReessayer}>Réessayer</button>
              </p>
            )}
            <BandeauService niveau={local.projet.contexte.niveau_service} />
            <div className="feuille doc-feuille px-6 py-8 sm:px-12 sm:py-10">
            <Document
              local={local} selection={selection} surlignes={surlignes} onSelect={choisir}
              onTitre={(t) => maj((l) => S.editerTitre(l, t))}
              onEdit={(el, avant, apres, n) => { maj((l) => S.editerElement(l, el.id, apres)); trackEdition(el, avant, apres, n, local.projet.id); }}
              onRemplir={(el, v) => { maj((l) => S.remplirTrou(l, el.id, v)); trackTrou(el, true, local.projet.id); }}
              onIgnorer={(el) => { maj((l) => S.ignorerTrou(l, el.id)); trackTrou(el, false, local.projet.id); }}
              onRouvrir={(el: Element) => maj((l) => S.rouvrirTrou(l, el.id))}
            />
            </div>
            <div className="mt-3 flex items-center gap-2 px-1 text-[13px] text-[var(--mute)]">
              <span>Ce projet vous a-t-il aidé ?</span>
              <Feedback local={local} onDetailler={() => setSignalement("amelioration")} onFeedback={(sens, motif) => { maj((l) => S.donnerFeedback(l, sens, motif)); track("feedback", { sens, motif }, local.projet.id); }} />
            </div>
          </div>
        </div>
        {alerteOuverte && <BandeauAlerte alerte={alerteOuverte} reste={ordreAlertes.length} onDecider={decider} />}
        <BarreActions
          local={local} occupe={occupe} exportEnCours={exportEnCours} onNotifier={onNotifier} onCompleter={onCompleter}
          onCopier={copier} onExporter={exporter}
          onSignaler={() => setSignalement("dysfonctionnement")}
          paysage={tel && paysage ? { onRaisonnement: () => setTiroir(true), ouvert: tiroir } : undefined}
        />
      </div>
      {tiroir && <button type="button" className="scrim min-[1180px]:hidden" aria-label="Fermer le panneau Raisonnement" tabIndex={-1} onClick={() => setTiroir(false)} />}
      <div className="tiroir-d min-h-0" data-ouvert={tiroir}>
        <PanneauRaisonnement
          onFermer={() => setTiroir(false)}
          onglet={onglet} onOnglet={setOnglet} local={local} generation={generation} etapes={etapes} element={element}
          alerteActive={alerteActive} correctionActive={correctionActive} onAlerte={activerAlerte}
          onDecider={decider}
          onCorrectionActive={setCorrectionActive}
          onDecision={(c: Correction, choix) => { maj((l) => S.decisionCorrection(l, c.id, choix)); track(choix === "original" ? "correction_rejetee" : "correction_acceptee", { confiance: Math.round(c.confiance * 100), candidat: choix !== "original" && choix !== c.corrige }, local.projet.id); }}
          onCopieCode={async (c: Code, texte) => { onNotifier((await copierTexte(texte)) ? "Code copié" : "Copie impossible"); trackCode("code_copie", c, local.projet.id); }}
          onModifierCode={(c, n) => { maj((l) => S.modifierCode(l, c, n)); trackCode("code_modifie", c, local.projet.id); }}
          onConsulte={(s) => { trackSource(s, local.projet.id); setSourceOuverte(s); }}
          onRemplir={(el, v) => { maj((l) => S.remplirTrou(l, el.id, v)); trackTrou(el, true, local.projet.id); }}
          onNotifier={onNotifier} onDocument={() => { setTiroir(false); centre.current?.querySelector<HTMLElement>("[data-nav]")?.focus(); }}
        />
      </div>
      {signalement && <FeuilleSignalement categorieInitiale={signalement} projetId={local.projet.id} ecran="projet" onFermer={() => setSignalement(null)} />}
      {sourceOuverte && <ConsultationSource source={sourceOuverte} onFermer={() => setSourceOuverte(null)} />}
    </>
  );
}

// Rappels vides pour le panneau avant que le projet n'existe.
const noop = () => {};
const vide = {
  onAlerte: noop, onDecider: noop, onCorrectionActive: noop, onDecision: noop, onCopieCode: noop, onModifierCode: noop, onConsulte: noop, onDocument: noop,
};
