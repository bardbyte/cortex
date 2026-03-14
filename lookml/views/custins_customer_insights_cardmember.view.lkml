# Customer Insights — Activity metrics, spending, tenure, segmentation
# Source: axp-lumid.dw.custins_customer_insights_cardmember
# Business Terms: Active Customers, Active Customers (Premium), Billed Business,
#                 Customer Tenure, Customers with Authorized Users
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ BIGQUERY OPTIMIZATION                                               │
# │                                                                     │
# │ Partition:  partition_date (DATE, daily)                            │
# │ Cluster:    cust_ref, card_prod_id                                  │
# │ Est. Size:  ~500M+ rows (full cardmember portfolio)                 │
# │                                                                     │
# │ EVERY query to this table MUST include a partition_date filter.     │
# │ Without it, BQ scans the full table — at Amex scale, that's a     │
# │ multi-TB scan costing $$$. The explore enforces this via           │
# │ sql_always_where (hard 365-day cap) + always_filter (user-facing). │
# │                                                                     │
# │ Cluster keys (cust_ref, card_prod_id) provide further pruning when │
# │ filtering by customer or card product. Tag these with              │
# │ tags: ["cluster_key"] so the AI agent can recommend them as        │
# │ filters for cost optimization.                                      │
# └─────────────────────────────────────────────────────────────────────┘
#
# COLUMN STATUS:
#   [CONFIRMED] = visible in Looker instance screenshots (Mar 6 2026)
#   [INFERRED]  = inferred from business terms / likely exists but needs
#                 Ayush to verify against BQ schema

