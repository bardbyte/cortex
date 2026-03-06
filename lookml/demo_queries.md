# Finance BU Demo Test Queries

Directed test plan for the Cortex pipeline. Run these in order —
each group validates a specific capability layer.

**Looker instance:** prj-d-lumi-gpt
**Connection:** prj-d-lumi-gpt (BQ: axp-lumid.dw)

---

## Group 1: Single-View Basics (custins only)
Validates: entity extraction, vector search, single-view query

| # | Natural Language Query | Expected Explore | Dimensions | Measures | Filters |
|---|----------------------|-----------------|------------|----------|---------|
| 1 | "How many total customers do we have?" | finance_cardmember_360 | — | total_customers | partition_date: last 90 days |
| 2 | "What is total billed business?" | finance_cardmember_360 | — | total_billed_business | partition_date: last 90 days |
| 3 | "How many active customers do we have?" | finance_cardmember_360 | — | active_customers_standard | partition_date: last 90 days |
| 4 | "Average spend per card member" | finance_cardmember_360 | — | avg_billed_business | partition_date: last 90 days |
| 5 | "Show me total accounts in force" | finance_cardmember_360 | — | total_accounts_in_force | partition_date: last 90 days |

**What to verify:**
- Agent finds `finance_cardmember_360` explore
- Partition filter auto-injected (sql_always_where + always_filter)
- Correct measure selected (not a dimension)
- Query #3 tests disambiguation: "active customers" maps to standard OR premium — agent should pick standard as default

---

## Group 2: Cross-View Join (custins + cmdl)
Validates: graph search, join path validation, multi-view query

| # | Natural Language Query | Expected Explore | Dimensions | Measures | Filters |
|---|----------------------|-----------------|------------|----------|---------|
| 6 | "Total billed business by generation" | finance_cardmember_360 | cmdl.generation | custins.total_billed_business | partition_date: last 90 days |
| 7 | "Active customers by card product" | finance_cardmember_360 | cmdl.card_prod_id | custins.active_customers_standard | partition_date: last 90 days |
| 8 | "Average tenure by generation" | finance_cardmember_360 | cmdl.generation | custins.avg_customer_tenure | partition_date: last 90 days |
| 9 | "Card replacement rate by card product" | finance_cardmember_360 | cmdl.card_prod_id | cmdl.replacement_rate | partition_date: last 90 days |
| 10 | "Millennial customers with billed business over $100" | finance_cardmember_360 | cmdl.generation | custins.active_customers_premium | generation: Millennial, partition_date: last 90 days |

**What to verify:**
- Agent correctly joins custins + cmdl via cust_ref
- Generation dimension comes from cmdl, not custins
- Graph validation confirms both fields in same explore
- Query #10 tests filter injection (generation = 'Millennial')

---

## Group 3: Segmentation & Filtering
Validates: filter handling, cluster key optimization, business term resolution

| # | Natural Language Query | Expected Explore | Dimensions | Measures | Filters |
|---|----------------------|-----------------|------------|----------|---------|
| 11 | "Billed business for OPEN segment" | finance_cardmember_360 | custins.bus_seg | custins.total_billed_business | bus_seg: OPEN |
| 12 | "New vs organic vs attrited customer counts" | finance_cardmember_360 | custins.basic_cust_noa | custins.total_customers | partition_date: last 90 days |
| 13 | "Active customers by business organization" | finance_cardmember_360 | custins.business_org | custins.active_customers_standard | partition_date: last 90 days |
| 14 | "Customers with Apple Pay by generation" | finance_cardmember_360 | cmdl.generation, cmdl.apple_pay_wallet_flag | custins.total_customers | partition_date: last 90 days |
| 15 | "Air services spend for Millennials in last 90 days" | finance_cardmember_360 | cmdl.generation | cmdl.avg_air_services_spend_90d | generation: Millennial |

**What to verify:**
- Business terms resolve correctly (OPEN → bus_seg, NOA → basic_cust_noa)
- Cluster key filters applied when appropriate
- Multi-dimension queries work across views
- Query #12 tests categorical breakdown (NOA segment)

---

## Group 4: Merchant Profitability (largest table)
Validates: cost optimization, aggregate table routing, cross-explore disambiguation

| # | Natural Language Query | Expected Explore | Dimensions | Measures |
|---|----------------------|-----------------|------------|----------|
| 16 | "Average ROC by merchant category" | finance_merchant_profitability | fin.oracle_mer_hier_lvl3 | fin.avg_roc_global |
| 17 | "Total restaurant spend" | finance_merchant_profitability | — | fin.total_restaurant_spend |
| 18 | "How many customers dine at restaurants?" | finance_merchant_profitability | — | fin.dining_customer_count |
| 19 | "ROC by generation" | finance_merchant_profitability | cmdl.generation | fin.avg_roc_global |
| 20 | "Dining customers by business segment" | finance_merchant_profitability | custins.bus_seg | fin.dining_customer_count |

