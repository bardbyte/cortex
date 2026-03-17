import React, { useState, useCallback } from 'react';
import { colors, typography, radius, shadows } from '../tokens';
import type { Message, ResolvedFilter } from '../types';
import ResultTable from './ResultTable';

interface AssistantResponseProps {
  message: Message;
  onFollowUp: (query: string) => void;
}

/* ── Confidence dot color ─────────────────────────────── */
function confidenceDotColor(confidence: number): string {
  if (confidence >= 80) return colors.success;
  if (confidence >= 60) return colors.warning;
  return colors.error;
}

/* ── SQL syntax highlighting (lightweight) ────────────── */
function highlightSQL(sql: string): React.ReactNode[] {
  const keywords =
    /\b(SELECT|FROM|WHERE|AND|OR|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP BY|ORDER BY|HAVING|LIMIT|AS|IN|NOT|NULL|IS|BETWEEN|LIKE|CASE|WHEN|THEN|ELSE|END|COUNT|SUM|AVG|MIN|MAX|DISTINCT|UNION|ALL|WITH|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|SET|VALUES|INTO|EXISTS|COALESCE|CAST|OVER|PARTITION BY|ROW_NUMBER|RANK|DENSE_RANK|ASC|DESC|OFFSET|FETCH|NEXT|ROWS|ONLY|TRUE|FALSE)\b/gi;

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  const matches = [...sql.matchAll(keywords)];

  if (matches.length === 0) {
    return [<span key="0">{sql}</span>];
  }

  matches.forEach((match, i) => {
    if (match.index !== undefined && match.index > lastIndex) {
      parts.push(
        <span key={`t-${i}`} style={{ color: '#E2E8F0' }}>
          {sql.slice(lastIndex, match.index)}
        </span>,
      );
    }
    parts.push(
      <span key={`k-${i}`} style={{ color: '#7DD3FC', fontWeight: 600 }}>
        {match[0].toUpperCase()}
      </span>,
    );
    lastIndex = (match.index ?? 0) + match[0].length;
  });

  if (lastIndex < sql.length) {
    parts.push(
      <span key="end" style={{ color: '#E2E8F0' }}>
        {sql.slice(lastIndex)}
      </span>,
    );
  }

  return parts;
}

