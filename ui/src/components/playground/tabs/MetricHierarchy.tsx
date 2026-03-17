import { useState } from 'react';
import type { CSSProperties } from 'react';
import { colors, typography, radius } from '../../../tokens';
import { METRIC_TREE, TIER_LABELS, SIMILARITY_MOCK } from '../../../mock/playground/metricHierarchyData';
import type { MetricNode, GovernanceTier } from '../../../mock/playground/metricHierarchyData';

function TierBadge({ tier }: { tier: GovernanceTier }) {
  const t = TIER_LABELS[tier];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '20px',
        height: '20px',
        borderRadius: '4px',
        background: t.bg,
        color: t.fg,
        fontSize: '11px',
        fontWeight: 700,
        fontFamily: typography.fontPrimary,
        flexShrink: 0,
      }}
    >
      {t.short}
    </span>
  );
}

export default function MetricHierarchy() {
  const [selectedId, setSelectedId] = useState<string>(METRIC_TREE.id);
  const [createInput, setCreateInput] = useState('');
  const [showSimilarity, setShowSimilarity] = useState(false);

  const allNodes = [METRIC_TREE, ...(METRIC_TREE.children ?? [])];
  const selected = allNodes.find((n) => n.id === selectedId) ?? METRIC_TREE;

  const handleCreateInput = (value: string) => {
    setCreateInput(value);
    setShowSimilarity(value.toLowerCase().includes('active') && value.length > 5);
  };

  const containerStyle: CSSProperties = {
    display: 'flex',
    gap: '24px',
    minHeight: '500px',
  };

  const treeStyle: CSSProperties = {
    width: '320px',
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  };

  const detailStyle: CSSProperties = {
    flex: 1,
    background: colors.surfacePrimary,
    border: `1px solid ${colors.borderDefault}`,
    borderRadius: radius.lg,
    padding: '24px',
  };

  const nodeStyle = (isSelected: boolean, depth: number): CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 14px',
    paddingLeft: `${14 + depth * 24}px`,
    borderRadius: radius.md,
    fontSize: '14px',
    fontWeight: 500,
    fontFamily: typography.fontPrimary,
    color: colors.textPrimary,
    cursor: 'pointer',
    border: `1px solid ${isSelected ? '#006FCF' : 'transparent'}`,
    background: isSelected ? '#EBF4FF' : 'transparent',
    transition: 'background 120ms, border-color 120ms',
  });

  const renderNode = (node: MetricNode, depth: number) => (
    <div key={node.id}>
      <div
        style={nodeStyle(selectedId === node.id, depth)}
        onClick={() => setSelectedId(node.id)}
        onMouseEnter={(e) => {
          if (selectedId !== node.id) e.currentTarget.style.background = '#F3F4F6';
        }}
        onMouseLeave={(e) => {
          if (selectedId !== node.id) e.currentTarget.style.background = 'transparent';
        }}
      >
        <TierBadge tier={node.tier} />
        <span>{node.name}</span>
      </div>
      {node.children?.map((child) => renderNode(child, depth + 1))}
    </div>
  );

  const renderDetail = (node: MetricNode) => {
    const tierInfo = TIER_LABELS[node.tier];

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <TierBadge tier={node.tier} />
          <span style={{ fontSize: '11px', fontWeight: 600, color: tierInfo.bg, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {tierInfo.label}
          </span>
        </div>
        <h3 style={{ fontSize: '20px', fontWeight: 700, color: colors.textPrimary, fontFamily: typography.fontPrimary, margin: 0 }}>
          {node.name}
        </h3>
        <p style={{ fontSize: '14px', color: colors.textSecondary, fontFamily: typography.fontPrimary, margin: 0, lineHeight: '1.6' }}>
          {node.definition}
        </p>
        <div style={{ fontSize: '13px', color: colors.textSecondary }}>
          <strong>Owner:</strong> {node.owner}
        </div>
        {node.formula && (
          <div style={{
            background: '#1E1E2E',
            borderRadius: radius.md,
            padding: '12px 16px',
            fontFamily: typography.fontMono,
            fontSize: '13px',
            color: '#E5E7EB',
          }}>
            {node.formula}
          </div>
        )}

        {/* Inheritance diff for BU variants */}
        {node.overrides && node.overrides.length > 0 && (
          <div style={{ display: 'flex', gap: '16px', marginTop: '8px' }}>
            <div style={{ flex: 1, padding: '16px', borderRadius: radius.md, background: '#F9FAFB' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: '#9CA3AF', textTransform: 'uppercase', marginBottom: '12px' }}>
                Inherited from Parent
              </div>
              {node.overrides.map((o, i) => (
                <div key={i} style={{ fontSize: '13px', color: '#9CA3AF', padding: '4px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="2" y="2" width="8" height="8" rx="1" stroke="#9CA3AF" strokeWidth="1.2" /></svg>
                  {o.field}: {o.parent}
                </div>
              ))}
            </div>
            <div style={{ flex: 1, padding: '16px', borderRadius: radius.md, background: '#EBF4FF', borderLeft: '3px solid #006FCF' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: '#006FCF', textTransform: 'uppercase', marginBottom: '12px' }}>
                This Variant Overrides
              </div>
              {node.overrides.map((o, i) => (
                <div key={i} style={{ fontSize: '13px', color: '#111827', fontWeight: 500, padding: '4px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6h8M6 2v8" stroke="#006FCF" strokeWidth="1.5" strokeLinecap="round" /></svg>
                  {o.field}: {o.override}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Warning for ungoverned metrics */}
        {node.warning && (
          <div style={{
            background: '#FFFBEB',
            border: '1px solid #B37700',
            borderRadius: radius.md,
            padding: '16px',
            color: '#92400E',
            fontSize: '13px',
            fontFamily: typography.fontPrimary,
            lineHeight: '1.5',
            display: 'flex',
            gap: '10px',
          }}>
            <span style={{ fontSize: '16px', flexShrink: 0 }}>!</span>
            <div>
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>Not Governed</div>
              {node.warning}
              <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                <button style={{
                  padding: '6px 14px', borderRadius: radius.sm, border: '1px solid #B37700', background: 'transparent',
                  color: '#B37700', fontSize: '12px', fontWeight: 600, cursor: 'pointer',
                }}>
                  Promote to Canonical
                </button>
                <button style={{
                  padding: '6px 14px', borderRadius: radius.sm, border: '1px solid #E5E7EB', background: 'transparent',
                  color: '#6B7280', fontSize: '12px', fontWeight: 500, cursor: 'pointer',
                }}>
                  View Lineage
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={containerStyle}>
      <div style={treeStyle}>
        {renderNode(METRIC_TREE, 0)}

        {/* Create metric button + dedup */}
        <div style={{ marginTop: '16px', borderTop: `1px solid ${colors.borderDefault}`, paddingTop: '16px' }}>
          <input
            type="text"
            value={createInput}
            onChange={(e) => handleCreateInput(e.target.value)}
            placeholder="+ Create Metric..."
            style={{
              width: '100%',
              padding: '10px 14px',
              borderRadius: radius.sm,
              border: `1px solid ${colors.borderDefault}`,
              fontSize: '14px',
              fontFamily: typography.fontPrimary,
              color: colors.textPrimary,
              background: colors.surfacePrimary,
              outline: 'none',
              boxSizing: 'border-box',
            }}
            onFocus={(e) => { e.target.style.borderColor = '#006FCF'; e.target.style.boxShadow = '0 0 0 3px rgba(0, 111, 207, 0.12)'; }}
            onBlur={(e) => { e.target.style.borderColor = ''; e.target.style.boxShadow = ''; }}
          />

          {showSimilarity && (
            <div style={{
              background: '#FFFBEB',
              borderLeft: '3px solid #B37700',
              borderRadius: `0 ${radius.md} ${radius.md} 0`,
              padding: '14px 16px',
              marginTop: '8px',
              animation: 'slideDown 200ms ease',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 600, color: '#92400E' }}>
                <span>~</span> Similar metric found
              </div>
              <div style={{ fontSize: '14px', fontWeight: 500, color: '#111827', marginTop: '6px' }}>
                "{SIMILARITY_MOCK.match}" — {Math.round(SIMILARITY_MOCK.score * 100)}% match
              </div>
              <div style={{ fontSize: '12px', color: '#6B7280', marginTop: '4px' }}>
                {TIER_LABELS[SIMILARITY_MOCK.tier].label} | {SIMILARITY_MOCK.owner} | {SIMILARITY_MOCK.detail}
              </div>
              {/* Score bar */}
              <div style={{ height: '4px', background: '#E5E7EB', borderRadius: '2px', marginTop: '8px' }}>
                <div style={{ height: '100%', width: `${SIMILARITY_MOCK.score * 100}%`, background: '#B37700', borderRadius: '2px' }} />
              </div>
              <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                <button
                  style={{
                    padding: '6px 14px', borderRadius: radius.sm, background: '#006FCF', color: '#FFFFFF',
                    border: 'none', fontSize: '12px', fontWeight: 600, cursor: 'pointer',
                  }}
                  onClick={() => { setSelectedId(METRIC_TREE.id); setCreateInput(''); setShowSimilarity(false); }}
                >
                  Use Existing
                </button>
                <button style={{
                  padding: '6px 14px', borderRadius: radius.sm, background: 'transparent', color: '#6B7280',
                  border: `1px solid ${colors.borderDefault}`, fontSize: '12px', cursor: 'pointer',
                }}>
                  Create Anyway
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
      <div style={detailStyle}>
        {renderDetail(selected)}
      </div>
      <style>{`@keyframes slideDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  );
}
