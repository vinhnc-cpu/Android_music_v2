"""
Build Feature Store — Android Music v2 Uninstall Prediction.

Milestone-based (default): snapshot_date = install_date + milestone per user.
Milestones D1, D7, D14, D21, D28 — mỗi user tối đa 5 rows, không ghost row.

Calendar-based (legacy / predict): snapshot_date = calendar date cố định.

Usage:
  # Milestone mode (training)
  python -m features.build_feature_store \\
    --install_from 2026-04-07 --install_to 2026-06-08

  # Calendar mode (predict / legacy)
  python -m features.build_feature_store --snapshot_date 2026-06-15
  python -m features.build_feature_store --date_from 2026-04-14 --date_to 2026-06-08 --step 7

  # Init tables
  python -m features.build_feature_store --init_tables

  # Risk scores
  python -m features.build_feature_store --build_risk --risk_cutoff 2026-04-14
"""
import argparse
import logging
from datetime import date, timedelta
from typing import List

import clickhouse_connect

from configs.settings import (
    ch, tables, TOP_SCREENS, TOP_BUTTONS,
    LABEL_HORIZON, FEATURE_WINDOW, MAX_INSTALL_AGE_DAYS, MILESTONES,
)

logger = logging.getLogger(__name__)


def get_client() -> clickhouse_connect.driver.Client:
    return clickhouse_connect.get_client(
        host=ch.host, port=ch.port,
        username=ch.username, password=ch.password,
        database=ch.database,
        send_receive_timeout=ch.send_receive_timeout,
        connect_timeout=ch.connect_timeout,
        settings={"max_memory_usage": 32_000_000_000},
    )


# ─────────────────────────────────────────────────────────────────────────────
# DDL
# ─────────────────────────────────────────────────────────────────────────────

def _screen_cols_ddl() -> str:
    lines = []
    for s in TOP_SCREENS:
        col = s.replace("-", "_").replace(" ", "_")
        lines.append(f"    screen_{col}_cnt_7d           UInt32 DEFAULT 0,")
    return "\n".join(lines)


def _button_cols_ddl() -> str:
    lines = []
    for b in TOP_BUTTONS:
        lines.append(f"    btn_{b}_cnt_7d                UInt32 DEFAULT 0,")
    return "\n".join(lines)


_DDL_FEATURE_STORE = """
CREATE TABLE IF NOT EXISTS {table}
(
    snapshot_date                   Date,
    user_pseudo_id                  String,

    -- A: Acquisition
    media_source                    String DEFAULT '',
    campaign                        String DEFAULT '',
    has_attribution                 UInt8  DEFAULT 0,

    -- B: Country / Language
    country                         String DEFAULT '',
    language                        String DEFAULT '',

    -- C: Device
    app_version                     String DEFAULT '',
    platform                        String DEFAULT '',

    -- D: Install
    days_since_install              Int32  DEFAULT 0,
    hours_since_install             Int32  DEFAULT 0,
    minutes_since_install           Int32  DEFAULT 0,
    seconds_since_install           Int32  DEFAULT 0,
    is_day0_user                    UInt8  DEFAULT 0,
    is_day1_user                    UInt8  DEFAULT 0,
    is_week1_user                   UInt8  DEFAULT 0,

    -- E: Session
    session_cnt_1d                  UInt32 DEFAULT 0,
    session_cnt_3d                  UInt32 DEFAULT 0,
    session_cnt_7d                  UInt32 DEFAULT 0,
    session_cnt_14d                 UInt32 DEFAULT 0,
    session_cnt_30d                 UInt32 DEFAULT 0,
    active_days_7d                  UInt32 DEFAULT 0,
    active_days_30d                 UInt32 DEFAULT 0,
    avg_sessions_per_day_7d         Float32 DEFAULT 0,
    session_trend_7d                Float32 DEFAULT 1,

    -- F: Engagement
    engagement_time_ms_1d           Int64  DEFAULT 0,
    engagement_time_ms_3d           Int64  DEFAULT 0,
    engagement_time_ms_7d           Int64  DEFAULT 0,
    engagement_time_ms_30d          Int64  DEFAULT 0,
    avg_engagement_per_session_7d   Float32 DEFAULT 0,
    engagement_trend_7d             Float32 DEFAULT 1,

    -- G: Recency (giờ kể từ lần cuối, 9999 = chưa bao giờ)
    hours_since_last_session        UInt32 DEFAULT 9999,
    hours_since_last_screen         UInt32 DEFAULT 9999,
    hours_since_last_click          UInt32 DEFAULT 9999,
    hours_since_last_ad             UInt32 DEFAULT 9999,
    hours_since_last_search         UInt32 DEFAULT 9999,
    hours_since_last_engagement     UInt32 DEFAULT 9999,

    -- H: Screens (7d)
{screen_cols}
    unique_screen_cnt_7d            UInt32 DEFAULT 0,
    home_ratio_7d                   Float32 DEFAULT 0,
    video_ratio_7d                  Float32 DEFAULT 0,
    lyrics_ratio_7d                 Float32 DEFAULT 0,
    permission_screen_ratio_7d      Float32 DEFAULT 0,

    -- I: Buttons (7d)
{button_cols}
    unique_button_cnt_7d            UInt32 DEFAULT 0,

    -- J: Search
    search_online_cnt_7d            UInt32 DEFAULT 0,
    search_quick_cnt_7d             UInt32 DEFAULT 0,
    search_screen_cnt_7d            UInt32 DEFAULT 0,
    used_search_7d                  UInt8  DEFAULT 0,
    search_days_7d                  UInt32 DEFAULT 0,

    -- K: Audio
    lyrics_screen_cnt_7d            UInt32 DEFAULT 0,
    audio_player_cnt_7d             UInt32 DEFAULT 0,
    playlist_cnt_7d                 UInt32 DEFAULT 0,
    queue_cnt_7d                    UInt32 DEFAULT 0,
    audio_screen_ratio_7d           Float32 DEFAULT 0,

    -- L: Video
    video_player_cnt_7d             UInt32 DEFAULT 0,
    video_tab_cnt_7d                UInt32 DEFAULT 0,
    floating_video_cnt_7d           UInt32 DEFAULT 0,

    -- M: Permission
    seen_notification_permission    UInt8  DEFAULT 0,
    seen_any_permission             UInt8  DEFAULT 0,
    permission_screen_cnt_7d        UInt32 DEFAULT 0,
    notif_permission_status         String DEFAULT '',

    -- N: Ads
    load_ad_cnt_7d                  UInt32 DEFAULT 0,
    show_ad_cnt_7d                  UInt32 DEFAULT 0,
    paid_ad_impression_cnt_7d       UInt32 DEFAULT 0,
    ads_per_session_7d              Float32 DEFAULT 0,
    ad_revenue_7d                   Float32 DEFAULT 0,

    -- O: IAP / Subscription
    iap_cnt_30d                     UInt32 DEFAULT 0,
    payer_flag                      UInt8  DEFAULT 0,

    -- P: App Quality
    app_exception_cnt_7d            UInt32 DEFAULT 0,
    app_clear_data_cnt_30d          UInt32 DEFAULT 0,
    app_update_cnt_30d              UInt32 DEFAULT 0,
    app_exit_cnt_7d                 UInt32 DEFAULT 0,

    -- Q: Journey
    first_screen                    String DEFAULT '',
    last_screen                     String DEFAULT '',
    first_button                    String DEFAULT '',
    last_button                     String DEFAULT '',
    home_to_search_flag             UInt8  DEFAULT 0,
    search_to_lyrics_flag           UInt8  DEFAULT 0,
    search_to_video_flag            UInt8  DEFAULT 0,
    lyrics_to_exit_flag             UInt8  DEFAULT 0,
    permission_to_exit_flag         UInt8  DEFAULT 0,

    -- R: Funnel
    visited_home                    UInt8  DEFAULT 0,
    visited_player                  UInt8  DEFAULT 0,
    visited_lyrics                  UInt8  DEFAULT 0,
    visited_search                  UInt8  DEFAULT 0,
    visited_video                   UInt8  DEFAULT 0,
    visited_playlist                UInt8  DEFAULT 0,
    visited_scan_music              UInt8  DEFAULT 0,
    funnel_depth                    UInt8  DEFAULT 0,

    -- T: Risk scores (target encoding — điền sau)
    country_uninstall_rate          Float32 DEFAULT -1,
    campaign_uninstall_rate         Float32 DEFAULT -1,
    media_source_uninstall_rate     Float32 DEFAULT -1,
    app_version_uninstall_rate      Float32 DEFAULT -1,

    -- Label
    label_uninstall_7d              UInt8  DEFAULT 0,

    created_at                      DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(snapshot_date)
ORDER BY (snapshot_date, user_pseudo_id)
SETTINGS index_granularity = 8192;
"""


