import React, { useState } from 'react';
import { colors, typography, radius, shadows } from '../tokens';
import type { ResolvedFilter, MandatoryFilter } from '../types';

/* ── Props ───────────────────────────────────────────── */

export interface CollapseBadgeProps {
  exploreName?: string;
  confidence?: number; // 0-100
  totalDurationMs?: number;
  filters?: {
    resolved: ResolvedFilter[];
    mandatory: MandatoryFilter[];
  };
  onToggleDetail: () => void;
  detailExpanded: boolean;
}

/* ── Helpers ──────────────────────────────────────────── */

function confidenceColor(confidence: number): string {
  if (confidence >= 80) return colors.success;
  if (confidence >= 60) return colors.warning;
  return colors.error;
}

function confidenceBgColor(confidence: number): string {
  if (confidence >= 80) return colors.successLight;
  if (confidence >= 60) return colors.warningLight;
  return colors.errorLight;
}

function formatDuration(ms: number | undefined): string {
  if (!ms) return '\u2014';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Extract short filter summaries from resolved + mandatory filters */
function filterSummaries(filters?: { resolved: ResolvedFilter[]; mandatory: MandatoryFilter[] }): string[] {
  if (!filters) return [];
  const items: string[] = [];
  filters.resolved.forEach((f) => items.push(f.resolved_to));
  filters.mandatory.forEach((f) => items.push(f.value));
  return items;
}

/* ── Component ───────────────────────────────────────── */

const CollapseBadge: React.FC<CollapseBadgeProps> = ({
  exploreName,
  confidence,
  totalDurationMs,
  filters,
  onToggleDetail,
  detailExpanded,
}) => {
  const [hovered, setHovered] = useState(false);

  const summaries = filterSummaries(filters);
  const durationLabel = formatDuration(totalDurationMs);

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        height: 36,
        backgroundColor: colors.surfaceSecondary,
        borderRadius: radius.lg,
        padding: '0 12px',
        border: `1px solid ${colors.borderDefault}`,
        fontFamily: typography.fontPrimary,
        boxShadow: hovered ? shadows.sm : 'none',
        transition: 'box-shadow 0.15s ease',
        gap: 8,
        minWidth: 0,
      }}
    >
      {/* ── Left side ─────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          minWidth: 0,
          overflow: 'hidden',
        }}
      >
        {/* Green checkmark */}
        <span
          style={{
            fontSize: 14,
            color: colors.success,
            flexShrink: 0,
            lineHeight: 1,
          }}
        >
          {'\u2713'}
        </span>

        {/* Explore name */}
        {exploreName && (
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: colors.textPrimary,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {exploreName}
          </span>
        )}

        {/* Filter summaries */}
        {summaries.length > 0 && (
          <>
            {exploreName && (
              <span style={{ fontSize: 11, color: colors.textTertiary, flexShrink: 0, userSelect: 'none' }}>
                {'\u00B7'}
              </span>
            )}
            {summaries.map((s, i) => (
              <React.Fragment key={`${s}-${i}`}>
                <span
                  style={{
                    fontSize: 11,
                    color: colors.textSecondary,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {s}
                </span>
                {i < summaries.length - 1 && (
                  <span style={{ fontSize: 11, color: colors.textTertiary, flexShrink: 0, userSelect: 'none' }}>
                    {'\u00B7'}
                  </span>
                )}
              </React.Fragment>
            ))}
          </>
        )}
      </div>

      {/* ── Right side ────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          flexShrink: 0,
        }}
      >
        {/* Confidence badge */}
        {confidence != null && (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '2px 8px',
              borderRadius: radius.full,
              backgroundColor: confidenceBgColor(confidence),
              fontSize: 11,
              fontWeight: 600,
              fontFamily: typography.fontMono,
              color: confidenceColor(confidence),
              whiteSpace: 'nowrap',
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                backgroundColor: confidenceColor(confidence),
                display: 'inline-block',
              }}
            />
            {confidence}% match
          </span>
        )}

        {/* Duration */}
        <span
          style={{
            fontSize: 11,
            fontFamily: typography.fontMono,
            color: colors.textTertiary,
            whiteSpace: 'nowrap',
          }}
        >
          {durationLabel}
        </span>

        {/* Toggle link */}
        <button
          onClick={onToggleDetail}
          aria-expanded={detailExpanded}
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            margin: 0,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 3,
            color: colors.textLink,
            fontSize: 12,
            fontWeight: 500,
            fontFamily: typography.fontPrimary,
            whiteSpace: 'nowrap',
          }}
        >
          Query details
          <span
            style={{
              fontSize: 11,
              display: 'inline-block',
              transform: detailExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
              transition: 'transform 0.2s ease',
              lineHeight: 1,
            }}
          >
            {'\u25BE'}
          </span>
        </button>
      </div>
    </div>
  );
};

export default CollapseBadge;
