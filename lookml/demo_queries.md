# Demo Queries — Finance BU (Cortex NL2SQL)

**Purpose:** These are the natural language questions the Cortex agent should be able to answer based on the 17 business terms mapped across 7 views and 5 explores.

**For each query:** the expected explore, dimensions, measures, and any filters are listed so Animesh can add these to the golden dataset.

---

## Explore 1: Card Member 360

### Q1: "How many active customers do we have?"
- **Explore:** `finance_cardmember_360`
- **Measures:** `custins_customer_insights_cardmember.active_customers_standard`
- **Notes:** Tests synonym matching ("active customers" → `is_active_standard`). May need disambiguation: "standard (>$50) or premium (>$100)?"

### Q2: "How many premium active customers do we have?"
- **Explore:** `finance_cardmember_360`
- **Measures:** `custins_customer_insights_cardmember.active_customers_premium`
- **Notes:** Tests the stricter >$100 threshold. Also known as "active customers 2."

### Q3: "What's the average billed business by generation?"
- **Explore:** `finance_cardmember_360`
- **Dimensions:** `cmdl_card_main.generation`
- **Measures:** `custins_customer_insights_cardmember.avg_billed_business`
- **Notes:** Cross-view query — customer spending × demographics. Tests join correctness.

### Q4: "Show me customer tenure distribution for Baby Boomers"
- **Explore:** `finance_cardmember_360`
- **Dimensions:** `custins_customer_insights_cardmember.customer_tenure_tier`
- **Measures:** `custins_customer_insights_cardmember.total_customers`
- **Filters:** `cmdl_card_main.generation` = "Baby Boomer"
- **Notes:** Tests filtering on joined dimension + tier bucketing.

### Q5: "How many customers have authorized users?"
- **Explore:** `finance_cardmember_360`
- **Measures:** `custins_customer_insights_cardmember.customers_with_authorized_users`
- **Notes:** Tests synonym matching ("authorized users" → "authorized agents" → `has_authorized_users`).

### Q6: "What's our total billed business?"
- **Explore:** `finance_cardmember_360`
- **Measures:** `custins_customer_insights_cardmember.total_billed_business`
- **Notes:** Simple single-measure query. Tests "billed business" = "total spend" synonym matching.

---

## Explore 2: Merchant Profitability

### Q7: "What's the average ROC globally?"
- **Explore:** `finance_merchant_profitability`
- **Measures:** `fin_card_member_merchant_profitability.avg_roc_global`
- **Notes:** Tests "ROC" synonym matching → "Return on Capital." Also known as "average ROC_test global."

### Q8: "How many customers dine at restaurants?"
- **Explore:** `finance_merchant_profitability`
- **Measures:** `fin_card_member_merchant_profitability.dining_customer_count`
- **Notes:** Tests the composite "dining at restaurant" definition (spend > 0 AND category = Restaurants).

### Q9: "What's the total restaurant spend by generation?"
- **Explore:** `finance_merchant_profitability`
- **Dimensions:** `cmdl_card_main.generation`
- **Measures:** `fin_card_member_merchant_profitability.total_restaurant_spend`
- **Notes:** Cross-view query — merchant profitability × demographics.

### Q10: "Average ROC for Millennial card members"
- **Explore:** `finance_merchant_profitability`
- **Measures:** `fin_card_member_merchant_profitability.avg_roc_global`
- **Filters:** `cmdl_card_main.generation` = "Millennial"
- **Notes:** Tests generation filter applied to profitability explore.

---

## Explore 3: Travel Sales

### Q11: "What are our gross travel sales by travel vertical?"
- **Explore:** `finance_travel_sales`
- **Dimensions:** `tlsarpt_travel_sales.travel_vertical`
- **Measures:** `tlsarpt_travel_sales.total_gross_tls_sales`
- **Notes:** Tests "gross TLS sales" synonym matching and travel vertical categorization.

### Q12: "What's the average hotel cost per night for round trip bookings?"
- **Explore:** `finance_travel_sales`
- **Measures:** `tlsarpt_travel_sales.avg_hotel_cost_per_night`
- **Filters:** `tlsarpt_travel_sales.air_trip_type` = "Round Trip"
- **Notes:** Compound query — hotel metric filtered by air trip type.

### Q13: "Total travel sales for Gen Z customers"
- **Explore:** `finance_travel_sales`
- **Measures:** `tlsarpt_travel_sales.total_gross_tls_sales`
- **Filters:** `cmdl_card_main.generation` = "Gen Z"
- **Notes:** Cross-view filter — travel data filtered by demographic.

### Q14: "Show me bookings by air trip type"
- **Explore:** `finance_travel_sales`
- **Dimensions:** `tlsarpt_travel_sales.air_trip_type`
- **Measures:** `tlsarpt_travel_sales.total_bookings`
- **Notes:** Simple dimensional breakdown. Tests "air trip type" field selection.

### Q15: "Average booking value by travel vertical"
- **Explore:** `finance_travel_sales`
- **Dimensions:** `tlsarpt_travel_sales.travel_vertical`
- **Measures:** `tlsarpt_travel_sales.avg_booking_value`
- **Notes:** Tests aggregated metric by category.

---

## Explore 4: Card Issuance

### Q16: "How many cards were issued through non-member campaigns?"
- **Explore:** `finance_card_issuance`
- **Measures:** `gihr_card_issuance.non_cm_initiated_issuances`
- **Notes:** Tests "campaign not CM initiated" synonym matching. Key demo query.

