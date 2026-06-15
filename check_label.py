import clickhouse_connect
client = clickhouse_connect.get_client(
    host="192.168.1.11", port=8123,
    username="default", password="TohGroupData@135",
    database="android_music_v2",
    send_receive_timeout=120,
)

# 1. Top event names liên quan đến uninstall/remove
print("=== 1. Event names liên quan uninstall ===")
r = client.query("""
    SELECT event_name, count() AS cnt
    FROM android_music_v2.android_music_v2_ga4_staging_flat
    WHERE lower(event_name) LIKE '%remove%'
       OR lower(event_name) LIKE '%uninstall%'
       OR lower(event_name) LIKE '%delete%'
    GROUP BY event_name ORDER BY cnt DESC
""")
for row in r.result_rows:
    print(f"  {row[0]:<40} {row[1]:>10,}")

# 2. Tổng app_remove vs unique users remove
print("\n=== 2. app_remove events vs unique users ===")
r = client.query("""
    SELECT
        count() AS total_events,
        uniqExact(user_pseudo_id) AS unique_users
    FROM android_music_v2.android_music_v2_ga4_staging_flat
    WHERE event_name = 'app_remove'
""")
ev, usr = r.result_rows[0]
print(f"  Total app_remove events : {ev:,}")
print(f"  Unique users with remove: {usr:,}")

# 3. Uninstall rate theo install age bucket trong feature store
print("\n=== 3. Uninstall rate theo install age bucket ===")
r = client.query("""
    SELECT
        multiIf(
            days_since_install = 0,           'D0 (same day)',
            days_since_install <= 3,          'D1-D3',
            days_since_install <= 7,          'D4-D7',
            days_since_install <= 14,         'D8-D14',
            days_since_install <= 30,         'D15-D30',
            days_since_install <= 60,         'D31-D60',
            'D61-D90'
        ) AS age_bucket,
        count()                               AS users,
        sum(label_uninstall_7d)               AS uninstalled,
        round(avg(label_uninstall_7d)*100, 2) AS rate_pct
    FROM android_music_v2.feature_store_uninstall FINAL
    WHERE snapshot_date < toDate('2026-06-08')
    GROUP BY age_bucket
    ORDER BY min(days_since_install)
""")
print(f"  {'Age bucket':<18} {'Users':>10} {'Uninstalled':>12} {'Rate':>8}")
for row in r.result_rows:
    print(f"  {row[0]:<18} {row[1]:>10,} {int(row[2]):>12,} {row[3]:>7}%")

# 4. Check label window: app_remove events rơi vào đâu so với snap
print("\n=== 4. app_remove distribution vs snapshot (sample snap=2026-05-12) ===")
r = client.query("""
    SELECT
        (event_date - toDate('2026-05-12')) AS days_from_snap,
        count() AS cnt
    FROM android_music_v2.android_music_v2_ga4_staging_flat
    WHERE event_name = 'app_remove'
      AND event_date >= toDate('2026-05-12') - 30
      AND event_date < toDate('2026-05-12') + 14
    GROUP BY days_from_snap
    ORDER BY days_from_snap
""")
print(f"  {'Days from snap':>15} {'Events':>10}")
for row in r.result_rows:
    marker = " ← label window" if 0 <= row[0] < 7 else (" ← OUTSIDE label" if row[0] >= 7 else "")
    print(f"  {row[0]:>15} {row[1]:>10,}{marker}")
