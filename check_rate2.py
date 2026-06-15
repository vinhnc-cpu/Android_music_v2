"""
Kiểm tra chi tiết tại sao uninstall rate thấp.
"""
import clickhouse_connect

client = clickhouse_connect.get_client(
    host="192.168.1.11", port=8123,
    username="default", password="TohGroupData@135",
    database="android_music_v2",
    send_receive_timeout=120,
)

# 1. Distribution of days_since_install in feature store (current state)
print("=== 1. Distribution theo days_since_install (feature store FINAL) ===")
r = client.query("""
    SELECT
        multiIf(
            days_since_install = 0,    'D0',
            days_since_install <= 3,   'D1-D3',
            days_since_install <= 7,   'D4-D7',
            days_since_install <= 14,  'D8-D14',
            days_since_install <= 30,  'D15-D30',
            days_since_install <= 60,  'D31-D60',
            'D61+'
        ) AS bucket,
        count()                                         AS rows,
        round(count()*100.0 / sum(count()) OVER(), 1)  AS pct,
        sum(label_uninstall_7d)                        AS uninstalled,
        round(avg(label_uninstall_7d)*100, 2)          AS rate_pct
    FROM android_music_v2.feature_store_uninstall FINAL
    WHERE snapshot_date < toDate('2026-06-09')
    GROUP BY bucket
    ORDER BY min(days_since_install)
""")
print(f"  {'Bucket':<12} {'Rows':>10} {'Pct':>7} {'Uninstalled':>12} {'Rate':>8}")
total_rows = 0
total_uninstalled = 0
for row in r.result_rows:
    print(f"  {row[0]:<12} {row[1]:>10,} {row[2]:>6}% {int(row[3]):>12,} {row[4]:>7}%")
    total_rows += row[1]
    total_uninstalled += int(row[3])
overall = round(total_uninstalled / total_rows * 100, 2) if total_rows else 0
print(f"  {'TOTAL':<12} {total_rows:>10,} {'100':>6}% {total_uninstalled:>12,} {overall:>7}%")

# 2. Install_date distribution in flat table — kiểm tra xem install_date thực sự là gì
print("\n=== 2. install_date distribution trong flat table ===")
r = client.query("""
    SELECT
        toDate(install_date)   AS idate,
        count()                AS events,
        uniqExact(user_pseudo_id) AS unique_users
    FROM android_music_v2.android_music_v2_ga4_staging_flat
    WHERE isNotNull(install_date)
      AND install_date > toDate('2026-01-01')
    GROUP BY idate
    ORDER BY idate
    LIMIT 60
""")
print(f"  {'Install Date':<15} {'Events':>10} {'Unique Users':>14}")
for row in r.result_rows:
    print(f"  {str(row[0]):<15} {row[1]:>10,} {row[2]:>14,}")

# 3. Tổng users từng snapshot vs users thực sự có install_date trong 30 ngày
print("\n=== 3. Per-snapshot: tổng rows vs rate theo snapshot_date ===")
r = client.query("""
    SELECT
        snapshot_date,
        count()                        AS total,
        countIf(days_since_install <= 7)  AS d0_d7,
        countIf(days_since_install <= 30) AS d0_d30,
        round(avg(label_uninstall_7d)*100, 2) AS overall_rate,
        round(avgIf(label_uninstall_7d, days_since_install <= 7)*100, 2)  AS d0_d7_rate,
        round(avgIf(label_uninstall_7d, days_since_install > 7)*100, 2)   AS d8plus_rate
    FROM android_music_v2.feature_store_uninstall FINAL
    WHERE snapshot_date < toDate('2026-06-09')
    GROUP BY snapshot_date
    ORDER BY snapshot_date
""")
print(f"  {'Snap Date':<12} {'Total':>8} {'D0-D7':>8} {'D0-D30':>8} {'Rate':>7} {'D0-D7 R':>8} {'D8+ R':>7}")
for row in r.result_rows:
    print(f"  {str(row[0]):<12} {row[1]:>8,} {row[2]:>8,} {row[3]:>8,} {row[4]:>6}% {row[5]:>7}% {row[6]:>6}%")

# 4. Check: bao nhiêu app_remove events trong label window thực sự?
print("\n=== 4. app_remove events trong label windows ===")
r = client.query("""
    SELECT
        toMonday(event_date) AS week,
        count()              AS remove_events,
        uniqExact(user_pseudo_id) AS unique_removers
    FROM android_music_v2.android_music_v2_ga4_staging_flat
    WHERE event_name = 'app_remove'
      AND event_date >= toDate('2026-04-07')
    GROUP BY week
    ORDER BY week
""")
print(f"  {'Week':>12} {'Events':>10} {'Unique Users':>14}")
for row in r.result_rows:
    print(f"  {str(row[0]):>12} {row[1]:>10,} {row[2]:>14,}")

# 5. Tính manual: với snap=2026-05-12, bao nhiêu users trong 30d install range có app_remove trong 7d?
print("\n=== 5. Manual check snap=2026-05-12 ===")
r = client.query("""
    SELECT
        uniqExact(user_pseudo_id)                          AS total_users_in_window,
        uniqExactIf(user_pseudo_id,
            event_name = 'app_remove'
            AND event_date >= toDate('2026-05-12')
            AND event_date < toDate('2026-05-19'))         AS uninstallers,
        round(uniqExactIf(user_pseudo_id,
            event_name = 'app_remove'
            AND event_date >= toDate('2026-05-12')
            AND event_date < toDate('2026-05-19')) * 100.0
            / uniqExact(user_pseudo_id), 2)                AS rate_pct
    FROM android_music_v2.android_music_v2_ga4_staging_flat
    WHERE event_date >= toDate('2026-05-12') - 30
      AND event_date < toDate('2026-05-19')
      AND toDate(install_date) >= toDate('2026-05-12') - 30
      AND toDate(install_date) <= toDate('2026-05-12')
""")
row = r.result_rows[0]
print(f"  Total users (install_date in 30d): {row[0]:,}")
print(f"  Users with app_remove in 7d:       {row[1]:,}")
print(f"  Rate:                              {row[2]}%")
