import { useState, useEffect, useRef } from 'react';
import type { CSSProperties } from 'react';
import type { ViewMode } from '../types';
import { colors, typography, radius } from '../tokens';
import RadixMark from './RadixMark';
import { useTheme } from '../hooks/useTheme';

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
  const { theme, toggle } = useTheme();

  // Track the active pill position for the sliding animation
  const segmentedRef = useRef<HTMLDivElement>(null);
  const analystRef = useRef<HTMLButtonElement>(null);
  const engineeringRef = useRef<HTMLButtonElement>(null);
  const [pillStyle, setPillStyle] = useState<CSSProperties>({});

  // For the segmented control pill, only track analyst/engineering (playground is a separate tab)
  useEffect(() => {
    if (viewMode === 'playground') return; // no pill movement for playground
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
    fontWeight: 700,
    color: colors.amexWhite,
    lineHeight: '1.2',
    fontFamily: typography.fontPrimary,
    letterSpacing: '0.5px',
  };

  const subtitleStyle: CSSProperties = {
    fontSize: '11px',
    color: 'rgba(255,255,255,0.70)',
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
        <RadixMark size={36} />
        <div style={separatorStyle} />
        <div style={brandTextStyle}>
          <span style={wordmarkStyle}>Radix</span>
          <span style={subtitleStyle}>Data Intelligence</span>
        </div>
      </div>

      {/* Center: Segmented control + Playground tab */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div ref={segmentedRef} style={segmentedContainerStyle}>
          {/* Animated pill background */}
          {viewMode !== 'playground' && <div style={pillStyle} />}
          <button
            ref={analystRef}
            style={viewMode === 'analyst' ? activeSegmentText : inactiveSegmentText}
            onClick={() => onViewModeChange('analyst')}
          >
            Chat
          </button>
          <button
            ref={engineeringRef}
            style={viewMode === 'engineering' ? activeSegmentText : inactiveSegmentText}
            onClick={() => onViewModeChange('engineering')}
          >
            Pipeline
          </button>
        </div>
        <button
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: viewMode === 'playground' ? 600 : 500,
            fontFamily: typography.fontPrimary,
            color: viewMode === 'playground' ? '#FFFFFF' : 'rgba(255,255,255,0.60)',
            padding: '0 16px',
            borderBottom: viewMode === 'playground' ? '2px solid #FFFFFF' : '2px solid transparent',
            paddingBottom: '2px',
            transition: 'color 150ms ease, border-color 150ms ease',
            whiteSpace: 'nowrap',
          }}
          onClick={() => onViewModeChange('playground')}
          onMouseEnter={(e) => { if (viewMode !== 'playground') e.currentTarget.style.color = 'rgba(255,255,255,0.85)'; }}
          onMouseLeave={(e) => { if (viewMode !== 'playground') e.currentTarget.style.color = 'rgba(255,255,255,0.60)'; }}
        >
          Metric Playground
        </button>
      </div>

      {/* Right: User */}
      <div style={rightSectionStyle}>
        <button
          onClick={toggle}
          aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '8px',
            borderRadius: radius.sm,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'rgba(255,255,255,0.70)',
            transition: 'color 150ms ease',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = '#FFFFFF';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.70)';
          }}
        >
          {theme === 'light' ? (
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M15.5 9.78A7 7 0 118.22 2.5 5.5 5.5 0 0015.5 9.78z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <circle cx="9" cy="9" r="3.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M9 1.5V3M9 15V16.5M1.5 9H3M15 9H16.5M3.4 3.4L4.5 4.5M13.5 13.5L14.6 14.6M3.4 14.6L4.5 13.5M13.5 4.5L14.6 3.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          )}
        </button>
        <div style={userInfoStyle}>
          <span style={userNameStyle}>Saheb Singh</span>
          <span style={buBadgeStyle}>Enterprise</span>
        </div>
        <div style={avatarStyle}>SS</div>
      </div>
    </nav>
  );
}