view: custins_customer_insights_cardmember {
  sql_table_name: `@{PROJECT_ID}.@{DATASET}.custins_customer_insights_cardmember` ;;

  # ---- Partition & Clustering (BQ Optimization) ----

  # [INFERRED] — partition_date column name needs verification.
  # BQ tables at Amex typically have a partition_date or rpt_dt column.
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

  # [INFERRED] — cust_ref as FK. Extremely likely (standard Amex key across all tables).
  dimension: cust_ref {
    primary_key: yes
    type: string
    sql: ${TABLE}.cust_ref ;;
    label: "Customer Reference"
    description: "Unique customer reference ID. Also known as: customer ID, CM ID, member number."
    hidden: yes
    tags: ["cluster_key"]
  }

  # [INFERRED] — org_id for organizational hierarchy join. Verify with Ayush.
  dimension: org_id {
    type: string
    sql: ${TABLE}.org_id ;;
    label: "Organization ID"
    description: "Organizational unit ID for the customer. Used to join to ace_organization."
    hidden: yes
  }

  # ---- Activity & Spending ----

  # [CONFIRMED] — "Billed Business or Spend by cardmembers"
  dimension: billed_business {
    type: number
    sql: ${TABLE}.billed_business ;;
    label: "Billed Business"
    description: "Total billed business amount (USD) for the card member, representing total spend charged to the card. Also known as: total spend, billing volume, charged amount, billed amount, card spend."
    group_label: "Spending"
    value_format_name: usd
  }

  # [CONFIRMED] — "Billed Business or Spend by cardmembers in Local Currency for the Issuer country"
  dimension: billed_business_local_am {
    type: number
    sql: ${TABLE}.billed_business_local_am ;;
    label: "Billed Business (Local Currency)"
    description: "Billed business in local currency for the issuer country. Use for international market analysis where USD conversion may distort trends. Also known as: local spend, local billing, issuer currency spend."
    group_label: "Spending"
    hidden: yes
  }

  # [CONFIRMED] — "Account in Force provides the count of active accounts"
  dimension: accounts_in_force {
    type: number
    sql: ${TABLE}.accounts_in_force ;;
    label: "Accounts in Force"
    description: "Count of active accounts for the card member. Accounts in Force is the official active account metric. Also known as: active accounts, AIF, active account count, accounts in force."
    group_label: "Activity Status"
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

  # [CONFIRMED] — "Customer segmentation by new, organic and attrited for the given reporting month"
  dimension: basic_cust_noa {
    type: string
    sql: ${TABLE}.basic_cust_noa ;;
    label: "Customer NOA Segment"
    description: "Customer segmentation: New (tenure <= 13 months with active account), Organic (active with tenure > 13 months), or Attrited. Also known as: customer lifecycle, new/organic/attrited, NOA segment, customer status, acquisition segment."
    group_label: "Segmentation"
  }

  # [CONFIRMED] — "Business Segment (CPS, OPEN, Commercial)"
  dimension: bus_seg {
    type: string
    sql: ${TABLE}.bus_seg ;;
    label: "Business Segment"
    description: "Business segment of the card member: CPS (Consumer & Personal Services), OPEN (Small Business), or Commercial. Also known as: customer segment, business line, card segment."
    group_label: "Segmentation"
  }

  # [CONFIRMED] — "Card Product Segmentation (e.g. Prop Lending, Charge, Cobrand, BIP, Vpay, etc.)"
  dimension: business_org {
    type: string
    sql: ${TABLE}.business_org ;;
    label: "Business Organization"
    description: "Card product segmentation: Prop Lending, Charge, Cobrand, BIP, Vpay, etc. Also known as: product line, card product group, business organization, product segmentation."
    group_label: "Segmentation"
  }

  # [CONFIRMED] — "Card Product Code IA (Initial Arrangement) level or PCT (Percent) Product Code"
  dimension: card_prod_id {
    type: string
    sql: ${TABLE}.card_prod_id ;;
    label: "Card Product ID"
    description: "Card Product Code at Initial Arrangement level. Uniquely identifies a product at a card level. Also known as: product code, card product, product ID, card type."
    group_label: "Card Details"
    tags: ["cluster_key"]
  }

  # [CONFIRMED] — "Date in which plastic is opened"
  dimension_group: card_setup {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    sql: ${TABLE}.card_setup_dt ;;
    label: "Card Setup"
    description: "Date the card plastic was opened/issued. Can be used to derive customer tenure. Also known as: account open date, card open date, setup date."
    group_label: "Card Details"
    convert_tz: no
  }

  # Derived: customer tenure in years from card_setup_dt
  dimension: customer_tenure_years {
    type: number
    sql: DATE_DIFF(CURRENT_DATE(), ${card_setup_raw}, YEAR) ;;
    label: "Customer Tenure (Years)"
    description: "Length of time since the card was opened, in years. Derived from card_setup_dt. Also known as: membership length, time as customer, loyalty duration, years as member, tenure."
    group_label: "Tenure"
  }

  dimension: customer_tenure_tier {
    type: tier
    tiers: [1, 3, 5, 10, 20]
    style: integer
    sql: ${customer_tenure_years} ;;
    label: "Tenure Tier"
    description: "Customer tenure grouped into ranges: <1 yr, 1-3 yr, 3-5 yr, 5-10 yr, 10-20 yr, 20+ yr. Also known as: tenure bucket, loyalty tier, membership length group."
    group_label: "Tenure"
  }

  # [CONFIRMED] — "Y or N based on the Cardmember's age"
  dimension: age35andover {
    type: string
    sql: ${TABLE}.age35andover ;;
    label: "Age 35 and Over"
    description: "Y or N flag indicating if the card member is age 35 or older. Also known as: age flag, over 35 indicator, age segment."
    group_label: "Demographics"
  }

  # [CONFIRMED] — "Account Margin seeks to isolate the revenue and expense associated with the account"
  dimension: account_margin {
    type: number
    sql: ${TABLE}.account_margin ;;
    label: "Account Margin"
    description: "Account profitability metric: deferred_card_fees + travel_commissions + other_fee + balance_transfer_fee + cash_advance_fee + membership_rewards_fee + other_revenue - total_cocms - account_payment_to_partners. Also known as: margin, account profitability, net revenue."
    group_label: "Profitability"
    value_format_name: usd
    hidden: yes
  }

  # [CONFIRMED] — "Total Discount Revenue earned on the transaction"
  dimension: bluebox_discount_revenue {
    type: number
    sql: ${TABLE}.bluebox_discount_revenue ;;
    label: "Discount Revenue"
    description: "Total discount revenue earned on the transaction. Also known as: bluebox discount revenue, merchant discount revenue."
    group_label: "Profitability"
    value_format_name: usd
    hidden: yes
  }

  # [CONFIRMED] — "Annual Revenue for Small Business Cardmembers"
  dimension: business_revenue {
    type: number
    sql: ${TABLE}.business_revenue ;;
    label: "Business Revenue"
    description: "Annual revenue for Small Business card members. Also known as: OPEN revenue, small business revenue."
    group_label: "Profitability"
    value_format_name: usd
    hidden: yes
  }

  # [INFERRED] — authorized_user_count. Verify column name with Ayush.
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
    drill_fields: [cust_ref, billed_business, customer_tenure_years]
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

  measure: total_accounts_in_force {
    type: sum
    sql: ${accounts_in_force} ;;
    label: "Total Accounts in Force"
    description: "Sum of active accounts across card members. Official active account metric. Also known as: total AIF, active account total."
    value_format_name: decimal_0
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
    sql: ${customer_tenure_years} ;;
    label: "Average Tenure"
    description: "Average customer tenure in years across the portfolio. Also known as: avg membership length, average loyalty duration."
    value_format_name: decimal_1
  }

  measure: total_account_margin {
    type: sum
    sql: ${account_margin} ;;
    label: "Total Account Margin"
    description: "Sum of account margin across the portfolio. Key profitability metric. Also known as: total margin, aggregate profitability."
    value_format_name: usd
  }

  measure: customers_with_authorized_users {
    type: count_distinct
    sql: CASE WHEN ${has_authorized_users} THEN ${cust_ref} END ;;
    label: "Customers with Authorized Users"
    description: "Count of card members who have at least one authorized user on their account. Also known as: customers with authorized agents, supplementary card holders, accounts with additional members."
    value_format_name: decimal_0
  }

  # ---- Min/Max Measures (S6: Extremes) ----

  measure: min_billed_business {
    type: min
    sql: ${billed_business} ;;
    label: "Minimum Billed Business"
    description: "Lowest billed business amount across card members. Also known as: min spend, lowest billing, minimum charge, smallest spend."
    value_format_name: usd
  }

  measure: max_billed_business {
    type: max
    sql: ${billed_business} ;;
    label: "Maximum Billed Business"
    description: "Highest billed business amount across card members. Also known as: max spend, peak billing, highest charge, top spender amount, largest spend."
    value_format_name: usd
  }

  # ---- Lifecycle Segment Counts (S2: Conditional Aggregation) ----

  measure: new_customer_count {
    type: count_distinct
    sql: CASE WHEN ${basic_cust_noa} = 'New' THEN ${cust_ref} END ;;
    label: "New Customers"
    description: "Count of card members classified as New (tenure <= 13 months with active account). Also known as: new members, recent acquisitions, new accounts, newly acquired customers."
    value_format_name: decimal_0
  }

  measure: organic_customer_count {
    type: count_distinct
    sql: CASE WHEN ${basic_cust_noa} = 'Organic' THEN ${cust_ref} END ;;
    label: "Organic Customers"
    description: "Count of card members classified as Organic (active with tenure > 13 months). The established customer base. Also known as: existing customers, established members, mature accounts."
    value_format_name: decimal_0
  }

  measure: attrited_customer_count {
    type: count_distinct
    sql: CASE WHEN ${basic_cust_noa} = 'Attrited' THEN ${cust_ref} END ;;
    label: "Attrited Customers"
    description: "Count of card members classified as Attrited (no longer active). Also known as: churned customers, lost customers, attrition count, cancelled members."
    value_format_name: decimal_0
  }

  # ---- Derived Rates (S5: Ratio / Derived) ----

  measure: attrition_rate {
    type: number
    sql: SAFE_DIVIDE(${attrited_customer_count}, ${total_customers}) ;;
    label: "Attrition Rate"
    description: "Percentage of card members who have attrited, calculated as attrited count divided by total customers. Also known as: churn rate, customer loss rate, attrition percentage, cancellation rate."
    value_format_name: percent_2
  }

  measure: new_customer_rate {
    type: number
    sql: SAFE_DIVIDE(${new_customer_count}, ${total_customers}) ;;
    label: "New Customer Rate"
    description: "Percentage of the portfolio that are new customers. Also known as: acquisition rate, new member share, new account percentage."
    value_format_name: percent_2
  }

  measure: active_rate_standard {
    type: number
    sql: SAFE_DIVIDE(${active_customers_standard}, ${total_customers}) ;;
    label: "Active Rate (Standard)"
    description: "Percentage of card members that are active under the standard definition (billed business > $50). Also known as: activation rate, active percentage, engagement rate."
    value_format_name: percent_2
  }

  measure: total_discount_revenue {
    type: sum
    sql: ${bluebox_discount_revenue} ;;
    label: "Total Discount Revenue"
    description: "Sum of discount revenue earned on transactions across card members. Revenue earned from merchant fees. Also known as: total merchant discount, aggregate discount revenue, merchant fee revenue, bluebox revenue."
    value_format_name: usd
  }
}
