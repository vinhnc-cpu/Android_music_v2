# Android Music v2 — Feature Catalog (Uninstall Prediction)

**Label**: `label_uninstall_7d` = 1 nếu user có `app_remove` trong 7 ngày sau snapshot  
**Label rate**: ~25.8% (373,057 / 1,450,000 users)  
**Feature window**: 30 ngày trước snapshot (`event_date < snapshot_date`)  
**Leakage rule**: tất cả feature dùng `event_date < snapshot_date`, label dùng `event_date ∈ [snapshot, snapshot+7)`

---

## Section A — Acquisition (3 features)

| Feature | Type | Mô tả |
|---|---|---|
| `media_source` | Cat | Kênh cài đặt (googleadwords_int, NA, NULL) |
| `campaign` | Cat | Campaign Google Ads |
| `has_attribution` | Binary | Có sự kiện `af_attribution_received` |

**Ghi chú**: Attribution data rất thưa (~94% NULL/NA). Nên dùng target encoding thay vì one-hot.

---

## Section B — Country / Language (2 features)

| Feature | Type | Mô tả |
|---|---|---|
| `country` | Cat | Quốc gia (top: MX, CU, NG, AO, SD) |
| `language` | Cat | Ngôn ngữ thiết bị |

---

## Section C — Device (2 features)

| Feature | Type | Mô tả |
|---|---|---|
| `app_version` | Cat | Phiên bản app (target encode: tỷ lệ uninstall theo version) |
| `platform` | Cat | Luôn ANDROID trong dataset này |

**Ghi chú**: `mobile_brand_name` và `operating_system` KHÔNG có trong flat table.

---

## Section D — Install (5 features)

| Feature | Type | Mô tả |
|---|---|---|
| `days_since_install` | Int | Ngày từ install_date đến snapshot |
| `hours_since_install` | Int | Giờ từ install đến snapshot |
| `is_day0_user` | Binary | install = snapshot - 1 (ngày đầu tiên) |
| `is_day1_user` | Binary | days_since_install = 1 |
| `is_week1_user` | Binary | days_since_install ≤ 7 |

---

## Section E — Session Behavior (9 features)

| Feature | Type | Mô tả |
|---|---|---|
| `session_cnt_1d` | Int | Số session ngày hôm qua |
| `session_cnt_3d` | Int | Số session 3 ngày qua |
| `session_cnt_7d` | Int | Số session 7 ngày qua |
| `session_cnt_14d` | Int | Số session 14 ngày qua |
| `session_cnt_30d` | Int | Số session 30 ngày qua |
| `active_days_7d` | Int | Số ngày có session trong 7d |
| `active_days_30d` | Int | Số ngày có session trong 30d |
| `avg_sessions_per_day_7d` | Float | session_cnt_7d / active_days_7d |
| `session_trend_7d` | Float | cnt_last7 / cnt_prev7 — **giảm → sắp uninstall** |

---

## Section F — Engagement Time (6 features)

| Feature | Type | Mô tả |
|---|---|---|
| `engagement_time_ms_1d` | Int64 | Tổng engagement_time (ms) 1d |
| `engagement_time_ms_3d` | Int64 | Tổng engagement_time (ms) 3d |
| `engagement_time_ms_7d` | Int64 | Tổng engagement_time (ms) 7d |
| `engagement_time_ms_30d` | Int64 | Tổng engagement_time (ms) 30d |
| `avg_engagement_per_session_7d` | Float | ms/session trong 7d |
| `engagement_trend_7d` | Float | last7d / prev7d engagement — **giảm → risk** |

---

## Section G — Recency (6 features)

