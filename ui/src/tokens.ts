/** Design tokens from cortex-demo-ui-design.md — single source of truth. */

export const colors = {
  // Brand
  amexBlue: '#006FCF',
  amexDarkBlue: '#00175A',
  amexWhite: '#FFFFFF',

  // Surface
  surfacePrimary: '#FFFFFF',
  surfaceSecondary: '#F7F8F9',
  surfaceTertiary: '#F0F2F5',
  surfaceInverse: '#00175A',

  // Text
  textPrimary: '#0D1117',
  textSecondary: '#6B7280',
  textTertiary: '#9CA3AF',
  textInverse: '#FFFFFF',
  textLink: '#006FCF',

  // Semantic
  success: '#008767',
  successLight: '#E6F4F1',
  warning: '#B37700',
  warningLight: '#FFF8E6',
  error: '#C40000',
  errorLight: '#FDE8E8',
  infoLight: '#E6F0FA',

  // Pipeline steps
  stepPending: '#9CA3AF',
  stepActive: '#006FCF',
  stepComplete: '#008767',
  stepWarning: '#B37700',
  stepError: '#C40000',

  // Borders
  borderDefault: '#E5E7EB',
  borderStrong: '#D1D5DB',
  borderFocus: '#006FCF',

  // Dark mode
  darkSurface: '#00175A',
  darkSurfaceRaised: '#0A2472',
  darkBorder: '#1E3A7A',
  darkTextPrimary: '#F9FAFB',
  darkTextSecondary: '#9CA3AF',
} as const;

export const typography = {
  fontPrimary: "'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif",
  fontMono: "'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace",
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
