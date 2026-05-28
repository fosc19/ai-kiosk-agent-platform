/**
 * Types for AI Kiosk Trace Viewer
 */

export interface TraceEvent {
  trace_id: string;
  turn_id: string;
  span_id: string;
  service: string;
  event: string;
  ts_ms: number;
  mono_ms: number;
  parent_span_id?: string;
  payload: Record<string, any>;
}

export interface TraceAnalysis {
  trace_id: string;
  event_count: number;
  turn_count: number;
  latencies: Record<string, number>;
  timeline: TimelineEvent[];
}

export interface TimelineEvent {
  offset_ms: number;
  service: string;
  event: string;
  turn_id: string;
  span_id: string;
}

export interface WaterfallBar {
  label: string;
  start_ms: number;
  duration_ms: number;
  color: string;
  service: string;
  violation: boolean;
  details: string;
  event: string;
}

export interface TraceSummary {
  trace_id: string;
  event_count: number;
  turn_count: number;
  duration_ms?: number;
  violations: boolean;
}

/**
 * SLA thresholds in milliseconds
 */
export const SLA_THRESHOLDS = {
  turn_total: 3000,
  asr: 500,
  llm_first_token: 800,
  tts_first_chunk: 500,
  classify: 150,
  tool_call: 100,
} as const;

/**
 * Service color mapping for waterfall chart
 */
export const SERVICE_COLORS = {
  orchestrator: '#3b82f6',  // Blue
  'mcp-tools': '#10b981',   // Green
  speech_asr: '#eab308',    // Yellow
  speech_tts: '#f97316',    // Orange
  speech: '#f97316',        // Orange (fallback)
  default: '#6b7280',       // Gray
} as const;
