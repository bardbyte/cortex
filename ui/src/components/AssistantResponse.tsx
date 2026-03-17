import React, { useState, useCallback } from 'react';
import { colors, typography, radius, shadows } from '../tokens';
import type { Message, ResolvedFilter } from '../types';
import CollapseBadge from './CollapseBadge';
import RadixMark from './RadixMark';
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

/* ── Main component ───────────────────────────────────── */
const AssistantResponse: React.FC<AssistantResponseProps> = ({ message, onFollowUp }) => {
  const [detailExpanded, setDetailExpanded] = useState(false);
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

  const handleToggleDetail = useCallback(() => {
    setDetailExpanded((prev) => !prev);
  }, []);

  /* ── Disambiguate state ──── */
  if (message.action === 'disambiguate' && message.disambiguateOptions) {
    return (
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', maxWidth: '100%' }}>
        <RadixAvatar />
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
            {message.content || 'Your question closely matches two data sources. Which one applies?'}
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
        <RadixAvatar />
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
            {message.clarifyMessage || message.content || 'I need a bit more context to find the right data.'}
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

  /* ── No match state ──── */
  if (message.action === 'no_match') {
    return (
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', maxWidth: '100%' }}>
        <RadixAvatar />
        <div style={{ flex: 1, minWidth: 0 }}>
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
            I couldn't find a matching data source for that question. Try rephrasing with a specific metric, time range, or dimension.
          </p>
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
  }

  /* ── Out of scope state ──── */
  if (message.action === 'out_of_scope') {
    return (
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', maxWidth: '100%' }}>
        <RadixAvatar />
        <div style={{ flex: 1, minWidth: 0 }}>
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
            That question is outside the data sources I can access. Try asking about a specific metric or dataset available in your business unit.
          </p>
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
  }

  /* ── Error state (content starts with "An error occurred") ──── */
  if (message.content && message.content.startsWith('An error occurred')) {
    return (
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', maxWidth: '100%' }}>
        <RadixAvatar />
        <div style={{ flex: 1, minWidth: 0 }}>
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
            Something went wrong processing that query. Try simplifying — for example, add a specific time range or segment.
          </p>
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
  }

  /* ── Standard response (proceed) ──── */
  const hasFilters = message.filters && (message.filters.resolved.length > 0 || message.filters.mandatory.length > 0);
  const isProceed = !message.action || message.action === 'proceed';

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', maxWidth: '100%' }}>
      <RadixAvatar />
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* 1. CollapseBadge — persistent summary for proceed responses */}
        {isProceed && (
          <div style={{ marginBottom: 10 }}>
            <CollapseBadge
              exploreName={message.explore}
              confidence={message.confidence}
              totalDurationMs={message.totalDurationMs}
              filters={message.filters}
              onToggleDetail={handleToggleDetail}
              detailExpanded={detailExpanded}
            />
          </div>
        )}

        {/* 2. Content text */}
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

        {/* 3. SQL block — ALWAYS visible for proceed responses (this IS the result) */}
        {isProceed && message.sql && (
          <div style={{ marginTop: 12 }}>
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
                backgroundColor: colors.codeSurface,
                borderRadius: radius.md,
                overflow: 'auto',
                maxHeight: 400,
                fontSize: 13,
                lineHeight: 1.6,
                fontFamily: typography.fontMono,
              }}
            >
              <code>{highlightSQL(message.sql)}</code>
            </pre>
          </div>
        )}

        {/* 4. Results table — rendered when backend returns query results */}
        {isProceed && message.results && message.results.columns.length > 0 && (
          <ResultTable
            columns={message.results.columns}
            rows={message.results.rows}
            rowCount={message.results.rowCount}
            truncated={message.results.truncated}
          />
        )}

        {/* 5. Filter translations — visible by default for proceed responses */}
        {isProceed && hasFilters && (
          <div style={{ marginTop: 12 }}>
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
              {message.filters!.resolved.map((f: ResolvedFilter) => (
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

        {/* 5. "Show details" expandable — explore metadata, entity extraction, filter resolution paths */}
        {isProceed && detailExpanded && (
          <div
            style={{
              marginTop: 12,
              padding: 16,
              backgroundColor: colors.surfaceSecondary,
              borderRadius: radius.lg,
              border: `1px solid ${colors.borderDefault}`,
            }}
          >
            {/* Explore metadata */}
            {(message.model || message.explore) && (
              <div style={{ marginBottom: 12 }}>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    color: colors.textTertiary,
                    letterSpacing: '0.05em',
                    display: 'block',
                    marginBottom: 6,
                  }}
                >
                  Explore Metadata
                </span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {message.model && (
                    <MetadataPill>
                      model: {message.model}
                    </MetadataPill>
                  )}
                  {message.explore && (
                    <MetadataPill>
                      explore: {message.explore}
                    </MetadataPill>
                  )}
                </div>
              </div>
            )}

            {/* Entity extraction summary */}
            {message.entities && (
              <div style={{ marginBottom: 12 }}>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    color: colors.textTertiary,
                    letterSpacing: '0.05em',
                    display: 'block',
                    marginBottom: 6,
                  }}
                >
                  Entity Extraction
                </span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {message.entities.intent && (
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        padding: '2px 10px',
                        borderRadius: radius.full,
                        backgroundColor: colors.infoLight,
                        color: colors.amexBlue,
                      }}
                    >
                      {message.entities.intent}
                    </span>
                  )}
                  {message.entities.metrics.map((m) => (
                    <EntityChip key={`m-${m}`} label={m} color={colors.amexBlue} bg={colors.infoLight} />
                  ))}
                  {message.entities.dimensions.map((d) => (
                    <EntityChip key={`d-${d}`} label={d} color={colors.textPrimary} bg={colors.surfaceTertiary} />
                  ))}
                  {message.entities.filters.map((f) => (
                    <EntityChip key={`f-${f}`} label={f} color={colors.warning} bg={colors.warningLight} />
                  ))}
                  {message.entities.time_range && (
                    <EntityChip label={message.entities.time_range} color={colors.textSecondary} bg={colors.surfaceTertiary} />
                  )}
                </div>
              </div>
            )}

            {/* Detailed filter resolution paths */}
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
                    marginBottom: 6,
                  }}
                >
                  Filter Resolution Paths
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {message.filters!.resolved.map((f: ResolvedFilter) => (
                    <div
                      key={`detail-${f.field}`}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        flexWrap: 'wrap',
                      }}
                    >
                      <span
                        style={{
                          fontSize: 11,
                          fontFamily: typography.fontMono,
                          color: colors.textSecondary,
                        }}
                      >
                        {f.field}
                      </span>
                      <span
                        style={{
                          fontSize: 11,
                          fontFamily: typography.fontMono,
                          padding: '2px 6px',
                          borderRadius: radius.sm,
                          backgroundColor: colors.warningLight,
                          color: colors.warning,
                        }}
                      >
                        {f.user_said}
                      </span>
                      <span style={{ fontSize: 11, color: colors.textTertiary }}>{'\u2192'}</span>
                      <span
                        style={{
                          fontSize: 11,
                          fontFamily: typography.fontMono,
                          padding: '2px 6px',
                          borderRadius: radius.sm,
                          backgroundColor: colors.successLight,
                          color: colors.success,
                        }}
                      >
                        {f.resolved_to}
                      </span>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          padding: '1px 5px',
                          borderRadius: radius.full,
                          backgroundColor: colors.surfaceTertiary,
                          color: colors.textSecondary,
                          textTransform: 'uppercase',
                          letterSpacing: '0.03em',
                        }}
                      >
                        {f.pass}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 6. Follow-up chips */}
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

const RadixAvatar: React.FC = () => <RadixMark size={32} />;

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

const EntityChip: React.FC<{ label: string; color: string; bg: string }> = ({ label, color: fg, bg }) => (
  <span
    style={{
      fontSize: 11,
      fontWeight: 500,
      padding: '2px 8px',
      borderRadius: radius.full,
      backgroundColor: bg,
      color: fg,
      fontFamily: typography.fontMono,
      whiteSpace: 'nowrap',
    }}
  >
    {label}
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
