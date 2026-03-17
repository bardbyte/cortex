/** Tab 3 — "Define a Metric" mock AI responses */

export const SQL_INPUT_MOCK = `SELECT SUM(billed_business) /
  COUNT(DISTINCT cust_ref)
FROM custins
WHERE partition_date >=
  DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)`;

export const SQL_EXTRACTION_RESULT = {
  canonical_name: 'spend_per_customer',
  display_label: 'Spend Per Customer',
  formula: 'SUM(billed_business) / COUNT(DISTINCT cust_ref)',
  aggregation: 'RATIO',
  required_filters: {
    partition_date: 'trailing 90 days',
  },
  suggested_synonyms: [
    'avg spend per member',
    'per-customer spend',
    'average billed business',
    'spend per cardholder',
  ],
};

export const BUSINESS_FORM_DEFAULTS = {
  name: 'Spend Per Customer',
  definition: 'Total billed business in trailing 90 days divided by distinct cardholder count',
  formula: 'SUM(billed_business) / COUNT(DISTINCT cust_ref)',
  synonyms: ['avg spend per member', 'per-customer spend'],
  owner: 'Finance Data Office',
  domain: 'Finance',
};

export const AI_SUGGESTED_ADDITIONS = {
  synonyms: [
    'average billed business',
    'spend per cardholder',
    'per-member spend',
  ],
  related_metrics: [
    { name: 'total_billed_business', relationship: 'parent' },
    { name: 'active_customers', relationship: 'denominator' },
  ],
};

export const LOOKML_BEFORE = `measure: total_billed_business {
  type: sum
  sql: \${TABLE}.billed_business ;;
}`;

export const LOOKML_AFTER_LINES = [
  { text: 'measure: total_billed_business {', added: false },
  { text: '  type: sum', added: false },
  { text: '  sql: ${TABLE}.billed_business ;;', added: false },
  { text: '  label: "Total Billed Business"', added: true },
  { text: '  description: "Total dollar amount billed to', added: true },
  { text: '    cardmembers within the period. Represents', added: true },
  { text: '    gross spend volume before adjustments or', added: true },
  { text: '    reversals. Also known as: total spend,', added: true },
  { text: '    billed business, gross spend."', added: true },
  { text: '  group_label: "Spend Metrics"', added: true },
  { text: '  tags: ["spend", "volume", "certified"]', added: true },
  { text: '}', added: false },
];