def create_tables(client):
    ddl = _DDL_FEATURE_STORE.format(
        table=tables.feature_store,
        screen_cols=_screen_cols_ddl(),
        button_cols=_button_cols_ddl(),
    )
    client.command(ddl)
    for col_ddl in [
        f"ALTER TABLE {tables.feature_store} ADD COLUMN IF NOT EXISTS minutes_since_install Int32 DEFAULT 0 AFTER hours_since_install",
        f"ALTER TABLE {tables.feature_store} ADD COLUMN IF NOT EXISTS seconds_since_install Int32 DEFAULT 0 AFTER minutes_since_install",
    ]:
        client.command(col_ddl)
    logger.info(f"Table {tables.feature_store} ready.")

    client.command(f"""
    CREATE TABLE IF NOT EXISTS {tables.training}
    AS {tables.feature_store}
    ENGINE = ReplacingMergeTree(created_at)
    PARTITION BY toYYYYMM(snapshot_date)
    ORDER BY (snapshot_date, user_pseudo_id)
    """)
    logger.info(f"Table {tables.training} ready.")


# ─────────────────────────────────────────────────────────────────────────────
# Milestone SQL (mới — anchor = install_date + M per user, không ghost row)
# ─────────────────────────────────────────────────────────────────────────────

def _screen_sql_cols_m(M: int) -> str:
    lines = []
    for s in TOP_SCREENS:
        col = s.replace("-", "_").replace(" ", "_")
        lines.append(
            f"    countIf(src.mapped_screen = '{s}'"
            f" AND src.event_date >= ui.idate + {M} - 7"
            f" AND src.event_date < ui.idate + {M})       AS screen_{col}_cnt_7d,"
        )
    return "\n".join(lines)


def _button_sql_cols_m(M: int) -> str:
    lines = []
    for b in TOP_BUTTONS:
        lines.append(
            f"    countIf(src.click_button_name = '{b}'"
            f" AND src.event_date >= ui.idate + {M} - 7"
            f" AND src.event_date < ui.idate + {M})          AS btn_{b}_cnt_7d,"
        )
    return "\n".join(lines)