### Q17: "What percentage of issuances are company-driven vs organic?"
- **Explore:** `finance_card_issuance`
- **Measures:** `gihr_card_issuance.pct_non_cm_initiated`, `gihr_card_issuance.total_issuances`
- **Notes:** Tests percentage measure and comparison framing.

### Q18: "Card issuance by campaign code"
- **Explore:** `finance_card_issuance`
- **Dimensions:** `gihr_card_issuance.cmgn_cd`
- **Measures:** `gihr_card_issuance.total_issuances`
- **Notes:** Simple dimensional breakdown by campaign.

---

## Explore 5: Customer Risk

### Q19: "What's the revolve index for our portfolio?"
- **Explore:** `finance_customer_risk`
- **Measures:** `risk_indv_cust.revolve_index`
- **Notes:** Core risk metric. Tests "revolve index" → revolving balance ratio.

### Q20: "Revolve index by generation"
- **Explore:** `finance_customer_risk`
- **Dimensions:** `cmdl_card_main.generation`
- **Measures:** `risk_indv_cust.revolve_index`
- **Notes:** Cross-view — risk × demographics. High-value insight for portfolio management.

### Q21: "How many customers are revolving by card type?"
- **Explore:** `finance_customer_risk`
- **Dimensions:** `cmdl_card_main.card_type`
- **Measures:** `risk_indv_cust.revolving_customer_count`
- **Notes:** Tests "revolving" synonym matching and card type segmentation.

---

## Cross-Cutting Queries (tests explore selection)

### Q22: "What's the replacement rate for Gen X card members?"
- **Explore:** `finance_cardmember_360`
- **Dimensions:** (none, or `cmdl_card_main.generation` as filter)
- **Measures:** `cmdl_card_main.replacement_rate`
- **Filters:** `cmdl_card_main.generation` = "Gen X"
- **Notes:** Tests explore routing — this needs cardmember_360 because replacement rate is on cmdl_card_main.

### Q23: "Compare active customer count vs revolve index by generation"
- **Explore:** `finance_cardmember_360`
- **Dimensions:** `cmdl_card_main.generation`
- **Measures:** `custins_customer_insights_cardmember.active_customers_standard`, `risk_indv_cust.revolve_index`
- **Notes:** Multi-measure query requiring three joined views. High-complexity test.

### Q24: "Total travel sales for active premium customers"
- **Explore:** `finance_travel_sales`
- **Measures:** `tlsarpt_travel_sales.total_gross_tls_sales`
- **Filters:** `custins_customer_insights_cardmember.is_active_premium` = "Yes"
- **Notes:** Tests compound filter — travel data for premium-active customers only.

### Q25: "Which generation spends the most at restaurants?"
- **Explore:** `finance_merchant_profitability`
- **Dimensions:** `cmdl_card_main.generation`
- **Measures:** `fin_card_member_merchant_profitability.total_restaurant_spend`
- **Sort:** `total_restaurant_spend` descending, limit 1
- **Notes:** Tests ranking/superlative query ("most") with cross-view join.

---

## Query Complexity Summary

| Complexity | Count | Description |
|---|---|---|
| Simple (single measure) | 7 | Q1, Q2, Q5, Q6, Q7, Q8, Q19 |
| Medium (dimension + measure) | 9 | Q3, Q11, Q14, Q15, Q17, Q18, Q20, Q21, Q25 |
| Filtered (measure + filter) | 6 | Q4, Q10, Q12, Q13, Q16, Q22 |
| Complex (multi-view, multi-measure) | 3 | Q23, Q24, Q9 |
| **Total** | **25** | |

## Business Terms Coverage

| # | Business Term | View | LookML Field | Covered in Query |
|---|---|---|---|---|
| 1 | Active Customers (Standard) | custins | `is_active_standard`, `active_customers_standard` | Q1, Q23 |
| 2 | Active Customers (Premium) | custins | `is_active_premium`, `active_customers_premium` | Q2, Q24 |
| 3 | Billed Business | custins | `billed_business`, `total_billed_business`, `avg_billed_business` | Q3, Q6 |
| 4 | Customer Tenure | custins | `customer_tenure`, `customer_tenure_tier` | Q4 |
| 5 | Customers with Authorized Users | custins | `has_authorized_users`, `customers_with_authorized_users` | Q5 |
| 6 | Generation | cmdl | `generation` | Q3, Q4, Q9, Q10, Q13, Q20, Q21, Q22, Q23, Q25 |
| 7 | Card Member Details | cmdl | `card_type`, `card_design` | Q21, Q22 |
| 8 | Replacement Rates | cmdl | `is_replacement`, `replacement_rate` | Q22 |
| 9 | Average ROC Global | fin | `avg_roc_global` | Q7, Q10 |
| 10 | Dining at Restaurant | fin | `is_dining_at_restaurant`, `dining_customer_count`, `total_restaurant_spend` | Q8, Q9, Q25 |
| 11 | Gross TLS Sales | tlsarpt | `total_gross_tls_sales` | Q11, Q13, Q24 |
| 12 | Travel Verticals | tlsarpt | `travel_vertical` | Q11, Q15 |
| 13 | Hotel Cost Per Night | tlsarpt | `avg_hotel_cost_per_night` | Q12 |
| 14 | Air Trip Type | tlsarpt | `air_trip_type` | Q12, Q14 |
| 15 | Revolve Index | risk | `revolve_index` | Q19, Q20, Q23 |
| 16 | Campaign Not CM Initiated | gihr | `is_not_cm_initiated`, `non_cm_initiated_issuances` | Q16, Q17 |
| 17 | ACE Organization Level | ace | `org_level`, `avg_org_level` | (via join on explores 1 & 4) |
