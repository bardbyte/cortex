import { useState, useCallback, useRef } from 'react';
import { PIPELINE_STEPS } from '../types';
import type {
  PipelineStep,
  StepName,
  StepStartPayload,
  StepCompletePayload,
  StepProgressPayload,
  ExploreScoredPayload,
  DisambiguatePayload,
  ClarifyPayload,
  SqlGeneratedPayload,
  ResultsPayload,
  FollowUpsPayload,
  DonePayload,
  PipelineAction,
  ResolvedFilter,
  MandatoryFilter,
} from '../types';

// ---------- Pipeline state exposed to UI ----------

export interface PipelineState {
  steps: PipelineStep[];
  explores: ExploreScoredPayload | null;
  sql: SqlGeneratedPayload | null;
  results: ResultsPayload | null;
  followUps: string[];
  disambiguate: DisambiguatePayload | null;
  clarify: ClarifyPayload | null;
  done: DonePayload | null;
  action: PipelineAction | null;
  filters: {
    resolved: ResolvedFilter[];
    mandatory: MandatoryFilter[];
  };
  entities: {
    intent: string;
    metrics: string[];
    dimensions: string[];
    filters: string[];
    time_range: string | null;
  } | null;
}

function initialSteps(): PipelineStep[] {
  return PIPELINE_STEPS.map((s) => ({
    ...s,
    status: 'pending' as const,
    expanded: false,
  }));
}

function initialPipelineState(): PipelineState {
  return {
    steps: initialSteps(),
    explores: null,
    sql: null,
    results: null,
    followUps: [],
    disambiguate: null,
    clarify: null,
    done: null,
    action: null,
    filters: { resolved: [], mandatory: [] },
    entities: null,
  };
}

// ---------- SSE line parser ----------

interface ParsedEvent {
  event: string;
  data: string;
}

/**
 * Parse an SSE text chunk into discrete events.
 * SSE format: `event: <type>\ndata: <json>\n\n`
 * Handles partial chunks by carrying a buffer across calls.
 */
function parseSSEChunk(buffer: string): { events: ParsedEvent[]; remaining: string } {
  const events: ParsedEvent[] = [];
  const blocks = buffer.split('\n\n');

  // Last element may be an incomplete block — carry it over.
  const remaining = blocks.pop() ?? '';

  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = 'message';
    let data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) {
        event = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        data = line.slice(5).trim();
      }
    }
    if (data) {
      events.push({ event, data });
    }
  }

  return { events, remaining };
}

// ---------- Hook ----------

export interface UseSSEOptions {
  apiUrl: string;
}

export interface UseSSEReturn {
  sendQuery: (query: string, conversationId?: string) => void;
  pipelineState: PipelineState;
  isProcessing: boolean;
  error: string | null;
  reset: () => void;
}

