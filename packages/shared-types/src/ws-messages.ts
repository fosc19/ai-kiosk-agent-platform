import { z } from 'zod';

// ============================================================
// WebSocket Message Types - Pi ↔ VPS
// ============================================================

export enum MessageType {
  // Pi → VPS
  SESSION_START = 'session.start',
  CAMERA_FRAME = 'camera.frame',
  AUDIO_UTTERANCE = 'audio.utterance',
  AUDIO_CHUNK = 'audio.chunk', // F3: streaming audio chunks
  USER_TEXT = 'user.text',
  CONTROL_STOP_TTS = 'control.stop_tts',
  PLAYBACK_COMPLETE = 'playback.complete', // F3: TTS playback finished

  // VPS → Pi
  PRESENCE_UPDATE = 'presence.update',
  UI_STATE = 'ui.state',
  UI_SAY = 'ui.say',
  TTS_CHUNK = 'tts.chunk',
  UI_ROUTE = 'ui.route',
  CONTROL_STOP_AUDIO = 'control.stop_audio',
  VAD_END_OF_SPEECH = 'vad.end_of_speech', // F3: VAD detected end of speech
  ASR_TRANSCRIPT = 'asr.transcript', // F3: ASR transcription result
}

export enum UIState {
  IDLE = 'idle',
  LISTENING = 'listening',
  THINKING = 'thinking',
  SPEAKING = 'speaking',
  GUIDING = 'guiding',
}

// ============================================================
// Pi → VPS Messages
// ============================================================

export const SessionStartSchema = z.object({
  type: z.literal(MessageType.SESSION_START),
  payload: z.object({
    kiosk_id: z.string(),
    device_info: z.object({
      model: z.string(),
      os: z.string(),
      ip: z.string().optional(),
    }),
    language: z.string().default('es'),
  }),
});
export type SessionStartMessage = z.infer<typeof SessionStartSchema>;

export const CameraFrameSchema = z.object({
  type: z.literal(MessageType.CAMERA_FRAME),
  payload: z.object({
    image_data: z.string(), // JPEG base64
    timestamp: z.number(),
  }),
});
export type CameraFrameMessage = z.infer<typeof CameraFrameSchema>;

export const AudioUtteranceSchema = z.object({
  type: z.literal(MessageType.AUDIO_UTTERANCE),
  payload: z.object({
    session_id: z.string(),
    turn_id: z.string(),
    audio_data: z.string(), // base64 PCM WAV
    sample_rate: z.number().default(16000),
  }),
});
export type AudioUtteranceMessage = z.infer<typeof AudioUtteranceSchema>;

export const UserTextSchema = z.object({
  type: z.literal(MessageType.USER_TEXT),
  payload: z.object({
    session_id: z.string(),
    text: z.string(),
  }),
});
export type UserTextMessage = z.infer<typeof UserTextSchema>;

export const ControlStopTTSSchema = z.object({
  type: z.literal(MessageType.CONTROL_STOP_TTS),
  payload: z.object({
    reason: z.enum(['barge_in', 'manual']),
  }),
});
export type ControlStopTTSMessage = z.infer<typeof ControlStopTTSSchema>;

// F3: Audio chunk for streaming
export const AudioChunkSchema = z.object({
  type: z.literal(MessageType.AUDIO_CHUNK),
  payload: z.object({
    session_id: z.string(),
    turn_id: z.string(),
    chunk_data: z.string(), // base64 PCM WAV 16kHz mono
    chunk_index: z.number(),
    sample_rate: z.number().optional().default(16000),
  }),
});
export type AudioChunkMessage = z.infer<typeof AudioChunkSchema>;

// F3: Playback complete notification
export const PlaybackCompleteSchema = z.object({
  type: z.literal(MessageType.PLAYBACK_COMPLETE),
  payload: z.object({
    turn_id: z.string(),
  }),
});
export type PlaybackCompleteMessage = z.infer<typeof PlaybackCompleteSchema>;

