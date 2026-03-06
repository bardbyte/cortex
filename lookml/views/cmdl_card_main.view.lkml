# Card Member Demographics — Core cardmember profile
# Source: axp-lumid.dw.cmdl_card_main
# Business Terms: Generation, Card Member Details, Replacement Rates
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ BIGQUERY OPTIMIZATION                                               │
# │                                                                     │
# │ Partition:  partition_date (DATE, daily snapshot)                    │
# │ Cluster:    cust_ref, card_prod_id                                  │
# │ Est. Size:  ~100M+ rows (all cardmembers, daily snapshots)          │
# │                                                                     │
# │ This is a snapshot/SCD table — each partition_date represents a    │
# │ point-in-time view of card member demographics. When joining to    │
# │ fact tables, ensure the partition_date aligns to avoid cross-day   │
# │ duplication.                                                        │
# └─────────────────────────────────────────────────────────────────────┘
#
# COLUMN STATUS:
#   [CONFIRMED] = visible in Looker instance screenshots (Mar 6 2026)
#   [INFERRED]  = inferred from business terms / likely exists but needs
#                 Ayush to verify against BQ schema
#
# NOTE: The real BQ table has 500+ columns. This view is CURATED to
# include only the ~20 dimensions relevant for Cortex AI retrieval.
# The auto-generated view in the Looker instance has every column.

view: cmdl_card_main {
  sql_table_name: `@{PROJECT_ID}.@{DATASET}.cmdl_card_main` ;;

  # ---- Partition & Clustering (BQ Optimization) ----

  # [INFERRED] — partition_date column. BQ tables at Amex have partition columns.
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

  # [INFERRED] — cust_ref. Standard FK across all Amex tables.
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

  # [INFERRED] — birth_year. May be named brth_yr or birth_yr in actual schema.
  # Verify column name with Ayush.
  dimension: birth_year {
    type: number
    sql: ${TABLE}.birth_year ;;
    label: "Birth Year"
    description: "Card member's year of birth, used for generational segmentation analysis. Also known as: year of birth, DOB year, brth_yr."
    group_label: "Demographics"
  }

  # Derived from birth_year — generation segmentation
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

  # [CONFIRMED] — "Y or N based on the Cardmember's age"
  # Note: This exists on cmdl_card_main too (not just custins).
  # Using it as a fallback if birth_year doesn't exist.
  # dimension: age35andover {
  #   type: string
  #   sql: ${TABLE}.age35andover ;;
  #   label: "Age 35 and Over"
  #   description: "Y or N flag indicating if the card member is age 35 or older."
  #   group_label: "Demographics"
  # }

  # ---- Card Details ----

  # [CONFIRMED] — "Card Product Code IA (Initial Arrangement) level or PCT Product Code"
  dimension: card_prod_id {
    type: string
    sql: ${TABLE}.card_prod_id ;;
    label: "Card Product"
    description: "Card Product Code at Initial Arrangement level. Uniquely identifies the product at a card level. Also known as: product type, card product, card tier, card category, card type, product code."
    group_label: "Card Details"
    tags: ["cluster_key"]
  }

  # [CONFIRMED] — "Current account category of the card member"
  dimension: acct_ctgy_cd {
    type: string
    sql: ${TABLE}.acct_ctgy_cd ;;
    label: "Account Category"
    description: "Current account category of the card member. Also known as: account type, card category code, account classification."
    group_label: "Card Details"
  }

  # [CONFIRMED] — "Indicates if the card is a basic or supplementary card. B - Basic Card, S - Supplementary."
  dimension: basic_supp_in {
    type: string
    sql: ${TABLE}.basic_supp_in ;;
    label: "Basic/Supplementary"
    description: "Whether the card is a basic (B) or supplementary (S) card. Basic cards are the primary card member, supplementary are authorized users. Also known as: card type basic supp, primary/secondary, basic or supplementary."
    group_label: "Card Details"
  }

  # [CONFIRMED] — "Smart Account Revenue Amount"
  dimension: acct_smrt_rvnue_am {
    type: number
    sql: ${TABLE}.acct_smrt_rvnue_am ;;
    label: "Smart Account Revenue"
    description: "Smart Account Revenue Amount for the card member. Also known as: account revenue, smart revenue."
    group_label: "Revenue"
    value_format_name: usd
    hidden: yes
  }

  # [CONFIRMED] — "Account Billed Balance Amount 30dpb as per latest cycle cut (Month 01)"
  dimension: acct_30dpb_bal_mth01_am {
    type: number
    sql: ${TABLE}.acct_30dpb_bal_mth01_am ;;
    label: "30DPB Balance (Month 01)"
    description: "Account billed balance amount 30 days past billing as per latest cycle cut (Month 01). Excludes 30dpb plus. Used for delinquency analysis. Also known as: 30 day past due balance, delinquency balance, DPB balance."
    group_label: "Risk"
    value_format_name: usd
    hidden: yes
  }

  # [CONFIRMED] — Various airline/travel spend dimensions
  dimension: air_srvc_spend_90_day {
    type: number
    sql: ${TABLE}.air_srvc_spend_90_day ;;
    label: "Air Services Spend (90 Day)"
    description: "Total spend amount in Air Services industry category in the last 90 days. Also known as: airline spend 90 days, air travel spending, flight spend."
    group_label: "Industry Spend"
    value_format_name: usd
  }

  dimension: air_srvc_spend_180_day {
    type: number
    sql: ${TABLE}.air_srvc_spend_180_day ;;
    label: "Air Services Spend (180 Day)"
    description: "Total spend amount in Air Services industry category in the last 180 days. Also known as: airline spend 180 days, air travel spending."
    group_label: "Industry Spend"
    value_format_name: usd
  }

  # [CONFIRMED] — "Total spend in Bar - Cafeteria industry category"
  dimension: bar_caf_spend_90_day {
    type: number
    sql: ${TABLE}.bar_caf_spend_90_day ;;
    label: "Bar/Cafeteria Spend (90 Day)"
    description: "Total spend in Bar and Cafeteria industry category in the last 90 days. Also known as: dining spend, restaurant spend 90 days, bar cafeteria spending."
    group_label: "Industry Spend"
    value_format_name: usd
  }

  # [CONFIRMED] — "Indicator if the card member has a card added to apple pay digital wallet(Y/N)"
  dimension: apple_pay_wallet_flag {
    type: string
    sql: ${TABLE}.apple_pay_wallet_flag ;;
    label: "Apple Pay Enrolled"
    description: "Whether the card member has a card added to Apple Pay digital wallet (Y/N). Also known as: digital wallet flag, apple pay status, mobile pay indicator."
    group_label: "Digital"
  }

  # [CONFIRMED] — "Indicates if the cardmember is enrolled for Airline Fee Credit service"
  dimension: afc_enroll_in {
    type: string
    sql: ${TABLE}.afc_enroll_in ;;
    label: "Airline Fee Credit Enrolled"
    description: "Whether the card member is enrolled for Airline Fee Credit service (Y/N). Also known as: AFC enrollment, airline credit status."
    group_label: "Benefits"
  }

  # [INFERRED] — cl_rpt_are for replacement reason. Verify with Ayush.
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
    drill_fields: [cust_ref, card_prod_id, generation]
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

  measure: avg_air_services_spend_90d {
    type: average
    sql: ${air_srvc_spend_90_day} ;;
    label: "Avg Air Services Spend (90d)"
    description: "Average air services spend in the last 90 days per card member. Also known as: avg airline spend, mean air travel spend."
    value_format_name: usd
  }
}
