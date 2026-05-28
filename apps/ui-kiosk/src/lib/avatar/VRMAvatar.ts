// apps/ui-kiosk/src/lib/avatar/VRMAvatar.ts
import * as THREE from 'three';
import { VRM, VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';

export class VRMAvatar {
	private scene: THREE.Scene;
	private camera: THREE.PerspectiveCamera;
	private renderer: THREE.WebGLRenderer;
	private vrm: VRM | null = null;
	private clock: THREE.Clock;

	constructor(canvas: HTMLCanvasElement) {
		// Scene setup
		this.scene = new THREE.Scene();
		this.clock = new THREE.Clock();

		// Camera
		this.camera = new THREE.PerspectiveCamera(30, canvas.width / canvas.height, 0.1, 20);
		this.camera.position.set(0, 1.4, 2);

		// Renderer
		this.renderer = new THREE.WebGLRenderer({
			canvas,
			alpha: true,
			antialias: true
		});
		this.renderer.setSize(canvas.width, canvas.height);
		this.renderer.setPixelRatio(window.devicePixelRatio);

		// Lighting
		const light = new THREE.DirectionalLight(0xffffff, 1);
		light.position.set(1, 1, 1);
		this.scene.add(light);

		const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
		this.scene.add(ambientLight);
	}

	async load(vrmPath: string) {
		const loader = new GLTFLoader();
		loader.register((parser) => new VRMLoaderPlugin(parser));

		const gltf = await loader.loadAsync(vrmPath);
		this.vrm = gltf.userData.vrm as VRM;

		// VRM0 compatibility
		VRMUtils.rotateVRM0(this.vrm);

		// Add to scene
		this.scene.add(this.vrm.scene);

		// Look at camera
		this.vrm.lookAt?.lookAt(new THREE.Vector3(0, 0, 0));

		console.log('[Avatar] VRM loaded successfully');
	}

	/**
	 * Lip-sync por volumen RMS del audio TTS
	 */
	updateMouth(audioData: Float32Array) {
		if (!this.vrm) return;

		// Calcular RMS (Root Mean Square)
		const rms = Math.sqrt(
			audioData.reduce((sum, v) => sum + v * v, 0) / audioData.length
		);

		// Mapear a apertura de boca (0-1)
		// Factor 5 ajustable según el audio
		const mouthValue = Math.min(rms * 5, 1.0);

		// Expresión "aa" (boca abierta)
		this.vrm.expressionManager?.setValue('aa', mouthValue);
	}

	/**
	 * Estados del avatar: idle, listening, thinking, speaking
	 */
	setState(state: 'idle' | 'listening' | 'thinking' | 'speaking') {
		if (!this.vrm) return;

		const expressions = this.vrm.expressionManager;
		if (!expressions) return;

		// Reset all
		expressions.setValue('happy', 0);
		expressions.setValue('neutral', 0);

		switch (state) {
			case 'idle':
				expressions.setValue('neutral', 0.5);
				break;

			case 'listening':
				// Postura atenta, ligeramente feliz
				expressions.setValue('happy', 0.3);
				break;

			case 'thinking':
				// Mirada pensativa (lookAt hacia arriba-derecha)
				this.vrm.lookAt?.lookAt(new THREE.Vector3(0.5, 0.2, 0));
				break;

			case 'speaking':
				// Expresión neutra/amigable
				expressions.setValue('neutral', 0.7);
				// lookAt a la cámara
				this.vrm.lookAt?.lookAt(new THREE.Vector3(0, 0, 0));
				break;
		}
	}

	/**
	 * Animation loop
	 */
	animate() {
		requestAnimationFrame(() => this.animate());

		const deltaTime = this.clock.getDelta();

		if (this.vrm) {
			// Update VRM (parpadeo automático, física, etc.)
			this.vrm.update(deltaTime);
		}

		this.renderer.render(this.scene, this.camera);
	}

	/**
	 * Resize handler
	 */
	onResize(width: number, height: number) {
		this.camera.aspect = width / height;
		this.camera.updateProjectionMatrix();
		this.renderer.setSize(width, height);
	}
}