| Feature | Type | Mô tả | Default |
|---|---|---|---|
| `hours_since_last_session` | Int | Giờ kể từ ngày cuối cùng có event | 9999 |
| `hours_since_last_screen` | Int | Giờ kể từ screen_view cuối | 9999 |
| `hours_since_last_click` | Int | Giờ kể từ click_btn_ev cuối | 9999 |
| `hours_since_last_ad` | Int | Giờ kể từ ad event cuối | 9999 |
| `hours_since_last_search` | Int | Giờ kể từ search cuối | 9999 |
| `hours_since_last_engagement` | Int | Giờ kể từ user_engagement cuối | 9999 |

---

## Section H — Screen Views (31 features)

### Per-screen counts (7d), 26 screens:

| Feature | Screen |
|---|---|
| `screen_VideoPlayer_cnt_7d` | VideoPlayer |
| `screen_AudioPlayerSong_cnt_7d` | AudioPlayerSong |
| `screen_AudioPlayerLyrics_cnt_7d` | AudioPlayerLyrics |
| `screen_MainAudioSongs_cnt_7d` | MainAudioSongs |
| `screen_AudioPlayerQueue_cnt_7d` | AudioPlayerQueue |
| `screen_PhotoDetail_cnt_7d` | PhotoDetail |
| `screen_AudioSelection_cnt_7d` | AudioSelection |
| `screen_FloatingPlayer_cnt_7d` | FloatingPlayer |
| `screen_MainVideoTabLocal_cnt_7d` | MainVideoTabLocal |
| `screen_MainAudioHome_cnt_7d` | MainAudioHome |
| `screen_Equalizer_cnt_7d` | Equalizer |
| `screen_AudioSearchAll_cnt_7d` | AudioSearchAll |
| `screen_AudioPlaylistsDetail_cnt_7d` | AudioPlaylistsDetail |
| `screen_LockScreen_cnt_7d` | LockScreen |
| `screen_VideoSelection_cnt_7d` | VideoSelection |
| `screen_FloatingVideo_cnt_7d` | FloatingVideo |
| `screen_MainMore_cnt_7d` | MainMore |
| `screen_ScanMusic_cnt_7d` | ScanMusic |
| `screen_MainAudioTabPlaylists_cnt_7d` | MainAudioTabPlaylists |
| `screen_MainAudioFolder_cnt_7d` | MainAudioFolder |
| `screen_PermissionNotif_cnt_7d` | MainAudio_RequestNotificationPermission |
| `screen_ConfigTheme_cnt_7d` | ConfigTheme |
| `screen_AudioFolderDetail_cnt_7d` | AudioFolderDetail |
| `screen_VideoFolderDetail_cnt_7d` | VideoFolderDetail |
| `screen_MainAudioAlbum_cnt_7d` | MainAudioAlbum |
| `screen_AudioEditTag_cnt_7d` | AudioEditTag |

### Aggregate screen features (5):

| Feature | Mô tả |
|---|---|
| `unique_screen_cnt_7d` | Số screen khác nhau (đa dạng hành vi) |
| `home_ratio_7d` | Tỷ lệ thời gian ở MainAudioHome |
| `video_ratio_7d` | Tỷ lệ screen thuộc nhóm Video |
| `lyrics_ratio_7d` | Tỷ lệ ở AudioPlayerLyrics |
| `permission_screen_ratio_7d` | Tỷ lệ ở màn hình Permission |

---

## Section I — Button Clicks (34 features)

### Per-button counts (7d), 33 buttons:

`btn_Play_cnt_7d`, `btn_Pause_cnt_7d`, `btn_Next_cnt_7d`, `btn_Previous_cnt_7d`,
`btn_Seek_cnt_7d`, `btn_Forward10s_cnt_7d`, `btn_Backward10s_cnt_7d`,
`btn_Back_cnt_7d`, `btn_Close_cnt_7d`, `btn_Search_cnt_7d`,
`btn_QuickSearchClicked_cnt_7d`, `btn_Favourite_cnt_7d`,
`btn_Delete_cnt_7d`, `btn_Ok_cnt_7d`, `btn_Cancel_cnt_7d`,
`btn_Confirm_cnt_7d`, `btn_TabVideo_cnt_7d`, `btn_TabSong_cnt_7d`,
`btn_TabLyric_cnt_7d`, `btn_TabAudio_cnt_7d`, `btn_TabPhoto_cnt_7d`,
`btn_Playlist_cnt_7d`, `btn_Save_cnt_7d`, `btn_Home_cnt_7d`,
`btn_MainMore_cnt_7d`, `btn_PlayAsAudio_cnt_7d`, `btn_Rotate_cnt_7d`,
`btn_ItemMore_cnt_7d`, `btn_More_cnt_7d`,
`btn_RepeatOne_cnt_7d`, `btn_RepeatAll_cnt_7d`, `btn_RepeatOff_cnt_7d`

