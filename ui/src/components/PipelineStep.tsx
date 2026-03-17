import React, { useState, useEffect, useRef, useCallback } from 'react';
import { colors, typography, radius } from '../tokens';
import type { PipelineStep as PipelineStepType, ResolvedFilter, MandatoryFilter, ScoredExplore } from '../types';

interface PipelineStepProps {
  step: PipelineStepType;
  isLast: boolean;
}

/* ------------------------------------------------------------------ */
/*  Inline SVG Icons                                                   */
/* ------------------------------------------------------------------ */

const CheckmarkIcon: React.FC = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <path d="M2.5 6L5 8.5L9.5 3.5" stroke={colors.amexWhite} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const ExclamationIcon: React.FC = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <path d="M6 3V7" stroke={colors.amexWhite} strokeWidth="1.8" strokeLinecap="round" />
    <circle cx="6" cy="9.25" r="0.75" fill={colors.amexWhite} />
  </svg>
);

const XIcon: React.FC = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <path d="M3 3L9 9M9 3L3 9" stroke={colors.amexWhite} strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);

const ChevronIcon: React.FC<{ expanded: boolean }> = ({ expanded }) => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 14 14"
    fill="none"
    style={{
      transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
      transition: 'transform 200ms ease',
    }}
  >
    <path d="M5 3L9 7L5 11" stroke={colors.textTertiary} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/* ------------------------------------------------------------------ */
/*  Keyframe injection (spinner + pulse)                               */
/* ------------------------------------------------------------------ */

const STYLE_ID = 'pipeline-step-keyframes';