export function useSSE({ apiUrl }: UseSSEOptions): UseSSEReturn {
  const [pipelineState, setPipelineState] = useState<PipelineState>(initialPipelineState);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ---- helpers that mutate pipeline state ----

  const updateStep = useCallback(
    (name: StepName, patch: Partial<PipelineStep>) => {
      setPipelineState((prev) => ({
        ...prev,
        steps: prev.steps.map((s) => (s.name === name ? { ...s, ...patch } : s)),
      }));
    },
    [],
  );

  // ---- event dispatch ----

  const handleEvent = useCallback(
    (eventType: string, payload: Record<string, unknown>) => {
      switch (eventType) {
        case 'step_start': {
          const d = payload as unknown as StepStartPayload;
          updateStep(d.step, { status: 'active', message: d.message });
          break;
        }
        case 'step_complete': {
          const d = payload as unknown as StepCompletePayload;
          updateStep(d.step, {
            status: 'complete',
            durationMs: d.duration_ms,
            message: d.message,
            detail: d.detail,
          });
          break;
        }
        case 'step_progress': {
          const d = payload as unknown as StepProgressPayload;
          updateStep(d.step, { message: d.message, detail: d.detail });
          break;
        }
        case 'explore_scored': {
          const d = payload as unknown as ExploreScoredPayload;
          setPipelineState((prev) => ({ ...prev, explores: d }));
          break;
        }
        case 'disambiguate': {
          const d = payload as unknown as DisambiguatePayload;
          setPipelineState((prev) => ({ ...prev, disambiguate: d, action: 'disambiguate' }));
          break;
        }
        case 'clarify': {
          const d = payload as unknown as ClarifyPayload;
          setPipelineState((prev) => ({ ...prev, clarify: d, action: 'clarify' }));
          break;
        }
        case 'sql_generated': {
          const d = payload as unknown as SqlGeneratedPayload;
          setPipelineState((prev) => ({ ...prev, sql: d }));
          break;
        }
        case 'results': {
          const d = payload as unknown as ResultsPayload;
          setPipelineState((prev) => ({ ...prev, results: d }));
          break;
        }
        case 'follow_ups': {
          const d = payload as unknown as FollowUpsPayload;
          setPipelineState((prev) => ({ ...prev, followUps: d.suggestions }));
          break;
        }
        case 'filter_resolved': {
          const resolved = (payload.resolved ?? []) as ResolvedFilter[];
          const mandatory = (payload.mandatory ?? []) as MandatoryFilter[];
          setPipelineState((prev) => ({
            ...prev,
            filters: { resolved, mandatory },
          }));
          break;
        }
        case 'entities_extracted': {
          setPipelineState((prev) => ({
            ...prev,
            entities: {
              intent: (payload.intent as string) ?? '',
              metrics: (payload.metrics as string[]) ?? [],
              dimensions: (payload.dimensions as string[]) ?? [],
              filters: (payload.filters as string[]) ?? [],
              time_range: (payload.time_range as string | null) ?? null,
            },
          }));
          break;
        }
        case 'no_match': {
          setPipelineState((prev) => ({ ...prev, action: 'no_match' }));
          break;
        }
        case 'out_of_scope': {
          setPipelineState((prev) => ({ ...prev, action: 'out_of_scope' }));
          break;
        }
        case 'done': {
          const d = payload as unknown as DonePayload;
          setPipelineState((prev) => ({
            ...prev,
            done: d,
            action: (d.action as PipelineAction) ?? prev.action ?? 'proceed',
          }));
          setIsProcessing(false);
          break;
        }
        case 'error': {
          const msg = (payload.message as string) ?? (payload.error as string) ?? 'Unknown error';
          setError(msg);
          // Mark the currently-active step as errored
          setPipelineState((prev) => ({
            ...prev,
            steps: prev.steps.map((s) => (s.status === 'active' ? { ...s, status: 'error' } : s)),
          }));
          setIsProcessing(false);
          break;
        }
        default:
          // Unknown events are silently ignored — forward-compatible.
          break;
      }
    },
    [updateStep],
  );

  // ---- send query ----

  const sendQuery = useCallback(
    async (query: string, conversationId?: string) => {
      // Abort any in-flight request.
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      // Reset state for the new query.
      setPipelineState(initialPipelineState());
      setError(null);
      setIsProcessing(true);

      try {
        const response = await fetch(`${apiUrl}/api/v1/query`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query,
            conversation_id: conversationId ?? undefined,
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const text = await response.text().catch(() => '');
          throw new Error(`Server returned ${response.status}: ${text || response.statusText}`);
        }

        if (!response.body) {
          throw new Error('Response body is null — SSE streaming not supported by the server.');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let sseBuffer = '';

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          sseBuffer += decoder.decode(value, { stream: true });
          const { events, remaining } = parseSSEChunk(sseBuffer);
          sseBuffer = remaining;

          for (const evt of events) {
            try {
              const payload = JSON.parse(evt.data) as Record<string, unknown>;
              handleEvent(evt.event, payload);
            } catch {
              // Malformed JSON in a single event — skip it.
              console.warn('[useSSE] Failed to parse event data:', evt.data);
            }
          }
        }

        // Flush any remaining buffer after stream ends.
        if (sseBuffer.trim()) {
          const { events } = parseSSEChunk(sseBuffer + '\n\n');
          for (const evt of events) {
            try {
              const payload = JSON.parse(evt.data) as Record<string, unknown>;
              handleEvent(evt.event, payload);
            } catch {
              // skip
            }
          }
        }
      } catch (err: unknown) {
        if ((err as DOMException)?.name === 'AbortError') {
          // User-initiated abort — not an error.
          return;
        }
        const msg = err instanceof Error ? err.message : 'Unknown error';
        setError(msg);
        setIsProcessing(false);
      }
    },
    [apiUrl, handleEvent],
  );

  // ---- reset ----

  const reset = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setPipelineState(initialPipelineState());
    setError(null);
    setIsProcessing(false);
  }, []);

  return { sendQuery, pipelineState, isProcessing, error, reset };
}

export default useSSE;
