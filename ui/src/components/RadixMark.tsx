import React, { useEffect } from 'react';
import { colors } from '../tokens';

/**
 * Radix logomark — a stylized radical symbol (√).
 *
 * "Radix" is Latin for "root" and the base of a number system.
 * The mark is a geometric √ inside a circle: the short spur,
 * the ascending stroke, and the vinculum (horizontal bar).
 *
 * Static: white √ on Amex blue circle.
 * Animated: drawing √ + spinning outer ring + pulsing glow.
 */

interface RadixMarkProps {
  size?: number;
  animated?: boolean;
}

/* ── Keyframe injection ──────────────────────────────── */

const KEYFRAME_ID = 'radix-mark-keyframes';

function ensureKeyframes(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(KEYFRAME_ID)) return;
  const style = document.createElement('style');
  style.id = KEYFRAME_ID;
  style.textContent = `
    @keyframes radixDraw {
      0%   { stroke-dashoffset: 100; }
      30%  { stroke-dashoffset: 0; }
      60%  { stroke-dashoffset: 0; }
      100% { stroke-dashoffset: -100; }
    }
    @keyframes radixSpin {
      0%   { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    @keyframes radixGlow {
      0%, 100% { transform: scale(1); opacity: 0.35; }
      50%      { transform: scale(1.35); opacity: 0.7; }
    }
  `;
  document.head.appendChild(style);
}

/* ── Component ───────────────────────────────────────── */

const RadixMark: React.FC<RadixMarkProps> = ({ size = 32, animated = false }) => {
  useEffect(() => {
    if (animated) ensureKeyframes();
  }, [animated]);

  return (
    <div
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {/* Pulsing glow ring (animated only) */}
      {animated && (
        <div
          style={{
            position: 'absolute',
            inset: -5,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(0, 111, 207, 0.2), transparent 70%)',
            animation: 'radixGlow 2.4s ease-in-out infinite',
            pointerEvents: 'none',
          }}
        />
      )}

      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        style={{ display: 'block', position: 'relative', overflow: 'visible' }}
      >
        {/* Spinner ring (animated only) */}
        {animated && (
          <circle
            cx="16"
            cy="16"
            r="14.5"
            stroke={colors.amexBlue}
            strokeWidth="1.5"
            fill="none"
            strokeDasharray="22 69"
            strokeLinecap="round"
            opacity="0.7"
            style={{
              transformOrigin: 'center center',
              animation: 'radixSpin 1.4s linear infinite',
            }}
          />
        )}

        {/* Background circle */}
        <circle
          cx="16"
          cy="16"
          r={animated ? 12.5 : 16}
          fill={colors.amexBlue}
        />

        {/*
          Radical mark √
          Three segments: spur (10.5,16.5→14,22), ascender (14,22→21.5,10), vinculum (21.5,10→25,10)
        */}
        <path
          d="M10.5 16.5 L14 22 L21.5 10 H25"
          stroke={colors.amexWhite}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
          pathLength={animated ? 100 : undefined}
          strokeDasharray={animated ? '100' : undefined}
          strokeDashoffset={animated ? 100 : undefined}
          style={animated ? { animation: 'radixDraw 2.4s ease-in-out infinite' } : undefined}
        />
      </svg>
    </div>
  );
};

export default RadixMark;