/* ── Typing indicator ─────────────────────────────────── */
const TypingIndicator: React.FC = () => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
    <span style={{ fontSize: 14, color: colors.textSecondary }}>Cortex is thinking</span>
    <div style={{ display: 'flex', gap: 4 }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            backgroundColor: colors.amexBlue,
            display: 'inline-block',
            animation: `pulseDot 1.4s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </div>
    <style>{`
      @keyframes pulseDot {
        0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
        40% { opacity: 1; transform: scale(1); }
      }
    `}</style>
  </div>
);

/* ── Main component ───────────────────────────────────── */
const AssistantResponse: React.FC<AssistantResponseProps> = ({ message, onFollowUp }) => {
  const [metadataExpanded, setMetadataExpanded] = useState(false);
  const [sqlCopied, setSqlCopied] = useState(false);

  const handleCopySQL = useCallback(async () => {
    if (!message.sql) return;
    try {
      await navigator.clipboard.writeText(message.sql);
      setSqlCopied(true);
      setTimeout(() => setSqlCopied(false), 2000);
    } catch {
      // Fallback: noop
    }
  }, [message.sql]);

  const isProcessing = !message.content && !message.action;

  /* ── Disambiguate state ──── */
  if (message.action === 'disambiguate' && message.disambiguateOptions) {
    return (
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', maxWidth: '100%' }}>
        <CortexAvatar />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              margin: 0,
              fontSize: 16,
              fontWeight: 500,
              color: colors.textPrimary,
              fontFamily: typography.fontPrimary,
              marginBottom: 12,
            }}
          >
            {message.content || 'I found multiple matching data sources. Which one fits your question?'}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {message.disambiguateOptions.map((opt) => {
              const dotColor = confidenceDotColor(opt.confidence);
              return (
                <DisambiguateCard
                  key={opt.explore}
                  explore={opt.explore}
                  description={opt.description}
                  confidence={opt.confidence}
                  dotColor={dotColor}
                  onSelect={() => onFollowUp(opt.explore)}
                />
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  /* ── Clarify state ──── */
  if (message.action === 'clarify') {
    return (
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', maxWidth: '100%' }}>
        <CortexAvatar />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              margin: 0,
              fontSize: 16,
              fontWeight: 500,
              color: colors.textPrimary,
              fontFamily: typography.fontPrimary,
              marginBottom: 8,
            }}
          >
            {message.clarifyMessage || message.content || 'Could you clarify your question?'}
          </p>
          {message.followUps && message.followUps.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
              {message.followUps.map((suggestion) => (
                <FollowUpChip key={suggestion} label={suggestion} onClick={() => onFollowUp(suggestion)} />
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  /* ── Processing / typing state ──── */
  if (isProcessing) {
    return (
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', maxWidth: '100%' }}>
        <CortexAvatar />
        <div style={{ paddingTop: 6 }}>
          <TypingIndicator />
        </div>
      </div>
    );
  }

  /* ── Standard response ──── */
  const hasMetadata = message.sql || message.explore || message.confidence != null || message.filters;
  const hasFilters = message.filters && (message.filters.resolved.length > 0 || message.filters.mandatory.length > 0);

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', maxWidth: '100%' }}>
      <CortexAvatar />
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* 1. Summary answer */}
        <p
          style={{
            margin: 0,
            fontSize: 16,
            fontWeight: 500,
            color: colors.textPrimary,
            fontFamily: typography.fontPrimary,
            lineHeight: 1.5,
          }}
        >
          {message.content}
        </p>

        {/* 2. Result table */}
        {message.results && (
          <ResultTable
            columns={message.results.columns}
            rows={message.results.rows}
            rowCount={message.results.row_count}
            truncated={message.results.truncated}
          />
        )}

        {/* 3. Metadata footer */}
        {hasMetadata && (
          <div style={{ marginTop: 12 }}>
            {/* Collapsed: inline pills */}
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
              {message.explore && (
                <MetadataPill>
                  explore: {message.explore}
                </MetadataPill>
              )}
              {message.confidence != null && (
                <MetadataPill>
                  <span
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: '50%',
                      backgroundColor: confidenceDotColor(message.confidence),
                      display: 'inline-block',
                      marginRight: 5,
                    }}
                  />
                  {message.confidence}% match
                </MetadataPill>
              )}
              {hasFilters && message.filters!.resolved.map((f: ResolvedFilter) => (
                <MetadataPill key={f.field}>
                  {f.user_said} {'\u2192'} {f.resolved_to}
                </MetadataPill>
              ))}
              <button
                onClick={() => setMetadataExpanded(!metadataExpanded)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: colors.textLink,
                  cursor: 'pointer',
                  fontSize: 12,
                  fontWeight: 500,
                  fontFamily: typography.fontPrimary,
                  padding: '2px 4px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                {metadataExpanded ? 'Hide details' : 'Show details'}
                <span style={{ fontSize: 10, transform: metadataExpanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
                  {'\u25BC'}
                </span>
              </button>
            </div>

            {/* Expanded */}
            {metadataExpanded && (
              <div
                style={{
                  marginTop: 10,
                  padding: 16,
                  backgroundColor: colors.surfaceSecondary,
                  borderRadius: radius.lg,
                  border: `1px solid ${colors.borderDefault}`,
                }}
              >
                {/* SQL block */}
                {message.sql && (
                  <div style={{ marginBottom: hasFilters ? 16 : 0 }}>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 8,
                      }}
                    >
                      <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: colors.textTertiary, letterSpacing: '0.05em' }}>
                        Generated SQL
                      </span>
                      <button
                        onClick={handleCopySQL}
                        style={{
                          background: 'none',
                          border: `1px solid ${colors.borderDefault}`,
                          borderRadius: radius.md,
                          padding: '4px 10px',
                          fontSize: 11,
                          fontWeight: 500,
                          color: sqlCopied ? colors.success : colors.textSecondary,
                          cursor: 'pointer',
                          fontFamily: typography.fontPrimary,
                          transition: 'color 0.15s',
                        }}
                      >
                        {sqlCopied ? 'Copied!' : 'Copy SQL'}
                      </button>
                    </div>
                    <pre
                      style={{
                        margin: 0,
                        padding: 16,
                        backgroundColor: colors.amexDarkBlue,
                        borderRadius: radius.md,
                        overflow: 'auto',
                        fontSize: 13,
                        lineHeight: 1.6,
                        fontFamily: typography.fontMono,
                      }}
                    >
                      <code>{highlightSQL(message.sql)}</code>
                    </pre>
                  </div>
                )}

                {/* Filter resolution details */}
                {hasFilters && (
                  <div>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        color: colors.textTertiary,
                        letterSpacing: '0.05em',
                        display: 'block',
                        marginBottom: 8,
                      }}
                    >
                      Filter Resolution
                    </span>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {message.filters!.resolved.map((f) => (
                        <div
                          key={f.field}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            fontSize: 13,
                            color: colors.textPrimary,
                            fontFamily: typography.fontPrimary,
                          }}
                        >
                          <span style={{ color: colors.textSecondary }}>{f.field}:</span>
                          <span
                            style={{
                              padding: '2px 8px',
                              backgroundColor: colors.warningLight,
                              borderRadius: radius.sm,
                              fontSize: 12,
                            }}
                          >
                            {f.user_said}
                          </span>
                          <span style={{ color: colors.textTertiary }}>{'\u2192'}</span>
                          <span
                            style={{
                              padding: '2px 8px',
                              backgroundColor: colors.successLight,
                              borderRadius: radius.sm,
                              fontSize: 12,
                              fontFamily: typography.fontMono,
                            }}
                          >
                            {f.resolved_to}
                          </span>
                          <span
                            style={{
                              fontSize: 11,
                              color: colors.textTertiary,
                            }}
                          >
                            ({f.confidence}%)
                          </span>
                        </div>
                      ))}
                      {message.filters!.mandatory.map((f) => (
                        <div
                          key={f.field}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            fontSize: 13,
                            color: colors.textPrimary,
                            fontFamily: typography.fontPrimary,
                          }}
                        >
                          <span style={{ color: colors.textSecondary }}>{f.field}:</span>
                          <span
                            style={{
                              padding: '2px 8px',
                              backgroundColor: colors.infoLight,
                              borderRadius: radius.sm,
                              fontSize: 12,
                              fontFamily: typography.fontMono,
                            }}
                          >
                            {f.value}
                          </span>
                          <span style={{ fontSize: 11, color: colors.textTertiary }}>
                            (mandatory: {f.reason})
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 4. Follow-up chips */}
        {message.followUps && message.followUps.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
            {message.followUps.map((fup) => (
              <FollowUpChip key={fup} label={fup} onClick={() => onFollowUp(fup)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

/* ── Sub-components ───────────────────────────────────── */

const CortexAvatar: React.FC = () => (
  <div
    style={{
      width: 32,
      height: 32,
      borderRadius: '50%',
      backgroundColor: colors.amexBlue,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexShrink: 0,
      color: colors.amexWhite,
      fontSize: 14,
      fontWeight: 700,
      fontFamily: typography.fontPrimary,
    }}
  >
    C
  </div>
);

const MetadataPill: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      padding: '3px 10px',
      borderRadius: radius.full,
      backgroundColor: colors.surfaceTertiary,
      fontSize: 12,
      fontWeight: 500,
      color: colors.textSecondary,
      fontFamily: typography.fontPrimary,
      whiteSpace: 'nowrap',
    }}
  >
    {children}
  </span>
);

const FollowUpChip: React.FC<{ label: string; onClick: () => void }> = ({ label, onClick }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '6px 14px',
        border: `1px solid ${hovered ? colors.amexBlue : colors.borderDefault}`,
        borderRadius: radius.full,
        backgroundColor: hovered ? colors.infoLight : colors.surfacePrimary,
        color: hovered ? colors.amexBlue : colors.textPrimary,
        fontSize: 13,
        fontWeight: 500,
        fontFamily: typography.fontPrimary,
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        outline: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </button>
  );
};

interface DisambiguateCardProps {
  explore: string;
  description: string;
  confidence: number;
  dotColor: string;
  onSelect: () => void;
}

const DisambiguateCard: React.FC<DisambiguateCardProps> = ({ explore, description, confidence, dotColor, onSelect }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        width: '100%',
        padding: 14,
        border: `1.5px solid ${hovered ? colors.amexBlue : colors.borderDefault}`,
        borderRadius: radius.lg,
        backgroundColor: hovered ? colors.infoLight : colors.surfacePrimary,
        cursor: 'pointer',
        textAlign: 'left',
        fontFamily: typography.fontPrimary,
        transition: 'all 0.15s ease',
        boxShadow: hovered ? shadows.sm : 'none',
        outline: 'none',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: colors.textPrimary, marginBottom: 2 }}>
          {explore}
        </div>
        <div style={{ fontSize: 12, color: colors.textSecondary, lineHeight: 1.4 }}>
          {description}
        </div>
      </div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          fontSize: 12,
          fontWeight: 600,
          color: colors.textSecondary,
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            backgroundColor: dotColor,
            display: 'inline-block',
          }}
        />
        {confidence}% match
      </div>
    </button>
  );
};

export default AssistantResponse;
