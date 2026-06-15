import clickhouse_connect
client = clickhouse_connect.get_client(
    host="192.168.1.11", port=8123,
    username="default", password="TohGroupData@135",
    database="android_music_v2",
    send_receive_timeout=120,
)

r = client.query("""
    SELECT
        uniqExact(user_pseudo_id) AS total_users,
        uniqExactIf(user_pseudo_id, event_name = 'app_remove') AS removed_users
    FROM android_music_v2.android_music_v2_ga4_staging_flat
""")
total, removed = r.result_rows[0]
print("=== Lifetime (flat table) ===")
print("  Total users   :", f"{total:,}")
print("  Removed users :", f"{removed:,}")
print("  Lifetime churn:", f"{removed/total*100:.1f}%")

r2 = client.query("""
    SELECT snapshot_date, count() AS users,
           sum(label_uninstall_7d) AS uninstalled,
           round(avg(label_uninstall_7d)*100,2) AS rate_pct,
           round(avg(days_since_install)) AS avg_age
    FROM android_music_v2.feature_store_uninstall FINAL
    GROUP BY snapshot_date ORDER BY snapshot_date
""")
print("\n=== Feature Store per snapshot ===")
print("Snapshot        Users       Uninstalled   Rate   Avg age(d)")
for row in r2.result_rows:
    print(str(row[0]), f"{row[1]:>12,}", f"{int(row[2]):>12,}", f"{row[3]:>6}%", f"{row[4]:>10.0f}d")
