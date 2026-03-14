# Travel & Lifestyle Sales — TLS booking and revenue data
# Source: axp-lumid.dw.tlsarpt_travel_sales
# Business Terms: Gross TLS Sales, Travel Verticals, Hotel Cost Per Night, Air Trip Type
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ BIGQUERY OPTIMIZATION                                               │
# │                                                                     │
# │ Partition:  booking_date (DATE, daily)                               │
# │ Cluster:    cust_ref, trip_type, air_trip_type                       │
# │ Est. Size:  ~200M+ rows (all travel bookings)                        │
# │                                                                     │
# │ Trip type and air trip type are cluster keys — filtering by         │
# │ travel vertical or air trip type will prune significant data.       │
# │ The AI agent should recommend these as filters when possible.       │
# └─────────────────────────────────────────────────────────────────────┘

view: tlsarpt_travel_sales {
  sql_table_name: `@{PROJECT_ID}.@{DATASET}.tlsarpt_travel_sales` ;;

  # ---- Partition & Clustering (BQ Optimization) ----

  dimension_group: booking {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    sql: ${TABLE}.booking_date ;;
    label: "Booking"
    description: "Date of the travel booking. This is the BigQuery partition column — MUST be filtered in every query to avoid full table scan. Also known as: transaction date, booking date, travel date, reservation date."
    group_label: "BQ Optimization"
    tags: ["partition_key"]
  }

  dimension: booking_id {
    primary_key: yes
    type: string
    sql: ${TABLE}.booking_id ;;
    label: "Booking ID"
    description: "Unique identifier for a travel booking transaction."
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

  # ---- Trip Classification ----

  dimension: trip_type_raw {
    type: string
    sql: ${TABLE}.trip_type ;;
    hidden: yes
    description: "Raw trip type code from source system."
    tags: ["cluster_key"]
  }

  dimension: travel_vertical {
    type: string
    sql: CASE
           WHEN LOWER(${trip_type_raw}) IN ('v', 'vacation') THEN 'Vacation'
           WHEN LOWER(${trip_type_raw}) IN ('y', 'business') THEN 'Business'
           WHEN LOWER(${trip_type_raw}) IN ('t', 'transit') THEN 'Transit'
           ELSE 'Other'
         END ;;
    label: "Travel Vertical"
    description: "Category of travel booking: Vacation, Business, or Transit. Derived from trip type code. Also known as: trip category, travel segment, booking type, travel verticals, trip vertical."
    group_label: "Trip Details"
  }

  dimension: air_trip_type_raw {
    type: string
    sql: ${TABLE}.air_trip_type ;;
    hidden: yes
    description: "Raw air trip type code."
    tags: ["cluster_key"]
  }

  dimension: air_trip_type {
    type: string
    sql: CASE
           WHEN ${air_trip_type_raw} = 'r' THEN 'Round Trip'
           WHEN ${air_trip_type_raw} = 'o' THEN 'One Way'
           WHEN ${air_trip_type_raw} = 'j' THEN 'Open Jaw'
           ELSE 'Unknown'
         END ;;
    label: "Air Trip Type"
    description: "Type of air travel itinerary: Round Trip, One Way, or Open Jaw. Also known as: flight type, air booking type, itinerary type, air trip category."
    group_label: "Trip Details"
  }

  dimension: rpt_stl {
    type: string
    sql: ${TABLE}.rpt_stl ;;
    label: "Booking Status"
    description: "Report status of the booking. Used to exclude cancelled bookings from revenue calculations. Also known as: reservation status, booking state."
    group_label: "Booking Details"
  }

  dimension: is_cancelled {
    type: yesno
    sql: LOWER(${rpt_stl}) = 'cancelled' ;;
    label: "Is Cancelled"
    description: "Whether the booking was cancelled. Cancelled bookings are excluded from gross sales calculations."
    group_label: "Booking Details"
  }

  # ---- Financial Dimensions (hidden, used by measures) ----

  dimension: gross_usd {
    type: number
    sql: ${TABLE}.gross_usd ;;
    label: "Gross USD"
    description: "Gross booking amount in US dollars."
    hidden: yes
  }

  dimension: hotel_night_count {
    type: number
    sql: ${TABLE}.hlt_nght_ct1 ;;
    label: "Hotel Night Count"
    description: "Number of hotel nights in the booking."
    hidden: yes
  }

  dimension: room_count {
    type: number
    sql: ${TABLE}.rm_na ;;
    label: "Room Count"
    description: "Number of rooms in the hotel booking."
    hidden: yes
  }

  # ---- Measures ----

  measure: total_gross_tls_sales {
    type: sum
    sql: CASE WHEN NOT ${is_cancelled} THEN ${gross_usd} ELSE 0 END ;;
    label: "Gross TLS Sales"
    description: "Total gross Travel & Lifestyle Services sales in USD, excluding cancelled bookings. Primary revenue metric for the travel business. Also known as: total travel sales, TLS revenue, gross travel revenue, travel booking volume, gross TLS sales global."
    value_format_name: usd
    drill_fields: [travel_vertical, air_trip_type, total_gross_tls_sales]
  }

  measure: avg_hotel_cost_per_night {
    type: number
    sql: SAFE_DIVIDE(
           SUM(CASE WHEN NOT ${is_cancelled} THEN ${gross_usd} ELSE 0 END),
           NULLIF(SUM(${hotel_night_count}), 0)
         ) ;;
    label: "Avg Hotel Cost Per Night"
    description: "Average hotel booking cost per night, calculated as gross USD (non-cancelled) divided by total hotel nights. Also known as: ADR, average daily rate, nightly rate, hotel rate, hotel cost per night."
    value_format_name: usd
  }

  measure: total_bookings {
    type: count_distinct
    sql: ${booking_id} ;;
    label: "Total Bookings"
    description: "Count of unique travel bookings. Also known as: booking count, reservation count, transaction count."
    value_format_name: decimal_0
    drill_fields: [booking_id, travel_vertical, air_trip_type, gross_usd]
  }

  measure: total_hotel_nights {
    type: sum
    sql: ${hotel_night_count} ;;
    label: "Total Hotel Nights"
    description: "Sum of all hotel nights booked. Also known as: room nights, hotel night volume, total nights."
    value_format_name: decimal_0
  }

  measure: avg_booking_value {
    type: average
    sql: CASE WHEN NOT ${is_cancelled} THEN ${gross_usd} END ;;
    label: "Average Booking Value"
    description: "Average gross value per non-cancelled booking. Also known as: avg transaction value, mean booking amount."
    value_format_name: usd
  }

  # ---- Min/Max (S6: Extremes) ----

  measure: max_booking_value {
    type: max
    sql: CASE WHEN NOT ${is_cancelled} THEN ${gross_usd} END ;;
    label: "Maximum Booking Value"
    description: "Highest individual non-cancelled booking amount. Also known as: max trip cost, largest booking, most expensive trip, peak booking."
    value_format_name: usd
  }

  measure: min_booking_value {
    type: min
    sql: CASE WHEN NOT ${is_cancelled} THEN ${gross_usd} END ;;
    label: "Minimum Booking Value"
    description: "Lowest individual non-cancelled booking amount. Also known as: min trip cost, smallest booking, cheapest trip."
    value_format_name: usd
  }

  # ---- Conditional Counts (S2) ----

  measure: cancelled_booking_count {
    type: count_distinct
    sql: CASE WHEN ${is_cancelled} THEN ${booking_id} END ;;
    label: "Cancelled Bookings"
    description: "Count of cancelled travel bookings. Also known as: cancellation count, cancelled reservations, cancelled trips."
    value_format_name: decimal_0
  }

  # ---- Derived Rates (S5: Ratio) ----

  measure: cancellation_rate {
    type: number
    sql: SAFE_DIVIDE(${cancelled_booking_count}, ${total_bookings}) ;;
    label: "Cancellation Rate"
    description: "Percentage of travel bookings that were cancelled. Also known as: cancel rate, cancellation percentage, booking cancellation rate."
    value_format_name: percent_2
  }

  measure: avg_rooms_per_booking {
    type: average
    sql: ${room_count} ;;
    label: "Average Rooms Per Booking"
    description: "Average number of rooms per hotel booking. Also known as: avg room count, rooms per reservation."
    value_format_name: decimal_1
  }
}
