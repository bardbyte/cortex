import { useState } from 'react';
import type { CSSProperties } from 'react';
import { colors, typography, radius } from '../../../tokens';

interface LayerCardProps {
  layerNumber: number;
  title: string;
  subtitle: string;
  tooltip: string;
  children: React.ReactNode;
  onActivate?: () => void;
  isActive?: boolean;
  shimmer?: boolean;
}

const BADGE_COLORS: Record<number, { bg: string; fg: string }> = {
  1: { bg: '#F3F4F6', fg: '#6B7280' },
  2: { bg: '#EBF4FF', fg: '#006FCF' },
  3: { bg: '#ECFDF5', fg: '#008767' },
};

export default function LayerCard({
  layerNumber,
  title,
  subtitle,
  tooltip,
  children,
  onActivate,
  isActive = false,
  shimmer = false,
}: LayerCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  const badgeColor = BADGE_COLORS[layerNumber] || BADGE_COLORS[1];

  const cardStyle: CSSProperties = {
    background: colors.surfacePrimary,
    border: `1px solid ${isActive ? '#006FCF' : colors.borderDefault}`,
    borderRadius: radius.lg,
    padding: '24px',
    cursor: 'pointer',
    transition: 'border-color 200ms ease, box-shadow 200ms ease',
    boxShadow: isActive ? '0 0 0 3px rgba(0, 111, 207, 0.12)' : 'none',
    position: 'relative',
    animation: shimmer ? 'layerShimmer 600ms ease' : undefined,
  };

  const badgeStyle: CSSProperties = {
    display: 'inline-block',
    padding: '2px 10px',
    borderRadius: '99px',
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    fontFamily: typography.fontPrimary,
    background: badgeColor.bg,
    color: badgeColor.fg,
  };

  const titleStyle: CSSProperties = {
    fontSize: '16px',
    fontWeight: 600,
    color: colors.textPrimary,
    fontFamily: typography.fontPrimary,
    marginTop: '12px',
  };

  const subtitleStyle: CSSProperties = {
    fontSize: '13px',
    color: colors.textSecondary,
    fontFamily: typography.fontPrimary,
    marginTop: '4px',
    marginBottom: '16px',
  };

  const tooltipBtnStyle: CSSProperties = {
    position: 'absolute',
    top: '16px',
    right: '16px',
    width: '18px',
    height: '18px',
    borderRadius: '50%',
    background: 'none',
    border: `1px solid ${colors.textTertiary}`,
    color: colors.textTertiary,
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 0,
  };

  const tooltipStyle: CSSProperties = {
    position: 'absolute',
    top: '40px',
    right: '16px',
    background: '#00175A',
    color: '#FFFFFF',
    fontSize: '13px',
    fontFamily: typography.fontPrimary,
    padding: '10px 14px',
    borderRadius: radius.md,
    maxWidth: '260px',
    boxShadow: '0 4px 16px rgba(0, 23, 90, 0.20)',
    zIndex: 10,
    lineHeight: '1.5',
  };

  return (
    <div style={cardStyle} onClick={onActivate}>
      <button
        style={tooltipBtnStyle}
        onClick={(e) => { e.stopPropagation(); setShowTooltip(!showTooltip); }}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        aria-label="More info"
      >
        ?
      </button>
      {showTooltip && <div style={tooltipStyle}>{tooltip}</div>}
      <span style={badgeStyle}>Layer {String(layerNumber).padStart(2, '0')}</span>
      <div style={titleStyle}>{title}</div>
      <div style={subtitleStyle}>{subtitle}</div>
      {children}
    </div>
  );
}
