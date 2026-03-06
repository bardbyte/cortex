# Card Member Demographics — Core cardmember profile
# Source: cmdl_card_main table
# Business Terms: Generation, Card Member Details, Replacement Rates
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ BIGQUERY OPTIMIZATION                                               │
# │                                                                     │
# │ Partition:  partition_date (DATE, daily snapshot)                    │
# │ Cluster:    cust_ref, card_type                                     │
# │ Est. Size:  ~100M+ rows (all cardmembers, daily snapshots)          │
# │                                                                     │
# │ This is a snapshot/SCD table — each partition_date represents a    │
# │ point-in-time view of card member demographics. When joining to    │
# │ fact tables, ensure the partition_date aligns to avoid cross-day   │
# │ duplication.                                                        │
# └─────────────────────────────────────────────────────────────────────┘

view: cmdl_card_main {
  sql_table_name: `@{PROJECT_ID}.@{DATASET}.cmdl_card_main` ;;

  # ---- Partition & Clustering (BQ Optimization) ----

  dimension_group: partition {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    sql: ${TABLE}.partition_date ;;
    label: "Partition"
    description: "BigQuery partition column (daily snapshot date). MUST be filtered to avoid full table scan. Also known as: snapshot date, data date."
    group_label: "BQ Optimization"
    tags: ["partition_key"]
  }

  dimension: cust_ref {
    primary_key: yes
    type: string
    sql: ${TABLE}.cust_ref ;;
    label: "Customer Reference"
    description: "Unique customer reference ID linking a card member across all systems. Also known as: customer ID, CM ID, member number, cust_ref."
    hidden: yes
    tags: ["cluster_key"]
  }

  # ---- Demographics ----

  dimension: birth_year {
    type: number
    sql: ${TABLE}.birth_year ;;
    label: "Birth Year"
    description: "Card member's year of birth, used for generational segmentation analysis. Also known as: year of birth, DOB year, brth_yr."
    group_label: "Demographics"
  }

  dimension: generation {
    type: string
    sql: CASE
           WHEN ${birth_year} >= 1997 THEN 'Gen Z'
           WHEN ${birth_year} BETWEEN 1981 AND 1996 THEN 'Millennial'
           WHEN ${birth_year} BETWEEN 1965 AND 1980 THEN 'Gen X'
           WHEN ${birth_year} BETWEEN 1945 AND 1964 THEN 'Baby Boomer'
           ELSE 'Other'
         END ;;
    label: "Generation"
    description: "Generational cohort of card member based on birth year. Gen Z (born 1997+), Millennial (1981-1996), Gen X (1965-1980), Baby Boomer (1945-1964). Also known as: generational segment, age group, demographic cohort, generation wise card members."
    group_label: "Demographics"
  }

  # ---- Card Details ----

  dimension: card_type {
    type: string
    sql: ${TABLE}.card_type ;;
    label: "Card Type"
    description: "Type of American Express card product held by the member. Also known as: product type, card product, card tier, card category."
    group_label: "Card Details"
    tags: ["cluster_key"]
  }

  dimension: card_design {
    type: string
    sql: ${TABLE}.card_design ;;
    label: "Card Design"
    description: "Physical card design variant issued to the member. Also known as: card style, card variant, design code."
    group_label: "Card Details"
  }

  dimension: cl_rpt_are {
    type: string
    sql: ${TABLE}.cl_rpt_are ;;
    label: "Replacement Reason"
    description: "Reason for card replacement. Values include CHANGE, CARD_DESIGN, LOST, DAMAGED. Used to calculate replacement rates by reason category. Also known as: card replacement reason, reissue reason, replacement type."
    group_label: "Card Details"
  }

  dimension: is_replacement {
    type: yesno
    sql: ${cl_rpt_are} IN ('CHANGE', 'CARD_DESIGN', 'LOST', 'DAMAGED') ;;
    label: "Is Replacement"
    description: "Whether this card was issued as a replacement (due to change, design update, loss, or damage). Also known as: replacement flag, was replaced, reissued card."
    group_label: "Card Details"
  }

  # ---- Measures ----

  measure: total_card_members {
    type: count_distinct
    sql: ${cust_ref} ;;
    label: "Total Card Members"
    description: "Count of unique card members. Also known as: member count, CM count, headcount, customer count."
    value_format_name: decimal_0
    drill_fields: [cust_ref, card_type, generation]
  }

  measure: total_replacements {
    type: count_distinct
    sql: CASE WHEN ${is_replacement} THEN ${cust_ref} END ;;
    label: "Total Replacements"
    description: "Count of card members who received a replacement card. Used for replacement rate analysis. Also known as: reissue count, replacement count."
    value_format_name: decimal_0
  }

  measure: replacement_rate {
    type: number
    sql: SAFE_DIVIDE(${total_replacements}, ${total_card_members}) ;;
    label: "Replacement Rate"
    description: "Percentage of card members who had a card replacement, calculated as replacement count divided by total members. Also known as: reissue rate, card replacement percentage, replacement ratio."
    value_format_name: percent_2
    drill_fields: [cl_rpt_are, total_replacements]
  }
}
