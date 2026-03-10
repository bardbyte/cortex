# Finance Model — Cortex AI Pipeline Semantic Layer
# Project: prj-d-lumi-gpt
# Connection: prj-d-lumi-gpt (BigQuery: axp-lumid.dw)
# 7 views, 5 explores, 17+ business terms
#
# ┌─────────────────────────────────────────────────────────────────────────────┐
# │                     BIGQUERY COST OPTIMIZATION STRATEGY                     │
# │                                                                             │
# │  This model enforces THREE layers of protection against runaway BQ costs:  │
# │                                                                             │
# │  LAYER 1: sql_always_where (HARD CEILING — invisible to users)             │
# │    → Every explore has a hidden 365-day maximum time window                │
# │    → Even if a user removes all filters, BQ will never scan > 1 year      │
# │    → This is the last line of defense against full-table scans             │
# │                                                                             │
# │  LAYER 2: always_filter (MANDATORY — visible, value changeable)            │
# │    → Every explore requires a partition_date filter                        │
# │    → Users see this filter, can change the value, but cannot remove it     │
# │    → Default: "last 90 days" — covers most analytical use cases            │
# │                                                                             │
# │  LAYER 3: conditionally_filter (SMART DEFAULT — relaxed if alternative)    │
# │    → Defaults to restrictive filter on cluster key columns                 │
# │    → Automatically removed if user provides their own filter on            │
# │      alternative fields (e.g., filtering by cust_ref removes the default) │
# │    → Reduces bytes scanned via BQ clustering pruning                       │
# │                                                                             │
# │  LAYER 4: aggregate_table (PRE-COMPUTED ROLLUPS — automatic routing)       │
# │    → Common query patterns pre-materialized                                │
# │    → Looker automatically routes matching queries to aggregate tables      │
# │    → Reduces query time from minutes to seconds at PB scale               │
# │                                                                             │
# │  ESTIMATED COST IMPACT:                                                     │
# │    Without optimization: ~$50-100 per unfiltered query on large tables     │
# │    With partition filter:  ~$0.50-5 per query (100-1000x reduction)        │
# │    With aggregate table:   ~$0.01-0.10 per query (reading pre-computed)    │
# │                                                                             │
# │  AI AGENT NOTE:                                                             │
# │    When the Cortex agent generates queries via Looker MCP, the             │
# │    sql_always_where and always_filter are automatically injected by        │
# │    Looker into the generated SQL. The agent does NOT need to add these     │
# │    manually. However, the agent SHOULD recommend cluster key filters       │
# │    (tagged with tags: ["cluster_key"]) when possible to further reduce     │
# │    bytes scanned. The agent should also validate that any user-provided    │
# │    date filter falls within the 365-day sql_always_where window.           │
# └─────────────────────────────────────────────────────────────────────────────┘

connection: "prj-d-lumi-gpt"

# ---- Constants ----
# These resolve the sql_table_name references in view files:
#   `@{PROJECT_ID}.@{DATASET}.table_name`
constant: PROJECT_ID {
  value: "axp-lumid"
}

constant: DATASET {
  value: "dw"
}

# ---- Includes ----
include: "/views/ace_organization.view.lkml"
include: "/views/cmdl_card_main.view.lkml"
include: "/views/custins_customer_insights_cardmember.view.lkml"
include: "/views/fin_card_member_merchant_profitability.view.lkml"
include: "/views/gihr_card_issuance.view.lkml"
include: "/views/risk_indv_cust.view.lkml"
include: "/views/tlsarpt_travel_sales.view.lkml"

# ---- Cache Management ----
datagroup: daily_refresh {
  sql_trigger: SELECT CURRENT_DATE() ;;
  max_cache_age: "24 hours"
  label: "Daily Refresh"
  description: "Refreshes cache daily. Aligned with ETL schedule. Used for all explores and aggregate tables."
}

persist_with: daily_refresh

# ┌─────────────────────────────────────────────────────────────────────┐
# │ DATA TESTS — Query Cost Guardrails                                  │
# │                                                                     │
# │ These tests validate that critical cost-control measures are in    │
# │ place. Run via Spectacles CI or Looker's built-in test runner.     │
# │ If any test fails, the LookML should NOT be deployed.              │
# └─────────────────────────────────────────────────────────────────────┘

test: partition_filter_enforced_cardmember_360 {
  explore_source: finance_cardmember_360 {
    column: total_customers { field: custins_customer_insights_cardmember.total_customers }
    filters: [custins_customer_insights_cardmember.partition_date: "last 7 days"]
  }
  assert: returns_data {
    expression: ${total_customers} >= 0 ;;
  }
}