def build_milestone_sql(milestone: int, install_from: str, install_to: str) -> str:
    """INSERT SQL cho milestone M.

    snapshot_date = install_date + M per user.
    Chỉ lấy user đã cài trong [install_from, install_to] và chưa remove trước milestone.
    Feature window : [install_date, install_date + M)  — không dùng dữ liệu tương lai.
    Label window   : [install_date + M, install_date + M + 7)  — app_remove xảy ra không?
    """
    M          = milestone
    source     = tables.source
    screen_sql = _screen_sql_cols_m(M)
    button_sql = _button_sql_cols_m(M)

    return f"""
INSERT INTO {tables.feature_store}
SELECT
    ui.idate + {M}      AS snapshot_date,
    src.user_pseudo_id,

    -- A: Acquisition
    ifNull(argMaxIf(src.up_af_media_source, src.event_timestamp,
        src.up_af_media_source != '' AND src.up_af_media_source IS NOT NULL
        AND src.event_date < ui.idate + {M}), '')           AS media_source,
    ifNull(argMaxIf(src.up_af_campaign, src.event_timestamp,
        src.up_af_campaign != '' AND src.up_af_campaign IS NOT NULL
        AND src.event_date < ui.idate + {M}), '')            AS campaign,
    toUInt8(countIf(src.event_name = 'af_attribution_received'
        AND src.event_date < ui.idate + {M}) > 0)            AS has_attribution,

    -- B: Country / Language
    ifNull(argMaxIf(src.country, src.event_timestamp,
        src.country != '' AND src.country IS NOT NULL
        AND src.event_date < ui.idate + {M}), '')             AS country,
    ifNull(argMaxIf(src.up_language, src.event_timestamp,
        src.up_language != '' AND src.up_language IS NOT NULL
        AND src.event_date < ui.idate + {M}), '')             AS language,

    -- C: Device
    ifNull(argMaxIf(src.app_version, src.event_timestamp,
        src.app_version IS NOT NULL AND src.event_date < ui.idate + {M}), '') AS app_version,
    ifNull(argMaxIf(src.platform, src.event_timestamp,
        src.platform IS NOT NULL AND src.event_date < ui.idate + {M}), '')    AS platform,

    -- D: Install (pre-computed flat table columns)
    toInt32(ifNull(maxIf(src.days_since_install,
        src.event_date < ui.idate + {M} AND src.days_since_install IS NOT NULL), 0))    AS days_since_install,
    toInt32(ifNull(maxIf(src.hours_since_install,
        src.event_date < ui.idate + {M} AND src.hours_since_install IS NOT NULL), 0))   AS hours_since_install,
    toInt32(ifNull(maxIf(src.minutes_since_install,
        src.event_date < ui.idate + {M} AND src.minutes_since_install IS NOT NULL), 0)) AS minutes_since_install,
    toInt32(ifNull(maxIf(src.seconds_since_install,
        src.event_date < ui.idate + {M} AND src.seconds_since_install IS NOT NULL), 0)) AS seconds_since_install,
    toUInt8(ifNull(maxIf(src.days_since_install,
        src.event_date < ui.idate + {M} AND src.days_since_install IS NOT NULL), 0) = 0)  AS is_day0_user,
    toUInt8(ifNull(maxIf(src.days_since_install,
        src.event_date < ui.idate + {M} AND src.days_since_install IS NOT NULL), 0) = 1)  AS is_day1_user,
    toUInt8(ifNull(maxIf(src.days_since_install,
        src.event_date < ui.idate + {M} AND src.days_since_install IS NOT NULL), 0) <= 7) AS is_week1_user,

    -- E: Session
    toUInt32(countDistinctIf(src.unique_session_id,
        src.event_name = 'session_start'
        AND src.event_date = ui.idate + {M} - 1))             AS session_cnt_1d,
    toUInt32(countDistinctIf(src.unique_session_id,
        src.event_name = 'session_start'
        AND src.event_date >= ui.idate + {M} - 3
        AND src.event_date < ui.idate + {M}))                 AS session_cnt_3d,
    toUInt32(countDistinctIf(src.unique_session_id,
        src.event_name = 'session_start'
        AND src.event_date >= ui.idate + {M} - 7
        AND src.event_date < ui.idate + {M}))                 AS session_cnt_7d,
    toUInt32(countDistinctIf(src.unique_session_id,
        src.event_name = 'session_start'
        AND src.event_date >= ui.idate + {M} - 14
        AND src.event_date < ui.idate + {M}))                 AS session_cnt_14d,
    toUInt32(countDistinctIf(src.unique_session_id,
        src.event_name = 'session_start'
        AND src.event_date >= ui.idate + {M} - 30
        AND src.event_date < ui.idate + {M}))                 AS session_cnt_30d,

    toUInt32(countDistinctIf(src.event_date,
        src.event_date >= ui.idate + {M} - 7
        AND src.event_date < ui.idate + {M}))                 AS active_days_7d,
    toUInt32(countDistinctIf(src.event_date,
        src.event_date >= ui.idate + {M} - 30
        AND src.event_date < ui.idate + {M}))                 AS active_days_30d,

    if(countDistinctIf(src.event_date,
            src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0,
       countDistinctIf(src.unique_session_id,
            src.event_name = 'session_start'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) /
       countDistinctIf(src.event_date,
            src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}),
       0.0)                                              AS avg_sessions_per_day_7d,

    if(countDistinctIf(src.unique_session_id,
            src.event_name = 'session_start'
            AND src.event_date >= ui.idate + {M} - 14 AND src.event_date < ui.idate + {M} - 7) > 0,
       toFloat32(countDistinctIf(src.unique_session_id,
            src.event_name = 'session_start'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})) /
       toFloat32(countDistinctIf(src.unique_session_id,
            src.event_name = 'session_start'
            AND src.event_date >= ui.idate + {M} - 14 AND src.event_date < ui.idate + {M} - 7)),
       if(countDistinctIf(src.unique_session_id,
            src.event_name = 'session_start'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0,
          2.0, 1.0))                                     AS session_trend_7d,

    -- F: Engagement
    toInt64(sumIf(ifNull(src.engagement_time, 0),
        src.event_date = ui.idate + {M} - 1))                 AS engagement_time_ms_1d,
    toInt64(sumIf(ifNull(src.engagement_time, 0),
        src.event_date >= ui.idate + {M} - 3 AND src.event_date < ui.idate + {M}))  AS engagement_time_ms_3d,
    toInt64(sumIf(ifNull(src.engagement_time, 0),
        src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS engagement_time_ms_7d,
    toInt64(sumIf(ifNull(src.engagement_time, 0),
        src.event_date >= ui.idate + {M} - 30 AND src.event_date < ui.idate + {M})) AS engagement_time_ms_30d,

    if(countDistinctIf(src.unique_session_id,
            src.event_name = 'session_start'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0,
       toFloat32(sumIf(ifNull(src.engagement_time, 0),
            src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})) /
       toFloat32(countDistinctIf(src.unique_session_id,
            src.event_name = 'session_start'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})),
       0.0)                                              AS avg_engagement_per_session_7d,

    if(sumIf(ifNull(src.engagement_time, 0),
            src.event_date >= ui.idate + {M} - 14 AND src.event_date < ui.idate + {M} - 7) > 0,
       toFloat32(sumIf(ifNull(src.engagement_time, 0),
            src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})) /
       toFloat32(sumIf(ifNull(src.engagement_time, 0),
            src.event_date >= ui.idate + {M} - 14 AND src.event_date < ui.idate + {M} - 7)),
       if(sumIf(ifNull(src.engagement_time, 0),
            src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0,
          2.0, 1.0))                                     AS engagement_trend_7d,

    -- G: Recency
    toUInt32(if(max(if(src.event_date < ui.idate + {M}, src.event_date, toDate('1970-01-01'))) > toDate('1970-01-01'),
        dateDiff('day',
            max(if(src.event_date < ui.idate + {M}, src.event_date, toDate('1970-01-01'))),
            ui.idate + {M}) * 24,
        9999))                                           AS hours_since_last_session,

    toUInt32(if(maxIf(src.event_date, src.event_name IN ('screen_view', 'screen_view_ev')
            AND src.event_date < ui.idate + {M}) > toDate('1970-01-01'),
        dateDiff('day',
            maxIf(src.event_date, src.event_name IN ('screen_view', 'screen_view_ev')
                AND src.event_date < ui.idate + {M}),
            ui.idate + {M}) * 24,
        9999))                                           AS hours_since_last_screen,

    toUInt32(if(maxIf(src.event_date, src.event_name = 'click_btn_ev'
            AND src.event_date < ui.idate + {M}) > toDate('1970-01-01'),
        dateDiff('day',
            maxIf(src.event_date, src.event_name = 'click_btn_ev'
                AND src.event_date < ui.idate + {M}),
            ui.idate + {M}) * 24,
        9999))                                           AS hours_since_last_click,

    toUInt32(if(maxIf(src.event_date, src.event_name IN ('show_ad_ev', 'load_ad_ev', 'paid_ad_impression')
            AND src.event_date < ui.idate + {M}) > toDate('1970-01-01'),
        dateDiff('day',
            maxIf(src.event_date, src.event_name IN ('show_ad_ev', 'load_ad_ev', 'paid_ad_impression')
                AND src.event_date < ui.idate + {M}),
            ui.idate + {M}) * 24,
        9999))                                           AS hours_since_last_ad,

    toUInt32(if(maxIf(src.event_date, src.click_button_name IN ('Search', 'QuickSearchClicked')
            AND src.event_date < ui.idate + {M}) > toDate('1970-01-01'),
        dateDiff('day',
            maxIf(src.event_date, src.click_button_name IN ('Search', 'QuickSearchClicked')
                AND src.event_date < ui.idate + {M}),
            ui.idate + {M}) * 24,
        9999))                                           AS hours_since_last_search,

    toUInt32(if(maxIf(src.event_date, src.event_name = 'user_engagement'
            AND src.event_date < ui.idate + {M}) > toDate('1970-01-01'),
        dateDiff('day',
            maxIf(src.event_date, src.event_name = 'user_engagement'
                AND src.event_date < ui.idate + {M}),
            ui.idate + {M}) * 24,
        9999))                                           AS hours_since_last_engagement,

    -- H: Screens (7d)
{screen_sql}
    toUInt32(countDistinctIf(src.mapped_screen,
        src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}
        AND src.mapped_screen IS NOT NULL AND src.mapped_screen != ''))  AS unique_screen_cnt_7d,

    if(countIf(src.mapped_screen IS NOT NULL AND src.mapped_screen != ''
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0,
       toFloat32(countIf(src.mapped_screen = 'MainAudioHome'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})) /
       toFloat32(countIf(src.mapped_screen IS NOT NULL AND src.mapped_screen != ''
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})),
       0.0)                                              AS home_ratio_7d,

    if(countIf(src.mapped_screen IS NOT NULL AND src.mapped_screen != ''
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0,
       toFloat32(countIf(src.mapped_screen IN (
            'VideoPlayer', 'MainVideoTabLocal', 'FloatingVideo', 'VideoSelection')
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})) /
       toFloat32(countIf(src.mapped_screen IS NOT NULL AND src.mapped_screen != ''
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})),
       0.0)                                              AS video_ratio_7d,

    if(countIf(src.mapped_screen IS NOT NULL AND src.mapped_screen != ''
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0,
       toFloat32(countIf(src.mapped_screen = 'AudioPlayerLyrics'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})) /
       toFloat32(countIf(src.mapped_screen IS NOT NULL AND src.mapped_screen != ''
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})),
       0.0)                                              AS lyrics_ratio_7d,

    if(countIf(src.mapped_screen IS NOT NULL AND src.mapped_screen != ''
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0,
       toFloat32(countIf(src.mapped_screen LIKE '%Permission%'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})) /
       toFloat32(countIf(src.mapped_screen IS NOT NULL AND src.mapped_screen != ''
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})),
       0.0)                                              AS permission_screen_ratio_7d,

    -- I: Buttons (7d)
{button_sql}
    toUInt32(countDistinctIf(src.click_button_name,
        src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}
        AND src.click_button_name IS NOT NULL AND src.click_button_name != ''))  AS unique_button_cnt_7d,

    -- J: Search
    toUInt32(countIf(src.click_button_name = 'Search'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS search_online_cnt_7d,
    toUInt32(countIf(src.click_button_name = 'QuickSearchClicked'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS search_quick_cnt_7d,
    toUInt32(countIf(src.mapped_screen = 'AudioSearchAll'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS search_screen_cnt_7d,
    toUInt8(countIf(src.click_button_name IN ('Search', 'QuickSearchClicked')
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0) AS used_search_7d,
    toUInt32(countDistinctIf(src.event_date,
        src.click_button_name IN ('Search', 'QuickSearchClicked')
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS search_days_7d,

    -- K: Audio
    toUInt32(countIf(src.mapped_screen = 'AudioPlayerLyrics'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS lyrics_screen_cnt_7d,
    toUInt32(countIf(src.mapped_screen = 'AudioPlayerSong'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS audio_player_cnt_7d,
    toUInt32(countIf(src.mapped_screen IN ('AudioPlaylistsDetail', 'MainAudioTabPlaylists')
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS playlist_cnt_7d,
    toUInt32(countIf(src.mapped_screen = 'AudioPlayerQueue'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS queue_cnt_7d,
    if(countIf(src.event_name IN ('screen_view', 'screen_view_ev')
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0,
       toFloat32(countIf(src.mapped_screen IN ('AudioPlayerSong', 'AudioPlayerLyrics', 'AudioPlayerQueue')
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})) /
       toFloat32(countIf(src.event_name IN ('screen_view', 'screen_view_ev')
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})),
       0.0)                                              AS audio_screen_ratio_7d,

    -- L: Video
    toUInt32(countIf(src.mapped_screen = 'VideoPlayer'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS video_player_cnt_7d,
    toUInt32(countIf(src.mapped_screen = 'MainVideoTabLocal'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS video_tab_cnt_7d,
    toUInt32(countIf(src.mapped_screen = 'FloatingVideo'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS floating_video_cnt_7d,

    -- M: Permission
    toUInt8(countIf(src.mapped_screen = 'MainAudio_RequestNotificationPermission'
        AND src.event_date < ui.idate + {M}) > 0)            AS seen_notification_permission,
    toUInt8(countIf(src.mapped_screen LIKE '%Permission%'
        AND src.event_date < ui.idate + {M}) > 0)            AS seen_any_permission,
    toUInt32(countIf(src.mapped_screen LIKE '%Permission%'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS permission_screen_cnt_7d,
    ifNull(argMaxIf(src.up_allow_notification, src.event_timestamp,
        src.event_date < ui.idate + {M}), '')                AS notif_permission_status,

    -- N: Ads
    toUInt32(countIf(src.event_name = 'load_ad_ev'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS load_ad_cnt_7d,
    toUInt32(countIf(src.event_name = 'show_ad_ev'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS show_ad_cnt_7d,
    toUInt32(countIf(src.event_name = 'paid_ad_impression'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS paid_ad_impression_cnt_7d,
    if(countDistinctIf(src.unique_session_id,
            src.event_name = 'session_start'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}) > 0,
       toFloat32(countIf(src.event_name = 'show_ad_ev'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})) /
       toFloat32(countDistinctIf(src.unique_session_id,
            src.event_name = 'session_start'
            AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M})),
       0.0)                                              AS ads_per_session_7d,
    toFloat32(sumIf(ifNull(src.ep_revenue, 0),
        src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))      AS ad_revenue_7d,

    -- O: IAP / Subscription
    toUInt32(countIf(src.event_name = 'iap_ev'
        AND src.event_date >= ui.idate + {M} - 30 AND src.event_date < ui.idate + {M})) AS iap_cnt_30d,
    toUInt8(countIf(src.event_name = 'iap_ev'
        AND src.event_date < ui.idate + {M}) > 0)             AS payer_flag,

    -- P: Quality
    toUInt32(countIf(src.event_name = 'app_exception'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS app_exception_cnt_7d,
    toUInt32(countIf(src.event_name = 'app_clear_data'
        AND src.event_date >= ui.idate + {M} - 30 AND src.event_date < ui.idate + {M})) AS app_clear_data_cnt_30d,
    toUInt32(countIf(src.event_name = 'app_update'
        AND src.event_date >= ui.idate + {M} - 30 AND src.event_date < ui.idate + {M})) AS app_update_cnt_30d,
    toUInt32(countIf(src.event_name = 'app_exit'
        AND src.event_date >= ui.idate + {M} - 7 AND src.event_date < ui.idate + {M}))  AS app_exit_cnt_7d,

    -- Q: Journey
    ifNull(argMinIf(src.mapped_screen, src.event_timestamp,
        src.mapped_screen IS NOT NULL AND src.mapped_screen != ''
        AND src.event_date < ui.idate + {M}), '')             AS first_screen,
    ifNull(argMaxIf(src.mapped_screen, src.event_timestamp,
        src.mapped_screen IS NOT NULL AND src.mapped_screen != ''
        AND src.event_date < ui.idate + {M}), '')             AS last_screen,
    ifNull(argMinIf(src.click_button_name, src.event_timestamp,
        src.click_button_name IS NOT NULL AND src.click_button_name != ''
        AND src.event_date < ui.idate + {M}), '')             AS first_button,
    ifNull(argMaxIf(src.click_button_name, src.event_timestamp,
        src.click_button_name IS NOT NULL AND src.click_button_name != ''
        AND src.event_date < ui.idate + {M}), '')             AS last_button,

    toUInt8(countIf(src.mapped_screen = 'MainAudioHome' AND src.event_date < ui.idate + {M}) > 0
        AND countIf(src.mapped_screen = 'AudioSearchAll' AND src.event_date < ui.idate + {M}) > 0) AS home_to_search_flag,
    toUInt8(countIf(src.mapped_screen = 'AudioSearchAll' AND src.event_date < ui.idate + {M}) > 0
        AND countIf(src.mapped_screen = 'AudioPlayerLyrics' AND src.event_date < ui.idate + {M}) > 0) AS search_to_lyrics_flag,
    toUInt8(countIf(src.mapped_screen = 'AudioSearchAll' AND src.event_date < ui.idate + {M}) > 0
        AND countIf(src.mapped_screen = 'VideoPlayer' AND src.event_date < ui.idate + {M}) > 0) AS search_to_video_flag,
    toUInt8(countIf(src.mapped_screen = 'AudioPlayerLyrics' AND src.event_date < ui.idate + {M}) > 0
        AND countIf(src.event_name = 'app_exit' AND src.event_date < ui.idate + {M}) > 0) AS lyrics_to_exit_flag,
    toUInt8(countIf(src.mapped_screen LIKE '%Permission%' AND src.event_date < ui.idate + {M}) > 0
        AND countIf(src.event_name = 'app_exit' AND src.event_date < ui.idate + {M}) > 0) AS permission_to_exit_flag,

    -- R: Funnel
    toUInt8(countIf(src.mapped_screen = 'MainAudioHome'
        AND src.event_date < ui.idate + {M}) > 0)             AS visited_home,
    toUInt8(countIf(src.mapped_screen IN ('AudioPlayerSong', 'AudioPlayerLyrics', 'VideoPlayer')
        AND src.event_date < ui.idate + {M}) > 0)             AS visited_player,
    toUInt8(countIf(src.mapped_screen = 'AudioPlayerLyrics'
        AND src.event_date < ui.idate + {M}) > 0)             AS visited_lyrics,
    toUInt8(countIf(src.mapped_screen = 'AudioSearchAll'
        AND src.event_date < ui.idate + {M}) > 0)             AS visited_search,
    toUInt8(countIf(src.mapped_screen IN ('VideoPlayer', 'MainVideoTabLocal')
        AND src.event_date < ui.idate + {M}) > 0)             AS visited_video,
    toUInt8(countIf(src.mapped_screen IN ('AudioPlaylistsDetail', 'MainAudioTabPlaylists')
        AND src.event_date < ui.idate + {M}) > 0)             AS visited_playlist,
    toUInt8(countIf(src.mapped_screen = 'ScanMusic'
        AND src.event_date < ui.idate + {M}) > 0)             AS visited_scan_music,

    toUInt8(
        toUInt8(countIf(src.mapped_screen = 'MainAudioHome'
            AND src.event_date < ui.idate + {M}) > 0) +
        toUInt8(countIf(src.mapped_screen IN ('AudioPlayerSong', 'VideoPlayer')
            AND src.event_date < ui.idate + {M}) > 0) +
        toUInt8(countIf(src.mapped_screen = 'AudioPlayerLyrics'
            AND src.event_date < ui.idate + {M}) > 0) +
        toUInt8(countIf(src.mapped_screen = 'AudioSearchAll'
            AND src.event_date < ui.idate + {M}) > 0) +
        toUInt8(countIf(src.mapped_screen IN ('AudioPlaylistsDetail', 'MainAudioTabPlaylists')
            AND src.event_date < ui.idate + {M}) > 0)
    )                                                    AS funnel_depth,

    -- T: Risk scores — mặc định -1, điền sau bằng build_risk_scores()
    toFloat32(-1)   AS country_uninstall_rate,
    toFloat32(-1)   AS campaign_uninstall_rate,
    toFloat32(-1)   AS media_source_uninstall_rate,
    toFloat32(-1)   AS app_version_uninstall_rate,

    -- Label: app_remove trong [idate + M, idate + M + 7)
    toUInt8(countIf(src.event_name = 'app_remove'
        AND src.event_date >= ui.idate + {M}
        AND src.event_date < ui.idate + {M} + {LABEL_HORIZON}) > 0) AS label_uninstall_7d,

    now()           AS created_at

FROM {source} src
INNER JOIN (
    SELECT
        user_pseudo_id,
        toDate(anyIf(install_date, isNotNull(install_date))) AS idate
    FROM {source}
    WHERE event_date >= toDate('{install_from}') - 1
      AND event_date <= toDate('{install_to}') + 1
    GROUP BY user_pseudo_id
    HAVING idate >= toDate('{install_from}')
       AND idate <= toDate('{install_to}')
) ui ON src.user_pseudo_id = ui.user_pseudo_id
WHERE src.event_date >= toDate('{install_from}') - {FEATURE_WINDOW}
  AND src.event_date <  toDate('{install_to}') + {M} + {LABEL_HORIZON}
GROUP BY src.user_pseudo_id, ui.idate
HAVING countIf(src.event_name = 'app_remove'
           AND src.event_date < ui.idate + {M}) = 0
"""


