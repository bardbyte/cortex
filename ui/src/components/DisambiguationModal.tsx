import React, { useState, useCallback, useEffect } from 'react';
import { colors, typography, radius, shadows } from '../tokens';
import type { DisambiguateOption } from '../types';

interface DisambiguationModalProps {
  options: DisambiguateOption[];
  onSelect: (explore: string) => void;
  open: boolean;
}

function confidenceColor(confidence: number): { bg: string; text: string; dot: string } {
  if (confidence >= 80) return { bg: colors.successLight, text: colors.success, dot: colors.success };
  if (confidence >= 60) return { bg: colors.warningLight, text: colors.warning, dot: colors.warning };
  return { bg: colors.errorLight, text: colors.error, dot: colors.error };
}

const DisambiguationModal: React.FC<DisambiguationModalProps> = ({ options, onSelect, open }) => {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // No explicit close callback; parent controls open state
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open]);

  const handleSelect = useCallback(
    (explore: string) => {
      onSelect(explore);
    },
    [onSelect],
  );

  if (!open) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 23, 90, 0.4)',
        backdropFilter: 'blur(4px)',
        WebkitBackdropFilter: 'blur(4px)',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 480,
          backgroundColor: colors.surfacePrimary,
          borderRadius: radius.xl,
          boxShadow: shadows.lg,
          padding: 32,
          fontFamily: typography.fontPrimary,
          animation: 'fadeInScale 0.2s ease-out',
        }}
      >
        {/* Header */}
        <h2
          style={{
            margin: 0,
            fontSize: 20,
            fontWeight: 600,
            color: colors.textPrimary,
            marginBottom: 4,
          }}
        >
          Which data source matches your question?
        </h2>
        <p
          style={{
            margin: 0,
            fontSize: 14,
            color: colors.textSecondary,
            marginBottom: 20,
          }}
        >
          We found multiple matching explores. Select the best fit.
        </p>

        {/* Option cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {options.map((opt, idx) => {
            const cc = confidenceColor(opt.confidence);
            const isHovered = hoveredIdx === idx;
            return (
              <button
                key={opt.explore}
                onClick={() => handleSelect(opt.explore)}
                onMouseEnter={() => setHoveredIdx(idx)}
                onMouseLeave={() => setHoveredIdx(null)}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  justifyContent: 'space-between',
                  gap: 12,
                  width: '100%',
                  padding: 16,
                  border: `1.5px solid ${isHovered ? colors.amexBlue : colors.borderDefault}`,
                  borderRadius: radius.lg,
                  backgroundColor: isHovered ? colors.infoLight : colors.surfacePrimary,
                  cursor: 'pointer',
                  textAlign: 'left',
                  fontFamily: typography.fontPrimary,
                  transition: 'all 0.15s ease',
                  outline: 'none',
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      color: colors.textPrimary,
                      marginBottom: 4,
                    }}
                  >
                    {opt.explore}
                  </div>
                  <div
                    style={{
                      fontSize: 13,
                      color: colors.textSecondary,
                      lineHeight: 1.4,
                    }}
                  >
                    {opt.description}
                  </div>
                </div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    backgroundColor: cc.bg,
                    color: cc.text,
                    padding: '4px 10px',
                    borderRadius: radius.full,
                    fontSize: 12,
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      backgroundColor: cc.dot,
                      display: 'inline-block',
                    }}
                  />
                  {opt.confidence}% match
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Inline keyframe animation */}
      <style>{`
        @keyframes fadeInScale {
          from { opacity: 0; transform: scale(0.95); }
          to { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
};

export default DisambiguationModal;
