# ACE Organization — Organizational hierarchy
# Source: axp-lumid.dw.ace_organization
# Business Terms: ACE Organization Level
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ BIGQUERY OPTIMIZATION                                               │
# │                                                                     │
# │ Partition:  NONE (small reference table, <10K rows)                 │
# │ Cluster:    NONE                                                    │
# │                                                                     │
# │ This is a reference/dimension table — small enough to full-scan    │
# │ without cost concern. No partition enforcement needed.              │
# │ Joined to fact explores via org_id (many_to_one from fact side).   │
# └─────────────────────────────────────────────────────────────────────┘

view: ace_organization {
  sql_table_name: `@{PROJECT_ID}.@{DATASET}.ace_organization` ;;

  dimension: org_id {
    primary_key: yes
    type: string
    sql: ${TABLE}.org_id ;;
    label: "Organization ID"
    description: "Unique identifier for the organizational unit."
    hidden: yes
  }

  # ---- Organization Hierarchy ----

  dimension: org_level {
    type: number
    sql: ${TABLE}.org_level ;;
    label: "Organization Level"
    description: "Numeric level in the ACE organizational hierarchy. Lower numbers represent higher levels (e.g., 1 = division, 2 = department). Also known as: ACE org level, hierarchy level, org depth, ace organization level."
    group_label: "Organization"
  }

  dimension: org_name {
    type: string
    sql: ${TABLE}.org_name ;;
    label: "Organization Name"
    description: "Name of the organizational unit. Also known as: department name, division name, org unit, business unit name."
    group_label: "Organization"
  }

  dimension: parent_org_id {
    type: string
    sql: ${TABLE}.parent_org_id ;;
    label: "Parent Organization ID"
    description: "ID of the parent organizational unit in the hierarchy."
    hidden: yes
  }

  dimension: org_type {
    type: string
    sql: ${TABLE}.org_type ;;
    label: "Organization Type"
    description: "Classification of the organizational unit (e.g., Division, Department, Team). Also known as: unit type, org classification."
    group_label: "Organization"
  }

  # ---- Measures ----

  measure: total_org_units {
    type: count_distinct
    sql: ${org_id} ;;
    label: "Total Organization Units"
    description: "Count of unique organizational units. Also known as: org count, department count."
    value_format_name: decimal_0
  }

  measure: avg_org_level {
    type: average
    sql: ${org_level} ;;
    label: "Average Organization Level"
    description: "Average organizational hierarchy level. Also known as: avg ACE organization level, mean org depth."
    value_format_name: decimal_1
  }
}
