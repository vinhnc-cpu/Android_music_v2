import clickhouse_connect
c = clickhouse_connect.get_client(
    host='192.168.1.11', port=8123,
    username='default', password='TohGroupData@135',
    database='android_music_v2', send_receive_timeout=120,
)

r = c.query("""
    WITH base AS (
        SELECT
            user_pseudo_id,
            toDate(anyIf(install_date, isNotNull(install_date))) AS idate,
            min(event_date) AS first_event
        FROM android_music_v2.android_music_v2_ga4_staging_flat
        WHERE event_name = 'app_remove'
          AND event_date >= toDate('2026-04-14')
          AND event_date <= toDate('2026-06-09')
        GROUP BY user_pseudo_id
        HAVING idate < toDate('2026-04-07')
    )
    SELECT
        multiIf(
            dateDiff('day', idate, toDate('2026-04-07')) < 90,  'D0-D89 khi data bat dau (<3 thang)',
            dateDiff('day', idate, toDate('2026-04-07')) < 180, 'D90-D179 (3-6 thang)',
            dateDiff('day', idate, toDate('2026-04-07')) < 365, 'D180-D364 (6-12 thang)',
            'D365+ (tren 1 nam)'
        ) AS age_bucket,
        count()      AS users,
        min(idate)   AS oldest_install,
        max(idate)   AS newest_install
    FROM base
    GROUP BY age_bucket
    ORDER BY min(dateDiff('day', idate, toDate('2026-04-07')))
""")
print("=== Tuoi user nhom A luc data bat dau (07/4/2026) ===")
print(f"  {'Bucket':<42} {'Users':>8}  Oldest      Newest")
for row in r.result_rows:
    print(f"  {row[0]:<42} {row[1]:>8,}  {str(row[2])}  {str(row[3])}")

# Có thể dùng behavior gần đây của họ không?
r2 = c.query("""
    WITH base AS (
        SELECT
            user_pseudo_id,
            toDate(anyIf(install_date, isNotNull(install_date))) AS idate
        FROM android_music_v2.android_music_v2_ga4_staging_flat
        WHERE event_name = 'app_remove'
          AND event_date >= toDate('2026-04-14')
          AND event_date <= toDate('2026-06-09')
        GROUP BY user_pseudo_id
        HAVING idate < toDate('2026-04-07')
    )
    SELECT
        count()  AS total_group_a,
        -- Có event_name = session_start trong 30 ngày trước khi remove?
        countIf(has_recent_session = 1)  AS has_recent_behavior,
        round(countIf(has_recent_session=1)*100.0/count(), 1) AS pct_has_behavior
    FROM (
        SELECT
            b.user_pseudo_id,
            toUInt8(countIf(f.event_name = 'session_start'
                AND f.event_date >= b.remove_date - 30
                AND f.event_date < b.remove_date) > 0) AS has_recent_session,
            b.remove_date
        FROM (
            SELECT user_pseudo_id,
                   toDate(anyIf(install_date, isNotNull(install_date))) AS idate,
                   min(event_date) AS remove_date
            FROM android_music_v2.android_music_v2_ga4_staging_flat
            WHERE event_name = 'app_remove'
              AND event_date >= toDate('2026-04-14')
              AND event_date <= toDate('2026-06-09')
            GROUP BY user_pseudo_id
            HAVING idate < toDate('2026-04-07')
        ) b
        LEFT JOIN android_music_v2.android_music_v2_ga4_staging_flat f
            ON b.user_pseudo_id = f.user_pseudo_id
        GROUP BY b.user_pseudo_id, b.remove_date
    )
""")
print()
print("=== Nhom A co du behavior data khong? ===")
row = r2.result_rows[0]
print(f"  Total group A:              {row[0]:,}")
print(f"  Co session trong 30d truoc remove: {row[1]:,} ({row[2]}%)")
print(f"  Khong co session nao:       {row[0]-row[1]:,} ({round((row[0]-row[1])*100/row[0],1)}%)")
