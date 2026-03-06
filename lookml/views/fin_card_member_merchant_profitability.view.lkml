# Card Member Merchant Profitability — Financial performance by merchant
# Source: axp-lumid.dw.fin_card_member_merchant_profitability
# Business Terms: Average ROC, Dining at Restaurant
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ BIGQUERY OPTIMIZATION                                               │
# │                                                                     │
# │ Partition:  partition_date (DATE, monthly/daily)                     │
# │ Cluster:    cust_ref, oracle_mer_hier_lvl3                          │
# │ Est. Size:  ~1B+ rows (every CM x merchant combination)             │
# │                                                                     │
# │ This is the LARGEST table in the Finance BU. Unfiltered queries     │
# │ will scan terabytes. The oracle_mer_hier_lvl3 cluster key means    │
# │ filtering by merchant category (e.g., "Restaurants") dramatically  │
# │ reduces bytes scanned — the AI agent should surface this as a      │
# │ recommended filter.                                                 │
# └─────────────────────────────────────────────────────────────────────┘

view: fin_card_member_merchant_profitability {
  sql_table_name: `@{PROJECT_ID}.@{DATASET}.fin_card_member_merchant_profitability` ;;

  # ---- Partition & Clustering (BQ Optimization) ----

  dimension_group: partition {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    sql: ${TABLE}.partition_date ;;
    label: "Partition"
    description: "BigQuery partition column. MUST be filtered to avoid full table scan. This table can be 1B+ rows unfiltered. Also known as: reporting period, data date."
    group_label: "BQ Optimization"
    tags: ["partition_key"]
  }

  dimension: profitability_id {
    primary_key: yes
    type: string
    sql: CONCAT(${TABLE}.cust_ref, '|', ${TABLE}.merchant_id) ;;
    label: "Profitability Record ID"
    description: "Composite key of customer reference and merchant ID."
    hidden: yes
  }

  dimension: cust_ref {
    type: string
    sql: ${TABLE}.cust_ref ;;
    label: "Customer Reference"
    description: "Customer reference linking to card member profile."
    hidden: yes
    tags: ["cluster_key"]
  }

  # ---- Merchant Details ----

  dimension: oracle_mer_hier_lvl3 {
    type: string
    sql: ${TABLE}.oracle_mer_hier_lvl3 ;;
    label: "Merchant Category (Level 3)"
    description: "Oracle merchant hierarchy level 3 classification. Top-level merchant category such as Restaurants, Retail, Travel, etc. Also known as: merchant category, merchant type, merchant segment, MCC group."
    group_label: "Merchant"
    tags: ["cluster_key"]
  }

  dimension: merchant_name {
    type: string
    sql: ${TABLE}.merchant_name ;;
    label: "Merchant Name"
    description: "Name of the merchant. Also known as: store name, vendor name, business name."
    group_label: "Merchant"
  }

  # ---- Financial Metrics ----

  dimension: roc_test_global {
    type: number
    sql: ${TABLE}.roc_test_global ;;
    label: "ROC Test Global"
    description: "Return on Capital test metric at global level for the card member-merchant relationship. Also known as: ROC, return on capital, profitability score, ROC_test."
    group_label: "Profitability"
    hidden: yes
  }

  dimension: tot_disc_bill_vol_usd_am {
    type: number
    sql: ${TABLE}.tot_disc_bill_vol_usd_am ;;
    label: "Total Discount Bill Volume (USD)"
    description: "Total discounted billed volume in US dollars for this merchant relationship. Represents the actual billed spending at the merchant. Also known as: merchant spend, billed volume, merchant billing amount."
    group_label: "Spending"
    value_format_name: usd
    hidden: yes
  }

  dimension: is_dining_at_restaurant {
    type: yesno
    sql: ${tot_disc_bill_vol_usd_am} > 0 AND ${oracle_mer_hier_lvl3} = 'Restaurants' ;;
    label: "Is Dining at Restaurant"
    description: "Whether the card member has positive spend at a restaurant merchant. True when billed volume > $0 and merchant category is 'Restaurants'. Also known as: restaurant diner, dining customer, eats at restaurants, restaurant spend flag."
    group_label: "Dining"
  }

  # ---- Measures ----

  measure: avg_roc_global {
    type: average
    sql: ${roc_test_global} ;;
    label: "Average ROC (Global)"
    description: "Average Return on Capital across card member-merchant relationships at global level. Key profitability indicator. Also known as: average ROC_test global, mean ROC, avg return on capital, profitability average."
    value_format_name: decimal_4
    drill_fields: [oracle_mer_hier_lvl3, avg_roc_global]
  }

  measure: total_merchant_spend {
    type: sum
    sql: ${tot_disc_bill_vol_usd_am} ;;
    label: "Total Merchant Spend"
    description: "Sum of all discounted billed volume in USD across merchants. Also known as: total merchant billing, aggregate merchant spend, total discount bill volume."
    value_format_name: usd
    drill_fields: [oracle_mer_hier_lvl3, merchant_name, total_merchant_spend]
  }

  measure: total_restaurant_spend {
    type: sum
    sql: CASE WHEN ${is_dining_at_restaurant} THEN ${tot_disc_bill_vol_usd_am} ELSE 0 END ;;
    label: "Total Restaurant Spend"
    description: "Total spend at restaurant merchants only. Filtered to oracle_mer_hier_lvl3 = 'Restaurants' with positive billed volume. Also known as: dining spend, restaurant billing, food and dining volume."
    value_format_name: usd
    drill_fields: [merchant_name, total_restaurant_spend]
  }

  measure: dining_customer_count {
    type: count_distinct
    sql: CASE WHEN ${is_dining_at_restaurant} THEN ${cust_ref} END ;;
    label: "Dining Customer Count"
    description: "Count of unique card members who dined at restaurants (positive spend at restaurant merchants). Also known as: restaurant customer count, dining at restaurant count, diners."
    value_format_name: decimal_0
  }
}
