/**
 * Fallback SQL + results for demo mode.
 *
 * When the backend Looker MCP connection fails (sql_generation error),
 * the frontend falls back to these pre-written SQL queries and mock results
 * so the demo flows end-to-end without a live Looker connection.
 *
 * Keyed by normalized query substring match — we fuzzy-match the user's
 * query against these keys and return the best match.
 */

export interface FallbackEntry {
  sql: string;
  explore: string;
  model: string;
  columns: string[];
  rows: Record<string, unknown>[];
}

const FALLBACKS: { keywords: string[]; entry: FallbackEntry }[] = [
  // ── Easy: Total billed business for OPEN segment ──
  {
    keywords: ['total billed business', 'open segment', 'billed business'],
    entry: {
      explore: 'finance_cardmember_360',
      model: 'proj-d-lumi-gpt',
      sql: `SELECT
  custins_customer_insights_cardmember.segment AS segment,
  SUM(custins_customer_insights_cardmember.billed_business) AS total_billed_business
FROM \`axp-lumid.dw.custins_customer_insights_cardmember\`
  AS custins_customer_insights_cardmember
WHERE
  custins_customer_insights_cardmember.segment = 'OPEN'
  AND custins_customer_insights_cardmember.partition_date
    BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND CURRENT_DATE()
GROUP BY 1
ORDER BY 2 DESC`,
      columns: ['Segment', 'Total Billed Business'],
      rows: [
        { segment: 'OPEN', total_billed_business: '$4,287,392,140' },
      ],
    },
  },

  // ── Medium: Attrited customers by generation ──
  {
    keywords: ['attrited customers', 'by generation', 'attrited', 'generation'],
    entry: {
      explore: 'finance_cardmember_360',
      model: 'proj-d-lumi-gpt',
      sql: `SELECT
  cmdl_card_main.generation AS generation,
  COUNT(DISTINCT custins_customer_insights_cardmember.cust_ref) AS attrited_customers
FROM \`axp-lumid.dw.custins_customer_insights_cardmember\`
  AS custins_customer_insights_cardmember
JOIN \`axp-lumid.dw.cmdl_card_main\` AS cmdl_card_main
  ON custins_customer_insights_cardmember.cust_ref = cmdl_card_main.cust_ref
WHERE
  custins_customer_insights_cardmember.attrition_flag = TRUE
  AND custins_customer_insights_cardmember.partition_date
    BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND CURRENT_DATE()
GROUP BY 1
ORDER BY 2 DESC`,
      columns: ['Generation', 'Attrited Customers'],
      rows: [
        { generation: 'Millennial', attrited_customers: '142,831' },
        { generation: 'Gen X', attrited_customers: '98,204' },
        { generation: 'Boomer', attrited_customers: '76,519' },
        { generation: 'Gen Z', attrited_customers: '54,302' },
        { generation: 'Silent', attrited_customers: '12,088' },
      ],
    },
  },

  // ── Hard: Attrition rate for Q4 2025 ──
  {
    keywords: ['attrition rate', 'q4 2025', 'attrition'],
    entry: {
      explore: 'finance_cardmember_360',
      model: 'proj-d-lumi-gpt',
      sql: `SELECT
  'Q4 2025' AS quarter,
  COUNT(DISTINCT CASE WHEN attrition_flag = TRUE THEN cust_ref END) AS attrited,
  COUNT(DISTINCT cust_ref) AS total_customers,
  ROUND(
    COUNT(DISTINCT CASE WHEN attrition_flag = TRUE THEN cust_ref END) * 100.0
    / COUNT(DISTINCT cust_ref), 2
  ) AS attrition_rate_pct
FROM \`axp-lumid.dw.custins_customer_insights_cardmember\`
WHERE
  partition_date BETWEEN '2025-10-01' AND '2025-12-31'`,
      columns: ['Quarter', 'Attrited', 'Total Customers', 'Attrition Rate %'],
      rows: [
        { quarter: 'Q4 2025', attrited: '384,944', total_customers: '12,847,210', attrition_rate_pct: '3.00%' },
      ],
    },
  },

  // ── Medium: Highest billed business by merchant category ──
  {
    keywords: ['merchant category', 'billed business', 'highest'],
    entry: {
      explore: 'finance_merchant_profitability',
      model: 'proj-d-lumi-gpt',
      sql: `SELECT
  merchant_profitability.merchant_category AS merchant_category,
  SUM(merchant_profitability.billed_business) AS total_billed_business
FROM \`axp-lumid.dw.merchant_profitability\` AS merchant_profitability
WHERE
  merchant_profitability.partition_date
    BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND CURRENT_DATE()
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10`,
      columns: ['Merchant Category', 'Total Billed Business'],
      rows: [
        { merchant_category: 'Airlines', total_billed_business: '$8,234,102,440' },
        { merchant_category: 'Restaurants', total_billed_business: '$5,891,203,887' },
        { merchant_category: 'Hotels & Lodging', total_billed_business: '$4,712,450,320' },
        { merchant_category: 'Retail - General', total_billed_business: '$3,998,771,205' },
        { merchant_category: 'Gas Stations', total_billed_business: '$2,847,392,140' },
        { merchant_category: 'Online Retail', total_billed_business: '$2,654,830,092' },
        { merchant_category: 'Healthcare', total_billed_business: '$1,923,847,203' },
        { merchant_category: 'Entertainment', total_billed_business: '$1,487,209,441' },
        { merchant_category: 'Grocery', total_billed_business: '$1,245,098,773' },
        { merchant_category: 'Automotive', total_billed_business: '$892,451,320' },
      ],
    },
  },

  // ── Hard: Top 5 travel verticals by gross sales ──
  {
    keywords: ['travel verticals', 'gross sales', 'booking count', 'travel'],
    entry: {
      explore: 'finance_travel_sales',
      model: 'proj-d-lumi-gpt',
      sql: `SELECT
  tls_travel_sales.vertical AS travel_vertical,
  SUM(tls_travel_sales.gross_sales) AS gross_sales,
  COUNT(DISTINCT tls_travel_sales.booking_id) AS booking_count
FROM \`axp-lumid.dw.tls_travel_sales\` AS tls_travel_sales
WHERE
  tls_travel_sales.partition_date
    BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND CURRENT_DATE()
GROUP BY 1
ORDER BY 2 DESC
LIMIT 5`,
      columns: ['Travel Vertical', 'Gross Sales', 'Booking Count'],
      rows: [
        { travel_vertical: 'Hotels', gross_sales: '$3,892,140,220', booking_count: '4,281,039' },
        { travel_vertical: 'Airlines', gross_sales: '$3,247,803,115', booking_count: '2,914,207' },
        { travel_vertical: 'Car Rental', gross_sales: '$987,450,320', booking_count: '1,832,445' },
        { travel_vertical: 'Cruise', gross_sales: '$654,209,887', booking_count: '412,088' },
        { travel_vertical: 'Vacation Packages', gross_sales: '$421,830,092', booking_count: '298,441' },
      ],
    },
  },

  // ── Easy: Total card issuance volume YOY ──
  {
    keywords: ['card issuance', 'year over year', 'issuance volume'],
    entry: {
      explore: 'finance_card_issuance',
      model: 'proj-d-lumi-gpt',
      sql: `SELECT
  EXTRACT(YEAR FROM card_issuance.issue_date) AS issue_year,
  COUNT(DISTINCT card_issuance.card_id) AS cards_issued
FROM \`axp-lumid.dw.card_issuance\` AS card_issuance
GROUP BY 1
ORDER BY 1 DESC`,
      columns: ['Issue Year', 'Cards Issued'],
      rows: [
        { issue_year: '2025', cards_issued: '8,924,130' },
        { issue_year: '2024', cards_issued: '8,412,847' },
        { issue_year: '2023', cards_issued: '7,891,203' },
        { issue_year: '2022', cards_issued: '7,245,098' },
        { issue_year: '2021', cards_issued: '6,892,451' },
      ],
    },
  },

  // ── Catch-all: total spend by generation (playground trace query) ──
  {
    keywords: ['total spend', 'spend by generation', 'spend'],
    entry: {
      explore: 'finance_cardmember_360',
      model: 'proj-d-lumi-gpt',
      sql: `SELECT
  cmdl_card_main.generation,
  SUM(custins_customer_insights_cardmember.total_billed_business_amt)
    AS total_billed_business
FROM \`axp-lumid.dw.custins_customer_insights_cardmember\`
  AS custins_customer_insights_cardmember
JOIN \`axp-lumid.dw.cmdl_card_main\` AS cmdl_card_main
  ON custins_customer_insights_cardmember.cust_ref = cmdl_card_main.cust_ref
WHERE
  custins_customer_insights_cardmember.partition_date
    BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND CURRENT_DATE()
GROUP BY 1
ORDER BY 2 DESC`,
      columns: ['Generation', 'Total Billed Business'],
      rows: [
        { generation: 'Millennial', total_billed_business: '$2,847,392,140' },
        { generation: 'Gen X', total_billed_business: '$1,923,847,203' },
        { generation: 'Boomer', total_billed_business: '$1,654,209,887' },
        { generation: 'Gen Z', total_billed_business: '$892,451,320' },
        { generation: 'Silent', total_billed_business: '$124,830,092' },
      ],
    },
  },
];

/**
 * Find the best fallback match for a user query.
 * Returns null if no reasonable match is found.
 */
export function findFallbackSQL(query: string): FallbackEntry | null {
  const q = query.toLowerCase();

  // Score each fallback by how many keywords match
  let bestScore = 0;
  let bestEntry: FallbackEntry | null = null;

  for (const fallback of FALLBACKS) {
    const score = fallback.keywords.reduce(
      (acc, kw) => acc + (q.includes(kw) ? 1 : 0),
      0,
    );
    if (score > bestScore) {
      bestScore = score;
      bestEntry = fallback.entry;
    }
  }

  return bestScore > 0 ? bestEntry : null;
}
