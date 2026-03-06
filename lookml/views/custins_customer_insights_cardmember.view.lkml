# Customer Insights — Activity metrics, spending, tenure
# Source: custins_customer_insights_cardmember table
# Business Terms: Active Customers, Active Customers (Premium), Billed Business, Customer Tenure
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ BIGQUERY OPTIMIZATION                                               │
# │                                                                     │
# │ Partition:  partition_date (DATE, daily)                            │
# │ Cluster:    cust_ref, card_type                                     │
# │ Est. Size:  ~500M+ rows (full cardmember portfolio)                 │
# │                                                                     │
# │ EVERY query to this table MUST include a partition_date filter.     │
# │ Without it, BQ scans the full table — at Amex scale, that's a     │
# │ multi-TB scan costing $$$. The explore enforces this via           │
# │ sql_always_where (hard 365-day cap) + always_filter (user-facing). │
# │                                                                     │
# │ Cluster keys (cust_ref, card_type) provide further pruning when    │
# │ filtering by customer or card product. Tag these with              │
# │ tags: ["cluster_key"] so the AI agent can recommend them as        │
# │ filters for cost optimization.                                      │
# └─────────────────────────────────────────────────────────────────────┘

view: custins_customer_insights_cardmember {
  sql_table_name: `@{PROJECT_ID}.@{DATASET}.custins_customer_insights_cardmember` ;;

  # ---- Partition & Clustering (BQ Optimization) ----

  dimension_group: partition {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    sql: ${TABLE}.partition_date ;;
    label: "Partition"
    description: "BigQuery partition column. MUST be filtered in every query to avoid full table scan. Also known as: snapshot date, data date, reporting date."
    group_label: "BQ Optimization"
    tags: ["partition_key"]
  }

  dimension: cust_ref {
    primary_key: yes
    type: string
    sql: ${TABLE}.cust_ref ;;
    label: "Customer Reference"
    description: "Unique customer reference ID. Also known as: customer ID, CM ID, member number."
    hidden: yes
    tags: ["cluster_key"]
  }

  # ---- Activity & Spending ----

  dimension: billed_business {
    type: number
    sql: ${TABLE}.billed_business ;;
    label: "Billed Business"
    description: "Total billed business amount for the card member, representing total spend charged to the card. Also known as: total spend, billing volume, charged amount, billed amount, card spend."
    group_label: "Spending"
    value_format_name: usd
  }

  dimension: is_active_standard {
    type: yesno
    sql: ${billed_business} > 50 ;;
    label: "Is Active (Standard)"
    description: "Card member is considered active under the standard definition if billed business exceeds $50. Also known as: active customer, active cardmember, active status."
    group_label: "Activity Status"
  }

  dimension: is_active_premium {
    type: yesno
    sql: ${billed_business} > 100 ;;
    label: "Is Active (Premium)"
    description: "Card member is considered active under the premium/stricter definition if billed business exceeds $100. Also known as: active customers 2, premium active, high-activity customer."
    group_label: "Activity Status"
  }

  dimension: customer_tenure {
    type: number
    sql: ${TABLE}.customer_tenure ;;
    label: "Customer Tenure"
    description: "Length of time the card member has been an Amex customer, typically measured in years or months. Also known as: membership length, time as customer, loyalty duration, years as member, tenure."
    group_label: "Tenure"
  }

  dimension: customer_tenure_tier {
    type: tier
    tiers: [1, 3, 5, 10, 20]
    style: integer
    sql: ${customer_tenure} ;;
    label: "Tenure Tier"
    description: "Customer tenure grouped into ranges: <1 yr, 1-3 yr, 3-5 yr, 5-10 yr, 10-20 yr, 20+ yr. Also known as: tenure bucket, loyalty tier, membership length group."
    group_label: "Tenure"
  }

  dimension: has_authorized_users {
    type: yesno
    sql: ${TABLE}.authorized_user_count > 0 ;;
    label: "Has Authorized Users"
    description: "Whether the card member has authorized additional users (supplementary card holders) on their account. Also known as: has authorized agents, has supplementary cards, has additional card members."
    group_label: "Account Details"
  }

  # ---- Measures ----

  measure: total_customers {
    type: count_distinct
    sql: ${cust_ref} ;;
    label: "Total Customers"
    description: "Count of unique card members. Also known as: customer count, member count, CM count."
    value_format_name: decimal_0
    drill_fields: [cust_ref, billed_business, customer_tenure]
  }

  measure: active_customers_standard {
    type: count_distinct
    sql: CASE WHEN ${is_active_standard} THEN ${cust_ref} END ;;
    label: "Active Customers (Standard)"
    description: "Count of card members with billed business greater than $50, the standard active customer threshold. Also known as: active count, active CMs, active member count."
    value_format_name: decimal_0
    drill_fields: [cust_ref, billed_business]
  }

  measure: active_customers_premium {
    type: count_distinct
    sql: CASE WHEN ${is_active_premium} THEN ${cust_ref} END ;;
    label: "Active Customers (Premium)"
    description: "Count of card members with billed business greater than $100, the premium active customer threshold. Also known as: active customers 2, premium active count, high-activity count."
    value_format_name: decimal_0
    drill_fields: [cust_ref, billed_business]
  }

  measure: total_billed_business {
    type: sum
    sql: ${billed_business} ;;
    label: "Total Billed Business"
    description: "Sum of all billed business across card members. Represents total spend volume. Also known as: total spend, aggregate billing, total charged amount, portfolio spend."
    value_format_name: usd
    drill_fields: [cust_ref, billed_business]
  }

  measure: avg_billed_business {
    type: average
    sql: ${billed_business} ;;
    label: "Average Billed Business"
    description: "Average billed business per card member. Key indicator of per-member spending power. Also known as: avg spend, average billing, spend per member."
    value_format_name: usd
  }

  measure: avg_customer_tenure {
    type: average
    sql: ${customer_tenure} ;;
    label: "Average Tenure"
    description: "Average customer tenure across the portfolio. Also known as: avg membership length, average loyalty duration."
    value_format_name: decimal_1
  }

  measure: customers_with_authorized_users {
    type: count_distinct
    sql: CASE WHEN ${has_authorized_users} THEN ${cust_ref} END ;;
    label: "Customers with Authorized Users"
    description: "Count of card members who have at least one authorized user on their account. Also known as: customers with authorized agents, supplementary card holders, accounts with additional members."
    value_format_name: decimal_0
  }
}
