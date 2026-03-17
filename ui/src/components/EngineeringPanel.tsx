import React from 'react';
import { colors, typography, radius } from '../tokens';
import type { PipelineStep as PipelineStepType } from '../types';
import PipelineStepComponent from './PipelineStep';

interface EngineeringPanelProps {
  steps: PipelineStepType[];
  overallConfidence: number;
  totalDurationMs: number;
  isProcessing: boolean;
}

/* ------------------------------------------------------------------ */
/*  Keyframe injection (pulse animation for Processing pill)           */
/* ------------------------------------------------------------------ */

const PULSE_STYLE_ID = 'engineering-panel-keyframes';

function ensurePulseKeyframes(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(PULSE_STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = PULSE_STYLE_ID;
  style.textContent = `
    @keyframes cortex-pulse {
      0%, 100% { opacity: 1; }
      50%      { opacity: 0.5; }
    }
  `;
  document.head.appendChild(style);
}

/* ------------------------------------------------------------------ */
/*  Branching Nodes Icon (pipeline trace icon)                         */
/* ------------------------------------------------------------------ */

const BranchingNodesIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <circle cx="4" cy="4" r="1.8" stroke={colors.textSecondary} strokeWidth="1.3" />
    <circle cx="4" cy="14" r="1.8" stroke={colors.textSecondary} strokeWidth="1.3" />
    <circle cx="14" cy="9" r="1.8" stroke={colors.textSecondary} strokeWidth="1.3" />
    <path d="M4 5.8V12.2" stroke={colors.textSecondary} strokeWidth="1.3" />
    <path d="M5.5 5C7 5 12 6.5 12.2 9" stroke={colors.textSecondary} strokeWidth="1.3" strokeLinecap="round" />
    <path d="M5.5 13C7 13 12 11.5 12.2 9" stroke={colors.textSecondary} strokeWidth="1.3" strokeLinecap="round" />
  </svg>
);

/* ------------------------------------------------------------------ */
/*  State Pill                                                         */
/* ------------------------------------------------------------------ */

type PanelState = 'idle' | 'processing' | 'complete' | 'error';

function derivePanelState(steps: PipelineStepType[], isProcessing: boolean): PanelState {
  if (steps.some((s) => s.status === 'error')) return 'error';
  if (isProcessing || steps.some((s) => s.status === 'active')) return 'processing';
  if (steps.every((s) => s.status === 'complete' || s.status === 'warning')) {
    // Only "complete" if at least one step ran
    if (steps.some((s) => s.status === 'complete' || s.status === 'warning')) return 'complete';
  }
  return 'idle';
}

const stateConfig: Record<PanelState, { label: string; bg: string; fg: string; animated: boolean }> = {
  idle: { label: 'Idle', bg: colors.surfaceTertiary, fg: colors.textTertiary, animated: false },
  processing: { label: 'Processing', bg: colors.infoLight, fg: colors.amexBlue, animated: true },
  complete: { label: 'Complete', bg: colors.successLight, fg: colors.success, animated: false },
  error: { label: 'Error', bg: colors.errorLight, fg: colors.error, animated: false },
};

const StatePill: React.FC<{ state: PanelState }> = ({ state }) => {
  React.useEffect(() => { ensurePulseKeyframes(); }, []);

  const cfg = stateConfig[state];
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        padding: '2px 10px',
        borderRadius: radius.full,
        backgroundColor: cfg.bg,
        color: cfg.fg,
        fontFamily: typography.fontPrimary,
        letterSpacing: '0.02em',
        animation: cfg.animated ? 'cortex-pulse 1.5s ease-in-out infinite' : 'none',
        whiteSpace: 'nowrap',
      }}
    >
      {cfg.label}
    </span>
  );
};

/* ------------------------------------------------------------------ */
/*  Confidence color helper                                            */
/* ------------------------------------------------------------------ */

function confidenceColor(value: number): string {
  if (value >= 0.8) return colors.success;
  if (value >= 0.6) return colors.warning;
  return colors.error;
}

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

