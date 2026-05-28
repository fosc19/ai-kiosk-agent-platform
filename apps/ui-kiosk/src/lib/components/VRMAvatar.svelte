<!-- apps/ui-kiosk/src/lib/components/VRMAvatar.svelte -->
<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { VRMAvatar } from '$lib/avatar/VRMAvatar';
	import { LipSyncController } from '$lib/avatar/LipSyncController';
	import { uiState } from '$lib/stores/ui';
	import { setLipSyncController } from '$lib/stores/lipSync';

	let canvas: HTMLCanvasElement;
	let avatar: VRMAvatar | null = null;
	let lipSync: LipSyncController | null = null;

	onMount(async () => {
		try {
			avatar = new VRMAvatar(canvas);

			// Try to load avatar VRM (graceful fallback if not found)
			try {
				await avatar.load('/models/avatar.vrm');
				console.log('[VRMAvatar] Avatar loaded successfully');

				// Initialize lip-sync controller
				lipSync = new LipSyncController(avatar);
				setLipSyncController(lipSync);
				console.log('[VRMAvatar] Lip-sync controller initialized');
			} catch (loadError) {
				console.warn('[VRMAvatar] Failed to load avatar model:', loadError);
				console.warn('[VRMAvatar] Please add avatar VRM to static/models/ directory');
				console.warn('[VRMAvatar] Avatar will not be displayed');
			}

			avatar.animate();

			// Resize handler
			const resizeObserver = new ResizeObserver((entries) => {
				const { width, height } = entries[0].contentRect;
				avatar?.onResize(width, height);
			});
			resizeObserver.observe(canvas.parentElement!);

			return () => {
				resizeObserver.disconnect();
			};
		} catch (error) {
			console.error('[VRMAvatar] Initialization error:', error);
		}
	});

	onDestroy(() => {
		// Cleanup lip-sync
		if (lipSync) {
			lipSync.disconnect();
			setLipSyncController(null);
		}
	});

	// Reaccionar a cambios de estado UI
	// UIState enum is already lowercase, matches avatar states directly
	$: if (avatar) {
		avatar.setState($uiState as 'idle' | 'listening' | 'thinking' | 'speaking');
	}
</script>

<div class="avatar-container">
	<canvas bind:this={canvas} width={800} height={1200}></canvas>
</div>

<style>
	.avatar-container {
		width: 100%;
		height: 100%;
		display: flex;
		justify-content: center;
		align-items: center;
	}

	canvas {
		max-width: 100%;
		max-height: 100%;
	}
</style>
