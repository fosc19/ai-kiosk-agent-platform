// Store para gestionar el LipSyncController globalmente
import { writable } from 'svelte/store';
import type { LipSyncController } from '$lib/avatar/LipSyncController';

/**
 * Global lip-sync controller store
 * Used by AudioQueue to connect TTS audio to avatar mouth movements
 */
export const lipSyncController = writable<LipSyncController | null>(null);

/**
 * Set the lip-sync controller (called by VRMAvatar component on mount)
 */
export function setLipSyncController(controller: LipSyncController | null): void {
	lipSyncController.set(controller);
	if (controller) {
		console.log('[LipSync] Controller registered');
	} else {
		console.log('[LipSync] Controller unregistered');
	}
}
