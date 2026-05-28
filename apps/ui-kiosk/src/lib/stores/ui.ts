// UI State Store
import { writable, get } from 'svelte/store';
import { UIState, MessageType, type UIStateMessage } from '@ai-kiosk/shared-types';
import { messages } from './websocket';

/**
 * Global UI state store
 * Controls avatar expressions and animations
 */
export const uiState = writable<UIState>(UIState.IDLE);

/**
 * Helper functions to update UI state
 */
export function setUIState(state: UIState): void {
	uiState.set(state);
	console.log('[UIState]', state);
}

export function setIdle(): void {
	setUIState(UIState.IDLE);
}

export function setListening(): void {
	setUIState(UIState.LISTENING);
}

export function setThinking(): void {
	setUIState(UIState.THINKING);
}

export function setSpeaking(): void {
	setUIState(UIState.SPEAKING);
}

export function setGuiding(): void {
	setUIState(UIState.GUIDING);
}

/**
 * Subscribe to WebSocket messages and update UI state automatically
 */
export function initUIStateSync(): void {
	messages.subscribe((msgs) => {
		if (msgs.length === 0) return;

		const lastMessage = msgs[msgs.length - 1];

		// Handle UI_STATE messages from orchestrator
		if (lastMessage.type === MessageType.UI_STATE) {
			const uiStateMsg = lastMessage as UIStateMessage;
			setUIState(uiStateMsg.payload.state);
		}
	});

	console.log('[UIState] Auto-sync with WebSocket enabled');
}

