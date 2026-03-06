# Individual Customer Risk — Risk scoring and revolve behavior
# Source: axp-lumid.dw.risk_indv_cust
# Business Terms: Revolve Index
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ BIGQUERY OPTIMIZATION                                               │
# │                                                                     │
# │ Partition:  partition_date (DATE, daily/monthly snapshot)            │
# │ Cluster:    cust_ref, rel_type                                      │
# │ Est. Size:  ~100M+ rows (all customers x relationship types)        │
# │                                                                     │
# │ rel_type is a cluster key — the revolve index calculation filters  │
# │ on rel_type = 'AA', so clustering on this column gives significant │
# │ pruning benefit for the most common query pattern.                  │
# └─────────────────────────────────────────────────────────────────────┘

view: risk_indv_cust {
  sql_table_name: `@{PROJECT_ID}.@{DATASET}.risk_indv_cust` ;;

  # ---- Partition & Clustering (BQ Optimization) ----

  dimension_group: partition {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    sql: ${TABLE}.partition_date ;;
    label: "Partition"
    description: "BigQuery partition column (risk snapshot date). MUST be filtered to avoid full table scan. Also known as: snapshot date, risk assessment date."
    group_label: "BQ Optimization"
    tags: ["partition_key"]
  }

  dimension: cust_ref {
    primary_key: yes
    type: string
    sql: ${TABLE}.cust_ref ;;
    label: "Customer Reference"
    description: "Unique customer reference ID linking to card member profile."
    hidden: yes
    tags: ["cluster_key"]
  }

  # ---- Risk Indicators ----

  dimension: rel_type {
    type: string
    sql: ${TABLE}.rel_type ;;
    label: "Relationship Type"
    description: "Type of customer relationship. 'AA' indicates primary account holder used in revolve index calculation. Also known as: account relationship, customer type."
    group_label: "Risk Profile"
    tags: ["cluster_key"]
  }

  dimension: cm11 {
    type: string
    sql: ${TABLE}.cm11 ;;
    label: "CM11 Identifier"
    description: "Card member level 11 identifier used in revolve calculations."
    hidden: yes
  }

  dimension: rnk_indv_cust {
    type: number
    sql: ${TABLE}.rnk_indv_cust ;;
    label: "Individual Customer Risk Rank"
    description: "Risk ranking score for the individual customer. Lower values indicate lower risk. Also known as: risk rank, customer risk score, risk rating."
    group_label: "Risk Profile"
  }

  # ---- Measures ----

  measure: revolve_index {
    type: number
    sql: SAFE_DIVIDE(
           COUNT(DISTINCT CASE WHEN ${rel_type} = 'AA' THEN ${cm11} END),
           NULLIF(COUNT(DISTINCT ${cm11}), 0)
         ) ;;
    label: "Revolve Index"
    description: "Ratio of revolving (AA relationship type) card members to total card members. Measures the proportion of the portfolio carrying revolving balances. Higher values indicate more revolving behavior. Also known as: revolve ratio, revolving balance index, credit utilization indicator, revolving proportion."
    value_format_name: percent_2
  }

  measure: total_risk_customers {
    type: count_distinct
    sql: ${cust_ref} ;;
    label: "Total Risk Customers"
    description: "Count of unique customers in the risk dataset. Also known as: risk population, assessed customers."
    value_format_name: decimal_0
  }

  measure: revolving_customer_count {
    type: count_distinct
    sql: CASE WHEN ${rel_type} = 'AA' THEN ${cust_ref} END ;;
    label: "Revolving Customer Count"
    description: "Count of customers with revolving balances (AA relationship type). Also known as: revolvers, revolving accounts, credit revolvers."
    value_format_name: decimal_0
  }

  measure: avg_risk_rank {
    type: average
    sql: ${rnk_indv_cust} ;;
    label: "Average Risk Rank"
    description: "Average risk ranking across the customer population. Also known as: mean risk score, avg risk rating."
    value_format_name: decimal_2
  }
}
