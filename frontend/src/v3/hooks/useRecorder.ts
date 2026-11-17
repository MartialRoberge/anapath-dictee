// Enregistreur vocal (MediaRecorder). Maintien de la touche Espace = push-to-talk ; bouton = bascule.
import { useCallback, useEffect, useRef, useState } from "react";

export type EtatMicro = "repos" | "demande" | "enregistre";

const MIN_MS = 700; // en dessous : appui accidentel, rien n'est envoyé

function typeMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((t) => MediaRecorder.isTypeSupported(t));
}

export function useRecorder(onFin: (blob: Blob) => void, onErreur: (message: string) => void) {
  const [etat, setEtat] = useState<EtatMicro>("repos");
  const [secondes, setSecondes] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const flux = useRef<MediaStream | null>(null);
  const morceaux = useRef<Blob[]>([]);
  const t0 = useRef(0);
  const minuteur = useRef<ReturnType<typeof setInterval> | null>(null);
  const annule = useRef(false);
  const voulu = useRef(false); // l'utilisateur veut enregistrer (utile si le relâchement précède l'autorisation micro)

  const nettoyer = () => {
    if (minuteur.current) clearInterval(minuteur.current);
    minuteur.current = null;
    flux.current?.getTracks().forEach((t) => t.stop());
    flux.current = null;
  };

  const arreter = useCallback((abandon = false) => {
    voulu.current = false;
    annule.current = abandon;
    if (rec.current && rec.current.state !== "inactive") rec.current.stop();
    else {
      nettoyer();
      setEtat("repos");
    }
  }, []);

  const demarrer = useCallback(async () => {
    if (rec.current && rec.current.state === "recording") return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      onErreur("L'enregistrement n'est pas pris en charge par ce navigateur. Collez ou tapez la dictée.");
      return;
    }
    voulu.current = true;
    setEtat("demande");
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!voulu.current) {
        s.getTracks().forEach((t) => t.stop());
        setEtat("repos");
        return;
      }
      flux.current = s;
      const mime = typeMime();
      const r = new MediaRecorder(s, mime ? { mimeType: mime } : undefined);
      rec.current = r;
      morceaux.current = [];
      annule.current = false;
      r.ondataavailable = (e) => e.data.size > 0 && morceaux.current.push(e.data);
      r.onstop = () => {
        const duree = Date.now() - t0.current;
        const blob = new Blob(morceaux.current, { type: r.mimeType || mime || "audio/webm" });
        nettoyer();
        setEtat("repos");
        setSecondes(0);
        rec.current = null;
        if (annule.current) return;
        if (duree < MIN_MS) onErreur("Enregistrement trop court. Maintenez la touche Espace pendant que vous dictez.");
        else onFin(blob);
      };
      t0.current = Date.now();
      setSecondes(0);
      minuteur.current = setInterval(() => setSecondes(Math.floor((Date.now() - t0.current) / 1000)), 250);
      r.start();
      setEtat("enregistre");
    } catch {
      voulu.current = false;
      setEtat("repos");
      onErreur("Accès au micro refusé. Autorisez le micro dans le navigateur, ou collez le texte.");
    }
  }, [onFin, onErreur]);

  useEffect(() => () => { annule.current = true; nettoyer(); }, []);

  return { etat, secondes, demarrer, arreter, basculer: () => (etat === "enregistre" ? arreter() : void demarrer()) };
}