def build_milestone_snapshot(
    client,
    milestone:    int,
    install_from: str,
    install_to:   str,
    dry_run:      bool = False,
    force:        bool = False,
):
    """Build feature store cho một milestone.

    snapshot_date range: [install_from + milestone, install_to + milestone]
    """
    snap_from = (date.fromisoformat(install_from) + timedelta(days=milestone)).isoformat()
    snap_to   = (date.fromisoformat(install_to)   + timedelta(days=milestone)).isoformat()
    label     = f"D{milestone:02d} [{install_from}→{install_to}]"

    existing = client.query(
        f"SELECT count() FROM {tables.feature_store} FINAL "
        f"WHERE snapshot_date >= toDate('{snap_from}') "
        f"  AND snapshot_date <= toDate('{snap_to}')"
    ).result_rows[0][0]

    if existing > 0 and not force and not dry_run:
        logger.info(f"[{label}] Already {existing:,} rows, skip (--force to overwrite)")
        return

    if existing > 0 and not dry_run:
        client.command(
            f"ALTER TABLE {tables.feature_store} "
            f"DELETE WHERE snapshot_date >= toDate('{snap_from}') "
            f"         AND snapshot_date <= toDate('{snap_to}')",
            settings={"mutations_sync": 1},
        )
        logger.info(f"[{label}] Deleted {existing:,} old rows")

    sql = build_milestone_sql(milestone, install_from, install_to)

    if dry_run:
        print(sql[:3000])
        print("... (dry run, SQL truncated)")
        return

    logger.info(f"[{label}] Building features...")
    client.command(sql, settings={"max_memory_usage": 32_000_000_000})

    count = client.query(
        f"SELECT count() FROM {tables.feature_store} FINAL "
        f"WHERE snapshot_date >= toDate('{snap_from}') "
        f"  AND snapshot_date <= toDate('{snap_to}')"
    ).result_rows[0][0]
    label_rate = client.query(
        f"SELECT avg(label_uninstall_7d) FROM {tables.feature_store} FINAL "
        f"WHERE snapshot_date >= toDate('{snap_from}') "
        f"  AND snapshot_date <= toDate('{snap_to}')"
    ).result_rows[0][0]
    logger.info(f"[{label}] Done: {count:,} users | uninstall_rate={label_rate:.1%}")


