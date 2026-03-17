import { useState, useCallback, useRef, useEffect } from 'react';
import type { CSSProperties } from 'react';
import type { ViewMode, Message, PipelineAction } from './types';
import { colors, typography } from './tokens';
import { useConversation } from './hooks/useConversation';
import { useSSE } from './hooks/useSSE';
import type { PipelineState } from './hooks/useSSE';
import TopNav from './components/TopNav';
import Sidebar from './components/Sidebar';
import ChatPanel from './components/ChatPanel';
import EngineeringPanel from './components/EngineeringPanel';

const API_URL = 'http://localhost:8080';
const NAV_HEIGHT = 64;

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function buildAssistantMessage(pipeline: PipelineState): Message {
  const { done, sql, followUps, action, disambiguate, clarify, filters, entities } =
    pipeline;

  // Derive content based on action
  let content = '';
  if (action === 'disambiguate' && disambiguate) {
    content = disambiguate.message || 'I found multiple matching data sources. Which one fits your question?';
  } else if (action === 'clarify' && clarify) {
    content = clarify.message || 'Could you clarify your question?';
  } else if (action === 'no_match') {
    content = 'I couldn\'t find a matching data source for that question. Try rephrasing with a specific metric, time range, or dimension.';
  } else if (action === 'out_of_scope') {
    content = 'That question is outside the data sources I can access. Try asking about a specific metric or dataset available in your business unit.';
  } else if (done?.error) {
    content = 'Something went wrong processing that query. Try simplifying — for example, add a specific time range or segment.';
  } else if (pipeline.steps.some(s => s.status === 'error')) {
    content = 'Something went wrong processing that query. Try simplifying — for example, add a specific time range or segment.';
  } else if (sql) {
    content = sql.explore
      ? `Here's what I found in ${sql.explore}.`
      : 'Here are your results.';
  } else {
    content = 'Query completed.';
  }

  return {
    id: generateId(),
    role: 'assistant',
    content,
    timestamp: new Date(),
    sql: sql?.sql,
    explore: sql?.explore,
    model: sql?.model,
    confidence: done?.overall_confidence != null
      ? Math.round((done.overall_confidence as number) * 100)
      : undefined,
    followUps: followUps.length > 0 ? followUps : undefined,
    action: (action ?? 'proceed') as PipelineAction,
    disambiguateOptions: disambiguate?.options,
    clarifyMessage: clarify?.message ?? undefined,
    steps: pipeline.steps,
    totalDurationMs: done?.total_duration_ms,
    traceId: done?.trace_id,
    filters: filters.resolved.length > 0 || filters.mandatory.length > 0
      ? { resolved: filters.resolved, mandatory: filters.mandatory }
      : undefined,
    entities: entities ?? undefined,
    results: pipeline.results ?? undefined,
  };
}

export default function App() {
  const [viewMode, setViewMode] = useState<ViewMode>('analyst');
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const {
    sessions,
    activeSessionId,
    createSession,
    setActiveSessionId,
    addMessage,
    getActiveSession,
    setConversationId,
  } = useConversation();

  const { sendQuery, pipelineState, isProcessing, error: sseError, reset } = useSSE({
    apiUrl: API_URL,
  });

  // Track whether we've already created an assistant message for the current query
  const pendingQueryRef = useRef(false);
  const prevIsProcessingRef = useRef(false);

  // When pipeline transitions from processing to done, create the assistant message
  useEffect(() => {
    if (prevIsProcessingRef.current && !isProcessing && pendingQueryRef.current) {
      // Pipeline just finished
      pendingQueryRef.current = false;
      if (activeSessionId) {
        const assistantMsg = buildAssistantMessage(pipelineState);
        addMessage(activeSessionId, assistantMsg);

        // Store backend conversation_id for multi-turn context
        if (pipelineState.done?.conversation_id) {
          setConversationId(activeSessionId, pipelineState.done.conversation_id);
        }
      }
    }
    prevIsProcessingRef.current = isProcessing;
  }, [isProcessing, pipelineState, activeSessionId, addMessage, setConversationId]);

  const handleSendQuery = useCallback(
    (content: string) => {
      // Ensure a session exists
      let sessionId = activeSessionId;
      if (!sessionId) {
        sessionId = createSession();
      }

      // Reset pipeline for new query
      reset();

      // Add user message
      const userMsg: Message = {
        id: generateId(),
        role: 'user',
        content,
        timestamp: new Date(),
      };
      addMessage(sessionId, userMsg);

      // Mark that we're waiting for a result
      pendingQueryRef.current = true;

      // Send backend conversation_id for multi-turn context (if available)
      const session = sessions.find((s) => s.id === sessionId);
      sendQuery(content, session?.conversationId ?? sessionId);
    },
    [activeSessionId, sessions, createSession, addMessage, sendQuery, reset],
  );

  const handleNewSession = useCallback(() => {
    reset();
    createSession();
  }, [createSession, reset]);

  const handleSelectSession = useCallback(
    (id: string) => {
      reset();
      setActiveSessionId(id);
    },
    [setActiveSessionId, reset],
  );

  const activeSession = getActiveSession();
  const messages = activeSession?.messages ?? [];

  // Compute engineering panel props from pipeline state
  const overallConfidence = pipelineState.done?.overall_confidence != null
    ? (pipelineState.done.overall_confidence as number)
    : 0;
  const totalDurationMs = pipelineState.done?.total_duration_ms ?? 0;

  // Derive activeStepLabel from pipeline state
  const activeStepLabel = pipelineState.steps.find((s) => s.status === 'active')?.label;

  // Layout styles
  const appContainerStyle: CSSProperties = {
    width: '100vw',
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    fontFamily: typography.fontPrimary,
    background: colors.surfaceSecondary,
    overflow: 'hidden',
  };

  const bodyStyle: CSSProperties = {
    display: 'flex',
    flex: 1,
    marginTop: `${NAV_HEIGHT}px`,
    overflow: 'hidden',
  };

  const mainContentStyle: CSSProperties = {
    display: 'flex',
    flex: 1,
    overflow: 'hidden',
  };

  const isEngineering = viewMode === 'engineering';

  const chatPanelContainerStyle: CSSProperties = {
    flex: isEngineering ? '0 0 55%' : '1 1 auto',
    overflow: 'hidden',
    transition: 'flex 250ms ease-out',
  };

  const engineeringPanelContainerStyle: CSSProperties = {
    flex: isEngineering ? '0 0 45%' : '0 0 0%',
    overflow: 'hidden',
    display: 'flex',
    transition: 'flex 250ms ease-out',
  };

  return (
    <div style={appContainerStyle}>
      <TopNav
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
      />

      <div style={bodyStyle}>
        <Sidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
          open={sidebarOpen}
        />

        <div style={mainContentStyle}>
          <div style={chatPanelContainerStyle}>
            <ChatPanel
              messages={messages}
              onSendQuery={handleSendQuery}
              isProcessing={isProcessing}
              viewMode={viewMode}
              activeStepLabel={activeStepLabel}
              entities={pipelineState.entities ?? undefined}
              filters={
                pipelineState.filters.resolved.length > 0 || pipelineState.filters.mandatory.length > 0
                  ? pipelineState.filters
                  : undefined
              }
              exploreName={pipelineState.sql?.explore}
              steps={pipelineState.steps}
              error={sseError}
            />
          </div>

          <div style={engineeringPanelContainerStyle}>
            <EngineeringPanel
              steps={pipelineState.steps}
              overallConfidence={overallConfidence}
              totalDurationMs={totalDurationMs}
              isProcessing={isProcessing}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
