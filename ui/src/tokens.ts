/** Radix UI — Design Tokens. Single source of truth. */

export const colors = {
  // Brand (always fixed — not theme-aware)
  amexBlue: '#006FCF',
  amexDarkBlue: '#00175A',
  amexWhite: '#FFFFFF',

  // Surface
  surfacePrimary: 'var(--color-surface-primary)',
  surfaceSecondary: 'var(--color-surface-secondary)',
  surfaceTertiary: 'var(--color-surface-tertiary)',
  surfaceInverse: 'var(--color-surface-inverse)',

  // Text
  textPrimary: 'var(--color-text-primary)',
  textSecondary: 'var(--color-text-secondary)',
  textTertiary: 'var(--color-text-tertiary)',
  textInverse: 'var(--color-text-inverse)',
  textLink: 'var(--color-text-link)',

  // Semantic
  success: 'var(--color-success)',
  successLight: 'var(--color-success-light)',
  warning: 'var(--color-warning)',
  warningLight: 'var(--color-warning-light)',
  error: 'var(--color-error)',
  errorLight: 'var(--color-error-light)',
  infoLight: 'var(--color-info-light)',
  filterSynonym: 'var(--color-filter-synonym)',
  filterSynonymLight: 'var(--color-filter-synonym-light)',

  // Pipeline steps
  stepPending: 'var(--color-step-pending)',
  stepActive: 'var(--color-step-active)',
  stepComplete: 'var(--color-step-complete)',
  stepWarning: 'var(--color-step-warning)',
  stepError: 'var(--color-step-error)',

  // Borders
  borderDefault: 'var(--color-border-default)',
  borderStrong: 'var(--color-border-strong)',
  borderFocus: 'var(--color-border-focus)',

  // Code blocks (SQL)
  codeSurface: 'var(--color-code-surface)',
  backdrop: 'var(--color-backdrop)',

  // Dark-specific (always fixed — used for always-dark UI elements)
  darkSurface: '#00175A',
  darkSurfaceRaised: '#0A2472',
  darkBorder: '#1E3A7A',
  darkTextPrimary: '#F9FAFB',
  darkTextSecondary: '#9CA3AF',
} as const;

export const typography = {
  fontPrimary: "'Inter', 'SF Pro Text', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  fontMono: "'Geist Mono', 'SF Mono', 'Cascadia Code', Consolas, 'Courier New', monospace",
  /** Use on all numeric displays (confidence, duration, percentages) for proper column alignment. */
  tabularNums: "'tnum' 1, 'lnum' 1" as const,
} as const;

export const radius = {
  sm: '4px',
  md: '8px',
  lg: '12px',
  xl: '16px',
  full: '9999px',
} as const;

export const shadows = {
  sm: '0 1px 2px 0 rgba(0,0,0,0.05)',
  md: '0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05)',
  lg: '0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.05)',
  glass: '0 4px 24px rgba(0,23,90,0.08), inset 0 1px 0 rgba(255,255,255,0.6)',
} as const;