const EngineeringPanel: React.FC<EngineeringPanelProps> = ({
  steps,
  overallConfidence,
  totalDurationMs,
  isProcessing,
}) => {
  const panelState = derivePanelState(steps, isProcessing);

  const formatDuration = (ms: number): string => {
    if (ms <= 0) return '\u2014';
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  // Gather per-step confidence values for breakdown
  const confidenceBreakdown = steps
    .filter((s) => s.detail?.confidence !== undefined && (s.status === 'complete' || s.status === 'warning'))
    .map((s) => ({
      label: s.label,
      value: s.detail!.confidence as number,
    }));

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
        height: '100%',
        backgroundColor: colors.surfacePrimary,
        borderLeft: `1px solid ${colors.borderDefault}`,
        fontFamily: typography.fontPrimary,
        overflow: 'hidden',
      }}
    >
      {/* ---- Panel Header (52px) ---- */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          height: 52,
          minHeight: 52,
          padding: '0 16px',
          backgroundColor: colors.surfaceSecondary,
          borderBottom: `1px solid ${colors.borderDefault}`,
          flexShrink: 0,
        }}
      >
        <BranchingNodesIcon />
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: colors.textPrimary,
            whiteSpace: 'nowrap',
          }}
        >
          Pipeline Trace
        </span>
        <StatePill state={panelState} />
        <div style={{ flex: 1 }} />
        <span
          style={{
            fontSize: 12,
            fontFamily: typography.fontMono,
            color: colors.textSecondary,
            whiteSpace: 'nowrap',
          }}
        >
          Total: {formatDuration(totalDurationMs)}
        </span>
      </div>

      {/* ---- Scrollable Step List ---- */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          padding: '16px 16px 8px 16px',
        }}
      >
        {steps.map((step, idx) => (
          <PipelineStepComponent
            key={step.name}
            step={step}
            isLast={idx === steps.length - 1}
          />
        ))}

        {steps.length === 0 && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '48px 16px',
              color: colors.textTertiary,
              fontSize: 13,
              textAlign: 'center',
              gap: 8,
            }}
          >
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" opacity={0.4}>
              <circle cx="16" cy="16" r="14" stroke={colors.textTertiary} strokeWidth="1.5" strokeDasharray="4 3" />
              <path d="M16 10V16L20 18" stroke={colors.textTertiary} strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <span>Ask a question to see the pipeline trace</span>
          </div>
        )}
      </div>

      {/* ---- Panel Footer (56px) ---- */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: 56,
          minHeight: 56,
          padding: '0 16px',
          borderTop: `1px solid ${colors.borderDefault}`,
          backgroundColor: colors.surfaceSecondary,
          flexShrink: 0,
        }}
      >
        {/* Left: overall confidence */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: colors.textTertiary,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              lineHeight: 1,
            }}
          >
            Overall Confidence
          </span>
          <span
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: overallConfidence > 0 ? confidenceColor(overallConfidence) : colors.textTertiary,
              fontFamily: typography.fontMono,
              lineHeight: 1.3,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {overallConfidence > 0 ? `${Math.round(overallConfidence * 100)}%` : '\u2014'}
          </span>
        </div>

        {/* Right: mini breakdown */}
        {confidenceBreakdown.length > 0 && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-end',
              gap: 1,
              maxWidth: '50%',
            }}
          >
            {confidenceBreakdown.slice(0, 3).map((entry) => (
              <div
                key={entry.label}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 10,
                  fontFamily: typography.fontPrimary,
                  color: colors.textSecondary,
                  whiteSpace: 'nowrap',
                }}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 100 }}>
                  {entry.label}
                </span>
                <span
                  style={{
                    fontWeight: 600,
                    fontFamily: typography.fontMono,
                    color: confidenceColor(entry.value),
                  }}
                >
                  {Math.round(entry.value * 100)}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default EngineeringPanel;
