import React, { useEffect, useState } from 'react';
import { colors, typography } from '../tokens';

/* ── Types ───────────────────────────────────────────── */

export interface IntentEchoEntities {
  intent: string;
  metrics: string[];
  dimensions: string[];
  filters: string[];
  time_range: string | null;
}

export interface IntentEchoProps {
  entities: IntentEchoEntities | null;
  isFollowUp?: boolean;
}

/* ── Component ───────────────────────────────────────── */

const IntentEcho: React.FC<IntentEchoProps> = ({ entities, isFollowUp = false }) => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (entities) {
      // Trigger fade-in on next frame
      const raf = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(raf);
    }
    setVisible(false);
  }, [entities]);

  if (!entities) return null;

  /* Collect all entity chips with their category */
  const chips: { label: string; category: 'metric' | 'dimension' | 'filter' | 'time_range' }[] = [];

  entities.metrics.forEach((m) => chips.push({ label: m, category: 'metric' }));
  entities.dimensions.forEach((d) => chips.push({ label: d, category: 'dimension' }));
  entities.filters.forEach((f) => chips.push({ label: f, category: 'filter' }));
  if (entities.time_range) {
    chips.push({ label: entities.time_range, category: 'time_range' });
  }

  /* If fewer than 2 total items, return null */
  if (chips.length < 2) return null;

  /* Color mapping */
  function chipStyle(category: 'metric' | 'dimension' | 'filter' | 'time_range'): React.CSSProperties {
    switch (category) {
      case 'metric':
        return { color: colors.amexBlue, fontWeight: 500 };
      case 'dimension':
        return { color: colors.textPrimary, fontWeight: 700 };
      case 'filter':
        return { color: colors.warning, fontWeight: 500 };
      case 'time_range':
        return { color: colors.textSecondary, fontWeight: 500 };
    }
  }

  return (
    <div
      style={{
        display: 'inline-flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 0,
        opacity: visible ? 1 : 0,
        transition: 'opacity 150ms ease',
        lineHeight: 1.4,
      }}
    >
      <span
        style={{
          fontSize: 11,
          color: colors.textSecondary,
          fontFamily: typography.fontPrimary,
          fontWeight: 400,
          marginRight: 6,
          whiteSpace: 'nowrap',
        }}
      >
        You asked about:
      </span>
      {chips.map((chip, i) => {
        const style = chipStyle(chip.category);
        const isInherited = isFollowUp && (chip.category === 'dimension' || chip.category === 'time_range' || chip.category === 'filter');
        const label = isInherited ? `[${chip.label}]` : chip.label;

        return (
          <React.Fragment key={`${chip.category}-${chip.label}-${i}`}>
            <span
              style={{
                fontSize: 11,
                fontFamily: typography.fontPrimary,
                whiteSpace: 'nowrap',
                ...style,
                ...(isInherited ? { opacity: 0.6 } : {}),
              }}
            >
              {label}
            </span>
            {i < chips.length - 1 && (
              <span
                style={{
                  fontSize: 11,
                  color: colors.textTertiary,
                  fontFamily: typography.fontPrimary,
                  margin: '0 6px',
                  userSelect: 'none',
                }}
              >
                {'\u00B7'}
              </span>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};

export default IntentEcho;