**What to verify:**
- Queries #16-17 should hit aggregate tables (monthly_merchant_category_rollup)
- Query #19 should hit roc_by_generation aggregate table
- Partition filter enforced (this is the biggest table — cost control critical)
- "restaurant spend" resolves to total_restaurant_spend, not total_merchant_spend

---

## Group 5: Travel, Risk, Issuance (other explores)
Validates: multi-explore routing, correct explore selection

| # | Natural Language Query | Expected Explore | Dimensions | Measures |
|---|----------------------|-----------------|------------|----------|
| 21 | "Gross TLS sales by travel vertical" | finance_travel_sales | tlsarpt.travel_vertical | tlsarpt.total_gross_tls_sales |
| 22 | "Average hotel cost per night" | finance_travel_sales | — | tlsarpt.avg_hotel_cost_per_night |
| 23 | "Round trip vs one way bookings" | finance_travel_sales | tlsarpt.air_trip_type | tlsarpt.total_bookings |
| 24 | "What is the revolve index?" | finance_customer_risk | — | risk.revolve_index |
| 25 | "Non-CM initiated card issuances by campaign" | finance_card_issuance | gihr.cmgn_cd | gihr.non_cm_initiated_issuances |

**What to verify:**
- Agent routes to correct explore (not finance_cardmember_360 for everything)
- Travel queries use booking_date as partition (not partition_date)
- "Revolve index" resolves to the custom ratio measure
- "Not CM initiated" resolves to the correct boolean-derived measure

---

## Group 6: Disambiguation & Edge Cases
Validates: disambiguation flow, graceful clarification, boundary detection

| # | Natural Language Query | Expected Behavior |
|---|----------------------|-------------------|
| 26 | "Show me active customers" | Should clarify: Standard ($50) or Premium ($100)? |
| 27 | "What is spend?" | Should clarify: Billed business? Merchant spend? TLS sales? |
| 28 | "Revenue by category and generation" | Should ask: Merchant category (profitability) or business org (cardmember)? |
| 29 | "Compare Millennial and Gen Z retention" | Should recognize no retention metric; suggest tenure/NOA as proxy |
| 30 | "Predict next quarter spend" | Should refuse: out of scope (no prediction capability) |

**What to verify:**
- Agent doesn't guess when ambiguous — asks for clarification
- When multiple explores could answer, agent presents options
- Out-of-scope queries get graceful refusal with redirect
- Query #26 is the critical test: the two active customer definitions are intentionally ambiguous

---

## Group 7: Follow-up / Multi-turn
Validates: conversation context, result modification, follow-up handling

Run as a conversation sequence:

| Turn | Query | Expected Behavior |
|------|-------|-------------------|
| A1 | "Total billed business by generation" | Returns data from finance_cardmember_360 |
| A2 | "Now break that down by card product too" | Adds cmdl.card_prod_id to previous dimensions |
| A3 | "Filter to just Millennials" | Adds generation = 'Millennial' filter |
| A4 | "What about for the OPEN segment?" | Adds bus_seg = 'OPEN' filter |
| A5 | "Switch to showing replacement rate instead" | Swaps measure to cmdl.replacement_rate, keeps filters |

**What to verify:**
- Each turn modifies the previous query, doesn't start from scratch
- Filters accumulate correctly
- Measure swap preserves dimension/filter context
- No redundant retrieval calls for follow-ups

---

## Coverage Matrix

| Business Term | Query # | Explore |
|--------------|---------|---------|
| Active Customers (Standard) | 3, 7, 13, 26 | cardmember_360 |
| Active Customers (Premium) | 10, 26 | cardmember_360 |
| Billed Business | 2, 6, 11 | cardmember_360 |
| Customer Tenure | 8 | cardmember_360 |
| Accounts in Force | 5 | cardmember_360 |
| NOA Segment | 12 | cardmember_360 |
| Generation | 6, 7, 8, 10, 14, 15, 19 | cardmember_360 + merchant |
| Card Product | 7, 9, A2 | cardmember_360 |
| Replacement Rate | 9, A5 | cardmember_360 |
| Average ROC | 16, 19 | merchant_profitability |
| Dining at Restaurant | 17, 18, 20 | merchant_profitability |
| Gross TLS Sales | 21 | travel_sales |
| Hotel Cost Per Night | 22 | travel_sales |
| Air Trip Type | 23 | travel_sales |
| Revolve Index | 24 | customer_risk |
| Campaign Not CM Initiated | 25 | card_issuance |
| ACE Organization Level | — (ref table, tested via joins) | card_issuance |

**Total: 30 test queries + 5 follow-ups = 35 test interactions**
**Coverage: 17/17 business terms**
