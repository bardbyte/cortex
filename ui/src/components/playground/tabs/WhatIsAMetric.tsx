import { useState } from 'react';
import type { CSSProperties } from 'react';
import { colors, typography, radius } from '../../../tokens';
import { SAMPLE_ROWS, LOOKML_CODE, ENRICHED_JSON, LAYER_TOOLTIPS } from '../../../mock/playground/metricLayerData';
import LayerCard from '../shared/LayerCard';
import ConnectingArrow from '../shared/ConnectingArrow';

export default function WhatIsAMetric() {
  const [activeLayer, setActiveLayer] = useState<number | null>(null);

  const codeBlockStyle: CSSProperties = {
    background: '#1E1E2E',
    borderRadius: radius.md,
    padding: '16px',
    fontFamily: typography.fontMono,
    fontSize: '13px',
    lineHeight: '1.6',
    color: '#E5E7EB',
    overflowX: 'auto',
    whiteSpace: 'pre',
  };

  const tableStyle: CSSProperties = {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '13px',
    fontFamily: typography.fontMono,
  };

  const thStyle: CSSProperties = {
    textAlign: 'left',
    padding: '8px 12px',
    borderBottom: `2px solid ${colors.borderDefault}`,
    color: colors.textSecondary,
    fontWeight: 600,
    fontSize: '12px',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  };

  const tdStyle: CSSProperties = {
    padding: '8px 12px',
    borderBottom: `1px solid ${colors.borderDefault}`,
    color: colors.textPrimary,
  };

  const highlightThStyle: CSSProperties = {
    ...thStyle,
    borderBottom: '2px solid #006FCF',
    color: '#006FCF',
  };

  const captionStyle: CSSProperties = {
    fontSize: '12px',
    color: '#9CA3AF',
    fontFamily: typography.fontPrimary,
    marginTop: '8px',
  };

  const renderEnrichedJSON = () => {
    const lines = JSON.stringify(ENRICHED_JSON, null, 2).split('\n');
    const synonymStart = lines.findIndex((l) => l.includes('"synonyms"'));
    const synonymEnd = lines.findIndex((l, i) => i > synonymStart && l.trim() === ']') + 1;
    const filterStart = lines.findIndex((l) => l.includes('"required_filters"'));
    const filterEnd = lines.findIndex((l, i) => i > filterStart && l.trim().startsWith('}')) + 1;

    return (
      <div style={{ position: 'relative' }}>
        <div style={codeBlockStyle}>
          {lines.map((line, i) => {
            const isSynonym = i >= synonymStart && i < synonymEnd;
            const isFilter = i >= filterStart && i < filterEnd;
            const bg = isSynonym
              ? 'rgba(0, 135, 103, 0.08)'
              : isFilter
              ? 'rgba(179, 119, 0, 0.08)'
              : 'transparent';
            const borderLeft = isSynonym
              ? '3px solid #008767'
              : isFilter
              ? '3px solid #B37700'
              : '3px solid transparent';
            return (
              <div key={i} style={{ background: bg, borderLeft, paddingLeft: '8px', marginLeft: '-8px' }}>
                {line}
              </div>
            );
          })}
        </div>
        <div style={{ display: 'flex', gap: '20px', marginTop: '12px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{ width: '3px', height: '14px', background: '#008767', borderRadius: '2px' }} />
            <span style={{ fontSize: '12px', color: '#008767', fontFamily: typography.fontPrimary }}>
              These synonyms are the vocabulary Radix searches.
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{ width: '3px', height: '14px', background: '#B37700', borderRadius: '2px' }} />
            <span style={{ fontSize: '12px', color: '#B37700', fontFamily: typography.fontPrimary }}>
              This filter is injected automatically — the analyst never needs to specify it.
            </span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <LayerCard
        layerNumber={1}
        title="Raw Column"
        subtitle="billed_business: a dollar amount on each transaction row"
        tooltip={LAYER_TOOLTIPS.layer1}
        onActivate={() => setActiveLayer(1)}
        isActive={activeLayer === 1}
      >
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>cust_ref</th>
              <th style={thStyle}>partition_date</th>
              <th style={highlightThStyle}>billed_business</th>
              <th style={thStyle}>generation</th>
            </tr>
          </thead>
          <tbody>
            {SAMPLE_ROWS.map((row, i) => (
              <tr key={i}>
                <td style={tdStyle}>{row.cust_ref}</td>
                <td style={tdStyle}>{row.partition_date}</td>
                <td style={{ ...tdStyle, fontWeight: 500 }}>
                  {row.billed_business.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </td>
                <td style={tdStyle}>{row.generation}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={captionStyle}>
          Showing 5 of ~2.4B rows in custins_customer_insights_cardmember
        </div>
      </LayerCard>

      <ConnectingArrow pulse={activeLayer === 1} />

      <LayerCard
        layerNumber={2}
        title="Metric Definition"
        subtitle="SUM(billed_business): the aggregation rule"
        tooltip={LAYER_TOOLTIPS.layer2}
        onActivate={() => setActiveLayer(2)}
        isActive={activeLayer === 2}
        shimmer={activeLayer === 1}
      >
        <div style={codeBlockStyle}>
          {LOOKML_CODE.split('\n').map((line, i) => {
            const isSqlLine = line.includes('sql:');
            return (
              <div
                key={i}
                style={{
                  background: isSqlLine ? 'rgba(179, 119, 0, 0.20)' : 'transparent',
                  paddingLeft: '4px',
                  marginLeft: '-4px',
                }}
              >
                {line}
              </div>
            );
          })}
        </div>
      </LayerCard>

      <ConnectingArrow pulse={activeLayer === 2} />

      <LayerCard
        layerNumber={3}
        title="Enriched Definition"
        subtitle="How Radix understands it"
        tooltip={LAYER_TOOLTIPS.layer3}
        onActivate={() => setActiveLayer(3)}
        isActive={activeLayer === 3}
        shimmer={activeLayer === 2}
      >
        {renderEnrichedJSON()}
        {activeLayer === 3 && (
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              marginTop: '16px',
              padding: '6px 12px',
              borderRadius: radius.full,
              background: '#ECFDF5',
              color: '#008767',
              fontSize: '12px',
              fontWeight: 600,
              fontFamily: typography.fontPrimary,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M3 7L6 10L11 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            AI-queryable
          </div>
        )}
      </LayerCard>
    </div>
  );
}
