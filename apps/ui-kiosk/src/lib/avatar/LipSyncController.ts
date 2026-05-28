// apps/ui-kiosk/src/lib/avatar/LipSyncController.ts
import type { VRMAvatar } from './VRMAvatar';

/**
 * Controlador de lip-sync usando análisis RMS del audio TTS
 */
export class LipSyncController {
	private avatar: VRMAvatar;
	private analyser: AnalyserNode | null = null;
	private audioContext: AudioContext | null = null;
	private dataArray: Float32Array | null = null;
	private animationFrameId: number | null = null;

	constructor(avatar: VRMAvatar) {
		this.avatar = avatar;
	}

	/**
	 * Conecta el audio TTS al analizador para lip-sync
	 */
	connect(audioElement: HTMLAudioElement, audioContext: AudioContext) {
		this.audioContext = audioContext;

		// Crear analyser si no existe
		if (!this.analyser) {
			this.analyser = audioContext.createAnalyser();
			this.analyser.fftSize = 256;
			this.dataArray = new Float32Array(this.analyser.fftSize);
		}

		// Crear source desde el audio element
		const source = audioContext.createMediaElementSource(audioElement);

		// Conectar: source -> analyser -> destination
		source.connect(this.analyser);
		this.analyser.connect(audioContext.destination);

		// Iniciar análisis
		this.startLipSync();
	}

	/**
	 * Conecta un AudioBufferSourceNode al analizador
	 */
	connectSource(source: AudioBufferSourceNode, destination: AudioDestinationNode) {
		// FIX: Get AudioContext from destination if not set
		if (!this.audioContext) {
			this.audioContext = destination.context as AudioContext;
		}

		// Crear analyser si no existe
		if (!this.analyser) {
			this.analyser = this.audioContext.createAnalyser();
			this.analyser.fftSize = 256;
			this.dataArray = new Float32Array(this.analyser.fftSize);
		}

		// Conectar: source -> analyser -> destination
		source.connect(this.analyser);
		this.analyser.connect(destination);

		// Iniciar análisis
		this.startLipSync();
	}

	/**
	 * Inicia el loop de análisis RMS para lip-sync
	 */
	private startLipSync() {
		if (this.animationFrameId !== null) {
			// Ya está corriendo
			return;
		}

		const updateLipSync = () => {
			if (!this.analyser || !this.dataArray) {
				return;
			}

			// Obtener datos de audio
			this.analyser.getFloatTimeDomainData(this.dataArray);

			// Actualizar boca del avatar
			this.avatar.updateMouth(this.dataArray);

			// Continuar loop
			this.animationFrameId = requestAnimationFrame(updateLipSync);
		};

		updateLipSync();
		console.log('[LipSync] Started');
	}

	/**
	 * Detiene el análisis de lip-sync
	 */
	stop() {
		if (this.animationFrameId !== null) {
			cancelAnimationFrame(this.animationFrameId);
			this.animationFrameId = null;
			console.log('[LipSync] Stopped');
		}
	}

	/**
	 * Desconecta y limpia recursos
	 */
	disconnect() {
		this.stop();

		if (this.analyser) {
			this.analyser.disconnect();
			this.analyser = null;
		}

		this.audioContext = null;
		this.dataArray = null;
	}
}
