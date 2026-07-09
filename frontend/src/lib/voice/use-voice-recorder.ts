"use client";

import { useCallback, useRef, useState } from "react";
import { transcribeAudio, VoiceApiError } from "./voice-api";

export type VoiceRecorderStatus = "idle" | "recording" | "processing";

/** Hard cap per steering-docs/VOICE_INTAKE_STEERING.md §2 — auto-stop and submit at 60s. */
const MAX_RECORDING_MS = 60_000;

interface UseVoiceRecorderOptions {
  accessToken: string | undefined;
  onTranscript: (transcript: string, detectedLanguage: "en" | "kn" | null) => void;
}

/**
 * Client-side mic capture -> upload -> transcript state machine
 * (steering-docs/VOICE_INTAKE_STEERING.md §2). States: idle -> recording ->
 * processing -> idle. The captured blob is never cached — it's discarded
 * immediately after the upload settles, win or lose.
 */
export function useVoiceRecorder({ accessToken, onTranscript }: UseVoiceRecorderOptions) {
  const [status, setStatus] = useState<VoiceRecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const finishRecording = useCallback(
    async (recorder: MediaRecorder) => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      chunksRef.current = [];
      recorder.stream.getTracks().forEach((track) => track.stop());

      if (!accessToken) {
        setStatus("idle");
        setError("You must be signed in to use voice input.");
        return;
      }

      setStatus("processing");
      try {
        const result = await transcribeAudio(blob, accessToken);
        setStatus("idle");
        onTranscript(result.transcript, result.detectedLanguage);
      } catch (err) {
        setStatus("idle");
        setError(
          err instanceof VoiceApiError
            ? "Transcription failed — please retype or try again."
            : "Something went wrong — please retype or try again."
        );
      }
    },
    [accessToken, onTranscript]
  );

  const start = useCallback(async () => {
    setError(null);

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone access denied. You can still type your question.");
      return;
    }

    const recorder = new MediaRecorder(stream);
    mediaRecorderRef.current = recorder;
    chunksRef.current = [];

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      if (stopTimerRef.current) {
        clearTimeout(stopTimerRef.current);
        stopTimerRef.current = null;
      }
      void finishRecording(recorder);
    };

    recorder.start();
    setStatus("recording");

    stopTimerRef.current = setTimeout(() => {
      if (recorder.state === "recording") recorder.stop();
    }, MAX_RECORDING_MS);
  }, [finishRecording]);

  const stop = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state === "recording") {
      recorder.stop();
    }
  }, []);

  const toggle = useCallback(() => {
    if (status === "idle") void start();
    else if (status === "recording") stop();
  }, [status, start, stop]);

  return { status, error, toggle };
}
