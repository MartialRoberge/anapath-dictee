// MARC v3 : application racine (auth, navigation, génération, historique local, télémétrie de session).
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import "./v3.css";
import AideRaccourcis from "./components/AideRaccourcis";
import LoginV3 from "./components/LoginV3";
import NouveauProjet from "./components/NouveauProjet";
import ProjetVue from "./components/ProjetVue";
import Sidebar from "./components/Sidebar";
import { useGeneration } from "./hooks/useGeneration";
import { useNotice } from "./hooks/useNotice";
import { useRecorder } from "./hooks/useRecorder";
import { useClavierVirtuel } from "./hooks/useTelephone";
import { genererAudio, genererTexte, iterer, modeDemo } from "./lib/api";
import * as H from "./lib/history";
import { creerLocal, fusionnerIteration, trousOuverts, type ProjetLocal } from "./lib/session";
import { ACTION, cleAlt, estChampSaisie } from "./lib/raccourcis";
import { track } from "./telemetry";
import type { Projet } from "./types";

const AdminLazy = lazy(() => import("./admin/AdminV3"));

type Vue = "nouveau" | "projet" | "admin";

export default function V3App() {
  const demo = modeDemo();
  const auth = useAuth();
  const user = demo ? { id: "demo", email: "demo@marc.local", name: "Dr Démonstration", role: "admin" } : auth.user;
  const [vue, setVue] = useState<Vue>("nouveau");
  const [local, setLocalBrut] = useState<ProjetLocal | null>(null);
  const [recents, setRecents] = useState<H.Recent[]>([]);
  const [brouillon, setBrouillon] = useState("");
  const [cleNouveau, setCleNouveau] = useState(0);
  const [navOuverte, setNavOuverte] = useState(false);
  const [aide, setAide] = useState(false);
  const { message, notifier } = useNotice();
  useClavierVirtuel();
  const source = useRef<"audio" | "texte">("texte");
  const localRef = useRef<ProjetLocal | null>(null);
  useEffect(() => { localRef.current = local; }, [local]);

  const rafraichir = useCallback(() => { void H.lister().then(setRecents); }, []);
  useEffect(rafraichir, [rafraichir]);

  // Toute modification est sauvegardée localement (jamais envoyée au serveur).
  const setLocal = useCallback((f: (l: ProjetLocal) => ProjetLocal) => {
    setLocalBrut((l) => {
      if (!l) return l;
      const n = f(l);
      void H.sauvegarder(n).then(rafraichir);
      return n;
    });
  }, [rafraichir]);

  const surProjet = useCallback((p: Projet, dureeMs: number, mode: "nouveau" | "iteration") => {
    const ancien = localRef.current;
    const n = mode === "iteration" && ancien ? fusionnerIteration(ancien, p) : creerLocal(p, source.current);
    setLocalBrut(n);
    setVue("projet");
    void H.sauvegarder(n).then(rafraichir);
    track(mode === "iteration" ? "projet_itere" : "projet_genere", {
      duree_ms: dureeMs, source: n.source, organes: p.contexte.organes, niveau_service: p.contexte.niveau_service,
      nb_elements: p.elements.length, nb_trous: trousOuverts(n), nb_alertes: p.alertes.length, nb_codes: p.codes.length,
      appels_llm: p.metriques.appels_llm, confiance_moyenne: Math.round(p.metriques.confiance_moyenne * 100),
    }, p.id);
  }, [rafraichir]);

  const gen = useGeneration({ onProjet: surProjet, onNonAutorise: () => { notifier("Session expirée."); auth.logout(); } });

  const lancerTexte = useCallback((texte: string) => {
    source.current = "texte";
    setBrouillon(texte);
    setLocalBrut(null);
    setVue("projet");
    void gen.executer((on, s) => genererTexte(texte, on, s), { mode: "nouveau", dictee: texte, audio: false });
  }, [gen]);

  const lancerAudio = useCallback((blob: Blob) => {
    source.current = "audio";
    setLocalBrut(null);
    setVue("projet");
    void gen.executer((on, s) => genererAudio(blob, on, s), { mode: "nouveau", audio: true });
  }, [gen]);

  const completer = useCallback((texte: string) => {
    const l = localRef.current;
    if (!l) return;
    void gen.executer((on, s) => iterer(l.projet, texte, on, s), { mode: "iteration", audio: false });
  }, [gen]);

  const micro = useRecorder(lancerAudio, notifier);
  const occupe = gen.etat.phase === "en_cours";
  const microActif = vue === "nouveau" && !occupe;

  // Maintien de la touche Espace = dictée (hors champs de saisie) ; Échap annule.
  useEffect(() => {
    if (!microActif) return;
    const editable = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
    const bas = (e: KeyboardEvent) => {
      if (e.code === "Escape" && micro.etat !== "repos") { micro.arreter(true); return; }
      if (e.code !== "Space" || e.repeat || editable(e.target) || e.metaKey || e.ctrlKey) return;
      e.preventDefault();
      void micro.demarrer();
    };
    const haut = (e: KeyboardEvent) => {
      if (e.code !== "Space" || editable(e.target)) return;
      e.preventDefault();
      if (micro.etat === "enregistre" || micro.etat === "demande") micro.arreter();
    };
    window.addEventListener("keydown", bas);
    window.addEventListener("keyup", haut);
    return () => { window.removeEventListener("keydown", bas); window.removeEventListener("keyup", haut); };
  }, [microActif, micro]);

  // Raccourcis globaux : ? (hors saisie) ou Alt+/ = aide ; Alt+N = nouveau projet ; Échap ferme tiroir et aide.
  const nouveauRef = useRef<(garder?: boolean) => void>(() => {});
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      const alt = cleAlt(e);
      if (alt === "Slash" || (e.key === "?" && !e.altKey && !e.ctrlKey && !e.metaKey && !estChampSaisie(e.target))) { e.preventDefault(); setAide((a) => !a); }
      else if (alt === "KeyN") { e.preventDefault(); nouveauRef.current(); }
      else if (e.key === "Escape") setNavOuverte(false);
    };
    const action = (e: Event) => { if ((e as CustomEvent).detail === "aide") setAide(true); };
    window.addEventListener("keydown", f);
    window.addEventListener(ACTION, action);
    return () => { window.removeEventListener("keydown", f); window.removeEventListener(ACTION, action); };
  }, []);

  // Temps de session actif (secondes, rien d'autre) envoyé quand l'onglet est quitté.
  useEffect(() => {
    let depuis = document.visibilityState === "visible" ? Date.now() : 0;
    const envoyer = () => { if (depuis) { track("session_temps", { secondes: Math.round((Date.now() - depuis) / 1000) }); depuis = 0; } };
    const vis = () => (document.visibilityState === "hidden" ? envoyer() : (depuis = Date.now()));
    document.addEventListener("visibilitychange", vis);
    window.addEventListener("pagehide", envoyer);
    return () => { document.removeEventListener("visibilitychange", vis); window.removeEventListener("pagehide", envoyer); envoyer(); };
  }, []);

  // `garder` : retour à la dictée après une erreur (le texte est conservé) ; sinon un nouveau projet repart d'une zone vide.
  const nouveau = useCallback((garder = false) => {
    gen.annuler();
    if (garder !== true) setBrouillon("");
    setLocalBrut(null);
    setVue("nouveau");
    setNavOuverte(false);
    setCleNouveau((k) => k + 1);
  }, [gen]);
  useEffect(() => { nouveauRef.current = nouveau; }, [nouveau]);

  const ouvrir = useCallback(async (id: string) => {
    gen.annuler();
    const l = await H.charger(id);
    if (l) { setLocalBrut(l); setVue("projet"); setNavOuverte(false); } else notifier("Projet introuvable sur cet appareil.");
  }, [gen, notifier]);

  if (!demo && auth.loading) return <div className="v3 coque" aria-busy="true" />;
  if (!user) return <div className="v3 coque"><LoginV3 onLogin={auth.login} onRegister={auth.register} /></div>;

  return (
    <div className="v3 coque">
      <a href="#contenu" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-[var(--card)] focus:p-2">Aller au contenu</a>
      <div className={`grid h-full grid-cols-1 grid-rows-[auto_minmax(0,1fr)] min-[900px]:grid-rows-1 ${vue === "projet" ? "min-[900px]:grid-cols-[208px_minmax(0,1fr)] min-[1180px]:grid-cols-[224px_minmax(0,1fr)_372px] min-[1360px]:grid-cols-[244px_minmax(0,1fr)_390px]" : "min-[900px]:grid-cols-[236px_minmax(0,1fr)] min-[1360px]:grid-cols-[252px_minmax(0,1fr)]"}`}>
        <header className="barre col-span-full flex items-center gap-3 border-b-0 px-4 py-1 min-[900px]:hidden">
          <button type="button" className="btn" aria-expanded={navOuverte} aria-controls="navigation-v3" onClick={() => setNavOuverte(true)}>Menu</button>
          <span className="text-[13px] font-semibold tracking-[0.18em]">MARC</span>
        </header>
        {navOuverte && <button type="button" className="scrim min-[900px]:hidden" aria-label="Fermer le menu" tabIndex={-1} onClick={() => setNavOuverte(false)} />}
        <div id="navigation-v3" className="tiroir-g min-h-0" data-ouvert={navOuverte}>
        <Sidebar
          recents={recents} courantId={local?.projet.id ?? null} vue={vue} nom={user.name} admin={user.role === "admin"} demo={demo}
          onNouveau={() => nouveau()} onOuvrir={ouvrir} onAdmin={() => { gen.annuler(); setVue("admin"); setNavOuverte(false); }} onDeconnexion={auth.logout}
          onAide={() => { setNavOuverte(false); setAide(true); }} onFermer={() => setNavOuverte(false)}
          onSupprimer={async (id) => { await H.supprimer(id); if (local?.projet.id === id) nouveau(); rafraichir(); }}
          onPurger={async () => { await H.purger(); rafraichir(); if (vue === "projet" && !occupe) nouveau(); notifier("Historique local supprimé"); }}
        />
        </div>
        <main id="contenu" tabIndex={-1} className={`outline-none ${vue === "projet" ? "contents" : "min-h-0 min-w-0 overflow-hidden"}`}>
          {vue === "nouveau" && (
            <div key={cleNouveau} className="flex h-full min-h-0 flex-col">
              <NouveauProjet occupe={occupe} nom={user.name} etatMicro={micro.etat} secondes={micro.secondes} brouillonInitial={brouillon}
                onBasculerMicro={micro.basculer} onAnnulerMicro={() => micro.arreter(true)} onTexte={lancerTexte} />
            </div>
          )}
          {vue === "projet" && (
            <ProjetVue key={local?.projet.id ?? "nouveau"} local={local} setLocal={setLocal} generation={gen.etat} onReessayer={gen.reessayer} onAnnuler={gen.annuler} onNouveau={() => nouveau(true)}
              onCompleter={completer} onNotifier={notifier} />
          )}
          {vue === "admin" && (
            <Suspense fallback={<p className="p-10 text-[15px] text-[var(--mute)]">Chargement…</p>}><AdminLazy /></Suspense>
          )}
        </main>
      </div>
      {aide && <AideRaccourcis onFermer={() => setAide(false)} />}
      <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-0 bottom-[max(24px,env(safe-area-inset-bottom))] z-[80] flex justify-center px-4">
        {message && <p className="enter max-w-full rounded-full bg-[var(--ink)] px-4 py-2.5 text-center text-[15px] text-[var(--on-ink)] shadow-lg">{message}</p>}
      </div>
    </div>
  );
}
