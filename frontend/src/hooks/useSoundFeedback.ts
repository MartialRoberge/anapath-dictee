import { useCallback, useRef, useState } from "react";

const MUTE_KEY = "marc_sound_muted";

/**
 * Retour sonore MARC — volontairement discret.
 * - Deux evenements seulement : debut de dictee + compte-rendu pret.
 * - Volume tres bas ; plus aucun bip d'etape intermediaire.
 * - Reglage muet persistant (localStorage), coupe par defaut si l'utilisateur
 *   l'a choisi une fois.
 */
export function useSoundFeedback() {
  const ctxRef = useRef<AudioContext | null>(null);
  const [muted, setMuted] = useState<boolean>(
    () => localStorage.getItem(MUTE_KEY) === "1"
  );

  const getCtx = useCallback(() => {
    if (!ctxRef.current) ctxRef.current = new AudioContext();
    return ctxRef.current;
  }, []);

  const playTone = useCallback(
    (freq: number, durationMs: number, type: OscillatorType = "sine", vol = 0.04) => {
      if (localStorage.getItem(MUTE_KEY) === "1") return;
      const ctx = getCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(vol, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + durationMs / 1000);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + durationMs / 1000);
    },
    [getCtx],
  );

  // Debut de dictee — une note breve et douce.
  const playStart = useCallback(() => {
    playTone(880, 90, "sine", 0.05);
  }, [playTone]);

  // Compte-rendu pret — accord discret a deux notes.
  const playAllDone = useCallback(() => {
    playTone(784, 90, "sine", 0.045);
    setTimeout(() => playTone(1046, 110, "sine", 0.045), 110);
  }, [playTone]);

  const toggleMuted = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      localStorage.setItem(MUTE_KEY, next ? "1" : "0");
      return next;
    });
  }, []);

  return { playStart, playAllDone, muted, toggleMuted };
}
