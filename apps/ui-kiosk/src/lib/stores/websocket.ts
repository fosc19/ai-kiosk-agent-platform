import { writable, derived, get } from 'svelte/store';
import type { VPSToPiMessage, PiToVPSMessage } from '@ai-kiosk/shared-types';
import { VPSToPiMessageSchema, MessageType } from '@ai-kiosk/shared-types';

interface WebSocketState {
  connected: boolean;
  reconnecting: boolean;
  error: string | null;
}

const WS_URL = import.meta.env.VITE_VPS_URL || 'ws://localhost:8765/ws';
const RECONNECT_DELAY = 2000;
const MAX_RECONNECT_ATTEMPTS = Infinity;

let ws: WebSocket | null = null;
let reconnectAttempts = 0;
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

export const wsState = writable<WebSocketState>({
  connected: false,
  reconnecting: false,
  error: null,
});

export const messages = writable<VPSToPiMessage[]>([]);

export function connect() {
  if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) {
    console.log('[WS] Already connected or connecting');
    return;
  }

  console.log(`[WS] Connecting to ${WS_URL}`);
  wsState.update((s) => ({ ...s, reconnecting: true, error: null }));

  try {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.log('[WS] Connected');
      wsState.set({ connected: true, reconnecting: false, error: null });
      reconnectAttempts = 0;

      // Send session start
      send({
        type: MessageType.SESSION_START,
        payload: {
          kiosk_id: import.meta.env.VITE_KIOSK_ID || 'pi-kiosk-dev',
          device_info: {
            model: 'Development',
            os: navigator.userAgent,
            ip: 'localhost',
          },
          language: 'es',
        },
      });
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const parsed = VPSToPiMessageSchema.parse(data);
        console.log('[WS] Message received:', parsed.type);
        messages.update((msgs) => [...msgs, parsed]);
      } catch (error) {
        console.error('[WS] Invalid message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('[WS] Error:', error);
      wsState.update((s) => ({ ...s, error: 'WebSocket error' }));
    };

    ws.onclose = () => {
      console.log('[WS] Disconnected');
      wsState.set({ connected: false, reconnecting: false, error: 'Disconnected' });

      // Auto-reconnect
      if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++;
        console.log(`[WS] Reconnecting in ${RECONNECT_DELAY}ms (attempt ${reconnectAttempts})`);
        reconnectTimeout = setTimeout(connect, RECONNECT_DELAY);
      }
    };
  } catch (error) {
    console.error('[WS] Connection error:', error);
    wsState.update((s) => ({ ...s, error: 'Failed to connect', reconnecting: false }));
  }
}

export function disconnect() {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }

  if (ws) {
    ws.close();
    ws = null;
  }

  wsState.set({ connected: false, reconnecting: false, error: null });
}

export function send(message: PiToVPSMessage) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.error('[WS] Cannot send message: not connected');
    return;
  }

  console.log('[WS] Sending:', message.type);
  ws.send(JSON.stringify(message));
}

// Derived store for latest UI state
export const uiState = derived(messages, ($messages) => {
  const stateMessages = $messages.filter((m) => m.type === MessageType.UI_STATE);
  const latest = stateMessages[stateMessages.length - 1];
  return latest?.payload.state || 'idle';
});

// F3: Derived store for latest transcript
export const transcript = derived(messages, ($messages) => {
  const transcriptMessages = $messages.filter((m) => m.type === MessageType.ASR_TRANSCRIPT);
  const latest = transcriptMessages[transcriptMessages.length - 1];
  if (latest && latest.type === MessageType.ASR_TRANSCRIPT) {
    return {
      text: latest.payload.text,
      isFinal: latest.payload.is_final,
      turnId: latest.payload.turn_id,
    };
  }
  return null;
});

// F3: Derived store for latest say text
export const sayText = derived(messages, ($messages) => {
  const sayMessages = $messages.filter((m) => m.type === MessageType.UI_SAY);
  const latest = sayMessages[sayMessages.length - 1];
  if (latest && latest.type === MessageType.UI_SAY) {
    return {
      text: latest.payload.text,
      turnId: latest.payload.turn_id,
    };
  }
  return null;
});

// Route data for navigation overlay
export interface RouteData {
  store_id: string;
  store_name: string;
  steps: Array<{
    instruction: string;
    direction: 'left' | 'right' | 'straight' | 'arrive';
    distance?: number;
  }>;
}

// F5/F6: Derived store for route data
export const routeData = derived(messages, ($messages) => {
  const routeMessages = $messages.filter((m) => m.type === MessageType.UI_ROUTE);
  const latest = routeMessages[routeMessages.length - 1];
  if (latest && latest.type === MessageType.UI_ROUTE) {
    return latest.payload as RouteData;
  }
  return null;
});
