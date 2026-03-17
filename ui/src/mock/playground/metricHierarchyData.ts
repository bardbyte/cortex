/** Tab 2 — "Metric Hierarchy" tree data */

export type GovernanceTier = 'canonical' | 'bu_variant' | 'team_derived';

export interface MetricNode {
  id: string;
  name: string;
  tier: GovernanceTier;
  owner: string;
  definition: string;
  children?: MetricNode[];
  overrides?: { field: string; parent: string; override: string }[];
  formula?: string;
  warning?: string;
}

export const TIER_LABELS: Record<GovernanceTier, { short: string; label: string; bg: string; fg: string }> = {
  canonical:    { short: 'C', label: 'Canonical',    bg: '#00175A', fg: '#FFFFFF' },
  bu_variant:   { short: 'B', label: 'BU Variant',   bg: '#006FCF', fg: '#FFFFFF' },
  team_derived: { short: 'T', label: 'Team Derived', bg: '#B37700', fg: '#FFFFFF' },
};

export const METRIC_TREE: MetricNode = {
  id: 'active_customers',
  name: 'Active Customers',
  tier: 'canonical',
  owner: 'Finance Data Office',
  definition: 'Cardmembers who billed >= $50 in the trailing 90 days',
  formula: 'COUNT(DISTINCT cust_ref) WHERE billed_business >= 50 AND partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)',
  children: [
    {
      id: 'active_premium',
      name: 'Active Customers (Premium)',
      tier: 'bu_variant',
      owner: 'Premium BU',
      definition: 'Active customers with threshold = $100 instead of $50',
      overrides: [
        { field: 'threshold', parent: '$50', override: '$100' },
      ],
    },
    {
      id: 'active_risk_adj',
      name: 'Active Customers (Risk-Adjusted)',
      tier: 'bu_variant',
      owner: 'Risk BU',
      definition: 'Active customers filtered to revolving cardmembers only',
      overrides: [
        { field: 'filter', parent: 'none', override: 'WHERE revolve_flag = TRUE' },
      ],
    },
    {
      id: 'millennial_active_pct',
      name: 'Millennial Active %',
      tier: 'team_derived',
      owner: 'Finance Analytics (ad hoc)',
      definition: 'Active Customers (generation = "Millennial") / Total Active Customers',
      formula: 'COUNT(DISTINCT cust_ref WHERE generation = "Millennial") / COUNT(DISTINCT cust_ref)',
      warning: 'This metric has no canonical owner and is not certified. Queries that resolve to this definition may produce inconsistent results across teams.',
    },
  ],
};

export const SIMILARITY_MOCK = {
  input: 'Active Cardholders',
  match: 'Active Customers',
  score: 0.92,
  tier: 'canonical' as GovernanceTier,
  owner: 'Finance Data Office',
  detail: '$50 threshold',
};
