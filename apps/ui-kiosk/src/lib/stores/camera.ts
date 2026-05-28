import { writable, get } from 'svelte/store';
import { MessageType } from '@ai-kiosk/shared-types';
import { send, wsState } from './websocket';

interface CameraState {
  stream: MediaStream | null;
  active: boolean;
  error: string | null;
  permissionDenied: boolean;
}

const FRAME_INTERVAL_MS = 200; // 5fps
const JPEG_QUALITY = 0.6;
const VIDEO_WIDTH = 640;
const VIDEO_HEIGHT = 480;

let frameInterval: ReturnType<typeof setInterval> | null = null;
let videoElement: HTMLVideoElement | null = null;
let canvasElement: HTMLCanvasElement | null = null;

export const cameraState = writable<CameraState>({
  stream: null,
  active: false,
  error: null,
  permissionDenied: false,
});

export async function initCamera(): Promise<MediaStream | null> {
  try {
    console.log('[Camera] Requesting access...');

    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: 'user',
        width: { ideal: VIDEO_WIDTH },
        height: { ideal: VIDEO_HEIGHT },
      },
      audio: false,
    });

    console.log('[Camera] Access granted');
    cameraState.set({
      stream,
      active: true,
      error: null,
      permissionDenied: false,
    });

    return stream;
  } catch (error) {
    const err = error as Error;
    console.error('[Camera] Access denied:', err.message);

    const isDenied = err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError';

    cameraState.set({
      stream: null,
      active: false,
      error: err.message,
      permissionDenied: isDenied,
    });

    return null;
  }
}

export function stopCamera() {
  console.log('[Camera] Stopping...');

  if (frameInterval) {
    clearInterval(frameInterval);
    frameInterval = null;
  }

  const state = get(cameraState);
  if (state.stream) {
    state.stream.getTracks().forEach((track) => track.stop());
  }

  cameraState.set({
    stream: null,
    active: false,
    error: null,
    permissionDenied: false,
  });
}

export function setVideoElement(video: HTMLVideoElement) {
  videoElement = video;
}

export function startFrameCapture() {
  if (frameInterval) {
    console.log('[Camera] Frame capture already running');
    return;
  }

  // Create canvas for frame capture
  canvasElement = document.createElement('canvas');
  canvasElement.width = VIDEO_WIDTH;
  canvasElement.height = VIDEO_HEIGHT;

  console.log('[Camera] Starting frame capture at 5fps');
  frameInterval = setInterval(captureAndSendFrame, FRAME_INTERVAL_MS);
}

export function stopFrameCapture() {
  if (frameInterval) {
    clearInterval(frameInterval);
    frameInterval = null;
    console.log('[Camera] Frame capture stopped');
  }
}

function captureAndSendFrame() {
  if (!videoElement || !canvasElement) {
    return;
  }

  // Check if video is ready
  if (videoElement.readyState < 2) {
    return;
  }

  // Check WebSocket connection
  const ws = get(wsState);
  if (!ws.connected) {
    return;
  }

  const ctx = canvasElement.getContext('2d');
  if (!ctx) {
    return;
  }

  // Draw video frame to canvas
  ctx.drawImage(videoElement, 0, 0, VIDEO_WIDTH, VIDEO_HEIGHT);

  // Convert to JPEG base64
  const dataUrl = canvasElement.toDataURL('image/jpeg', JPEG_QUALITY);
  const base64Data = dataUrl.split(',')[1];

  // Send via WebSocket
  send({
    type: MessageType.CAMERA_FRAME,
    payload: {
      image_data: base64Data,
      timestamp: Date.now(),
    },
  });
}
