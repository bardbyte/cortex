import { useState } from 'react';
import type { CSSProperties } from 'react';
import { colors, typography, radius } from '../../../tokens';
import {
  SQL_INPUT_MOCK,
  SQL_EXTRACTION_RESULT,
  BUSINESS_FORM_DEFAULTS,
  AI_SUGGESTED_ADDITIONS,
  LOOKML_BEFORE,
  LOOKML_AFTER_LINES,
} from '../../../mock/playground/defineMetricMocks';
import AISpinner from '../shared/AISpinner';

const PATH_BADGES: Record<number, { label: string; sub: string; bg: string; fg: string }> = {
  1: { label: 'From SQL', sub: 'You have existing SQL logic', bg: '#EBF4FF', fg: '#006FCF' },
  2: { label: 'From Business Knowledge', sub: "You know the definition, not the SQL", bg: '#ECFDF5', fg: '#008767' },
  3: { label: 'Enhance Existing', sub: 'A field exists — it just needs a description', bg: '#F5F3FF', fg: '#7C3AED' },
};

function PathCard({ pathNumber, children }: { pathNumber: number; children: React.ReactNode }) {
  const badge = PATH_BADGES[pathNumber];
  const cardStyle: CSSProperties = {
    flex: 1,
    minWidth: '280px',
    background: colors.surfacePrimary,
    border: `1px solid ${colors.borderDefault}`,
    borderRadius: radius.lg,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  };
  const headerStyle: CSSProperties = {
    background: '#F7F8F9',
    padding: '12px 16px',
    borderBottom: `1px solid ${colors.borderDefault}`,
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  };
  const badgeStyle: CSSProperties = {
    padding: '2px 8px',
    borderRadius: radius.sm,
    fontSize: '11px',
    fontWeight: 700,
    background: badge.bg,
    color: badge.fg,
    fontFamily: typography.fontPrimary,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  };

  return (
    <div style={cardStyle}>
      <div style={headerStyle}>
        <span style={badgeStyle}>Path {String(pathNumber).padStart(2, '0')}</span>
        <span style={{ fontSize: '14px', fontWeight: 500, color: colors.textPrimary }}>{badge.label}</span>
      </div>
      <div style={{ fontSize: '12px', color: colors.textSecondary, padding: '12px 16px 0', fontStyle: 'italic' }}>
        {badge.sub}
      </div>
      <div style={{ padding: '16px', flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {children}
      </div>
    </div>
  );
}

/* ──────── Path 1: From SQL ──────── */
function FromSQL() {
  const [extracted, setExtracted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [accepted, setAccepted] = useState(false);

  const handleExtract = () => {
    setLoading(true);
    setTimeout(() => { setLoading(false); setExtracted(true); }, 1400);
  };

  const codeStyle: CSSProperties = {
    background: '#1E1E2E', borderRadius: radius.md, padding: '14px',
    fontFamily: typography.fontMono, fontSize: '13px', color: '#E5E7EB',
    whiteSpace: 'pre', lineHeight: '1.6',
  };

  return (
    <>
      <div style={codeStyle}>{SQL_INPUT_MOCK}</div>
      {!extracted && !loading && (
        <button onClick={handleExtract} style={{
          padding: '10px 20px', borderRadius: radius.sm, background: '#006FCF', color: '#FFFFFF',
          border: 'none', fontSize: '14px', fontWeight: 600, cursor: 'pointer', fontFamily: typography.fontPrimary,
        }}>
          Extract Metric Definition
        </button>
      )}
      {loading && <AISpinner />}
      {extracted && !accepted && (
        <div style={{
          borderLeft: '3px solid #008767', borderRadius: `0 ${radius.md} ${radius.md} 0`,
          padding: '16px', background: '#F0FDF9',
        }}>
          <div style={{ fontSize: '12px', fontWeight: 600, color: '#008767', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '14px' }}>AI</span> Proposed Metric Definition
          </div>
          {Object.entries(SQL_EXTRACTION_RESULT).map(([key, val]) => (
            <div key={key} style={{ fontSize: '13px', padding: '3px 0', color: colors.textPrimary }}>
              <span style={{ color: colors.textSecondary, fontWeight: 500 }}>{key}:</span>{' '}
              {Array.isArray(val) ? val.map((v, i) => (
                <span key={i} style={{
                  display: 'inline-block', padding: '2px 8px', margin: '2px 4px 2px 0', borderRadius: radius.full,
                  background: '#ECFDF5', color: '#008767', fontSize: '12px',
                }}>
                  {v}
                </span>
              )) : typeof val === 'object' ? JSON.stringify(val) : String(val)}
            </div>
          ))}
          <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
            <button onClick={() => setAccepted(true)} style={{
              padding: '6px 14px', borderRadius: radius.sm, background: '#008767',
              color: '#FFFFFF', border: 'none', fontSize: '12px', fontWeight: 600, cursor: 'pointer',
            }}>Accept</button>
            <button style={{
              padding: '6px 14px', borderRadius: radius.sm, background: 'transparent',
              color: '#6B7280', border: `1px solid ${colors.borderDefault}`, fontSize: '12px', cursor: 'pointer',
            }}>Edit</button>
            <button onClick={() => setExtracted(false)} style={{
              padding: '6px 14px', borderRadius: radius.sm, background: 'transparent',
              color: '#6B7280', border: `1px solid ${colors.borderDefault}`, fontSize: '12px', cursor: 'pointer',
            }}>Discard</button>
          </div>
        </div>
      )}
      {accepted && (
        <div style={{
          border: '2px solid #008767', borderRadius: radius.md, padding: '16px',
          display: 'flex', alignItems: 'center', gap: '8px', color: '#008767', fontWeight: 600,
        }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 8L7 12L13 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Spend Per Customer — Saved
        </div>
      )}
    </>
  );
}

/* ──────── Path 2: From Business Knowledge ──────── */
function FromBusiness() {
  const [synonyms, setSynonyms] = useState(BUSINESS_FORM_DEFAULTS.synonyms);
  const [newSynonym, setNewSynonym] = useState('');
  const [showAI, setShowAI] = useState(false);
  const [loading, setLoading] = useState(false);

  const inputStyle: CSSProperties = {
    width: '100%', padding: '8px 12px', borderRadius: radius.sm,
    border: `1px solid ${colors.borderDefault}`, fontSize: '14px', fontFamily: typography.fontPrimary,
    color: colors.textPrimary, background: colors.surfacePrimary, outline: 'none', boxSizing: 'border-box',
  };

  const labelStyle: CSSProperties = {
    fontSize: '12px', fontWeight: 600, color: colors.textSecondary, marginBottom: '4px',
    textTransform: 'uppercase', letterSpacing: '0.04em',
  };

  const handleSave = () => {
    setLoading(true);
    setTimeout(() => { setLoading(false); setShowAI(true); }, 1400);
  };

  return (
    <>
      {[
        { label: 'Name', value: BUSINESS_FORM_DEFAULTS.name },
        { label: 'Definition', value: BUSINESS_FORM_DEFAULTS.definition, multiline: true },
        { label: 'Formula (optional)', value: BUSINESS_FORM_DEFAULTS.formula },
      ].map(({ label, value, multiline }) => (
        <div key={label}>
          <div style={labelStyle}>{label}</div>
          {multiline ? (
            <textarea defaultValue={value} rows={2} style={{ ...inputStyle, resize: 'vertical' }} />
          ) : (
            <input defaultValue={value} style={inputStyle} />
          )}
        </div>
      ))}

      {/* Synonym tags */}
      <div>
        <div style={labelStyle}>Synonyms</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
          {synonyms.map((s, i) => (
            <span key={i} style={{
              display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '4px 10px', borderRadius: radius.full,
              background: '#ECFDF5', color: '#008767', fontSize: '12px', fontWeight: 500,
            }}>
              {s}
              <button onClick={() => setSynonyms(synonyms.filter((_, j) => j !== i))}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#008767', fontSize: '14px', padding: 0, lineHeight: 1 }}>
                x
              </button>
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          <input
            value={newSynonym}
            onChange={(e) => setNewSynonym(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && newSynonym.trim()) { setSynonyms([...synonyms, newSynonym.trim()]); setNewSynonym(''); } }}
            placeholder="Type and press Enter..."
            style={{ ...inputStyle, flex: 1 }}
          />
        </div>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px', marginTop: '8px',
          padding: '8px 12px', borderRadius: radius.sm, background: '#EBF4FF', border: '1px solid #BFDBFE',
          fontSize: '12px', fontWeight: 500, color: '#006FCF',
        }}>
          AI will suggest additional synonyms and related terms when you save
        </div>
      </div>

      {!loading && !showAI && (
        <button onClick={handleSave} style={{
          padding: '10px 20px', borderRadius: radius.sm, background: '#006FCF', color: '#FFFFFF',
          border: 'none', fontSize: '14px', fontWeight: 600, cursor: 'pointer', marginTop: '8px',
        }}>
          Save and Enrich
        </button>
      )}
      {loading && <AISpinner />}
      {showAI && (
        <div style={{ borderLeft: '3px solid #008767', borderRadius: `0 ${radius.md} ${radius.md} 0`, padding: '16px', background: '#F0FDF9' }}>
          <div style={{ fontSize: '12px', fontWeight: 600, color: '#008767', marginBottom: '10px' }}>AI-suggested additions</div>
          <div style={{ fontSize: '12px', fontWeight: 600, color: colors.textSecondary, marginBottom: '6px' }}>Additional synonyms:</div>
          {AI_SUGGESTED_ADDITIONS.synonyms.map((s, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
              <span style={{ fontSize: '13px', color: colors.textPrimary }}>"{s}"</span>
              <button onClick={() => { if (!synonyms.includes(s)) setSynonyms([...synonyms, s]); }}
                style={{ padding: '3px 10px', borderRadius: radius.sm, background: '#EBF4FF', color: '#006FCF', border: 'none', fontSize: '11px', fontWeight: 600, cursor: 'pointer' }}>
                Add
              </button>
            </div>
          ))}
          <div style={{ fontSize: '12px', fontWeight: 600, color: colors.textSecondary, marginTop: '12px', marginBottom: '6px' }}>Related metrics to link:</div>
          {AI_SUGGESTED_ADDITIONS.related_metrics.map((m, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
              <span style={{ fontSize: '13px', color: colors.textPrimary }}>"{m.name}" <span style={{ color: '#9CA3AF' }}>({m.relationship})</span></span>
              <button style={{ padding: '3px 10px', borderRadius: radius.sm, background: '#EBF4FF', color: '#006FCF', border: 'none', fontSize: '11px', fontWeight: 600, cursor: 'pointer' }}>
                Link
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

/* ──────── Path 3: Enhance Existing ──────── */
function EnhanceExisting() {
  const [enhanced, setEnhanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [accepted, setAccepted] = useState(false);

  const codeStyle: CSSProperties = {
    background: '#1E1E2E', borderRadius: radius.md, padding: '14px',
    fontFamily: typography.fontMono, fontSize: '13px', color: '#E5E7EB',
    whiteSpace: 'pre', lineHeight: '1.6',
  };

  const handleGenerate = () => {
    setLoading(true);
    setTimeout(() => { setLoading(false); setEnhanced(true); }, 1400);
  };

  return (
    <>
      <div>
        <div style={{ fontSize: '11px', fontWeight: 600, color: colors.textSecondary, textTransform: 'uppercase', marginBottom: '8px' }}>
          Before — LookML field as imported
        </div>
        <div style={codeStyle}>{LOOKML_BEFORE}</div>
      </div>

      {!enhanced && !loading && (
        <button onClick={handleGenerate} style={{
          padding: '10px 20px', borderRadius: radius.sm, background: '#7C3AED', color: '#FFFFFF',
          border: 'none', fontSize: '14px', fontWeight: 600, cursor: 'pointer',
        }}>
          Generate Description
        </button>
      )}
      {loading && <AISpinner />}
      {enhanced && !accepted && (
        <div>
          <div style={{ fontSize: '11px', fontWeight: 600, color: colors.textSecondary, textTransform: 'uppercase', marginBottom: '8px' }}>
            After — AI-proposed enrichment
          </div>
          <div style={codeStyle}>
            {LOOKML_AFTER_LINES.map((line, i) => (
              <div key={i} style={{
                background: line.added ? 'rgba(0, 135, 103, 0.06)' : 'transparent',
                borderLeft: line.added ? '3px solid #008767' : '3px solid transparent',
                paddingLeft: '8px',
                marginLeft: '-8px',
              }}>
                {line.added && <span style={{ color: '#008767', marginRight: '4px' }}>+</span>}
                {line.text}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
            <button onClick={() => setAccepted(true)} style={{
              padding: '6px 14px', borderRadius: radius.sm, background: '#008767', color: '#FFFFFF',
              border: 'none', fontSize: '12px', fontWeight: 600, cursor: 'pointer',
            }}>Approve</button>
            <button style={{
              padding: '6px 14px', borderRadius: radius.sm, background: 'transparent', color: '#6B7280',
              border: `1px solid ${colors.borderDefault}`, fontSize: '12px', cursor: 'pointer',
            }}>Edit Inline</button>
            <button onClick={() => setEnhanced(false)} style={{
              padding: '6px 14px', borderRadius: radius.sm, background: 'transparent', color: '#6B7280',
              border: `1px solid ${colors.borderDefault}`, fontSize: '12px', cursor: 'pointer',
            }}>Regenerate</button>
          </div>
        </div>
      )}
      {accepted && (
        <div style={{
          border: '2px solid #008767', borderRadius: radius.md, padding: '16px',
          display: 'flex', alignItems: 'center', gap: '8px', color: '#008767', fontWeight: 600,
        }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 8L7 12L13 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Enrichment Approved — Ready for Cortex
        </div>
      )}
    </>
  );
}

/* ──────── Main Tab ──────── */
export default function DefineAMetric() {
  return (
    <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
      <PathCard pathNumber={1}><FromSQL /></PathCard>
      <PathCard pathNumber={2}><FromBusiness /></PathCard>
      <PathCard pathNumber={3}><EnhanceExisting /></PathCard>
    </div>
  );
}
