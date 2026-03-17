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
  const { done, sql, results, followUps, action, disambiguate, clarify, filters, entities } =
    pipeline;

  // Derive content based on action
  let content = '';
  if (action === 'disambiguate' && disambiguate) {
    content = disambiguate.message || 'I found multiple matching data sources. Which one fits your question?';
  } else if (action === 'clarify' && clarify) {
    content = clarify.message || 'Could you clarify your question?';
  } else if (action === 'no_match') {
    content = 'I could not find a matching data source for your query. Could you rephrase or try a different question?';
  } else if (action === 'out_of_scope') {
    content = 'This question is outside the scope of available data sources. Please ask a question about finance data.';
  } else if (done?.error) {
    content = `An error occurred: ${done.error}`;
  } else if (results) {
    content = `Found ${results.row_count} result${results.row_count !== 1 ? 's' : ''}.`;
  } else {
    content = 'Query completed.';
  }

  return {
    id: generateId(),
    role: 'assistant',
    content,
    timestamp: new Date(),
    results: results ?? undefined,
    sql: sql?.sql,
    explore: sql?.explore,
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
  };
}

export default function App() {
  const [viewMode, setViewMode] = useState<ViewMode>('analyst');
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const {
    sessions,
    activeSessionId,
    createSession,
    setActiveSessionId,
    addMessage,
    getActiveSession,
  } = useConversation();

  const { sendQuery, pipelineState, isProcessing, error: _sseError, reset } = useSSE({
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
      }
    }
    prevIsProcessingRef.current = isProcessing;
  }, [isProcessing, pipelineState, activeSessionId, addMessage]);

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

      // Fire SSE query
      sendQuery(content, sessionId);
    },
    [activeSessionId, createSession, addMessage, sendQuery, reset],
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

  const chatPanelContainerStyle: CSSProperties = {
    flex: viewMode === 'engineering' ? '0 0 55%' : '1 1 auto',
    overflow: 'hidden',
    transition: 'flex 250ms ease-out',
  };

  const engineeringPanelContainerStyle: CSSProperties = {
    flex: '0 0 45%',
    overflow: 'hidden',
    display: viewMode === 'engineering' ? 'flex' : 'none',
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
            />
          </div>

          {viewMode === 'engineering' && (
            <div style={engineeringPanelContainerStyle}>
              <EngineeringPanel
                steps={pipelineState.steps}
                overallConfidence={overallConfidence}
                totalDurationMs={totalDurationMs}
                isProcessing={isProcessing}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
