import { useState, useEffect } from 'react';
import type { CSSProperties } from 'react';
import { typography } from '../../../tokens';

interface ScoreBarProps {
  score: number;
  label: string;
  note?: string;
  isTop?: boolean;
  animate?: boolean;
}

export default function ScoreBar({ score, label, note, isTop = false, animate = true }: ScoreBarProps) {
  const [width, setWidth] = useState(animate ? 0 : score * 100);

  useEffect(() => {
    if (animate) {
      const timer = setTimeout(() => setWidth(score * 100), 100);
      return () => clearTimeout(timer);
    }
  }, [score, animate]);

  const rowStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '6px 0',
  };

  const labelStyle: CSSProperties = {
    fontSize: '13px',
    fontFamily: typography.fontMono,
    color: isTop ? '#111827' : '#6B7280',
    minWidth: '200px',
    fontWeight: isTop ? 600 : 400,
  };

  const barContainerStyle: CSSProperties = {
    flex: 1,
    height: '8px',
    background: '#F3F4F6',
    borderRadius: '4px',
    overflow: 'hidden',
  };

  const barFillStyle: CSSProperties = {
    height: '100%',
    width: `${width}%`,
    background: isTop ? '#006FCF' : 'rgba(0, 111, 207, 0.45)',
    borderRadius: '4px',
    transition: animate ? 'width 600ms ease-out' : undefined,
  };

  const scoreStyle: CSSProperties = {
    fontSize: '13px',
    fontFamily: typography.fontMono,
    fontWeight: 600,
    color: isTop ? '#006FCF' : '#9CA3AF',
    minWidth: '36px',
    textAlign: 'right',
    fontFeatureSettings: typography.tabularNums,
  };

  const noteStyle: CSSProperties = {
    fontSize: '11px',
    color: '#6B7280',
    fontFamily: typography.fontPrimary,
    fontStyle: 'italic',
  };

  return (
    <div>
      <div style={rowStyle}>
        <span style={labelStyle}>{label}</span>
        <div style={barContainerStyle}>
          <div style={barFillStyle} />
        </div>
        <span style={scoreStyle}>{score.toFixed(2)}</span>
      </div>
      {note && <div style={{ ...noteStyle, marginLeft: '212px', marginTop: '-2px' }}>{note}</div>}
    </div>
  );
}
