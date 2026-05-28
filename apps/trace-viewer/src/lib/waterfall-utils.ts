/**
 * Utilities for converting trace events to waterfall bars
 */

import type { TraceEvent, WaterfallBar } from './types';
import { SERVICE_COLORS, SLA_THRESHOLDS } from './types';

interface EventPair {
  start: TraceEvent;
  end?: TraceEvent;
}

/**
 * Find matching start/end event pairs for spans
 */
function findEventPairs(events: TraceEvent[]): EventPair[] {
  const pairs: EventPair[] = [];
  const startEvents = new Map<string, TraceEvent>();

  for (const event of events) {
    const eventName = event.event;

    if (eventName.endsWith('_start')) {
      const baseKey = eventName.replace('_start', '');
      startEvents.set(baseKey, event);
    } else if (eventName.endsWith('_end')) {
      const baseKey = eventName.replace('_end', '');
      const startEvent = startEvents.get(baseKey);
      if (startEvent) {
        pairs.push({ start: startEvent, end: event });
        startEvents.delete(baseKey);
      }
    } else {
      // Standalone events (no start/end)
      pairs.push({ start: event });
    }
  }

  // Add remaining start events without end
  for (const [, startEvent] of startEvents) {
    pairs.push({ start: startEvent });
  }

  return pairs;
}

/**
 * Get color for a service
 */
function getServiceColor(service: string, event: string): string {
  if (event.includes('asr')) return SERVICE_COLORS.speech_asr;
  if (event.includes('tts')) return SERVICE_COLORS.speech_tts;
  return SERVICE_COLORS[service as keyof typeof SERVICE_COLORS] || SERVICE_COLORS.default;
}

/**
 * Get human-readable label for an event
 */
function getEventLabel(event: string, payload?: any): string {
  // Remove prefixes
  const cleanEvent = event.replace(/^(orch\.|mcp\.|speech\.|ui\.)/, '');

  // Handle specific events
  if (cleanEvent.includes('classify')) return 'Classify Intent';
  if (cleanEvent.includes('turn_start')) return 'Turn Start';
  if (cleanEvent.includes('turn_end')) return 'Turn End';
  if (cleanEvent.includes('asr')) return 'ASR (Transcription)';
  if (cleanEvent.includes('tts_first_chunk')) return 'TTS First Chunk';
  if (cleanEvent.includes('tts')) return 'TTS (Synthesis)';
  if (cleanEvent.includes('tool_call') && payload?.tool_name) {
    return `Tool: ${payload.tool_name}`;
  }
  if (cleanEvent.includes('call_start') && payload?.tool_name) {
    return `MCP: ${payload.tool_name}`;
  }

  // Default: capitalize and remove underscores
  return cleanEvent
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Check if a duration violates SLA
 */
function checkSLAViolation(event: string, durationMs: number): boolean {
  const eventLower = event.toLowerCase();

  if (eventLower.includes('classify')) {
    return durationMs > SLA_THRESHOLDS.classify;
  }
  if (eventLower.includes('asr')) {
    return durationMs > SLA_THRESHOLDS.asr;
  }
  if (eventLower.includes('tts') && eventLower.includes('first')) {
    return durationMs > SLA_THRESHOLDS.tts_first_chunk;
  }
  if (eventLower.includes('tool') || eventLower.includes('call')) {
    return durationMs > SLA_THRESHOLDS.tool_call;
  }

  return false;
}

/**
 * Convert trace events to waterfall bars
 */
export function eventsToWaterfallBars(
  events: TraceEvent[],
  turnId?: string
): WaterfallBar[] {
  // Filter by turn if specified
  const filteredEvents = turnId
    ? events.filter(e => e.turn_id === turnId)
    : events;

  if (filteredEvents.length === 0) {
    return [];
  }

  // Sort by monotonic time
  const sortedEvents = [...filteredEvents].sort((a, b) => a.mono_ms - b.mono_ms);

  // Find start time for offset calculation
  const startTime = sortedEvents[0].mono_ms;

  // Find event pairs
  const pairs = findEventPairs(sortedEvents);

  // Convert to waterfall bars
  const bars: WaterfallBar[] = pairs.map((pair) => {
    const { start, end } = pair;

    const startOffset = start.mono_ms - startTime;
    const duration = end ? end.mono_ms - start.mono_ms : 10; // Default 10ms for instant events

    const label = getEventLabel(start.event, start.payload);
    const color = getServiceColor(start.service, start.event);
    const violation = checkSLAViolation(start.event, duration);

    // Build details for tooltip
    const details = [
      `Event: ${start.event}`,
      `Service: ${start.service}`,
      `Duration: ${duration.toFixed(2)}ms`,
      `Start: ${startOffset.toFixed(2)}ms`,
    ];

    if (start.payload && Object.keys(start.payload).length > 0) {
      details.push(`Payload: ${JSON.stringify(start.payload, null, 2)}`);
    }

    return {
      label,
      start_ms: startOffset,
      duration_ms: duration,
      color: violation ? '#ef4444' : color, // Red if violation
      service: start.service,
      violation,
      details: details.join('\n'),
      event: start.event,
    };
  });

  return bars;
}

/**
 * Calculate total duration from waterfall bars
 */
export function calculateTotalDuration(bars: WaterfallBar[]): number {
  if (bars.length === 0) return 0;

  const maxEnd = Math.max(...bars.map(b => b.start_ms + b.duration_ms));
  return maxEnd;
}

/**
 * Group bars by turn
 */
export function groupBarsByTurn(events: TraceEvent[]): Map<string, WaterfallBar[]> {
  const turns = new Set(events.map(e => e.turn_id).filter(Boolean));
  const grouped = new Map<string, WaterfallBar[]>();

  for (const turn of turns) {
    const bars = eventsToWaterfallBars(events, turn);
    grouped.set(turn, bars);
  }

  return grouped;
}