# ─────────────────────────────────────────────────────────────────────────────
# Calendar SQL (legacy — giữ lại cho predict pipeline)
# ─────────────────────────────────────────────────────────────────────────────

def _screen_sql_cols(snap: str) -> str:
    lines = []
    for s in TOP_SCREENS:
        col = s.replace("-", "_").replace(" ", "_")
        lines.append(
            f"    countIf(mapped_screen = '{s}'"
            f" AND event_date >= toDate('{snap}') - 7"
            f" AND event_date < toDate('{snap}'))       AS screen_{col}_cnt_7d,"
        )
    return "\n".join(lines)


def _button_sql_cols(snap: str) -> str:
    lines = []
    for b in TOP_BUTTONS:
        lines.append(
            f"    countIf(click_button_name = '{b}'"
            f" AND event_date >= toDate('{snap}') - 7"
            f" AND event_date < toDate('{snap}'))          AS btn_{b}_cnt_7d,"
        )
    return "\n".join(lines)


def build_feature_sql(snap: str) -> str:
    """Calendar-based INSERT SQL (dùng cho predict pipeline).

    Feature window : [snap - 30, snap)
    Label window   : [snap, snap + 7)
    Cohort filter  : install_date ∈ [snap - 30, snap]
    """
    s            = snap
    source_table = tables.source
    screen_sql   = _screen_sql_cols(s)
    button_sql   = _button_sql_cols(s)

    return f"""
INSERT INTO {tables.feature_store}
SELECT
    toDate('{s}')          AS snapshot_date,
    src.user_pseudo_id,

    -- A: Acquisition
    ifNull(argMaxIf(up_af_media_source, event_timestamp,
        up_af_media_source != '' AND up_af_media_source IS NOT NULL
        AND event_date < toDate('{s}')), '')           AS media_source,
    ifNull(argMaxIf(up_af_campaign, event_timestamp,
        up_af_campaign != '' AND up_af_campaign IS NOT NULL
        AND event_date < toDate('{s}')), '')            AS campaign,
    toUInt8(countIf(event_name = 'af_attribution_received'
        AND event_date < toDate('{s}')) > 0)            AS has_attribution,

    -- B: Country / Language
    ifNull(argMaxIf(country, event_timestamp,
        country != '' AND country IS NOT NULL
        AND event_date < toDate('{s}')), '')             AS country,
    ifNull(argMaxIf(up_language, event_timestamp,
        up_language != '' AND up_language IS NOT NULL
        AND event_date < toDate('{s}')), '')             AS language,

    -- C: Device
    ifNull(argMaxIf(app_version, event_timestamp,
        app_version IS NOT NULL AND event_date < toDate('{s}')), '') AS app_version,
    ifNull(argMaxIf(platform, event_timestamp,
        platform IS NOT NULL AND event_date < toDate('{s}')), '')    AS platform,

    -- D: Install
    toInt32(ifNull(maxIf(src.days_since_install,
        event_date < toDate('{s}') AND src.days_since_install IS NOT NULL), 0))    AS days_since_install,
    toInt32(ifNull(maxIf(src.hours_since_install,
        event_date < toDate('{s}') AND src.hours_since_install IS NOT NULL), 0))   AS hours_since_install,
    toInt32(ifNull(maxIf(src.minutes_since_install,
        event_date < toDate('{s}') AND src.minutes_since_install IS NOT NULL), 0)) AS minutes_since_install,
    toInt32(ifNull(maxIf(src.seconds_since_install,
        event_date < toDate('{s}') AND src.seconds_since_install IS NOT NULL), 0)) AS seconds_since_install,
    toUInt8(ifNull(maxIf(src.days_since_install,
        event_date < toDate('{s}') AND src.days_since_install IS NOT NULL), 0) = 0)  AS is_day0_user,
    toUInt8(ifNull(maxIf(src.days_since_install,
        event_date < toDate('{s}') AND src.days_since_install IS NOT NULL), 0) = 1)  AS is_day1_user,
    toUInt8(ifNull(maxIf(src.days_since_install,
        event_date < toDate('{s}') AND src.days_since_install IS NOT NULL), 0) <= 7) AS is_week1_user,

    -- E: Session
    toUInt32(countDistinctIf(unique_session_id,
        event_name = 'session_start'
        AND event_date = toDate('{s}') - 1))             AS session_cnt_1d,
    toUInt32(countDistinctIf(unique_session_id,
        event_name = 'session_start'
        AND event_date >= toDate('{s}') - 3
        AND event_date < toDate('{s}')))                 AS session_cnt_3d,
    toUInt32(countDistinctIf(unique_session_id,
        event_name = 'session_start'
        AND event_date >= toDate('{s}') - 7
        AND event_date < toDate('{s}')))                 AS session_cnt_7d,
    toUInt32(countDistinctIf(unique_session_id,
        event_name = 'session_start'
        AND event_date >= toDate('{s}') - 14
        AND event_date < toDate('{s}')))                 AS session_cnt_14d,
    toUInt32(countDistinctIf(unique_session_id,
        event_name = 'session_start'
        AND event_date >= toDate('{s}') - 30
        AND event_date < toDate('{s}')))                 AS session_cnt_30d,

    toUInt32(countDistinctIf(event_date,
        event_date >= toDate('{s}') - 7
        AND event_date < toDate('{s}')))                 AS active_days_7d,
    toUInt32(countDistinctIf(event_date,
        event_date >= toDate('{s}') - 30
        AND event_date < toDate('{s}')))                 AS active_days_30d,

    if(countDistinctIf(event_date,
            event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0,
       countDistinctIf(unique_session_id,
            event_name = 'session_start'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) /
       countDistinctIf(event_date,
            event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')),
       0.0)                                              AS avg_sessions_per_day_7d,

    if(countDistinctIf(unique_session_id,
            event_name = 'session_start'
            AND event_date >= toDate('{s}') - 14 AND event_date < toDate('{s}') - 7) > 0,
       toFloat32(countDistinctIf(unique_session_id,
            event_name = 'session_start'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))) /
       toFloat32(countDistinctIf(unique_session_id,
            event_name = 'session_start'
            AND event_date >= toDate('{s}') - 14 AND event_date < toDate('{s}') - 7)),
       if(countDistinctIf(unique_session_id,
            event_name = 'session_start'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0,
          2.0, 1.0))                                     AS session_trend_7d,

    -- F: Engagement
    toInt64(sumIf(ifNull(engagement_time, 0),
        event_date = toDate('{s}') - 1))                 AS engagement_time_ms_1d,
    toInt64(sumIf(ifNull(engagement_time, 0),
        event_date >= toDate('{s}') - 3 AND event_date < toDate('{s}')))  AS engagement_time_ms_3d,
    toInt64(sumIf(ifNull(engagement_time, 0),
        event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS engagement_time_ms_7d,
    toInt64(sumIf(ifNull(engagement_time, 0),
        event_date >= toDate('{s}') - 30 AND event_date < toDate('{s}'))) AS engagement_time_ms_30d,

    if(countDistinctIf(unique_session_id,
            event_name = 'session_start'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0,
       toFloat32(sumIf(ifNull(engagement_time, 0),
            event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))) /
       toFloat32(countDistinctIf(unique_session_id,
            event_name = 'session_start'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))),
       0.0)                                              AS avg_engagement_per_session_7d,

    if(sumIf(ifNull(engagement_time, 0),
            event_date >= toDate('{s}') - 14 AND event_date < toDate('{s}') - 7) > 0,
       toFloat32(sumIf(ifNull(engagement_time, 0),
            event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))) /
       toFloat32(sumIf(ifNull(engagement_time, 0),
            event_date >= toDate('{s}') - 14 AND event_date < toDate('{s}') - 7)),
       if(sumIf(ifNull(engagement_time, 0),
            event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0,
          2.0, 1.0))                                     AS engagement_trend_7d,

    -- G: Recency
    toUInt32(if(max(if(event_date < toDate('{s}'), event_date, toDate('1970-01-01'))) > toDate('1970-01-01'),
        dateDiff('day',
            max(if(event_date < toDate('{s}'), event_date, toDate('1970-01-01'))),
            toDate('{s}')) * 24,
        9999))                                           AS hours_since_last_session,

    toUInt32(if(maxIf(event_date, event_name IN ('screen_view', 'screen_view_ev')
            AND event_date < toDate('{s}')) > toDate('1970-01-01'),
        dateDiff('day',
            maxIf(event_date, event_name IN ('screen_view', 'screen_view_ev')
                AND event_date < toDate('{s}')),
            toDate('{s}')) * 24,
        9999))                                           AS hours_since_last_screen,

    toUInt32(if(maxIf(event_date, event_name = 'click_btn_ev'
            AND event_date < toDate('{s}')) > toDate('1970-01-01'),
        dateDiff('day',
            maxIf(event_date, event_name = 'click_btn_ev'
                AND event_date < toDate('{s}')),
            toDate('{s}')) * 24,
        9999))                                           AS hours_since_last_click,

    toUInt32(if(maxIf(event_date, event_name IN ('show_ad_ev', 'load_ad_ev', 'paid_ad_impression')
            AND event_date < toDate('{s}')) > toDate('1970-01-01'),
        dateDiff('day',
            maxIf(event_date, event_name IN ('show_ad_ev', 'load_ad_ev', 'paid_ad_impression')
                AND event_date < toDate('{s}')),
            toDate('{s}')) * 24,
        9999))                                           AS hours_since_last_ad,

    toUInt32(if(maxIf(event_date, click_button_name IN ('Search', 'QuickSearchClicked')
            AND event_date < toDate('{s}')) > toDate('1970-01-01'),
        dateDiff('day',
            maxIf(event_date, click_button_name IN ('Search', 'QuickSearchClicked')
                AND event_date < toDate('{s}')),
            toDate('{s}')) * 24,
        9999))                                           AS hours_since_last_search,

    toUInt32(if(maxIf(event_date, event_name = 'user_engagement'
            AND event_date < toDate('{s}')) > toDate('1970-01-01'),
        dateDiff('day',
            maxIf(event_date, event_name = 'user_engagement'
                AND event_date < toDate('{s}')),
            toDate('{s}')) * 24,
        9999))                                           AS hours_since_last_engagement,

    -- H: Screens (7d)
{screen_sql}
    toUInt32(countDistinctIf(mapped_screen,
        event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')
        AND mapped_screen IS NOT NULL AND mapped_screen != ''))  AS unique_screen_cnt_7d,

    if(countIf(mapped_screen IS NOT NULL AND mapped_screen != ''
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0,
       toFloat32(countIf(mapped_screen = 'MainAudioHome'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))) /
       toFloat32(countIf(mapped_screen IS NOT NULL AND mapped_screen != ''
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))),
       0.0)                                              AS home_ratio_7d,

    if(countIf(mapped_screen IS NOT NULL AND mapped_screen != ''
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0,
       toFloat32(countIf(mapped_screen IN (
            'VideoPlayer', 'MainVideoTabLocal', 'FloatingVideo', 'VideoSelection')
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))) /
       toFloat32(countIf(mapped_screen IS NOT NULL AND mapped_screen != ''
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))),
       0.0)                                              AS video_ratio_7d,

    if(countIf(mapped_screen IS NOT NULL AND mapped_screen != ''
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0,
       toFloat32(countIf(mapped_screen = 'AudioPlayerLyrics'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))) /
       toFloat32(countIf(mapped_screen IS NOT NULL AND mapped_screen != ''
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))),
       0.0)                                              AS lyrics_ratio_7d,

    if(countIf(mapped_screen IS NOT NULL AND mapped_screen != ''
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0,
       toFloat32(countIf(mapped_screen LIKE '%Permission%'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))) /
       toFloat32(countIf(mapped_screen IS NOT NULL AND mapped_screen != ''
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))),
       0.0)                                              AS permission_screen_ratio_7d,

    -- I: Buttons (7d)
{button_sql}
    toUInt32(countDistinctIf(click_button_name,
        event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')
        AND click_button_name IS NOT NULL AND click_button_name != ''))  AS unique_button_cnt_7d,

    -- J: Search
    toUInt32(countIf(click_button_name = 'Search'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS search_online_cnt_7d,
    toUInt32(countIf(click_button_name = 'QuickSearchClicked'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS search_quick_cnt_7d,
    toUInt32(countIf(mapped_screen = 'AudioSearchAll'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS search_screen_cnt_7d,
    toUInt8(countIf(click_button_name IN ('Search', 'QuickSearchClicked')
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0) AS used_search_7d,
    toUInt32(countDistinctIf(event_date,
        click_button_name IN ('Search', 'QuickSearchClicked')
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS search_days_7d,

    -- K: Audio
    toUInt32(countIf(mapped_screen = 'AudioPlayerLyrics'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS lyrics_screen_cnt_7d,
    toUInt32(countIf(mapped_screen = 'AudioPlayerSong'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS audio_player_cnt_7d,
    toUInt32(countIf(mapped_screen IN ('AudioPlaylistsDetail', 'MainAudioTabPlaylists')
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS playlist_cnt_7d,
    toUInt32(countIf(mapped_screen = 'AudioPlayerQueue'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS queue_cnt_7d,
    if(countIf(event_name IN ('screen_view', 'screen_view_ev')
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0,
       toFloat32(countIf(mapped_screen IN ('AudioPlayerSong', 'AudioPlayerLyrics', 'AudioPlayerQueue')
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))) /
       toFloat32(countIf(event_name IN ('screen_view', 'screen_view_ev')
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))),
       0.0)                                              AS audio_screen_ratio_7d,

    -- L: Video
    toUInt32(countIf(mapped_screen = 'VideoPlayer'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS video_player_cnt_7d,
    toUInt32(countIf(mapped_screen = 'MainVideoTabLocal'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS video_tab_cnt_7d,
    toUInt32(countIf(mapped_screen = 'FloatingVideo'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS floating_video_cnt_7d,

    -- M: Permission
    toUInt8(countIf(mapped_screen = 'MainAudio_RequestNotificationPermission') > 0) AS seen_notification_permission,
    toUInt8(countIf(mapped_screen LIKE '%Permission%') > 0)  AS seen_any_permission,
    toUInt32(countIf(mapped_screen LIKE '%Permission%'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS permission_screen_cnt_7d,
    ifNull(argMaxIf(up_allow_notification, event_timestamp,
        event_date < toDate('{s}')), '')                 AS notif_permission_status,

    -- N: Ads
    toUInt32(countIf(event_name = 'load_ad_ev'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS load_ad_cnt_7d,
    toUInt32(countIf(event_name = 'show_ad_ev'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS show_ad_cnt_7d,
    toUInt32(countIf(event_name = 'paid_ad_impression'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS paid_ad_impression_cnt_7d,
    if(countDistinctIf(unique_session_id,
            event_name = 'session_start'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')) > 0,
       toFloat32(countIf(event_name = 'show_ad_ev'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))) /
       toFloat32(countDistinctIf(unique_session_id,
            event_name = 'session_start'
            AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}'))),
       0.0)                                              AS ads_per_session_7d,
    toFloat32(sumIf(ifNull(ep_revenue, 0),
        event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))      AS ad_revenue_7d,

    -- O: IAP / Subscription
    toUInt32(countIf(event_name = 'iap_ev'
        AND event_date >= toDate('{s}') - 30 AND event_date < toDate('{s}'))) AS iap_cnt_30d,
    toUInt8(countIf(event_name = 'iap_ev'
        AND event_date < toDate('{s}')) > 0)             AS payer_flag,

    -- P: Quality
    toUInt32(countIf(event_name = 'app_exception'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS app_exception_cnt_7d,
    toUInt32(countIf(event_name = 'app_clear_data'
        AND event_date >= toDate('{s}') - 30 AND event_date < toDate('{s}'))) AS app_clear_data_cnt_30d,
    toUInt32(countIf(event_name = 'app_update'
        AND event_date >= toDate('{s}') - 30 AND event_date < toDate('{s}'))) AS app_update_cnt_30d,
    toUInt32(countIf(event_name = 'app_exit'
        AND event_date >= toDate('{s}') - 7 AND event_date < toDate('{s}')))  AS app_exit_cnt_7d,

    -- Q: Journey
    ifNull(argMinIf(mapped_screen, event_timestamp,
        mapped_screen IS NOT NULL AND mapped_screen != ''
        AND event_date < toDate('{s}')), '')             AS first_screen,
    ifNull(argMaxIf(mapped_screen, event_timestamp,
        mapped_screen IS NOT NULL AND mapped_screen != ''
        AND event_date < toDate('{s}')), '')             AS last_screen,
    ifNull(argMinIf(click_button_name, event_timestamp,
        click_button_name IS NOT NULL AND click_button_name != ''
        AND event_date < toDate('{s}')), '')             AS first_button,
    ifNull(argMaxIf(click_button_name, event_timestamp,
        click_button_name IS NOT NULL AND click_button_name != ''
        AND event_date < toDate('{s}')), '')             AS last_button,

    toUInt8(countIf(mapped_screen = 'MainAudioHome' AND event_date < toDate('{s}')) > 0
        AND countIf(mapped_screen = 'AudioSearchAll' AND event_date < toDate('{s}')) > 0) AS home_to_search_flag,
    toUInt8(countIf(mapped_screen = 'AudioSearchAll' AND event_date < toDate('{s}')) > 0
        AND countIf(mapped_screen = 'AudioPlayerLyrics' AND event_date < toDate('{s}')) > 0) AS search_to_lyrics_flag,
    toUInt8(countIf(mapped_screen = 'AudioSearchAll' AND event_date < toDate('{s}')) > 0
        AND countIf(mapped_screen = 'VideoPlayer' AND event_date < toDate('{s}')) > 0) AS search_to_video_flag,
    toUInt8(countIf(mapped_screen = 'AudioPlayerLyrics' AND event_date < toDate('{s}')) > 0
        AND countIf(event_name = 'app_exit' AND event_date < toDate('{s}')) > 0) AS lyrics_to_exit_flag,
    toUInt8(countIf(mapped_screen LIKE '%Permission%' AND event_date < toDate('{s}')) > 0
        AND countIf(event_name = 'app_exit' AND event_date < toDate('{s}')) > 0) AS permission_to_exit_flag,

    -- R: Funnel
    toUInt8(countIf(mapped_screen = 'MainAudioHome' AND event_date < toDate('{s}')) > 0)   AS visited_home,
    toUInt8(countIf(mapped_screen IN ('AudioPlayerSong', 'AudioPlayerLyrics', 'VideoPlayer')
        AND event_date < toDate('{s}')) > 0)             AS visited_player,
    toUInt8(countIf(mapped_screen = 'AudioPlayerLyrics' AND event_date < toDate('{s}')) > 0) AS visited_lyrics,
    toUInt8(countIf(mapped_screen = 'AudioSearchAll' AND event_date < toDate('{s}')) > 0)  AS visited_search,
    toUInt8(countIf(mapped_screen IN ('VideoPlayer', 'MainVideoTabLocal')
        AND event_date < toDate('{s}')) > 0)             AS visited_video,
    toUInt8(countIf(mapped_screen IN ('AudioPlaylistsDetail', 'MainAudioTabPlaylists')
        AND event_date < toDate('{s}')) > 0)             AS visited_playlist,
    toUInt8(countIf(mapped_screen = 'ScanMusic' AND event_date < toDate('{s}')) > 0)       AS visited_scan_music,

    toUInt8(
        toUInt8(countIf(mapped_screen = 'MainAudioHome' AND event_date < toDate('{s}')) > 0) +
        toUInt8(countIf(mapped_screen IN ('AudioPlayerSong', 'VideoPlayer')
            AND event_date < toDate('{s}')) > 0) +
        toUInt8(countIf(mapped_screen = 'AudioPlayerLyrics' AND event_date < toDate('{s}')) > 0) +
        toUInt8(countIf(mapped_screen = 'AudioSearchAll' AND event_date < toDate('{s}')) > 0) +
        toUInt8(countIf(mapped_screen IN ('AudioPlaylistsDetail', 'MainAudioTabPlaylists')
            AND event_date < toDate('{s}')) > 0)
    )                                                    AS funnel_depth,

    toFloat32(-1)   AS country_uninstall_rate,
    toFloat32(-1)   AS campaign_uninstall_rate,
    toFloat32(-1)   AS media_source_uninstall_rate,
    toFloat32(-1)   AS app_version_uninstall_rate,

    toUInt8(countIf(event_name = 'app_remove'
        AND event_date >= toDate('{s}')
        AND event_date < toDate('{s}') + {LABEL_HORIZON}) > 0) AS label_uninstall_7d,

    now()           AS created_at

FROM {source_table} src
WHERE src.event_date >= toDate('{s}') - {FEATURE_WINDOW}
  AND src.event_date < toDate('{s}') + {LABEL_HORIZON}
GROUP BY src.user_pseudo_id
HAVING toDate(anyIf(install_date, isNotNull(install_date))) >= toDate('{s}') - {MAX_INSTALL_AGE_DAYS}
   AND toDate(anyIf(install_date, isNotNull(install_date))) <= toDate('{s}')
"""


