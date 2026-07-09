const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class VoiceApiError extends Error {}

export interface TranscribeResult {
  transcript: string;
  detectedLanguage: "en" | "kn" | null;
  requestId: string | null;
}

/**
 * Backend-mediated Sarvam Saaras v3 transcription (steering-docs/VOICE_INTAKE_STEERING.md
 * §3). The client never talks to Sarvam directly — the API key stays server-side.
 */
export async function transcribeAudio(
  blob: Blob,
  accessToken: string
): Promise<TranscribeResult> {
  const form = new FormData();
  form.append("audio_file", blob, "recording.webm");

  const res = await fetch(`${API_URL}/voice/transcribe`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: form,
  });

  if (!res.ok) {
    throw new VoiceApiError("Transcription failed");
  }

  const body = await res.json();
  return {
    transcript: body.transcript,
    detectedLanguage: body.detected_language ?? null,
    requestId: body.request_id ?? null,
  };
}
