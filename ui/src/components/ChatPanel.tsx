import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { colors, typography, radius, shadows } from '../tokens';
import type { Message, ViewMode } from '../types';
import AssistantResponse from './AssistantResponse';

interface ChatPanelProps {
  messages: Message[];
  onSendQuery: (query: string) => void;
  isProcessing: boolean;
  viewMode: ViewMode;
}

/* ── Starter questions ────────────────────────────────── */
const STARTER_QUESTIONS = [
  'Total billed business by generation',
  'Top 5 merchants by card spend',
  'Customer attrition rate by tenure',
  'Card product issuance volume this quarter',
  'Dining spend by customer segment',
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
const ChatPanel: React.FC<ChatPanelProps> = ({ messages, onSendQuery, isProcessing, viewMode }) => {
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
      {/* Content area */}
      <div
        style={{
          flex: 1,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {hasMessages ? (
          <MessageThread messages={messages} onFollowUp={onSendQuery} maxWidth={maxWidth} />
        ) : (
          <WelcomeState onSendQuery={onSendQuery} maxWidth={maxWidth} />
        )}
      </div>

      {/* Sticky bottom: ChatInput */}
      <ChatInput
        onSendQuery={onSendQuery}
        isProcessing={isProcessing}
        maxWidth={maxWidth}
      />
    </div>
  );
};

/* ── WelcomeState ─────────────────────────────────────── */
const WelcomeState: React.FC<{ onSendQuery: (q: string) => void; maxWidth: number }> = ({
  onSendQuery,
  maxWidth,
}) => {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 24px',
        maxWidth,
        margin: '0 auto',
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
          fontSize: 16,
          color: colors.textSecondary,
          textAlign: 'center',
        }}
      >
        Ask anything about your Finance data. I'll find the answer.
      </p>

      {/* Starter cards: 2-column grid, 2+2+1 centered */}
      <div
        style={{
          marginTop: 32,
          width: '100%',
          maxWidth: 520,
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 12,
        }}
      >
        {STARTER_QUESTIONS.map((q, idx) => (
          <StarterCard
            key={q}
            question={q}
            onClick={() => onSendQuery(q)}
            style={
              idx === STARTER_QUESTIONS.length - 1
                ? { gridColumn: '1 / -1', maxWidth: 254, justifySelf: 'center' }
                : undefined
            }
          />
        ))}
      </div>
    </div>
  );
};

/* ── StarterCard ──────────────────────────────────────── */
const StarterCard: React.FC<{
  question: string;
  onClick: () => void;
  style?: React.CSSProperties;
}> = ({ question, onClick, style }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: 16,
        border: `1px solid ${hovered ? colors.amexBlue : colors.borderDefault}`,
        borderRadius: radius.lg,
        backgroundColor: hovered ? colors.infoLight : colors.surfacePrimary,
        cursor: 'pointer',
        textAlign: 'left',
        fontFamily: typography.fontPrimary,
        fontSize: 14,
        fontWeight: 500,
        color: hovered ? colors.amexBlue : colors.textPrimary,
        lineHeight: 1.4,
        transition: 'all 0.15s ease',
        outline: 'none',
        ...style,
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
}> = ({ messages, onFollowUp, maxWidth }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.length, messages[messages.length - 1]?.content]);

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
            placeholder={isProcessing ? 'Cortex is processing...' : 'Ask a question about your data...'}
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
              outline: 'none',
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
            color: colors.textTertiary,
            textAlign: 'center',
            fontFamily: typography.fontPrimary,
          }}
        >
          Cortex may make mistakes. Always verify critical decisions.
        </p>
      </div>
    </div>
  );
};

export default ChatPanel;
