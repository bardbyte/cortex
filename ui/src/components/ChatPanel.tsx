import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { colors, typography, radius, shadows } from '../tokens';
import type { Message, ViewMode, PipelineStep } from '../types';
import AssistantResponse from './AssistantResponse';
import IntentEcho from './IntentEcho';
import ProcessingIndicator from './ProcessingIndicator';

interface ChatPanelProps {
  messages: Message[];
  onSendQuery: (query: string) => void;
  isProcessing: boolean;
  viewMode: ViewMode;
  // NEW: pipeline state for live processing display
  activeStepLabel?: string;
  entities?: Message['entities'];
  filters?: Message['filters'];
  exploreName?: string;
  steps?: PipelineStep[];
  error?: string | null;
}

/* ── Starter questions ────────────────────────────────── */
const API_URL = 'http://localhost:8080';

const FALLBACK_STARTER_QUESTIONS = [
  'Total billed business by customer segment',
  'Top 5 merchants by card spend this quarter',
  'Active cardmembers by generation',
  'Card issuance volume year over year',
  'Average spend per customer by product type',
];

/* ── Time-based greeting ──────────────────────────────── */
function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/* ── Send icon SVG ────────────────────────────────────── */
const SendIcon: React.FC<{ color: string }> = ({ color }) => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path
      d="M14.5 1.5L7 9M14.5 1.5L10 14.5L7 9M14.5 1.5L1.5 6L7 9"
      stroke={color}
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

/* ── ChatPanel ────────────────────────────────────────── */
const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  onSendQuery,
  isProcessing,
  viewMode,
  activeStepLabel,
  entities,
  filters,
  exploreName,
  steps,
  error,
}) => {
  const maxWidth = viewMode === 'analyst' ? 800 : 680;
  const hasMessages = messages.length > 0;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        fontFamily: typography.fontPrimary,
        backgroundColor: colors.surfacePrimary,
        overflow: 'hidden',
      }}
    >
      {hasMessages ? (
        <>
          {/* Conversation mode: messages + bottom-anchored input */}
          <div
            style={{
              flex: 1,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <MessageThread
              messages={messages}
              onFollowUp={onSendQuery}
              maxWidth={maxWidth}
              isProcessing={isProcessing}
              activeStepLabel={activeStepLabel}
              entities={entities}
              filters={filters}
              exploreName={exploreName}
              steps={steps}
              error={error}
            />
          </div>
          <ChatInput
            onSendQuery={onSendQuery}
            isProcessing={isProcessing}
            maxWidth={maxWidth}
          />
        </>
      ) : (
        /* Welcome mode: centered input with starters — no bottom bar */
        <WelcomeState onSendQuery={onSendQuery} maxWidth={maxWidth} />
      )}
    </div>
  );
};