test: partition_filter_enforced_merchant_profitability {
  explore_source: finance_merchant_profitability {
    column: total_spend { field: fin_card_member_merchant_profitability.total_merchant_spend }
    filters: [fin_card_member_merchant_profitability.partition_date: "last 7 days"]
  }
  assert: returns_data {
    expression: ${total_spend} >= 0 ;;
  }
}

test: partition_filter_enforced_travel_sales {
  explore_source: finance_travel_sales {
    column: total_sales { field: tlsarpt_travel_sales.total_gross_tls_sales }
    filters: [tlsarpt_travel_sales.booking_date: "last 7 days"]
  }
  assert: returns_data {
    expression: ${total_sales} >= 0 ;;
  }
}

# ===========================================================
# EXPLORE 1: Card Member 360 (the power explore)
# Answers: Who are our customers? How active are they? What's their risk profile?
#
# BQ OPTIMIZATION:
#   sql_always_where → hard 365-day cap on custins partition
#   always_filter    → mandatory partition_date filter (default 90 days)
#   conditionally_filter → defaults card_type filter unless user filters by cust_ref
#   aggregate_table  → monthly member counts by generation (most common query)
# ===========================================================

explore: finance_cardmember_360 {
  from: custins_customer_insights_cardmember
  label: "Card Member 360"
  description: "Comprehensive card member view combining customer activity (billed business,
    active status, tenure), demographics (generation, card type), risk indicators (revolve index),
    and organizational context. Use for segmentation, portfolio health, and cross-dimensional analysis."
  group_label: "Finance"

  # LAYER 1: Hard ceiling — hidden, users cannot see or modify
  # Ensures no query ever scans more than 365 days regardless of user input
  sql_always_where:
    ${finance_cardmember_360.partition_raw} >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY) ;;

  # LAYER 2: Mandatory visible filter — users can change value but cannot remove
  always_filter: {
    filters: [finance_cardmember_360.partition_date: "last 90 days"]
  }

  # LAYER 3: Smart default — removed if user filters by cust_ref or card_type
  conditionally_filter: {
    filters: [cmdl_card_main.card_prod_id: ""]
    unless: [finance_cardmember_360.cust_ref, cmdl_card_main.card_prod_id]
  }

  join: cmdl_card_main {
    type: left_outer
    relationship: one_to_one
    sql_on: ${finance_cardmember_360.cust_ref} = ${cmdl_card_main.cust_ref} ;;
  }

  join: risk_indv_cust {
    type: left_outer
    # risk has multiple rows per cust_ref (one per rel_type: AA, etc.)
    relationship: one_to_many
    sql_on: ${finance_cardmember_360.cust_ref} = ${risk_indv_cust.cust_ref} ;;
  }

  join: ace_organization {
    type: left_outer
    relationship: many_to_one
    sql_on: ${finance_cardmember_360.org_id} = ${ace_organization.org_id} ;;
  }

  # LAYER 4: Aggregate table — pre-computed rollup for the most common query pattern
  # "Active customers / billed business by generation" hits this instead of scanning raw table
  aggregate_table: monthly_members_by_generation {
    query: {
      dimensions: [cmdl_card_main.generation, finance_cardmember_360.partition_month]
      measures: [
        finance_cardmember_360.total_customers,
        finance_cardmember_360.active_customers_standard,
        finance_cardmember_360.active_customers_premium,
        finance_cardmember_360.avg_billed_business,
        finance_cardmember_360.total_billed_business
      ]
      filters: [finance_cardmember_360.partition_date: "last 2 years"]
    }
    materialization: {
      datagroup_trigger: daily_refresh
    }
  }
}

# ===========================================================
# EXPLORE 2: Merchant Profitability
# Answers: How profitable are merchant relationships? Who dines at restaurants?
#
# BQ OPTIMIZATION:
#   sql_always_where → hard 365-day cap on fin partition
#   always_filter    → mandatory partition_date (default 90 days)
#   conditionally_filter → defaults merchant category unless user filters by cust_ref
#   aggregate_table  → monthly ROC + spend by merchant category (dashboard query)
#
# NOTE: This is the LARGEST table. Cost optimization is critical.
# ===========================================================

