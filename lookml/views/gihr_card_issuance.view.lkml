# Card Issuance — New card events and campaign tracking
# Source: gihr_card_issuance table
# Business Terms: Campaign Not CM Initiated
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ BIGQUERY OPTIMIZATION                                               │
# │                                                                     │
# │ Partition:  issuance_date (DATE) — already defined as dim group     │
# │ Cluster:    cmgn_cd, lis_type, cust_ref                             │
# │ Est. Size:  ~50M+ rows (all card issuance events)                   │
# │                                                                     │
# │ issuance_date serves double duty: business dimension AND partition  │
# │ key. The explore's always_filter targets this field.                │
# │ cmgn_cd and lis_type are the primary filter dimensions — BQ        │
# │ clustering on these means campaign-specific queries prune heavily. │
# └─────────────────────────────────────────────────────────────────────┘

view: gihr_card_issuance {
  sql_table_name: `@{PROJECT_ID}.@{DATASET}.gihr_card_issuance` ;;

  dimension: issuance_id {
    primary_key: yes
    type: string
    sql: ${TABLE}.issuance_id ;;
    label: "Issuance ID"
    description: "Unique identifier for a card issuance event."
    hidden: yes
  }

  dimension: cust_ref {
    type: string
    sql: ${TABLE}.cust_ref ;;
    label: "Customer Reference"
    description: "Customer reference for the issued card."
    hidden: yes
    tags: ["cluster_key"]
  }

  # ---- Campaign Details ----

  dimension: cmgn_cd {
    type: string
    sql: ${TABLE}.cmgn_cd ;;
    label: "Campaign Code"
    description: "Code identifying the marketing or operational campaign that triggered card issuance. Also known as: campaign ID, campaign identifier, marketing code."
    group_label: "Campaign"
    tags: ["cluster_key"]
  }

  dimension: lis_type {
    type: string
    sql: ${TABLE}.lis_type ;;
    label: "List Type"
    description: "Type of issuance list used for the campaign. MASS_MIGRATION indicates bulk card migration events. Also known as: issuance list type, list category."
    group_label: "Campaign"
    tags: ["cluster_key"]
  }

  dimension: is_not_cm_initiated {
    type: yesno
    sql: ${cmgn_cd} != 'FUMM' OR ${lis_type} = 'MASS_MIGRATION' ;;
    label: "Not CM Initiated"
    description: "Whether the card issuance was NOT initiated by the card member themselves. True when campaign code is not 'FUMM' (member-initiated) or when list type is 'MASS_MIGRATION'. Used to distinguish organic acquisitions from company-driven campaigns. Also known as: campaign not CM initiated, non-member-initiated, company-driven issuance, non-organic issuance."
    group_label: "Campaign"
  }

  dimension: is_cm_initiated {
    type: yesno
    sql: ${cmgn_cd} = 'FUMM' AND ${lis_type} != 'MASS_MIGRATION' ;;
    label: "CM Initiated"
    description: "Whether the card issuance was initiated by the card member (organic acquisition). Also known as: member-initiated, organic issuance, self-service application."
    group_label: "Campaign"
  }

  # ---- Issuance Details ----

  dimension_group: issuance {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    sql: ${TABLE}.issuance_date ;;
    label: "Issuance"
    description: "Date of card issuance. Also known as: issue date, card issue date, activation date."
    group_label: "Issuance Timeline"
  }

  # ---- Measures ----

  measure: total_issuances {
    type: count_distinct
    sql: ${issuance_id} ;;
    label: "Total Card Issuances"
    description: "Count of unique card issuance events. Also known as: new cards issued, issuance count, card activations."
    value_format_name: decimal_0
    drill_fields: [cmgn_cd, lis_type, total_issuances]
  }

  measure: non_cm_initiated_issuances {
    type: count_distinct
    sql: CASE WHEN ${is_not_cm_initiated} THEN ${issuance_id} END ;;
    label: "Non-CM Initiated Issuances"
    description: "Count of card issuances that were not initiated by the card member (campaign-driven or mass migration). Also known as: campaign not CM initiated count, non-organic issuances, company-driven cards."
    value_format_name: decimal_0
    drill_fields: [cmgn_cd, lis_type, non_cm_initiated_issuances]
  }

  measure: cm_initiated_issuances {
    type: count_distinct
    sql: CASE WHEN ${is_cm_initiated} THEN ${issuance_id} END ;;
    label: "CM Initiated Issuances"
    description: "Count of card issuances initiated by the card member (organic). Also known as: organic issuances, member-driven cards, self-service issuances."
    value_format_name: decimal_0
  }

  measure: pct_non_cm_initiated {
    type: number
    sql: SAFE_DIVIDE(${non_cm_initiated_issuances}, ${total_issuances}) ;;
    label: "% Non-CM Initiated"
    description: "Percentage of card issuances that were not member-initiated. Also known as: non-organic rate, campaign issuance rate."
    value_format_name: percent_2
  }
}