### Aggregate (1):
| `unique_button_cnt_7d` | Số loại button khác nhau trong 7d |

---

## Section J — Search (5 features)

| Feature | Mô tả |
|---|---|
| `search_online_cnt_7d` | Clicks nút Search trong 7d |
| `search_quick_cnt_7d` | QuickSearchClicked trong 7d |
| `search_screen_cnt_7d` | Lần vào AudioSearchAll screen |
| `used_search_7d` | Binary: đã dùng search không |
| `search_days_7d` | Số ngày có search trong 7d |

---

## Section K — Audio Behavior (5 features)

| Feature | Mô tả |
|---|---|
| `lyrics_screen_cnt_7d` | Số lần xem lyrics |
| `audio_player_cnt_7d` | Số lần vào AudioPlayerSong |
| `playlist_cnt_7d` | Số lần vào playlist screens |
| `queue_cnt_7d` | Số lần xem hàng chờ phát |
| `audio_screen_ratio_7d` | % screen views thuộc nhóm audio player |

---

## Section L — Video Behavior (4 features)

| Feature | Mô tả |
|---|---|
| `video_player_cnt_7d` | Số lần xem VideoPlayer |
| `video_tab_cnt_7d` | Số lần vào tab video |
| `floating_video_cnt_7d` | Số lần dùng floating video |
| `video_ratio_7d` | % screen views thuộc nhóm video |

---

## Section M — Permission (4 features)

| Feature | Mô tả |
|---|---|
| `seen_notification_permission` | Binary: đã thấy màn hình xin phép notification |
| `seen_any_permission` | Binary: đã thấy bất kỳ permission screen |
| `permission_screen_cnt_7d` | Số lần vào permission screens trong 7d |
| `notif_permission_status` | Giá trị up_allow_notification gần nhất |

---

## Section N — Ads (5 features)

| Feature | Mô tả |
|---|---|
| `load_ad_cnt_7d` | Số lần load ad |
| `show_ad_cnt_7d` | Số lần hiển thị ad |
| `paid_ad_impression_cnt_7d` | Paid ad impressions |
| `ads_per_session_7d` | Trung bình ad/session — **cao → irritation** |
| `ad_revenue_7d` | Tổng revenue từ ads (USD) |

---

## Section O — IAP / Subscription (2 features)

| Feature | Mô tả |
|---|---|
| `iap_cnt_30d` | Số lần in-app purchase trong 30d |
| `payer_flag` | Binary: đã từng mua (subscription/IAP) |

**Ghi chú**: 94.9% user miễn phí. `payer_flag=1` là tín hiệu mạnh giữ chân.

---

## Section P — App Quality (4 features)

| Feature | Mô tả |
|---|---|
| `app_exception_cnt_7d` | Số app crash/exception trong 7d |
| `app_clear_data_cnt_30d` | Số lần xóa data app |
| `app_update_cnt_30d` | Số lần update app |
| `app_exit_cnt_7d` | Số lần app_exit event |

---

## Section Q — Journey (9 features)