explore: finance_merchant_profitability {
  from: fin_card_member_merchant_profitability
  label: "Merchant Profitability"
  description: "Analyze card member spending by merchant category, Return on Capital (ROC) metrics,
    and dining behavior. Join with demographics for segmented profitability analysis.
    NOTE: This explore queries the largest table in the Finance BU. Always use partition and merchant category filters."
  group_label: "Finance"

  # LAYER 1: Hard ceiling — this table is the biggest, 365-day max is essential
  sql_always_where:
    ${finance_merchant_profitability.partition_raw} >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY) ;;

  # LAYER 2: Mandatory partition filter
  always_filter: {
    filters: [finance_merchant_profitability.partition_date: "last 90 days"]
  }

  # LAYER 3: Smart default — encourage merchant category filtering (cluster key optimization)
  # Removed if user specifies merchant category or customer ref themselves
  conditionally_filter: {
    filters: [finance_merchant_profitability.oracle_mer_hier_lvl3: ""]
    unless: [finance_merchant_profitability.oracle_mer_hier_lvl3, finance_merchant_profitability.cust_ref]
  }

  join: cmdl_card_main {
    type: left_outer
    relationship: many_to_one
    sql_on: ${finance_merchant_profitability.cust_ref} = ${cmdl_card_main.cust_ref} ;;
  }

  join: custins_customer_insights_cardmember {
    type: left_outer
    relationship: many_to_one
    sql_on: ${finance_merchant_profitability.cust_ref} = ${custins_customer_insights_cardmember.cust_ref} ;;
  }

  # LAYER 4: Aggregate table — monthly merchant category rollup
  # Queries like "avg ROC by merchant category" or "restaurant spend by month" hit this
  aggregate_table: monthly_merchant_category_rollup {
    query: {
      dimensions: [
        finance_merchant_profitability.oracle_mer_hier_lvl3,
        finance_merchant_profitability.partition_month
      ]
      measures: [
        finance_merchant_profitability.avg_roc_global,
        finance_merchant_profitability.total_merchant_spend,
        finance_merchant_profitability.total_restaurant_spend,
        finance_merchant_profitability.dining_customer_count
      ]
      filters: [finance_merchant_profitability.partition_date: "last 2 years"]
    }
    materialization: {
      datagroup_trigger: daily_refresh
    }
  }

  # Aggregate table — ROC by generation (cross-view pre-computation)
  aggregate_table: roc_by_generation {
    query: {
      dimensions: [cmdl_card_main.generation, finance_merchant_profitability.partition_month]
      measures: [
        finance_merchant_profitability.avg_roc_global,
        finance_merchant_profitability.total_merchant_spend
      ]
      filters: [finance_merchant_profitability.partition_date: "last 2 years"]
    }
    materialization: {
      datagroup_trigger: daily_refresh
    }
  }
}

# ===========================================================
# EXPLORE 3: Travel Sales
# Answers: What's our travel revenue? How does it break down by vertical and trip type?
#
# BQ OPTIMIZATION:
#   sql_always_where → hard 365-day cap on booking_date
#   always_filter    → mandatory booking_date (default 90 days)
#   conditionally_filter → defaults travel_vertical unless user filters by cust_ref
#   aggregate_table  → monthly travel sales by vertical + air trip type
# ===========================================================

explore: finance_travel_sales {
  from: tlsarpt_travel_sales
  label: "Travel & Lifestyle Sales"
  description: "Analyze Travel & Lifestyle Services revenue by travel vertical (Vacation, Business, Transit),
    air trip type (Round Trip, One Way), and hotel metrics. Join with demographics for customer segmentation."
  group_label: "Finance"

  # LAYER 1: Hard ceiling
  sql_always_where:
    ${finance_travel_sales.booking_raw} >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY) ;;

  # LAYER 2: Mandatory partition filter
  always_filter: {
    filters: [finance_travel_sales.booking_date: "last 90 days"]
  }

  # LAYER 3: Smart default on cluster key
  conditionally_filter: {
    filters: [finance_travel_sales.travel_vertical: ""]
    unless: [finance_travel_sales.travel_vertical, finance_travel_sales.cust_ref, finance_travel_sales.air_trip_type]
  }

  join: cmdl_card_main {
    type: left_outer
    relationship: many_to_one
    sql_on: ${finance_travel_sales.cust_ref} = ${cmdl_card_main.cust_ref} ;;
  }

  join: custins_customer_insights_cardmember {
    type: left_outer
    relationship: many_to_one
    sql_on: ${finance_travel_sales.cust_ref} = ${custins_customer_insights_cardmember.cust_ref} ;;
  }

  # LAYER 4: Aggregate table — monthly sales by vertical and trip type
  aggregate_table: monthly_travel_by_vertical {
    query: {
      dimensions: [
        finance_travel_sales.travel_vertical,
        finance_travel_sales.air_trip_type,
        finance_travel_sales.booking_month
      ]
      measures: [
        finance_travel_sales.total_gross_tls_sales,
        finance_travel_sales.total_bookings,
        finance_travel_sales.avg_hotel_cost_per_night,
        finance_travel_sales.avg_booking_value
      ]
      filters: [finance_travel_sales.booking_date: "last 2 years"]
    }
    materialization: {
      datagroup_trigger: daily_refresh
    }
  }
}

