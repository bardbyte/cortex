import { useState, useEffect, useRef } from 'react';
import type { CSSProperties } from 'react';
import { colors, typography, radius } from '../../../tokens';
import { TRACE_QUERY, TRACE_STEPS, TRACE_RESULTS, NO_ENRICHMENT_CALLOUT } from '../../../mock/playground/pipelineTraceData';
import ScoreBar from '../shared/ScoreBar';

export default function HowAIUsesIt() {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
  const [autoPlayed, setAutoPlayed] = useState(false);
  const timerRefs = useRef<ReturnType<typeof setTimeout>[]>([]);

  const startTrace = () => {
    setExpandedSteps(new Set());
    timerRefs.current.forEach(clearTimeout);
    timerRefs.current = [];

    TRACE_STEPS.forEach((step, i) => {
      const timer = setTimeout(() => {
        setExpandedSteps((prev) => new Set([...prev, step.number]));
      }, (i + 1) * 1200);
      timerRefs.current.push(timer);
    });
  };

  useEffect(() => {
    if (!autoPlayed) {
      setAutoPlayed(true);
      startTrace();
    }
    return () => timerRefs.current.forEach(clearTimeout);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleStep = (num: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num);
      else next.add(num);
      return next;
    });
  };

  const codeStyle: CSSProperties = {
    background: '#1E1E2E',
    borderRadius: radius.md,
    padding: '14px',
    fontFamily: typography.fontMono,
    fontSize: '13px',
    color: '#E5E7EB',
    whiteSpace: 'pre',
    lineHeight: '1.6',
    overflowX: 'auto',
  };

  const highlightNoteStyle: CSSProperties = {
    background: '#EBF4FF',
    borderLeft: '3px solid #006FCF',
    borderRadius: `0 ${radius.md} ${radius.md} 0`,
    padding: '12px 16px',
    fontSize: '13px',
    color: '#1E3A5F',
    fontFamily: typography.fontPrimary,
    lineHeight: '1.5',
    marginTop: '12px',
  };

  const amberNoteStyle: CSSProperties = {
    ...highlightNoteStyle,
    borderLeftColor: '#B37700',
    color: '#92400E',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
      {/* Query bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '14px 20px', background: '#F7F8F9', borderRadius: radius.lg,
        border: `1px solid ${colors.borderDefault}`, marginBottom: '24px',
      }}>
        <div style={{ fontSize: '14px', color: colors.textPrimary, fontFamily: typography.fontPrimary }}>
          <span style={{ color: colors.textSecondary, fontWeight: 500 }}>Query: </span>
          <span style={{ fontWeight: 600 }}>"{TRACE_QUERY}"</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button onClick={startTrace} style={{
            padding: '6px 14px', borderRadius: radius.sm, background: '#006FCF', color: '#FFFFFF',
            border: 'none', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
          }}>
            Trace
          </button>
          <button onClick={() => { setExpandedSteps(new Set()); setAutoPlayed(false); }}
            style={{
              padding: '6px 14px', borderRadius: radius.sm, background: 'transparent',
              color: '#6B7280', border: `1px solid ${colors.borderDefault}`, fontSize: '12px', cursor: 'pointer',
            }}>
            Replay trace
          </button>
        </div>
      </div>

      {/* Steps */}
      {TRACE_STEPS.map((step, idx) => {
        const isExpanded = expandedSteps.has(step.number);
        const isPassed = expandedSteps.has(step.number);

        return (
          <div key={step.number}>
            {idx > 0 && (
              <div style={{
                width: '2px',
                height: '24px',
                marginLeft: '19px',
                background: isPassed ? '#006FCF' : '#E5E7EB',
                transition: 'background 400ms ease-in-out',
              }} />
            )}

            <div
              style={{
                border: `1px solid ${isExpanded ? '#006FCF' : colors.borderDefault}`,
                borderRadius: radius.lg,
                background: colors.surfacePrimary,
                overflow: 'hidden',
                transition: 'border-color 200ms ease',
                cursor: 'pointer',
              }}
              onClick={() => toggleStep(step.number)}
            >
              <div style={{
                display: 'flex', alignItems: 'center', gap: '12px', padding: '16px 20px',
              }}>
                <div style={{
                  width: '28px', height: '28px', borderRadius: '50%',
                  background: isExpanded ? '#006FCF' : '#F3F4F6',
                  color: isExpanded ? '#FFFFFF' : '#6B7280',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '13px', fontWeight: 700, flexShrink: 0,
                  transition: 'background 200ms ease, color 200ms ease',
                }}>
                  {String(step.number).padStart(2, '0')}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '14px', fontWeight: 600, color: colors.textPrimary }}>{step.title}</div>
                  <div style={{ fontSize: '12px', color: colors.textSecondary, marginTop: '2px' }}>{step.summary}</div>
                </div>
                <svg
                  width="16" height="16" viewBox="0 0 16 16" fill="none"
                  style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 200ms ease', flexShrink: 0 }}
                >
                  <path d="M4 6L8 10L12 6" stroke={colors.textTertiary} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>

              <div style={{
                maxHeight: isExpanded ? '1000px' : '0',
                overflow: 'hidden',
                transition: 'max-height 350ms ease-out',
              }}>
                <div style={{ padding: '0 20px 20px', borderTop: `1px solid ${colors.borderDefault}` }}>
                  <div style={{ paddingTop: '16px' }}>
                    {step.matches && (
                      <div style={{ marginBottom: '16px' }}>
                        <div style={{ fontSize: '12px', fontWeight: 600, color: colors.textSecondary, textTransform: 'uppercase', marginBottom: '8px' }}>
                          Top Matches
                        </div>
                        {step.matches.map((m, i) => (
                          <ScoreBar key={i} label={m.field} score={m.score} note={m.note} isTop={i === 0} animate={isExpanded} />
                        ))}
                        <div style={{ fontSize: '13px', color: colors.textSecondary, marginTop: '8px' }}>
                          Selected: <strong>{step.matches[0].field}</strong> (score {step.matches[0].score} {'>'} threshold 0.85)
                        </div>
                      </div>
                    )}

                    {step.number === 4 ? (
                      <>
                        <div style={codeStyle}>{step.content}</div>
                        <table style={{
                          width: '100%', borderCollapse: 'collapse', marginTop: '16px',
                          fontSize: '13px', fontFamily: typography.fontMono,
                        }}>
                          <thead>
                            <tr>
                              <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: `2px solid ${colors.borderDefault}`, color: colors.textSecondary, fontSize: '12px', fontWeight: 600 }}>
                                Generation
                              </th>
                              <th style={{ textAlign: 'right', padding: '8px 12px', borderBottom: `2px solid ${colors.borderDefault}`, color: colors.textSecondary, fontSize: '12px', fontWeight: 600 }}>
                                Total Billed Business
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {TRACE_RESULTS.map((row, i) => (
                              <tr key={i}>
                                <td style={{ padding: '8px 12px', borderBottom: `1px solid ${colors.borderDefault}`, color: colors.textPrimary }}>{row.generation}</td>
                                <td style={{ padding: '8px 12px', borderBottom: `1px solid ${colors.borderDefault}`, color: colors.textPrimary, textAlign: 'right', fontWeight: 500 }}>{row.total_billed_business}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </>
                    ) : !step.matches ? (
                      <div style={step.number === 3 ? { ...codeStyle, background: colors.surfacePrimary, color: colors.textPrimary, border: `1px solid ${colors.borderDefault}` } : codeStyle}>
                        {step.content}
                      </div>
                    ) : null}

                    {step.highlight && (
                      <div style={step.number === 3 ? amberNoteStyle : highlightNoteStyle}>
                        {step.highlight}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {/* "What if" callout */}
      <div style={{
        background: '#00175A',
        borderRadius: radius.lg,
        padding: '28px 32px',
        marginTop: '40px',
        color: '#FFFFFF',
      }}>
        <div style={{ fontSize: '18px', fontWeight: 700, fontFamily: typography.fontPrimary, marginBottom: '16px' }}>
          What if total_billed_business had no enriched description?
        </div>
        <div style={{ fontSize: '14px', color: '#D1D5DB', lineHeight: '1.6', marginBottom: '12px' }}>
          Step 1 result without synonym "total spend":
        </div>
        <div style={{ fontSize: '14px', color: '#D1D5DB', lineHeight: '1.6' }}>
          "total spend" vs "billed_business_amt" → score: <strong style={{ color: '#EF4444' }}>{NO_ENRICHMENT_CALLOUT.without_score}</strong>
          <br />
          Below threshold ({NO_ENRICHMENT_CALLOUT.threshold}). <strong style={{ color: '#EF4444' }}>No match found.</strong>
        </div>

        <div style={{
          background: 'rgba(255, 255, 255, 0.08)',
          borderRadius: radius.md,
          padding: '16px',
          fontFamily: typography.fontMono,
          color: '#93C5FD',
          fontSize: '14px',
          lineHeight: '1.6',
          marginTop: '16px',
        }}>
          What Radix would have returned:
          <br />
          <br />
          "{NO_ENRICHMENT_CALLOUT.fallback_response}"
        </div>

        <div style={{
          fontSize: '16px',
          fontWeight: 700,
          color: '#FFFFFF',
          fontFamily: typography.fontPrimary,
          marginTop: '24px',
          lineHeight: '1.5',
        }}>
          The synonym bridge is the fuel.
          <br />
          {NO_ENRICHMENT_CALLOUT.punchline}
        </div>
      </div>
    </div>
  );
}