| Feature | Mô tả |
|---|---|
| `first_screen` | Screen đầu tiên user từng vào |
| `last_screen` | Screen gần nhất trước snapshot |
| `first_button` | Button đầu tiên user click |
| `last_button` | Button cuối cùng trước snapshot |
| `home_to_search_flag` | User từng đi Home → Search |
| `search_to_lyrics_flag` | User từng đi Search → Lyrics |
| `search_to_video_flag` | User từng đi Search → Video |
| `lyrics_to_exit_flag` | User thường kết thúc ở Lyrics → Exit |
| `permission_to_exit_flag` | User thấy Permission screen rồi exit |

---

## Section R — Funnel Depth (8 features)

| Feature | Mô tả |
|---|---|
| `visited_home` | Đã vào MainAudioHome |
| `visited_player` | Đã vào audio/video player |
| `visited_lyrics` | Đã xem lyrics |
| `visited_search` | Đã dùng search screen |
| `visited_video` | Đã xem video |
| `visited_playlist` | Đã dùng playlist |
| `visited_scan_music` | Đã scan nhạc từ thiết bị |
| `funnel_depth` | Tổng số milestone đạt được (0-5) |

---

## Section T — Risk Scores / Target Encoding (4 features)

Được tính sau khi build features, dùng historical uninstall rate theo giá trị categorical.

| Feature | Mô tả |
|---|---|
| `country_uninstall_rate` | Tỷ lệ uninstall lịch sử theo quốc gia |
| `campaign_uninstall_rate` | Tỷ lệ uninstall theo campaign |
| `media_source_uninstall_rate` | Tỷ lệ uninstall theo kênh attribution |
| `app_version_uninstall_rate` | Tỷ lệ uninstall theo phiên bản app |

**Lưu ý**: tính trên `snapshot_date < cutoff` để tránh leakage.

---

## Tổng kết

| Section | Features |
|---|---|
| A: Acquisition | 3 |
| B: Country/Language | 2 |
| C: Device | 2 |
| D: Install | 5 |
| E: Session | 9 |
| F: Engagement | 6 |
| G: Recency | 6 |
| H: Screens | 31 (26 per-screen + 5 aggregate) |
| I: Buttons | 34 (33 per-button + 1 aggregate) |
| J: Search | 5 |
| K: Audio | 5 |
| L: Video | 4 |
| M: Permission | 4 |
| N: Ads | 5 |
| O: IAP | 2 |
| P: Quality | 4 |
| Q: Journey | 9 |
| R: Funnel | 8 |
| T: Risk Scores | 4 |
| **TOTAL** | **158** |

Plus categorical features requiring encoding: `media_source`, `campaign`, `country`, `language`, `app_version`, `first_screen`, `last_screen`, `first_button`, `last_button`, `notif_permission_status` = **10 categorical**

---

## Top 50 Features Dự Kiến Quan Trọng (SHAP estimate)

Dựa trên kinh nghiệm uninstall prediction và đặc điểm data:

