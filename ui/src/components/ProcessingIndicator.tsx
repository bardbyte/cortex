import React, { useEffect, useRef, useState } from 'react';
import { colors, typography } from '../tokens';
import type { PipelineStep, ResolvedFilter, MandatoryFilter } from '../types';
import type { IntentEchoProps } from './IntentEcho';
import RadixMark from './RadixMark';

/* ── Props ───────────────────────────────────────────── */

export interface ProcessingIndicatorProps {
  steps: PipelineStep[];
  entities: IntentEchoProps['entities'];
  filters: {
    resolved: ResolvedFilter[];
    mandatory: MandatoryFilter[];
  };
  exploreName?: string;
}

/* ── Keyframe injection (once) ───────────────────────── */

const KEYFRAME_ID = 'cortex-processing-indicator-keyframes';

function ensureKeyframes(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(KEYFRAME_ID)) return;
  const style = document.createElement('style');
  style.id = KEYFRAME_ID;
  style.textContent = `
    @keyframes cortexFadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes cortexTextFadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
  `;
  document.head.appendChild(style);
}

/* ── Filter pass → color ─────────────────────────────── */

function filterPassColor(pass: string): string {
  switch (pass) {
    case 'exact':
    case 'fuzzy':
      return colors.success;
    case 'synonym':
    case 'semantic':
      return colors.warning;
    case 'llm':
      return colors.error;
    default:
      return colors.textPrimary;
  }
}

/* ── Helpers ──────────────────────────────────────────── */

function stepStatus(steps: PipelineStep[], name: string): 'pending' | 'active' | 'complete' | 'warning' | 'error' | undefined {
  const s = steps.find((st) => st.name === name);
  return s?.status;
}

function isActiveOrLater(status: string | undefined): boolean {
  return status === 'active' || status === 'complete';
}

/* ── Detect phase ────────────────────────────────────── */

type Phase = 1 | 2 | 3;

function detectPhase(steps: PipelineStep[]): Phase {
  const sqlStatus = stepStatus(steps, 'sql_generation');
  if (sqlStatus === 'active' || sqlStatus === 'complete') return 3;

  const retrievalStatus = stepStatus(steps, 'retrieval');
  const scoringStatus = stepStatus(steps, 'explore_scoring');
  const filterStatus = stepStatus(steps, 'filter_resolution');
  if (isActiveOrLater(retrievalStatus) || isActiveOrLater(scoringStatus) || isActiveOrLater(filterStatus)) return 2;

  return 1;
}

/* ── Main component ──────────────────────────────────── */

const ProcessingIndicator: React.FC<ProcessingIndicatorProps> = ({
  steps,
  entities,
  filters,
  exploreName,
}) => {
  const prevPhaseRef = useRef<Phase>(1);
  const [textKey, setTextKey] = useState(0);

  useEffect(() => {
    ensureKeyframes();
  }, []);

  const phase = detectPhase(steps);

  // Trigger re-animation on phase change
  useEffect(() => {
    if (phase !== prevPhaseRef.current) {
      prevPhaseRef.current = phase;
      setTextKey((k) => k + 1);
    }
  }, [phase]);

  const intentComplete = stepStatus(steps, 'intent_classification') === 'complete';
  const scoringComplete = stepStatus(steps, 'explore_scoring') === 'complete';
  const filterActive = stepStatus(steps, 'filter_resolution') === 'active';
  const filterComplete = stepStatus(steps, 'filter_resolution') === 'complete';
  const showFilters = (filterActive || filterComplete) && filters.resolved.length > 0;

  /* Primary metric name for parameterized text */
  const primaryMetric = entities?.metrics?.[0] ?? null;

  /* ── Phase text ────────────── */
  let messageText: string;
  let subMessage: string | null = null;

  switch (phase) {
    case 1:
      messageText = 'Understanding your question...';
      break;
    case 2:
      messageText = primaryMetric
        ? `Searching for ${primaryMetric} data...`
        : 'Searching for relevant data...';
      if (scoringComplete && exploreName) {
        subMessage = `Found relevant data in ${exploreName}`;
      }
      break;
    case 3:
      messageText = exploreName
        ? `Building query against ${exploreName}...`
        : 'Building the query...';
      break;
  }

  /* ── Entity chips (inline after Phase 1 completion) ── */
  const showEntityChips = phase === 1 && intentComplete && entities;
  const entityChips: { label: string; color: string }[] = [];
  if (showEntityChips && entities) {
    entities.metrics.forEach((m) => entityChips.push({ label: m, color: colors.amexBlue }));
    entities.dimensions.forEach((d) => entityChips.push({ label: d, color: colors.textPrimary }));
    entities.filters.forEach((f) => entityChips.push({ label: f, color: colors.warning }));
    if (entities.time_range) entityChips.push({ label: entities.time_range, color: colors.textSecondary });
  }

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <RadixMark size={32} animated />
      <div style={{ flex: 1, minWidth: 0, paddingTop: 4 }}>
        {/* Primary message */}
        <div
          key={`msg-${textKey}`}
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 8,
            animation: 'cortexTextFadeIn 250ms ease forwards',
          }}
        >
          <span
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: colors.textSecondary,
              fontFamily: typography.fontPrimary,
            }}
          >
            {messageText}
          </span>

          {/* Inline entity chips after intent completes in Phase 1 */}
          {showEntityChips && entityChips.length > 0 && entityChips.map((chip, i) => (
            <span
              key={`chip-${i}`}
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: chip.color,
                fontFamily: typography.fontPrimary,
                whiteSpace: 'nowrap',
              }}
            >
              {chip.label}
              {i < entityChips.length - 1 && (
                <span style={{ color: colors.textTertiary, margin: '0 4px', fontWeight: 400 }}>{'\u00B7'}</span>
              )}
            </span>
          ))}
        </div>

        {/* Sub-message (e.g. "Found relevant data in ...") */}
        {subMessage && (
          <div
            key={`sub-${subMessage}`}
            style={{
              marginTop: 4,
              fontSize: 13,
              fontWeight: 500,
              color: colors.success,
              fontFamily: typography.fontPrimary,
              animation: 'cortexTextFadeIn 250ms ease forwards',
            }}
          >
            {subMessage}
          </div>
        )}

        {/* Filter translation sub-display */}
        {showFilters && (
          <div style={{ marginTop: 10, paddingLeft: 2 }}>
            <span
              style={{
                fontSize: 12,
                fontWeight: 500,
                color: colors.textSecondary,
                fontFamily: typography.fontPrimary,
                display: 'block',
                marginBottom: 6,
              }}
            >
              Translating filters:
            </span>
            {filters.resolved.map((f, i) => (
              <div
                key={`${f.field}-${i}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  marginBottom: 4,
                  paddingLeft: 12,
                  animation: `cortexFadeIn 200ms ease ${i * 80}ms forwards`,
                  opacity: 0,
                }}
              >
                <span
                  style={{
                    fontSize: 12,
                    color: colors.textSecondary,
                    fontFamily: typography.fontPrimary,
                    fontStyle: 'italic',
                    minWidth: 0,
                  }}
                >
                  &ldquo;{f.user_said}&rdquo;
                </span>
                <span
                  style={{
                    fontSize: 11,
                    color: colors.textTertiary,
                    fontFamily: typography.fontPrimary,
                    flexShrink: 0,
                  }}
                >
                  {'\u2192'}
                </span>
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: filterPassColor(f.pass),
                    fontFamily: typography.fontMono,
                    minWidth: 0,
                  }}
                >
                  {f.resolved_to}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ProcessingIndicator;
