import { useState } from 'react';
import type { CSSProperties } from 'react';
import { colors, typography, radius } from '../../tokens';
import WhatIsAMetric from './tabs/WhatIsAMetric';
import MetricHierarchy from './tabs/MetricHierarchy';
import DefineAMetric from './tabs/DefineAMetric';
import HowAIUsesIt from './tabs/HowAIUsesIt';

const TABS = [
  { id: 'what', label: 'What is a Metric?' },
  { id: 'hierarchy', label: 'Metric Hierarchy' },
  { id: 'define', label: 'Define a Metric' },
  { id: 'how', label: 'How the AI Uses It' },
] as const;

type TabId = typeof TABS[number]['id'];

interface MetricPlaygroundProps {
  onBack: () => void;
}

export default function MetricPlayground({ onBack }: MetricPlaygroundProps) {
  const [activeTab, setActiveTab] = useState<TabId>('what');

  const containerStyle: CSSProperties = {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    background: colors.surfaceSecondary,
  };

  const contentOuterStyle: CSSProperties = {
    flex: 1,
    overflow: 'auto',
    display: 'flex',
    justifyContent: 'center',
  };

  const contentInnerStyle: CSSProperties = {
    width: '100%',
    maxWidth: '960px',
    padding: '0 24px 48px',
  };

  const tabBarStyle: CSSProperties = {
    position: 'sticky',
    top: 0,
    zIndex: 10,
    background: colors.surfacePrimary,
    borderBottom: `1px solid ${colors.borderDefault}`,
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
    display: 'flex',
    alignItems: 'center',
    padding: '12px 24px',
    gap: '4px',
  };

  const backStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 12px',
    borderRadius: radius.sm,
    border: 'none',
    background: 'transparent',
    color: colors.textSecondary,
    fontSize: '13px',
    fontFamily: typography.fontPrimary,
    cursor: 'pointer',
    marginRight: '16px',
    transition: 'color 150ms ease',
    flexShrink: 0,
  };

  const tabStyle = (isActive: boolean): CSSProperties => ({
    padding: '8px 20px',
    borderRadius: radius.sm,
    fontSize: '14px',
    fontWeight: isActive ? 600 : 500,
    fontFamily: typography.fontPrimary,
    color: isActive ? '#006FCF' : '#374151',
    background: isActive ? '#EBF4FF' : 'transparent',
    border: 'none',
    cursor: 'pointer',
    transition: 'background 120ms ease, color 120ms ease',
    whiteSpace: 'nowrap',
  });

  const renderTab = () => {
    switch (activeTab) {
      case 'what': return <WhatIsAMetric />;
      case 'hierarchy': return <MetricHierarchy />;
      case 'define': return <DefineAMetric />;
      case 'how': return <HowAIUsesIt />;
    }
  };

  return (
    <div style={containerStyle}>
      <div style={tabBarStyle}>
        <button
          style={backStyle}
          onClick={onBack}
          onMouseEnter={(e) => { e.currentTarget.style.color = colors.textPrimary; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = colors.textSecondary as string; }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M9 3L5 7L9 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back to Cortex
        </button>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            style={tabStyle(activeTab === tab.id)}
            onClick={() => setActiveTab(tab.id)}
            onMouseEnter={(e) => {
              if (activeTab !== tab.id) e.currentTarget.style.background = '#F3F4F6';
            }}
            onMouseLeave={(e) => {
              if (activeTab !== tab.id) e.currentTarget.style.background = 'transparent';
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div style={contentOuterStyle}>
        <div style={contentInnerStyle}>
          <div style={{ paddingTop: '24px' }}>
            {renderTab()}
          </div>
        </div>
      </div>

      {/* Global animations */}
      <style>{`
        @keyframes layerShimmer {
          0% { background-color: var(--color-surface-primary, #FFFFFF); }
          50% { background-color: #EBF4FF; }
          100% { background-color: var(--color-surface-primary, #FFFFFF); }
        }
      `}</style>
    </div>
  );
}