| Rank | Feature | Lý do quan trọng |
|---|---|---|
| 1 | `session_trend_7d` | Signal trực tiếp nhất: user đang giảm dùng |
| 2 | `engagement_trend_7d` | Thời gian dùng giảm → sắp rời bỏ |
| 3 | `hours_since_last_session` | Bao lâu rồi không dùng |
| 4 | `active_days_7d` | Số ngày hoạt động gần đây |
| 5 | `days_since_install` | New user (D0-7) có risk cao nhất |
| 6 | `session_cnt_7d` | Tần suất sử dụng tuần này |
| 7 | `engagement_time_ms_7d` | Tổng thời gian dùng |
| 8 | `payer_flag` | Paid user hiếm khi uninstall |
| 9 | `funnel_depth` | User explore nhiều tính năng → ít uninstall |
| 10 | `ads_per_session_7d` | Quá nhiều ad → irritation |
| 11 | `country_uninstall_rate` | Mexico/Cuba/Nigeria có rate cao |
| 12 | `screen_PermissionNotif_cnt_7d` | Thấy màn hình permission → friction |
| 13 | `permission_to_exit_flag` | Thấy permission rồi exit = bad signal |
| 14 | `app_exception_cnt_7d` | Crash nhiều → frustrated |
| 15 | `app_clear_data_cnt_30d` | Xóa data là bước trước uninstall |
| 16 | `unique_screen_cnt_7d` | Explore nhiều = engaged |
| 17 | `unique_button_cnt_7d` | Dùng nhiều tính năng = retained |
| 18 | `audio_screen_ratio_7d` | Core feature ratio |
| 19 | `video_ratio_7d` | Video user có behavior khác |
| 20 | `is_week1_user` | First-week critical period |
| 21 | `avg_engagement_per_session_7d` | Session quality |
| 22 | `session_cnt_1d` | Activity cực kỳ gần đây |
| 23 | `btn_Play_cnt_7d` | Core action frequency |
| 24 | `screen_AudioPlayerSong_cnt_7d` | Core screen usage |
| 25 | `lyrics_ratio_7d` | Lyrics = deep engagement |
| 26 | `app_version_uninstall_rate` | Buggy version = risk |
| 27 | `screen_VideoPlayer_cnt_7d` | Video feature engagement |
| 28 | `visited_lyrics` | Reached deep content |
| 29 | `visited_scan_music` | Local music scan = high intent |
| 30 | `hours_since_last_engagement` | Recency of real engagement |
| 31 | `btn_Seek_cnt_7d` | Active music navigation |
| 32 | `btn_Next_cnt_7d` | Song discovery behavior |
| 33 | `search_days_7d` | Consistent search = engaged |
| 34 | `screen_Equalizer_cnt_7d` | Power user feature |
| 35 | `permission_screen_cnt_7d` | Friction count |
| 36 | `show_ad_cnt_7d` | Ad exposure intensity |
| 37 | `engagement_time_ms_1d` | Very recent activity |
| 38 | `screen_MainAudioHome_cnt_7d` | Return to home = browsing |
| 39 | `btn_Favourite_cnt_7d` | Curation behavior = retention |
| 40 | `playlist_cnt_7d` | Playlist use = stickiness |
| 41 | `active_days_30d` | Long-term engagement pattern |
| 42 | `hours_since_last_search` | Search recency |
| 43 | `home_to_search_flag` | Discovery pattern |
| 44 | `btn_TabLyric_cnt_7d` | Lyrics tab usage |
| 45 | `media_source_uninstall_rate` | Acquisition quality signal |
| 46 | `ad_revenue_7d` | Revenue contributed (inverse risk) |
| 47 | `seen_notification_permission` | Onboarding friction |
| 48 | `screen_LockScreen_cnt_7d` | Background play = sticky |
| 49 | `avg_sessions_per_day_7d` | Usage intensity |
| 50 | `app_exit_cnt_7d` | Intentional exit pattern |

---

## Encoding Strategy

### Categorical (10 features)
| Strategy | Features | Lý do |
|---|---|---|
| **Target Encoding** | country, campaign, media_source, app_version | Cardinality cao, risk proxy rõ ràng |
| **LabelEncoder** | first_screen, last_screen, first_button, last_button, language, notif_permission_status | Cardinality thấp-trung bình |

### Missing Value Strategy
| Feature group | Default | Lý do |
|---|---|---|
| Count features (7d/30d) | 0 | Không có = không dùng |
| Recency features | 9999 | Không bao giờ = rất lâu rồi |
| Ratio features | 0.0 | Không có hoạt động = 0% |
| Trend features | 1.0 | Không đổi = neutral |
| Risk scores | -1 | Chưa đủ sample (xử lý bằng imputation) |

### Feature Selection
1. **Remove** features với variance gần 0 (`VarianceThreshold`)
2. **Remove** highly correlated pairs (r > 0.95, giữ lại SHAP quan trọng hơn)
3. **Keep** top 80 features theo SHAP mean absolute value
4. Đặc biệt giữ lại: trend features, recency, funnel_depth dù SHAP thấp (interpretability)