def build_snapshot(client, snap: str, dry_run: bool = False, force: bool = False):
    """Calendar-based snapshot (dùng cho predict pipeline)."""
    existing = client.query(
        f"SELECT count() FROM {tables.feature_store} FINAL "
        f"WHERE snapshot_date = toDate('{snap}')"
    ).result_rows[0][0]
    if existing > 0 and not force and not dry_run:
        logger.info(f"[{snap}] Đã có {existing:,} rows, skip (dùng --force để ghi đè)")
        return

    if existing > 0 and not dry_run:
        client.command(
            f"ALTER TABLE {tables.feature_store} "
            f"DELETE WHERE snapshot_date = toDate('{snap}')",
            settings={"mutations_sync": 1},
        )
        logger.info(f"[{snap}] Deleted {existing:,} old rows")

    sql = build_feature_sql(snap)

    if dry_run:
        print(sql[:3000])
        print("... (dry run, SQL truncated)")
        return

    logger.info(f"[{snap}] Building features...")
    client.command(sql, settings={"max_memory_usage": 32_000_000_000})

    count      = client.query(
        f"SELECT count() FROM {tables.feature_store} FINAL "
        f"WHERE snapshot_date = toDate('{snap}')"
    ).result_rows[0][0]
    label_rate = client.query(
        f"SELECT avg(label_uninstall_7d) FROM {tables.feature_store} FINAL "
        f"WHERE snapshot_date = toDate('{snap}')"
    ).result_rows[0][0]
    logger.info(f"[{snap}] Done: {count:,} users | uninstall_rate={label_rate:.1%}")


