import { useCallback, useRef } from "react";

export function useSoundFeedback() {
  const ctxRef = useRef<AudioContext | null>(null);

  const getCtx = useCallback(() => {
    if (!ctxRef.current) ctxRef.current = new AudioContext();
    return ctxRef.current;
  }, []);

  const playTone = useCallback(
    (freq: number, durationMs: number, type: OscillatorType = "sine", vol = 0.12) => {
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

  const playStart = useCallback(() => {
    playTone(880, 120, "sine");
    setTimeout(() => playTone(1320, 100, "sine"), 80);
  }, [playTone]);

  const playStop = useCallback(() => {
    playTone(660, 150, "sine");
  }, [playTone]);

  const playStepDone = useCallback(() => {
    playTone(1046, 80, "sine", 0.06);
  }, [playTone]);

  const playAllDone = useCallback(() => {
    playTone(784, 100, "sine", 0.08);
    setTimeout(() => playTone(1046, 100, "sine", 0.08), 100);
    setTimeout(() => playTone(1318, 120, "sine", 0.08), 200);
  }, [playTone]);

  return { playStart, playStop, playStepDone, playAllDone };
}