/* ── WelcomeState ─────────────────────────────────────── */
const WelcomeState: React.FC<{ onSendQuery: (q: string) => void; maxWidth: number }> = ({
  onSendQuery,
  maxWidth,
}) => {
  const [value, setValue] = useState('');
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [starterQuestions, setStarterQuestions] = useState<string[]>(FALLBACK_STARTER_QUESTIONS);

  // Fetch dynamic starter questions from capabilities endpoint
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/v1/capabilities`)
      .then((res) => res.json())
      .then((data) => {
        if (cancelled) return;
        const questions = data?.starter_questions;
        if (Array.isArray(questions) && questions.length > 0) {
          setStarterQuestions(questions.map((q: { text: string }) => q.text));
        }
      })
      .catch(() => {
        // Silently fall back to hardcoded questions
      });
    return () => { cancelled = true; };
  }, []);

  const canSend = value.trim().length > 0;

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSendQuery(trimmed);
    setValue('');
  }, [value, onSendQuery]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const el = e.target;
    el.style.height = '52px';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  const handlePrefill = useCallback((q: string) => {
    setValue(q);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, []);

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0 24px 60px',
        width: '100%',
        boxSizing: 'border-box',
      }}
    >
      {/* Greeting */}
      <h1
        style={{
          margin: 0,
          fontSize: 28,
          fontWeight: 600,
          color: colors.textPrimary,
          textAlign: 'center',
          lineHeight: 1.3,
        }}
      >
        {getGreeting()}, what would you like to know?
      </h1>
      <p
        style={{
          margin: '8px 0 0',
          fontSize: 15,
          color: colors.textSecondary,
          textAlign: 'center',
        }}
      >
        Ask a question about your data — I'll find the right source and build the query.
      </p>

      {/* Centered input box */}
      <div
        style={{
          marginTop: 28,
          width: '100%',
          maxWidth: Math.min(maxWidth, 640),
        }}
      >
        <div
          style={{
            position: 'relative',
            border: `1.5px solid ${focused ? colors.borderFocus : colors.borderDefault}`,
            borderRadius: radius.lg,
            boxShadow: focused
              ? `0 0 0 3px rgba(0, 111, 207, 0.1), ${shadows.lg}`
              : shadows.lg,
            backgroundColor: colors.surfacePrimary,
            transition: 'border-color 0.15s, box-shadow 0.15s',
          }}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            aria-label="Ask a data question"
            placeholder="Ask about your data, e.g. 'Top merchants by spend this quarter'"
            rows={1}
            style={{
              width: '100%',
              minHeight: 52,
              maxHeight: 160,
              padding: '14px 52px 14px 16px',
              border: 'none',
              outline: 'none',
              resize: 'none',
              fontSize: 15,
              fontFamily: typography.fontPrimary,
              color: colors.textPrimary,
              backgroundColor: 'transparent',
              lineHeight: 1.5,
              boxSizing: 'border-box',
            }}
          />
          <button
            onClick={handleSend}
            disabled={!canSend}
            aria-label="Send query"
            style={{
              position: 'absolute',
              right: 10,
              bottom: 10,
              width: 32,
              height: 32,
              borderRadius: '50%',
              border: 'none',
              backgroundColor: canSend ? colors.amexBlue : colors.surfaceTertiary,
              cursor: canSend ? 'pointer' : 'default',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background-color 0.15s',
              padding: 0,
            }}
          >
            <SendIcon color={canSend ? colors.amexWhite : colors.textTertiary} />
          </button>
        </div>
      </div>

      {/* Starter chips below input — prefill on click */}
      <div
        style={{
          marginTop: 20,
          width: '100%',
          maxWidth: Math.min(maxWidth, 640),
          display: 'flex',
          flexWrap: 'wrap',
          gap: 8,
          justifyContent: 'center',
        }}
      >
        {starterQuestions.map((q) => (
          <StarterChip key={q} question={q} onClick={() => handlePrefill(q)} />
        ))}
      </div>

      {/* Disclaimer */}
      <p
        style={{
          margin: '16px 0 0',
          fontSize: 11,
          color: colors.textSecondary,
          textAlign: 'center',
          fontFamily: typography.fontPrimary,
        }}
      >
        Always verify results with your data owner before using in reports.
      </p>
    </div>
  );
};

/* ── StarterChip ─────────────────────────────────────── */
const StarterChip: React.FC<{
  question: string;
  onClick: () => void;
}> = ({ question, onClick }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '8px 16px',
        border: `1px solid ${hovered ? colors.amexBlue : colors.borderDefault}`,
        borderRadius: radius.full,
        backgroundColor: hovered ? colors.infoLight : colors.surfacePrimary,
        cursor: 'pointer',
        textAlign: 'left',
        fontFamily: typography.fontPrimary,
        fontSize: 13,
        fontWeight: 500,
        color: hovered ? colors.amexBlue : colors.textSecondary,
        lineHeight: 1.3,
        transition: 'all 0.15s ease',
        whiteSpace: 'nowrap',
      }}
    >
      {question}
    </button>
  );
};

/* ── MessageThread ────────────────────────────────────── */
const MessageThread: React.FC<{
  messages: Message[];
  onFollowUp: (q: string) => void;
  maxWidth: number;
  isProcessing: boolean;
  activeStepLabel?: string;
  entities?: Message['entities'];
  filters?: Message['filters'];
  exploreName?: string;
  steps?: PipelineStep[];
  error?: string | null;
}> = ({ messages, onFollowUp, maxWidth, isProcessing, activeStepLabel, entities, filters, exploreName, steps, error }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or processing state changes
  useEffect(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.length, messages[messages.length - 1]?.content, isProcessing, activeStepLabel]);

  return (
    <div
      ref={containerRef}
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '24px 24px 16px',
      }}
    >
      <div
        style={{
          maxWidth,
          margin: '0 auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 24,
        }}
      >
        {messages.map((msg) =>
          msg.role === 'user' ? (
            <UserMessage key={msg.id} message={msg} />
          ) : (
            <AssistantResponse key={msg.id} message={msg} onFollowUp={onFollowUp} />
          ),
        )}

        {/* Processing section — rendered after the last user message while pipeline is active */}
        {isProcessing && steps && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
          >
            {/* Intent echo — show extracted entities during processing */}
            {entities && (
              <div style={{ paddingLeft: 44 }}>
                <IntentEcho entities={entities} />
              </div>
            )}

            {/* Adaptive 3-phase processing indicator */}
            <ProcessingIndicator
              steps={steps}
              entities={entities ?? null}
              filters={filters ?? { resolved: [], mandatory: [] }}
              exploreName={exploreName}
            />
          </div>
        )}

        {/* Error is now unified in the assistant message — no duplicate inline error */}
      </div>
    </div>
  );
};

/* ── UserMessage ──────────────────────────────────────── */
const UserMessage: React.FC<{ message: Message }> = ({ message }) => {
  const timeStr = useMemo(() => {
    return message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }, [message.timestamp]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
      <div
        style={{
          maxWidth: '70%',
          backgroundColor: colors.amexBlue,
          color: colors.textInverse,
          fontSize: 15,
          fontFamily: typography.fontPrimary,
          padding: '10px 16px',
          borderRadius: '16px 16px 4px 16px',
          lineHeight: 1.5,
          wordBreak: 'break-word',
        }}
      >
        {message.content}
      </div>
      <span
        style={{
          fontSize: 11,
          color: colors.textTertiary,
          marginTop: 4,
          paddingRight: 4,
        }}
      >
        {timeStr}
      </span>
    </div>
  );
};

/* ── ChatInput ────────────────────────────────────────── */
const ChatInput: React.FC<{
  onSendQuery: (query: string) => void;
  isProcessing: boolean;
  maxWidth: number;
}> = ({ onSendQuery, isProcessing, maxWidth }) => {
  const [value, setValue] = useState('');
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend = value.trim().length > 0 && !isProcessing;

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isProcessing) return;
    onSendQuery(trimmed);
    setValue('');
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = '52px';
    }
  }, [value, isProcessing, onSendQuery]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    // Auto-expand
    const el = e.target;
    el.style.height = '52px';
    const scrollHeight = el.scrollHeight;
    el.style.height = `${Math.min(scrollHeight, 200)}px`;
  }, []);

  return (
    <div
      style={{
        borderTop: `1px solid ${colors.borderDefault}`,
        padding: '12px 24px 16px',
        backgroundColor: colors.surfacePrimary,
      }}
    >
      <div
        style={{
          maxWidth,
          margin: '0 auto',
        }}
      >
        {/* Input wrapper */}
        <div
          style={{
            position: 'relative',
            border: `1.5px solid ${focused ? colors.borderFocus : colors.borderDefault}`,
            borderRadius: radius.lg,
            boxShadow: focused ? `0 0 0 3px rgba(0, 111, 207, 0.1), ${shadows.md}` : shadows.md,
            backgroundColor: colors.surfacePrimary,
            transition: 'border-color 0.15s, box-shadow 0.15s',
          }}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            disabled={isProcessing}
            aria-label="Ask a data question"
            placeholder={isProcessing ? 'Processing your query...' : 'Ask about your data...'}
            rows={1}
            style={{
              width: '100%',
              minHeight: 52,
              maxHeight: 200,
              padding: '14px 52px 14px 16px',
              border: 'none',
              outline: 'none',
              resize: 'none',
              fontSize: 15,
              fontFamily: typography.fontPrimary,
              color: colors.textPrimary,
              backgroundColor: 'transparent',
              lineHeight: 1.5,
              boxSizing: 'border-box',
            }}
          />
          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!canSend}
            aria-label="Send query"
            style={{
              position: 'absolute',
              right: 10,
              bottom: 10,
              width: 32,
              height: 32,
              borderRadius: '50%',
              border: 'none',
              backgroundColor: canSend ? colors.amexBlue : colors.surfaceTertiary,
              cursor: canSend ? 'pointer' : 'default',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background-color 0.15s',
              padding: 0,
            }}
          >
            <SendIcon color={canSend ? colors.amexWhite : colors.textTertiary} />
          </button>
        </div>

        {/* Disclaimer */}
        <p
          style={{
            margin: '6px 0 0',
            fontSize: 11,
            color: colors.textSecondary,
            textAlign: 'center',
            fontFamily: typography.fontPrimary,
          }}
        >
          Always verify results with your data owner before using in reports.
        </p>
      </div>
    </div>
  );
};

export default ChatPanel;