# ─────────────────────────────────────────────────────────────────────────────
# Target Encoding (Section T)
# ─────────────────────────────────────────────────────────────────────────────

_RISK_BASELINE_DDL = """
CREATE TABLE IF NOT EXISTS {risk_table}
(
    dimension      String,
    value          String,
    uninstall_rate Float32,
    sample_size    UInt32,
    updated_at     DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (dimension, value);
"""

_RISK_INSERT_SQL = """
INSERT INTO {risk_table} (dimension, value, uninstall_rate, sample_size)
SELECT
    '{dim}'      AS dimension,
    {col}        AS value,
    round(avg(label_uninstall_7d), 4) AS uninstall_rate,
    count()      AS sample_size
FROM {feature_table} FINAL
WHERE snapshot_date < toDate('{cutoff}')
  AND {col} != '' AND {col} IS NOT NULL
GROUP BY {col}
HAVING sample_size >= 100
"""


def build_risk_scores(client, cutoff: str, update_from: str):
    client.command(_RISK_BASELINE_DDL.format(risk_table=tables.risk_baseline))

    for dim, col in [
        ("country",      "country"),
        ("campaign",     "campaign"),
        ("media_source", "media_source"),
        ("app_version",  "app_version"),
    ]:
        client.command(_RISK_INSERT_SQL.format(
            risk_table=tables.risk_baseline,
            feature_table=tables.feature_store,
            dim=dim, col=col, cutoff=cutoff,
        ))
        logger.info(f"[risk] Built baseline for {dim}")

    rates = client.query(
        f"SELECT dimension, value, uninstall_rate FROM {tables.risk_baseline} FINAL"
    ).result_rows

    for col in ["country", "campaign", "media_source", "app_version"]:
        col_rates = {row[1]: row[2] for row in rates if row[0] == col}
        if not col_rates:
            logger.warning(f"[risk] Không có rates cho {col}, bỏ qua")
            continue
        cases = " ".join(
            f"WHEN {col} = '{v.replace(chr(39), chr(39)*2)}' THEN toFloat32({r})"
            for v, r in col_rates.items()
        )
        client.command(
            f"ALTER TABLE {tables.feature_store} "
            f"UPDATE {col}_uninstall_rate = CASE {cases} ELSE toFloat32(-1) END "
            f"WHERE snapshot_date >= toDate('{update_from}')",
            settings={"mutations_sync": 1},
        )
        logger.info(f"[risk] Updated {col}_uninstall_rate ({len(col_rates)} values)")


