/** Tab 1 — "What is a Metric?" static data */

export const SAMPLE_ROWS = [
  { cust_ref: 'CUST_0041892', partition_date: '2025-11-15', billed_business: 247.83, generation: 'Millennial' },
  { cust_ref: 'CUST_0087231', partition_date: '2025-11-15', billed_business: 1204.50, generation: 'Gen X' },
  { cust_ref: 'CUST_0012943', partition_date: '2025-11-16', billed_business: 88.20, generation: 'Gen Z' },
  { cust_ref: 'CUST_0056712', partition_date: '2025-11-16', billed_business: 3891.00, generation: 'Boomer' },
  { cust_ref: 'CUST_0099034', partition_date: '2025-11-17', billed_business: 612.45, generation: 'Millennial' },
];

export const LOOKML_CODE = `measure: total_billed_business {
  type: sum
  sql: \${TABLE}.billed_business ;;
  label: "Total Billed Business"
  value_format_name: usd_0
  group_label: "Spend Metrics"
}`;

export const ENRICHED_JSON = {
  canonical_name: 'total_billed_business',
  display_label: 'Total Billed Business',
  description: 'Total dollar amount billed to cardmembers within the period. Represents gross spend volume before adjustments or reversals.',
  synonyms: [
    'total spend',
    'billed business',
    'gross spend',
    'spend volume',
    'billed dollars',
    'total billed',
  ],
  formula: 'SUM(billed_business)',
  aggregation_type: 'SUM',
  required_filters: {
    partition_date: 'BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND CURRENT_DATE()',
  },
  group_label: 'Spend Metrics',
  domain: 'Finance',
  owner: 'Finance Data Office',
  looker_field: 'custins_customer_insights_cardmember.total_billed_business_amt',
  governance_tier: 'canonical',
};

export const LAYER_TOOLTIPS = {
  layer1: "Raw columns have no meaning to an AI. 'billed_business' as a string is just noise.",
  layer2: "The aggregation rule is the metric formula. But 'total_billed_business' still means nothing to natural language.",
  layer3: 'Enriched descriptions, synonyms, and required filters are what allow Cortex to map "total spend" to this exact field.',
};