// ============================================================
// VPS → Pi Messages
// ============================================================

export const PresenceUpdateSchema = z.object({
  type: z.literal(MessageType.PRESENCE_UPDATE),
  payload: z.object({
    present: z.boolean(),
    look_direction: z.number().min(-1).max(1), // -1 (left), 0 (center), 1 (right)
    confidence: z.number().min(0).max(1),
  }),
});
export type PresenceUpdateMessage = z.infer<typeof PresenceUpdateSchema>;

export const UIStateSchema = z.object({
  type: z.literal(MessageType.UI_STATE),
  payload: z.object({
    state: z.nativeEnum(UIState),
  }),
});
export type UIStateMessage = z.infer<typeof UIStateSchema>;

export const UISaySchema = z.object({
  type: z.literal(MessageType.UI_SAY),
  payload: z.object({
    text: z.string(),
    turn_id: z.string(),
  }),
});
export type UISayMessage = z.infer<typeof UISaySchema>;

export const TTSChunkSchema = z.object({
  type: z.literal(MessageType.TTS_CHUNK),
  payload: z.object({
    audio_data: z.string(), // base64 MP3/WAV chunk
    chunk_index: z.number(),
    total_chunks: z.number().optional(), // deprecated: use is_last instead
    is_last: z.boolean().optional().default(false), // true if this is the final chunk
    turn_id: z.string(),
  }),
});
export type TTSChunkMessage = z.infer<typeof TTSChunkSchema>;

export const UIRouteSchema = z.object({
  type: z.literal(MessageType.UI_ROUTE),
  payload: z.object({
    store_id: z.string(),
    store_name: z.string(),
    steps: z.array(
      z.object({
        instruction: z.string(),
        direction: z.enum(['left', 'right', 'straight', 'arrive']),
        distance: z.number().optional(),
      })
    ),
  }),
});
export type UIRouteMessage = z.infer<typeof UIRouteSchema>;

export const ControlStopAudioSchema = z.object({
  type: z.literal(MessageType.CONTROL_STOP_AUDIO),
  payload: z.object({}),
});
export type ControlStopAudioMessage = z.infer<typeof ControlStopAudioSchema>;

// F3: VAD end of speech notification
export const VADEndOfSpeechSchema = z.object({
  type: z.literal(MessageType.VAD_END_OF_SPEECH),
  payload: z.object({
    turn_id: z.string(),
    speech_duration_ms: z.number(),
  }),
});
export type VADEndOfSpeechMessage = z.infer<typeof VADEndOfSpeechSchema>;

// F3: ASR transcript result
export const ASRTranscriptSchema = z.object({
  type: z.literal(MessageType.ASR_TRANSCRIPT),
  payload: z.object({
    text: z.string(),
    turn_id: z.string(),
    is_final: z.boolean(),
    confidence: z.number().optional(),
  }),
});
export type ASRTranscriptMessage = z.infer<typeof ASRTranscriptSchema>;

// ============================================================
// Union Types
// ============================================================

export const PiToVPSMessageSchema = z.discriminatedUnion('type', [
  SessionStartSchema,
  CameraFrameSchema,
  AudioUtteranceSchema,
  AudioChunkSchema,
  UserTextSchema,
  ControlStopTTSSchema,
  PlaybackCompleteSchema,
]);
export type PiToVPSMessage = z.infer<typeof PiToVPSMessageSchema>;

export const VPSToPiMessageSchema = z.discriminatedUnion('type', [
  PresenceUpdateSchema,
  UIStateSchema,
  UISaySchema,
  TTSChunkSchema,
  UIRouteSchema,
  ControlStopAudioSchema,
  VADEndOfSpeechSchema,
  ASRTranscriptSchema,
]);
export type VPSToPiMessage = z.infer<typeof VPSToPiMessageSchema>;

export type WSMessage = PiToVPSMessage | VPSToPiMessage;
