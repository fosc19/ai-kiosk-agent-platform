import { writable } from 'svelte/store';

export interface SessionState {
  session_id: string | null;
  turn_id: string | null;
  language: string;
}

export const session = writable<SessionState>({
  session_id: null,
  turn_id: null,
  language: 'es',
});

export function generateTurnId(): string {
  return `turn_${Date.now()}_${Math.random().toString(36).substring(7)}`;
}