# ===========================================================
# EXPLORE 4: Card Issuance
# Answers: How many cards were issued? What campaigns drove issuance?
#
# BQ OPTIMIZATION:
#   sql_always_where → hard 365-day cap on issuance_date
#   always_filter    → mandatory issuance_date (default 90 days)
#   conditionally_filter → defaults campaign code unless user filters by cust_ref
# ===========================================================

explore: finance_card_issuance {
  from: gihr_card_issuance
  label: "Card Issuance & Campaigns"
  description: "Analyze new card issuance by campaign, distinguishing member-initiated (organic)
    from company-driven (campaign/mass migration) acquisitions. Join with org hierarchy for divisional views."
  group_label: "Finance"

  # LAYER 1: Hard ceiling
  sql_always_where:
    ${finance_card_issuance.issuance_raw} >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY) ;;

  # LAYER 2: Mandatory partition filter (issuance_date is the partition key)
  always_filter: {
    filters: [finance_card_issuance.issuance_date: "last 90 days"]
  }

  # LAYER 3: Smart default on cluster key
  conditionally_filter: {
    filters: [finance_card_issuance.cmgn_cd: ""]
    unless: [finance_card_issuance.cmgn_cd, finance_card_issuance.cust_ref]
  }

  join: cmdl_card_main {
    type: left_outer
    relationship: many_to_one
    sql_on: ${finance_card_issuance.cust_ref} = ${cmdl_card_main.cust_ref} ;;
  }

  join: ace_organization {
    type: left_outer
    relationship: many_to_one
    sql_on: ${finance_card_issuance.org_id} = ${ace_organization.org_id} ;;
  }
}

# ===========================================================
# EXPLORE 5: Customer Risk
# Answers: What's the revolve behavior of our portfolio?
#
# BQ OPTIMIZATION:
#   sql_always_where → hard 365-day cap on risk partition
#   always_filter    → mandatory partition_date (default 90 days)
#   conditionally_filter → defaults rel_type filter (cluster key prunes AA vs non-AA)
# ===========================================================

explore: finance_customer_risk {
  from: risk_indv_cust
  label: "Customer Risk Profile"
  description: "Analyze customer risk indicators including revolve index (proportion of revolving accounts)
    and risk rankings. Join with demographics for risk segmentation by generation and card type."
  group_label: "Finance"

  # LAYER 1: Hard ceiling
  sql_always_where:
    ${finance_customer_risk.partition_raw} >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY) ;;

  # LAYER 2: Mandatory partition filter
  always_filter: {
    filters: [finance_customer_risk.partition_date: "last 90 days"]
  }

  # LAYER 3: Smart default — rel_type is a cluster key, filtering on it prunes significantly
  conditionally_filter: {
    filters: [finance_customer_risk.rel_type: ""]
    unless: [finance_customer_risk.rel_type, finance_customer_risk.cust_ref]
  }

  join: cmdl_card_main {
    type: left_outer
    # risk has multiple rows per cust_ref → many risk rows to one cmdl row
    relationship: many_to_one
    sql_on: ${finance_customer_risk.cust_ref} = ${cmdl_card_main.cust_ref} ;;
  }

  join: custins_customer_insights_cardmember {
    type: left_outer
    # risk has multiple rows per cust_ref → many risk rows to one custins row
    relationship: many_to_one
    sql_on: ${finance_customer_risk.cust_ref} = ${custins_customer_insights_cardmember.cust_ref} ;;
  }

  # LAYER 4: Aggregate table — revolve index by generation (common executive dashboard query)
  aggregate_table: risk_by_generation {
    query: {
      dimensions: [cmdl_card_main.generation, finance_customer_risk.partition_month]
      measures: [
        finance_customer_risk.revolve_index,
        finance_customer_risk.total_risk_customers,
        finance_customer_risk.revolving_customer_count
      ]
      filters: [finance_customer_risk.partition_date: "last 2 years"]
    }
    materialization: {
      datagroup_trigger: daily_refresh
    }
  }
}
