# Financial Services Query Patterns — Exhaustive Research
# Generated: 2026-03-12
# Source: Web research across Amex filings, industry benchmarks, academic papers
# Purpose: Thread 1 input — validate LookML coverage against real-world query patterns

## Finance VP Dashboard: Top 20 Questions

| # | Question | Frequency | Current LookML Coverage |
|---|----------|-----------|------------------------|
| 1 | What is our total billed business this quarter vs last quarter? | Weekly | YES - total_billed_business |
| 2 | How many active cardmembers do we have? | Weekly | YES - active_customers_standard/premium |
| 3 | What is our new card acquisition this month? | Monthly | YES - total_issuances |
| 4 | What is our attrition rate? | Monthly | PARTIAL - basic_cust_noa has "Attrited" but no rate |
| 5 | What is average spend per cardmember by segment? | Monthly | YES - avg_billed_business + bus_seg |
| 6 | What is our net card fee revenue? | Quarterly | NO - no fee revenue measure |
| 7 | What is our discount revenue by merchant category? | Quarterly | PARTIAL - bluebox_discount_revenue hidden |
| 8 | What is our revolve rate / transactor-revolver mix? | Monthly | YES - revolve_index |
| 9 | What is our delinquency rate (30/60/90 DPD)? | Weekly | NO |
| 10 | What is our net charge-off rate? | Monthly | NO |
| 11 | What is our provision for credit losses? | Quarterly | NO |
| 12 | What is our ROC by merchant category? | Monthly | YES - avg_roc_global |
| 13 | What is our travel revenue and how is it trending? | Monthly | YES - total_gross_tls_sales |
| 14 | What percentage of new cards are organic vs campaign-driven? | Monthly | YES - pct_non_cm_initiated |
| 15 | How does spend vary by generation? | Quarterly | YES - generation dimension |
| 16 | What is our customer tenure distribution? | Quarterly | YES - customer_tenure_tier |
| 17 | How many cardmembers have authorized users? | Quarterly | YES - customers_with_authorized_users |
| 18 | What is CLV by segment? | Quarterly | NO |
| 19 | What is our digital wallet penetration? | Monthly | PARTIAL - apple_pay_wallet_flag exists |
| 20 | What is our market share vs competitors? | Quarterly | NO - external data |

**Coverage: 10/20 fully, 3/20 partially, 7/20 not covered.**

## Natural Language Synonym Space (Top 30 Metrics)

### Critical Ambiguity Pairs (23 identified)

| Ambiguous Phrase | Could Mean | Could Also Mean |
|-----------------|-----------|----------------|
| "Total spend" | total_billed_business | total_merchant_spend |
| "Revenue" | discount_revenue | total_billed_business |
| "Active customers" | active_customers_standard (>$50) | active_customers_premium (>$100) |
| "How many accounts" | total_customers | total_accounts_in_force |
| "Profitability" | avg_roc_global | total_account_margin |
| "Attrition" | basic_cust_noa='Attrited' count | attrition rate (not computed) |
| "New customers" | total_issuances | basic_cust_noa='New' count |
| "Travel revenue" | total_gross_tls_sales | merchant spend in travel MCC |
| "Card type" | card_prod_id | business_org |
| "Segment" | bus_seg | basic_cust_noa | business_org |
| "Restaurant" | total_restaurant_spend | dining_customer_count |
| "Risk" | revolve_index | avg_risk_rank |
| "By month" | partition_month | booking_month | issuance_month |

## Real Enterprise Query Complexity Distribution

```
TIER 1: Simple Aggregation (no joins)                     ~30-35%
TIER 2: Aggregation with Joins + Filters                  ~25-30%
TIER 3: Time Intelligence + Comparison                    ~15-20%
TIER 4: Complex Analytics                                 ~10-15%
TIER 5: Multi-Step / Unsolvable                           ~5-10%
```

## NL2SQL Accuracy by Tier (State of Art 2025)

| Tier | Best Accuracy | Our Target |
|------|--------------|------------|
| Tier 1 | ~90-95% | 95% |
| Tier 2 | ~75-85% | 90% (our sweet spot) |
| Tier 3 | ~40-60% | 70% (stretch) |
| Tier 4 | ~20-40% | Graceful refusal |
| Tier 5 | ~0-5% | Graceful refusal |

## Sources
- Amex FY 2024 Earnings Release
- Amex 10-K SEC Filing
- FINCH Financial NL2SQL Benchmark (arXiv:2510.01887)
- NL2SQL is a solved problem... Not! (CIDR 2024)
- Spider, BIRD benchmarks
- Visa Portfolio Optimization Framework
- Philadelphia Fed Large Bank Credit Card Data
- Credit Card KPIs (ExecViva, CULytics, i2c)
