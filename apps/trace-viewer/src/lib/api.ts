/**
 * API client for Trace Collector
 */

import type { TraceEvent, TraceAnalysis, TraceSummary } from './types';

const TRACE_COLLECTOR_URL = import.meta.env.VITE_TRACE_COLLECTOR_URL || 'http://localhost:9005';

export class TraceCollectorClient {
  private baseUrl: string;

  constructor(baseUrl: string = TRACE_COLLECTOR_URL) {
    this.baseUrl = baseUrl;
  }

  /**
   * Check if Trace Collector is healthy
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/healthz`);
      return response.ok;
    } catch (error) {
      console.error('Health check failed:', error);
      return false;
    }
  }

  /**
   * List available traces
   */
  async listTraces(params?: {
    limit?: number;
    turn_id?: string;
    service?: string;
  }): Promise<string[]> {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.turn_id) searchParams.set('turn_id', params.turn_id);
    if (params?.service) searchParams.set('service', params.service);

    const url = `${this.baseUrl}/traces${searchParams.toString() ? '?' + searchParams : ''}`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to list traces: ${response.statusText}`);
    }

    const data = await response.json();
    return data.traces || [];
  }

  /**
   * Get all events for a specific trace
   */
  async getTrace(traceId: string): Promise<TraceEvent[]> {
    const response = await fetch(`${this.baseUrl}/traces/${traceId}`);

    if (!response.ok) {
      throw new Error(`Failed to get trace ${traceId}: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Get analysis for a specific trace
   */
  async analyzeTrace(traceId: string): Promise<TraceAnalysis> {
    const response = await fetch(`${this.baseUrl}/analysis/${traceId}`);

    if (!response.ok) {
      throw new Error(`Failed to analyze trace ${traceId}: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Get summary information for multiple traces
   */
  async getTraceSummaries(limit: number = 20): Promise<TraceSummary[]> {
    const traceIds = await this.listTraces({ limit });

    const summaries = await Promise.all(
      traceIds.map(async (traceId) => {
        try {
          const analysis = await this.analyzeTrace(traceId);

          // Calculate total duration from timeline
          const duration = analysis.timeline.length > 0
            ? Math.max(...analysis.timeline.map(e => e.offset_ms))
            : 0;

          // Check for SLA violations
          const violations = Object.entries(analysis.latencies).some(([key, value]) => {
            if (key.includes('_total')) return value > 3000;
            if (key.includes('classify')) return value > 150;
            if (key.includes('asr')) return value > 500;
            if (key.includes('tts')) return value > 500;
            return false;
          });

          return {
            trace_id: traceId,
            event_count: analysis.event_count,
            turn_count: analysis.turn_count,
            duration_ms: duration,
            violations,
          };
        } catch (error) {
          console.error(`Failed to get summary for ${traceId}:`, error);
          return {
            trace_id: traceId,
            event_count: 0,
            turn_count: 0,
            violations: false,
          };
        }
      })
    );

    return summaries;
  }
}

export const traceCollectorClient = new TraceCollectorClient();
