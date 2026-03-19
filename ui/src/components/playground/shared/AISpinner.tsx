import type { CSSProperties } from 'react';
import { typography } from '../../../tokens';

export default function AISpinner() {
  const containerStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '12px',
    padding: '32px 0',
  };

  const labelStyle: CSSProperties = {
    fontSize: '13px',
    color: '#6B7280',
    fontFamily: typography.fontPrimary,
  };

  return (
    <div style={containerStyle}>
      <svg width="32" height="32" viewBox="0 0 32 32" style={{ animation: 'spin 1s linear infinite' }}>
        <circle
          cx="16"
          cy="16"
          r="12"
          fill="none"
          stroke="#E5E7EB"
          strokeWidth="3"
        />
        <path
          d="M16 4a12 12 0 0 1 12 12"
          fill="none"
          stroke="#006FCF"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
      <span style={labelStyle}>Analyzing with Radix AI...</span>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
