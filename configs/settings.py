"""
Cấu hình dự án Android Music v2 — Uninstall Prediction.
File này tự đủ, không phụ thuộc vào project nw3-churn.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# ─────────────────────────────────────────────────────────────────────────────
# ClickHouse
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ClickHouseConfig:
    host:                 str = field(default_factory=lambda: os.getenv("CLICKHOUSE_HOST", "192.168.1.11"))
    port:                 int = field(default_factory=lambda: int(os.getenv("CLICKHOUSE_PORT", "8123")))
    username:             str = field(default_factory=lambda: os.getenv("CLICKHOUSE_USER", "default"))
    password:             str = field(default_factory=lambda: os.getenv("CLICKHOUSE_PASSWORD", "TohGroupData@135"))
    database:             str = field(default_factory=lambda: os.getenv("CLICKHOUSE_DATABASE", "android_music_v2"))
    send_receive_timeout: int = 3600
    connect_timeout:      int = 30

ch = ClickHouseConfig()

# ─────────────────────────────────────────────────────────────────────────────
# Tables
# ─────────────────────────────────────────────────────────────────────────────

DATABASE   = "android_music_v2"
FLAT_TABLE = "android_music_v2.android_music_v2_ga4_staging_flat"

@dataclass
class TableConfig:
    source:        str = FLAT_TABLE
    feature_store: str = "android_music_v2.feature_store_uninstall"
    training:      str = "android_music_v2.training_uninstall"
    validation:    str = "android_music_v2.validation_uninstall"
    risk_baseline: str = "android_music_v2.risk_baseline"
    predictions:   str = "android_music_v2.music_uninstall_predictions"

tables = TableConfig()

# ─────────────────────────────────────────────────────────────────────────────
# Model & Pipeline
# ─────────────────────────────────────────────────────────────────────────────

LABEL_HORIZON       = 7    # ngày dự báo uninstall
FEATURE_WINDOW      = 30   # ngày lịch sử để tính feature
MAX_INSTALL_AGE_DAYS = 30  # chỉ dự đoán user cài trong 30 ngày gần nhất (D0-D30 early-churn)

MODEL_DIR = Path(os.getenv("MODEL_DIR", "models"))

MLFLOW_URI        = os.getenv("MLFLOW_TRACKING_URI", "http://192.168.1.11:5000")
MLFLOW_EXPERIMENT = "android_music_v2_uninstall"

# ─────────────────────────────────────────────────────────────────────────────
# Top screens từ dữ liệu thực tế (loại unknown screen)
# ─────────────────────────────────────────────────────────────────────────────

TOP_SCREENS: List[str] = [
    "VideoPlayer", "AudioPlayerSong", "AudioPlayerLyrics",
    "MainAudioSongs", "AudioPlayerQueue", "PhotoDetail",
    "AudioSelection", "FloatingPlayer", "MainVideoTabLocal",
    "MainAudioHome", "Equalizer", "AudioSearchAll",
    "AudioPlaylistsDetail", "LockScreen", "VideoSelection",
    "FloatingVideo", "MainMore", "ScanMusic",
    "MainAudioTabPlaylists", "MainAudioFolder",
    "MainAudio_RequestNotificationPermission", "ConfigTheme",
    "AudioFolderDetail", "VideoFolderDetail",
    "MainAudioAlbum", "AudioEditTag",
]

# ─────────────────────────────────────────────────────────────────────────────
# Top buttons từ dữ liệu thực tế
# ─────────────────────────────────────────────────────────────────────────────

TOP_BUTTONS: List[str] = [
    "Play", "Pause", "Next", "Previous", "Seek",
    "Forward10s", "Backward10s", "Back", "Close",
    "Search", "QuickSearchClicked", "Favourite",
    "Delete", "Ok", "Cancel", "Confirm",
    "TabVideo", "TabSong", "TabLyric", "TabAudio", "TabPhoto",
    "Playlist", "Save", "Home", "MainMore",
    "PlayAsAudio", "Rotate", "ItemMore", "More",
    "RepeatOne", "RepeatAll", "RepeatOff",
]

# ─────────────────────────────────────────────────────────────────────────────
# Feature columns
# ─────────────────────────────────────────────────────────────────────────────

CATEGORICAL_FEATURES: List[str] = [
    "media_source", "campaign", "country", "language",
    "app_version", "first_screen", "last_screen",
    "first_button", "last_button", "notif_permission_status",
]

NUMERICAL_FEATURES: List[str] = [
    # D: Install
    "days_since_install", "hours_since_install",
    "is_day0_user", "is_day1_user", "is_week1_user",
    # E: Session
    "session_cnt_1d", "session_cnt_3d", "session_cnt_7d",
    "session_cnt_14d", "session_cnt_30d",
    "active_days_7d", "active_days_30d",
    "avg_sessions_per_day_7d", "session_trend_7d",
    # F: Engagement
    "engagement_time_ms_1d", "engagement_time_ms_3d",
    "engagement_time_ms_7d", "engagement_time_ms_30d",
    "avg_engagement_per_session_7d", "engagement_trend_7d",
    # G: Recency
    "hours_since_last_session", "hours_since_last_screen",
    "hours_since_last_click", "hours_since_last_ad",
    "hours_since_last_search", "hours_since_last_engagement",
    # H: Screens (7d) — tự động từ TOP_SCREENS
    *[f"screen_{s.replace('-', '_')}_cnt_7d" for s in TOP_SCREENS],
    "unique_screen_cnt_7d", "home_ratio_7d",
    "video_ratio_7d", "lyrics_ratio_7d", "permission_screen_ratio_7d",
    # I: Buttons (7d) — tự động từ TOP_BUTTONS
    *[f"btn_{b}_cnt_7d" for b in TOP_BUTTONS],
    "unique_button_cnt_7d",
    # J: Search
    "search_online_cnt_7d", "search_quick_cnt_7d",
    "search_screen_cnt_7d", "used_search_7d", "search_days_7d",
    # K: Audio
    "lyrics_screen_cnt_7d", "audio_player_cnt_7d",
    "playlist_cnt_7d", "queue_cnt_7d", "audio_screen_ratio_7d",
    # L: Video
    "video_player_cnt_7d", "video_tab_cnt_7d", "floating_video_cnt_7d",
    # M: Permission
    "seen_notification_permission", "seen_any_permission",
    "permission_screen_cnt_7d",
    # N: Ads
    "load_ad_cnt_7d", "show_ad_cnt_7d",
    "paid_ad_impression_cnt_7d", "ads_per_session_7d", "ad_revenue_7d",
    # O: IAP
    "iap_cnt_30d", "payer_flag",
    # P: Quality
    "app_exception_cnt_7d", "app_clear_data_cnt_30d",
    "app_update_cnt_30d", "app_exit_cnt_7d",
    # Q: Journey flags
    "home_to_search_flag", "search_to_lyrics_flag",
    "search_to_video_flag", "lyrics_to_exit_flag",
    "permission_to_exit_flag",
    # R: Funnel
    "visited_home", "visited_player", "visited_lyrics",
    "visited_search", "visited_video", "visited_playlist",
    "visited_scan_music", "funnel_depth",
    # T: Risk scores (target encoding)
    "country_uninstall_rate", "campaign_uninstall_rate",
    "media_source_uninstall_rate", "app_version_uninstall_rate",
]

ALL_FEATURES = NUMERICAL_FEATURES + CATEGORICAL_FEATURES
LABEL_COL    = "label_uninstall_7d"

# Metric dùng để chọn model tối ưu sau training
# auc_pr tốt hơn auc_roc khi label rate thấp (~25.8%)
MODEL_SELECTION_METRIC: str = "auc_pr"