function ensureKeyframes(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    @keyframes cortex-spin {
      0%   { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  `;
  document.head.appendChild(style);
}

/* ------------------------------------------------------------------ */
/*  Step Indicator Circle                                              */
/* ------------------------------------------------------------------ */

const StepIndicator: React.FC<{ status: PipelineStepType['status'] }> = ({ status }) => {
  useEffect(() => { ensureKeyframes(); }, []);

  const base: React.CSSProperties = {
    width: 20,
    height: 20,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    position: 'relative',
  };

  switch (status) {
    case 'pending':
      return (
        <div style={{ ...base, backgroundColor: colors.surfaceTertiary, border: `1.5px solid ${colors.borderStrong}` }} />
      );
    case 'active':
      return (
        <div style={{ ...base, backgroundColor: colors.stepActive }}>
          {/* Spinning ring */}
          <div
            style={{
              position: 'absolute',
              inset: -3,
              borderRadius: '50%',
              border: `2px solid transparent`,
              borderTopColor: colors.stepActive,
              animation: 'cortex-spin 0.8s linear infinite',
            }}
          />
          {/* Inner dot */}
          <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: colors.amexWhite }} />
        </div>
      );
    case 'complete':
      return (
        <div style={{ ...base, backgroundColor: colors.stepComplete }}>
          <CheckmarkIcon />
        </div>
      );
    case 'warning':
      return (
        <div style={{ ...base, backgroundColor: colors.stepWarning }}>
          <ExclamationIcon />
        </div>
      );
    case 'error':
      return (
        <div style={{ ...base, backgroundColor: colors.stepError }}>
          <XIcon />
        </div>
      );
  }
};

/* ------------------------------------------------------------------ */
/*  Timing badge                                                       */
/* ------------------------------------------------------------------ */

const TimingBadge: React.FC<{ durationMs: number }> = ({ durationMs }) => {
  const isSlow = durationMs > 500;
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 500,
        fontFamily: typography.fontMono,
        padding: '1px 6px',
        borderRadius: radius.full,
        backgroundColor: isSlow ? colors.warningLight : colors.successLight,
        color: isSlow ? colors.warning : colors.success,
        whiteSpace: 'nowrap',
      }}
    >
      {durationMs < 1000 ? `${Math.round(durationMs)}ms` : `${(durationMs / 1000).toFixed(1)}s`}
    </span>
  );
};

/* ------------------------------------------------------------------ */
/*  Expanded detail renderers per step name                            */
/* ------------------------------------------------------------------ */

function renderIntentClassification(detail: Record<string, unknown>): React.ReactNode {
  const intent = (detail.intent as string) || (detail.intent_type as string) || '';
  const measures = (detail.measures as string[]) || (detail.metrics as string[]) || [];
  const dimensions = (detail.dimensions as string[]) || [];
  const filters = (detail.filters as string[]) || [];
  const timeRange = (detail.time_range as string) || null;

  const chip = (label: string, bg: string, fg: string) => (
    <span
      key={label}
      style={{
        display: 'inline-block',
        fontSize: 11,
        fontWeight: 500,
        padding: '2px 8px',
        borderRadius: radius.full,
        backgroundColor: bg,
        color: fg,
        marginRight: 4,
        marginBottom: 4,
        fontFamily: typography.fontMono,
      }}
    >
      {label}
    </span>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {intent && (
        <div>
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
            {intent}
          </span>
        </div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 0 }}>
        {measures.map((m) => chip(m, colors.successLight, colors.success))}
        {dimensions.map((d) => chip(d, colors.infoLight, colors.amexBlue))}
        {filters.map((f) => chip(f, colors.warningLight, colors.warning))}
        {timeRange && chip(timeRange, '#F3E8FF', '#7C3AED')}
      </div>
    </div>
  );
}

function renderRetrieval(detail: Record<string, unknown>): React.ReactNode {
  const exploreCount = (detail.explore_count as number) || (detail.candidate_count as number) || 0;
  return (
    <div style={{ fontSize: 12, color: colors.textSecondary }}>
      Found <span style={{ fontWeight: 600, color: colors.textPrimary }}>{exploreCount}</span> candidate explores
    </div>
  );
}

function renderExploreScoring(detail: Record<string, unknown>): React.ReactNode {
  const explores = (detail.explores as ScoredExplore[]) || [];
  const confidence = detail.confidence as number | undefined;

  if (explores.length === 0) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 11,
            fontFamily: typography.fontPrimary,
          }}
        >
          <thead>
            <tr>
              {['Explore', 'Coverage', 'Score', 'Status'].map((h) => (
                <th
                  key={h}
                  style={{
                    textAlign: 'left',
                    fontWeight: 600,
                    fontSize: 10,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    color: colors.textTertiary,
                    padding: '4px 8px',
                    borderBottom: `1px solid ${colors.borderDefault}`,
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {explores.map((exp) => {
              const isWinner = exp.is_winner;
              const isNearMiss = !isWinner && exp.score > 0.5;
              return (
                <tr
                  key={exp.name}
                  style={{
                    backgroundColor: isWinner ? colors.successLight : 'transparent',
                    borderLeft: isWinner
                      ? `3px solid ${colors.success}`
                      : isNearMiss
                        ? `3px solid ${colors.warning}`
                        : '3px solid transparent',
                  }}
                >
                  <td
                    style={{
                      padding: '5px 8px',
                      fontWeight: isWinner ? 600 : 400,
                      color: colors.textPrimary,
                      fontFamily: typography.fontMono,
                      fontSize: 11,
                    }}
                  >
                    {exp.name}
                  </td>
                  <td style={{ padding: '5px 8px', fontFamily: typography.fontMono, fontSize: 11 }}>
                    {Math.round(exp.coverage * 100)}%
                  </td>
                  <td style={{ padding: '5px 8px', fontFamily: typography.fontMono, fontSize: 11 }}>
                    {exp.score.toFixed(2)}
                  </td>
                  <td style={{ padding: '5px 8px' }}>
                    {isWinner && (
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 600,
                          padding: '1px 6px',
                          borderRadius: radius.full,
                          backgroundColor: colors.success,
                          color: colors.amexWhite,
                        }}
                      >
                        WINNER
                      </span>
                    )}
                    {isNearMiss && (
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 600,
                          padding: '1px 6px',
                          borderRadius: radius.full,
                          backgroundColor: colors.warningLight,
                          color: colors.warning,
                        }}
                      >
                        NEAR MISS
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {confidence !== undefined && (
        <div
          style={{
            fontSize: 11,
            color: confidence >= 0.8 ? colors.success : confidence >= 0.6 ? colors.warning : colors.error,
            fontWeight: 600,
          }}
        >
          Confidence: {Math.round(confidence * 100)}%
        </div>
      )}
    </div>
  );
}

function renderFilterResolution(detail: Record<string, unknown>): React.ReactNode {
  const resolved = (detail.resolved as ResolvedFilter[]) || [];
  const mandatory = (detail.mandatory as MandatoryFilter[]) || [];
  const unresolved = (detail.unresolved as Array<{ field: string; user_said: string; reason?: string }>) || [];

  const passBadgeColor: Record<string, { bg: string; fg: string }> = {
    exact: { bg: colors.successLight, fg: colors.success },
    fuzzy: { bg: colors.infoLight, fg: colors.amexBlue },
    synonym: { bg: '#F3E8FF', fg: '#7C3AED' },
    semantic: { bg: colors.warningLight, fg: colors.warning },
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {resolved.map((f, i) => {
        const pc = passBadgeColor[f.pass] || { bg: colors.surfaceTertiary, fg: colors.textSecondary };
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
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
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M2 6H10M10 6L7 3M10 6L7 9" stroke={colors.textTertiary} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
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
                fontSize: 10,
                fontWeight: 600,
                padding: '1px 5px',
                borderRadius: radius.full,
                backgroundColor: pc.bg,
                color: pc.fg,
                textTransform: 'uppercase',
                letterSpacing: '0.03em',
              }}
            >
              {f.pass}
            </span>
          </div>
        );
      })}
      {mandatory.map((m, i) => (
        <div key={`m-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              fontSize: 11,
              fontFamily: typography.fontMono,
              color: colors.textSecondary,
            }}
          >
            {m.field}: {m.value}
          </span>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              padding: '1px 5px',
              borderRadius: radius.full,
              backgroundColor: colors.infoLight,
              color: colors.amexBlue,
              textTransform: 'uppercase',
            }}
          >
            auto-injected
          </span>
        </div>
      ))}
      {unresolved.map((u, i) => (
        <div key={`u-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              fontSize: 11,
              fontFamily: typography.fontMono,
              color: colors.error,
            }}
          >
            {u.field}: &quot;{u.user_said}&quot;
          </span>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              padding: '1px 5px',
              borderRadius: radius.full,
              backgroundColor: colors.errorLight,
              color: colors.error,
              textTransform: 'uppercase',
            }}
          >
            unresolved
          </span>
        </div>
      ))}
    </div>
  );
}

function renderSqlGeneration(detail: Record<string, unknown>): React.ReactNode {
  const sql = (detail.sql as string) || '';
  const explore = (detail.explore as string) || '';
  const model = (detail.model as string) || '';

  const handleCopy = () => {
    navigator.clipboard.writeText(sql).catch(() => {});
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ position: 'relative' }}>
        <pre
          style={{
            margin: 0,
            padding: '12px 14px',
            paddingRight: 60,
            backgroundColor: colors.amexDarkBlue,
            color: '#E2E8F0',
            fontFamily: typography.fontMono,
            fontSize: 11,
            lineHeight: 1.5,
            borderRadius: radius.md,
            overflowX: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {sql}
        </pre>
        <button
          onClick={handleCopy}
          style={{
            position: 'absolute',
            top: 6,
            right: 6,
            padding: '3px 8px',
            fontSize: 10,
            fontWeight: 500,
            fontFamily: typography.fontPrimary,
            backgroundColor: 'rgba(255,255,255,0.12)',
            color: '#CBD5E1',
            border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: radius.sm,
            cursor: 'pointer',
          }}
        >
          Copy SQL
        </button>
      </div>
      {(explore || model) && (
        <div style={{ fontSize: 11, color: colors.textSecondary }}>
          {model && <span>Model: <span style={{ fontFamily: typography.fontMono, fontWeight: 500 }}>{model}</span></span>}
          {model && explore && <span style={{ margin: '0 6px' }}>/</span>}
          {explore && <span>Explore: <span style={{ fontFamily: typography.fontMono, fontWeight: 500 }}>{explore}</span></span>}
        </div>
      )}
    </div>
  );
}

function renderResultsProcessing(detail: Record<string, unknown>): React.ReactNode {
  const rowCount = (detail.row_count as number) || 0;
  const truncated = (detail.truncated as boolean) || false;
  const totalRows = (detail.total_rows as number) || rowCount;

  return (
    <div style={{ fontSize: 12, color: colors.textSecondary }}>
      {truncated ? (
        <span>
          <span style={{ fontWeight: 600, color: colors.textPrimary }}>{rowCount}</span> rows
          <span style={{ color: colors.warning }}> (truncated from {totalRows})</span>
        </span>
      ) : (
        <span>
          <span style={{ fontWeight: 600, color: colors.textPrimary }}>{rowCount}</span> rows returned
        </span>
      )}
    </div>
  );
}

function renderResponseFormatting(detail: Record<string, unknown>): React.ReactNode {
  const answer = (detail.answer as string) || (detail.response as string) || '';
  const followUps = (detail.follow_ups as string[]) || (detail.suggestions as string[]) || [];

  const truncatedAnswer = answer.length > 100 ? answer.slice(0, 100) + '...' : answer;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {truncatedAnswer && (
        <div
          style={{
            fontSize: 12,
            color: colors.textPrimary,
            padding: '6px 10px',
            backgroundColor: colors.surfaceSecondary,
            borderRadius: radius.sm,
            borderLeft: `2px solid ${colors.amexBlue}`,
            lineHeight: 1.4,
          }}
        >
          {truncatedAnswer}
        </div>
      )}
      {followUps.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 2 }}>
          <span style={{ fontSize: 10, fontWeight: 600, color: colors.textTertiary, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Follow-ups
          </span>
          {followUps.map((f, i) => (
            <span key={i} style={{ fontSize: 11, color: colors.textSecondary, paddingLeft: 8 }}>
              {'\u2022'} {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Detail router                                                      */
/* ------------------------------------------------------------------ */

function renderDetail(step: PipelineStepType): React.ReactNode {
  if (!step.detail) return null;
  switch (step.name) {
    case 'intent_classification': return renderIntentClassification(step.detail);
    case 'retrieval': return renderRetrieval(step.detail);
    case 'explore_scoring': return renderExploreScoring(step.detail);
    case 'filter_resolution': return renderFilterResolution(step.detail);
    case 'sql_generation': return renderSqlGeneration(step.detail);
    case 'results_processing': return renderResultsProcessing(step.detail);
    case 'response_formatting': return renderResponseFormatting(step.detail);
    default: return null;
  }
}

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

const PipelineStep: React.FC<PipelineStepProps> = ({ step, isLast }) => {
  const [manualExpanded, setManualExpanded] = useState<boolean | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState(0);

  // Auto-expand when step becomes active
  useEffect(() => {
    if (step.status === 'active') {
      setManualExpanded(null); // reset manual override so auto-expand works
    }
  }, [step.status]);

  // Determine effective expanded state
  const isExpandable = step.status === 'complete' || step.status === 'warning' || step.status === 'error';
  const isAutoExpanded = step.status === 'active';
  const isExpanded = manualExpanded !== null ? manualExpanded : (isAutoExpanded || step.expanded);

  // Measure content for animation
  useEffect(() => {
    if (contentRef.current) {
      setContentHeight(contentRef.current.scrollHeight);
    }
  }, [step.detail, isExpanded]);

  const handleToggle = useCallback(() => {
    if (isExpandable) {
      setManualExpanded((prev) => (prev !== null ? !prev : !step.expanded));
    }
  }, [isExpandable, step.expanded]);

  // Connector line color
  const connectorColor = (): string => {
    if (step.status === 'complete') return colors.stepComplete;
    if (step.status === 'active') return colors.stepActive;
    return colors.borderDefault;
  };

  const connectorDashed = step.status !== 'complete' && step.status !== 'error' && step.status !== 'warning';

  const hasDetail = step.detail && Object.keys(step.detail).length > 0;
  const showExpanded = isExpanded && hasDetail;

  return (
    <div
      style={{
        position: 'relative',
        paddingLeft: 32,
        paddingBottom: isLast ? 0 : 4,
        minHeight: 38,
      }}
    >
      {/* Step indicator circle — positioned in the left column */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 1,
        }}
      >
        <StepIndicator status={step.status} />
      </div>

      {/* Vertical connector line */}
      {!isLast && (
        <div
          style={{
            position: 'absolute',
            left: 9,
            top: 22,
            bottom: 0,
            width: 0,
            borderLeft: `1.5px ${connectorDashed ? 'dashed' : 'solid'} ${connectorColor()}`,
          }}
        />
      )}

      {/* Step header */}
      <div
        onClick={handleToggle}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          cursor: isExpandable ? 'pointer' : 'default',
          userSelect: 'none',
          paddingTop: 0,
          paddingBottom: 4,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              fontFamily: typography.fontPrimary,
              color: step.status === 'pending' ? colors.textTertiary : colors.textPrimary,
              lineHeight: 1.2,
            }}
          >
            {step.label}
          </div>
          <div
            style={{
              fontSize: 11,
              color: colors.textSecondary,
              fontFamily: typography.fontPrimary,
              lineHeight: 1.3,
              marginTop: 1,
            }}
          >
            {step.message || step.subLabel}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          {step.durationMs !== undefined && step.durationMs > 0 && (
            <TimingBadge durationMs={step.durationMs} />
          )}
          {isExpandable && hasDetail && <ChevronIcon expanded={!!showExpanded} />}
        </div>
      </div>

      {/* Expandable detail content with animated height */}
      <div
        style={{
          overflow: 'hidden',
          transition: 'max-height 250ms ease, opacity 200ms ease',
          maxHeight: showExpanded ? contentHeight + 20 : 0,
          opacity: showExpanded ? 1 : 0,
        }}
      >
        <div
          ref={contentRef}
          style={{
            paddingTop: 4,
            paddingBottom: 8,
            paddingLeft: 0,
            paddingRight: 4,
          }}
        >
          {renderDetail(step)}
        </div>
      </div>
    </div>
  );
};

export default PipelineStep;