# ─────────────────────────────────────────────────────────────────────────────
# Legacy helper (calendar range mode)
# ─────────────────────────────────────────────────────────────────────────────

def _snapshot_dates(date_from: str, date_to: str, step: int) -> List[str]:
    d   = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    dates = []
    while d <= end:
        dates.append(d.isoformat())
        d += timedelta(days=step)
    return dates


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Build Android Music v2 Feature Store")

    # Milestone mode (training)
    parser.add_argument("--install_from",   type=str, default=None,
                        help="Install cohort start date (milestone mode)")
    parser.add_argument("--install_to",     type=str, default=None,
                        help="Install cohort end date (milestone mode)")
    parser.add_argument("--milestone_days", type=str, default=None,
                        help="Comma-separated milestone days, default '1,7,14,21,28'")

    # Calendar mode (predict / legacy)
    parser.add_argument("--snapshot_date", type=str, default=None)
    parser.add_argument("--date_from",     type=str, default=None)
    parser.add_argument("--date_to",       type=str, default=None)
    parser.add_argument("--step",          type=int, default=7)

    parser.add_argument("--init_tables",   action="store_true")
    parser.add_argument("--build_risk",    action="store_true")
    parser.add_argument("--risk_cutoff",   type=str, default=None)
    parser.add_argument("--force",         action="store_true")
    parser.add_argument("--dry_run",       action="store_true")
    args = parser.parse_args()

    client = get_client()

    if args.init_tables:
        create_tables(client)
        logger.info("Tables created.")
        if not (args.install_from or args.snapshot_date or args.date_from):
            return

    if args.install_from and args.install_to:
        milestones = [int(x) for x in (args.milestone_days or "1,7,14,21,28").split(",")]
        logger.info(
            f"Milestone mode: {args.install_from} → {args.install_to}, "
            f"milestones={milestones}"
        )
        for m in milestones:
            try:
                build_milestone_snapshot(
                    client, m, args.install_from, args.install_to,
                    dry_run=args.dry_run, force=args.force,
                )
            except Exception as e:
                logger.error(f"[D{m}] FAILED: {e}")

    elif args.snapshot_date:
        build_snapshot(client, args.snapshot_date, dry_run=args.dry_run, force=args.force)

    elif args.date_from and args.date_to:
        snaps = _snapshot_dates(args.date_from, args.date_to, args.step)
        logger.info(f"Calendar mode (legacy): {len(snaps)} snapshots")
        for snap in snaps:
            try:
                build_snapshot(client, snap, dry_run=args.dry_run, force=args.force)
            except Exception as e:
                logger.error(f"[{snap}] FAILED: {e}")

    else:
        yesterday  = (date.today() - timedelta(days=1)).isoformat()
        milestones = MILESTONES
        logger.info(f"Default: milestone mode for install_date={yesterday}")
        for m in milestones:
            build_milestone_snapshot(
                client, m, yesterday, yesterday,
                dry_run=args.dry_run, force=args.force,
            )

    if args.build_risk:
        cutoff      = args.risk_cutoff or args.install_from or args.snapshot_date
        update_from = args.install_from or args.snapshot_date or cutoff
        build_risk_scores(client, cutoff=cutoff, update_from=update_from)


if __name__ == "__main__":
    main()
