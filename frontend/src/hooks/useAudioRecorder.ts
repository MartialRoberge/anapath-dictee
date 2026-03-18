import { useRef, useState, useCallback, useEffect } from "react";

export type RecorderState = "idle" | "recording" | "stopped";

export function useAudioRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [duration, setDuration] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);

  const startRecording = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;

    const audioCtx = new AudioContext();
    audioCtxRef.current = audioCtx;
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    analyserRef.current = analyser;

    const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    mediaRecorderRef.current = mediaRecorder;
    chunksRef.current = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    mediaRecorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      setAudioBlob(blob);
      stream.getTracks().forEach((t) => t.stop());
      if (timerRef.current) clearInterval(timerRef.current);
      audioCtx.close();
    };

    setDuration(0);
    setAudioBlob(null);
    timerRef.current = setInterval(() => setDuration((d) => d + 1), 1000);

    mediaRecorder.start();
    setState("recording");
  }, []);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
    setState("stopped");
  }, []);

  const reset = useCallback(() => {
    setAudioBlob(null);
    setDuration(0);
    setState("idle");
    analyserRef.current = null;
  }, []);

  const getAnalyser = useCallback(() => analyserRef.current, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      audioCtxRef.current?.close();
    };
  }, []);

  return { state, audioBlob, duration, startRecording, stopRecording, reset, getAnalyser };
}
