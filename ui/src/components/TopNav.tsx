import { useState, useEffect, useRef } from 'react';
import type { CSSProperties } from 'react';
import type { ViewMode } from '../types';
import { colors, typography, radius } from '../tokens';

interface TopNavProps {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
}

const NAV_HEIGHT = 64;

export default function TopNav({
  viewMode,
  onViewModeChange,
  sidebarOpen,
  onToggleSidebar,
}: TopNavProps) {
  // Track the active pill position for the sliding animation
  const segmentedRef = useRef<HTMLDivElement>(null);
  const analystRef = useRef<HTMLButtonElement>(null);
  const engineeringRef = useRef<HTMLButtonElement>(null);
  const [pillStyle, setPillStyle] = useState<CSSProperties>({});

  useEffect(() => {
    const activeRef = viewMode === 'analyst' ? analystRef : engineeringRef;
    const container = segmentedRef.current;
    const button = activeRef.current;
    if (container && button) {
      const containerRect = container.getBoundingClientRect();
      const buttonRect = button.getBoundingClientRect();
      setPillStyle({
        position: 'absolute',
        top: '3px',
        left: `${buttonRect.left - containerRect.left}px`,
        width: `${buttonRect.width}px`,
        height: 'calc(100% - 6px)',
        background: colors.amexWhite,
        borderRadius: radius.md,
        transition: 'left 250ms ease-out, width 250ms ease-out',
        zIndex: 0,
      });
    }
  }, [viewMode]);

  const navStyle: CSSProperties = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    height: `${NAV_HEIGHT}px`,
    background: colors.amexDarkBlue,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 20px',
    zIndex: 100,
    fontFamily: typography.fontPrimary,
  };

  const leftSectionStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  };

  const hamburgerStyle: CSSProperties = {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    padding: '8px',
    borderRadius: radius.sm,
  };

  const hamburgerLineStyle: CSSProperties = {
    width: '18px',
    height: '2px',
    background: colors.amexWhite,
    borderRadius: '1px',
    transition: 'transform 200ms ease',
  };

  const logoCircleStyle: CSSProperties = {
    width: '40px',
    height: '40px',
    borderRadius: '50%',
    background: colors.amexBlue,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: colors.amexWhite,
    fontSize: '16px',
    fontWeight: 700,
    fontFamily: typography.fontPrimary,
    letterSpacing: '0.5px',
    flexShrink: 0,
  };

  const separatorStyle: CSSProperties = {
    width: '1px',
    height: '28px',
    background: 'rgba(255,255,255,0.20)',
  };

  const brandTextStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
  };

  const wordmarkStyle: CSSProperties = {
    fontSize: '18px',
    fontWeight: 600,
    color: colors.amexWhite,
    lineHeight: '1.2',
    fontFamily: typography.fontPrimary,
  };

  const subtitleStyle: CSSProperties = {
    fontSize: '11px',
    color: 'rgba(255,255,255,0.55)',
    lineHeight: '1.2',
    fontFamily: typography.fontPrimary,
    marginTop: '1px',
  };

  // Center: segmented control
  const segmentedContainerStyle: CSSProperties = {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    background: 'rgba(255,255,255,0.10)',
    borderRadius: radius.md,
    padding: '3px',
    gap: '0px',
  };

  const segmentButtonBase: CSSProperties = {
    position: 'relative',
    zIndex: 1,
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    padding: '6px 18px',
    fontSize: '13px',
    fontWeight: 500,
    fontFamily: typography.fontPrimary,
    borderRadius: radius.md,
    transition: 'color 200ms ease',
    whiteSpace: 'nowrap',
  };

  const activeSegmentText: CSSProperties = {
    ...segmentButtonBase,
    color: colors.amexDarkBlue,
  };

  const inactiveSegmentText: CSSProperties = {
    ...segmentButtonBase,
    color: 'rgba(255,255,255,0.60)',
  };

  // Right: user info
  const rightSectionStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  };

  const avatarStyle: CSSProperties = {
    width: '32px',
    height: '32px',
    borderRadius: '50%',
    background: colors.amexBlue,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: colors.amexWhite,
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: typography.fontPrimary,
    flexShrink: 0,
  };

  const userInfoStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
  };

  const userNameStyle: CSSProperties = {
    fontSize: '13px',
    color: colors.amexWhite,
    fontWeight: 500,
    fontFamily: typography.fontPrimary,
    lineHeight: '1.2',
  };

  const buBadgeStyle: CSSProperties = {
    fontSize: '11px',
    color: 'rgba(255,255,255,0.70)',
    background: 'rgba(255,255,255,0.10)',
    padding: '2px 8px',
    borderRadius: radius.full,
    fontFamily: typography.fontPrimary,
    lineHeight: '1.4',
    marginTop: '2px',
  };

  return (
    <nav style={navStyle}>
      {/* Left section */}
      <div style={leftSectionStyle}>
        <button
          style={hamburgerStyle}
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
        >
          <span style={hamburgerLineStyle} />
          <span style={hamburgerLineStyle} />
          <span style={hamburgerLineStyle} />
        </button>
        <div style={logoCircleStyle}>AX</div>
        <div style={separatorStyle} />
        <div style={brandTextStyle}>
          <span style={wordmarkStyle}>Cortex</span>
          <span style={subtitleStyle}>Finance Intelligence</span>
        </div>
      </div>

      {/* Center: Segmented control */}
      <div ref={segmentedRef} style={segmentedContainerStyle}>
        {/* Animated pill background */}
        <div style={pillStyle} />
        <button
          ref={analystRef}
          style={viewMode === 'analyst' ? activeSegmentText : inactiveSegmentText}
          onClick={() => onViewModeChange('analyst')}
        >
          Analyst
        </button>
        <button
          ref={engineeringRef}
          style={viewMode === 'engineering' ? activeSegmentText : inactiveSegmentText}
          onClick={() => onViewModeChange('engineering')}
        >
          Engineering
        </button>
      </div>

      {/* Right: User */}
      <div style={rightSectionStyle}>
        <div style={userInfoStyle}>
          <span style={userNameStyle}>Finance Analyst</span>
          <span style={buBadgeStyle}>Finance BU</span>
        </div>
        <div style={avatarStyle}>F</div>
      </div>
    </nav>
  );
}
