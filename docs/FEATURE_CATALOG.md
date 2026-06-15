# Android Music v2 — Feature Catalog (Uninstall Prediction)

## Tổng quan pipeline

| Thông số | Giá trị |
|---|---|
| **Bảng nguồn** | `android_music_v2.android_music_v2_ga4_staging_flat` |
| **Feature store** | `android_music_v2.feature_store_uninstall` |
| **Dạng bảng** | `ReplacingMergeTree(created_at)` — INSERT mới với `created_at` cao hơn sẽ thay thế hàng cũ |
| **Đơn vị hàng** | `(snapshot_date, user_pseudo_id)` — mỗi cặp = 1 hàng |
| **Feature window** | `[snapshot_date - 30, snapshot_date)` — không dùng dữ liệu tương lai |
| **Label window** | `[snapshot_date, snapshot_date + 7)` |
| **Label** | `label_uninstall_7d = 1` nếu có event `app_remove` trong 7 ngày sau snapshot |
| **Label rate** | ~4–10% (tùy snapshot, D0-D30 cohort) |
| **User filter** | `install_date ∈ [snapshot_date - 30, snapshot_date]` — chỉ dự đoán user D0–D30 |
| **Leakage rule** | Mọi feature dùng `event_date < snapshot_date`; label dùng `event_date >= snapshot_date` |

### WHERE clause trong SQL

```sql
WHERE src.event_date >= toDate('{snap}') - 30   -- quét 30 ngày lịch sử
  AND src.event_date < toDate('{snap}') + 7      -- + label window để tính label trong 1 pass
GROUP BY src.user_pseudo_id
HAVING toDate(anyIf(install_date, isNotNull(install_date)))
           >= toDate('{snap}') - 30              -- chỉ lấy user cài trong 30 ngày
   AND toDate(anyIf(install_date, isNotNull(install_date)))
           <= toDate('{snap}')
```

---

## Các cột nguồn trong flat table

| Cột | Ý nghĩa |
|---|---|
| `user_pseudo_id` | ID user (dạng hash) |
| `event_date` | Ngày xảy ra event (`Date`) |
| `event_timestamp` | Timestamp microseconds, dùng để lấy giá trị mới nhất (`argMaxIf`) |
| `event_name` | Tên event: `session_start`, `app_remove`, `screen_view`, `click_btn_ev`, ... |
| `install_date` | Ngày cài đặt app (`DateTime`, cột user-level, denorm trên mọi row) |
| `up_af_media_source` | Kênh attribution (AppsFlyer) |
| `up_af_campaign` | Campaign attribution |
| `country` | Quốc gia của user |
| `up_language` | Ngôn ngữ thiết bị |
| `app_version` | Phiên bản app tại thời điểm event |
| `platform` | ANDROID (luôn cố định) |
| `unique_session_id` | ID session duy nhất (dùng `countDistinctIf` để đếm session) |
| `engagement_time` | Thời gian engagement (milliseconds) từ `user_engagement` event |
| `mapped_screen` | Tên màn hình đã map (từ `screen_view` / `screen_view_ev`) |
| `click_button_name` | Tên nút bấm (từ `click_btn_ev`) |
| `up_allow_notification` | Trạng thái permission notification |
| `ep_revenue` | Revenue từ ad event |

---

## Section A — Acquisition (3 features)

**Nguồn cột**: `up_af_media_source`, `up_af_campaign`, `event_name`

| Feature | Công thức SQL | Ghi chú |
|---|---|---|
| `media_source` | `ifNull(argMaxIf(up_af_media_source, event_timestamp, up_af_media_source != '' AND up_af_media_source IS NOT NULL AND event_date < snap), '')` | Giá trị mới nhất trước snapshot |
| `campaign` | `ifNull(argMaxIf(up_af_campaign, event_timestamp, up_af_campaign != '' AND up_af_campaign IS NOT NULL AND event_date < snap), '')` | Giá trị mới nhất trước snapshot |
| `has_attribution` | `toUInt8(countIf(event_name = 'af_attribution_received' AND event_date < snap) > 0)` | 1 nếu từng nhận attribution |

> ~94% user có `media_source = ''` hoặc `'NA'`. Dùng target encoding (`media_source_uninstall_rate`) thay one-hot.

---

## Section B — Country / Language (2 features)

**Nguồn cột**: `country`, `up_language`

| Feature | Công thức SQL | Ghi chú |
|---|---|---|
| `country` | `ifNull(argMaxIf(country, event_timestamp, country != '' AND country IS NOT NULL AND event_date < snap), '')` | Quốc gia mới nhất trước snapshot |
| `language` | `ifNull(argMaxIf(up_language, event_timestamp, up_language != '' AND up_language IS NOT NULL AND event_date < snap), '')` | Ngôn ngữ thiết bị mới nhất |

> Top countries: MX, CU, NG, AO, SD. Dùng target encoding (`country_uninstall_rate`).

---

## Section C — Device (2 features)

**Nguồn cột**: `app_version`, `platform`

| Feature | Công thức SQL | Ghi chú |
|---|---|---|
| `app_version` | `ifNull(argMaxIf(app_version, event_timestamp, app_version IS NOT NULL AND event_date < snap), '')` | Version mới nhất trước snapshot |
| `platform` | `ifNull(argMaxIf(platform, event_timestamp, platform IS NOT NULL AND event_date < snap), '')` | Luôn = `ANDROID` trong dataset này |

---

## Section D — Install (5 features)

**Nguồn cột**: `install_date` (DateTime, user-level property, có trên mọi row)

Ký hiệu: `idate = toDate(anyIf(install_date, isNotNull(install_date)))`
— dùng `anyIf` thay `min()` để tránh bị ảnh hưởng bởi filter `event_date >= snap-30`.

| Feature | Công thức SQL | Giải thích |
|---|---|---|
| `days_since_install` | `toInt32(dateDiff('day', idate, toDate(snap)))` | Số ngày từ cài → snapshot. D0=0, D1=1, ... |
| `hours_since_install` | `toInt32(dateDiff('hour', toDateTime(idate), toDateTime(toDate(snap))))` | Cùng ý nghĩa nhưng đơn vị giờ |
| `is_day0_user` | `toUInt8(idate = toDate(snap) - 1)` | **Lưu ý**: flag = 1 khi `install_date = snap - 1`, tức `days_since_install = 1` — đặt tên "D0" nhưng thực chất là D1 user |
| `is_day1_user` | `toUInt8(dateDiff('day', idate, toDate(snap)) = 1)` | = 1 khi `days_since_install = 1` — **trùng với `is_day0_user`** |
| `is_week1_user` | `toUInt8(dateDiff('day', idate, toDate(snap)) <= 7)` | = 1 khi user cài trong 7 ngày qua |

> `is_day0_user` và `is_day1_user` tính cùng một điều kiện (`days_since_install = 1`). User cài đúng ngày snapshot (`days_since_install = 0`) không được flag riêng — nhưng vẫn có trong feature store và được model nhận biết qua `days_since_install = 0`.

---

## Section E — Session Behavior (9 features)

**Nguồn cột**: `unique_session_id`, `event_name = 'session_start'`, `event_date`

| Feature | Công thức SQL | Window |
|---|---|---|
| `session_cnt_1d` | `countDistinctIf(unique_session_id, event_name='session_start' AND event_date = snap-1)` | 1 ngày qua |
| `session_cnt_3d` | `countDistinctIf(unique_session_id, event_name='session_start' AND event_date ∈ [snap-3, snap))` | 3 ngày qua |
| `session_cnt_7d` | `countDistinctIf(unique_session_id, event_name='session_start' AND event_date ∈ [snap-7, snap))` | 7 ngày qua |
| `session_cnt_14d` | `countDistinctIf(unique_session_id, event_name='session_start' AND event_date ∈ [snap-14, snap))` | 14 ngày qua |
| `session_cnt_30d` | `countDistinctIf(unique_session_id, event_name='session_start' AND event_date ∈ [snap-30, snap))` | 30 ngày qua |
| `active_days_7d` | `countDistinctIf(event_date, event_date ∈ [snap-7, snap))` | Số ngày có bất kỳ event trong 7d |
| `active_days_30d` | `countDistinctIf(event_date, event_date ∈ [snap-30, snap))` | Số ngày có bất kỳ event trong 30d |
| `avg_sessions_per_day_7d` | `session_cnt_7d / active_days_7d` (nếu `active_days_7d > 0`, else `0`) | Tần suất session/ngày |
| `session_trend_7d` | `session_cnt_7d / session_cnt_prev7d` — nếu prev=0 và cur>0 → `2.0`, nếu cả hai = 0 → `1.0` | Xu hướng: **< 1 = đang giảm dùng** |

---

## Section F — Engagement Time (6 features)

**Nguồn cột**: `engagement_time` (milliseconds, từ `user_engagement` event)

| Feature | Công thức SQL | Window |
|---|---|---|
| `engagement_time_ms_1d` | `toInt64(sumIf(ifNull(engagement_time,0), event_date = snap-1))` | 1 ngày |
| `engagement_time_ms_3d` | `toInt64(sumIf(ifNull(engagement_time,0), event_date ∈ [snap-3, snap)))` | 3 ngày |
| `engagement_time_ms_7d` | `toInt64(sumIf(ifNull(engagement_time,0), event_date ∈ [snap-7, snap)))` | 7 ngày |
| `engagement_time_ms_30d` | `toInt64(sumIf(ifNull(engagement_time,0), event_date ∈ [snap-30, snap)))` | 30 ngày |
| `avg_engagement_per_session_7d` | `engagement_time_ms_7d / session_cnt_7d` (nếu `session_cnt_7d > 0`, else `0`) | ms/session |
| `engagement_trend_7d` | `eng_7d / eng_prev7d` — fallback giống `session_trend_7d` | **< 1 = giảm engagement** |

---

## Section G — Recency (6 features)

**Nguồn cột**: `event_date`, `event_name`, `click_button_name`

Công thức chung: `dateDiff('day', maxIf(event_date, <điều kiện> AND event_date < snap), snap) * 24`
— nhân 24 để ra đơn vị giờ (tính theo ngày vì flat table chỉ có `event_date`).
Default = `9999` nếu không có event nào phù hợp.

| Feature | Điều kiện lọc event | Default |
|---|---|---|
| `hours_since_last_session` | `event_date < snap` (bất kỳ event nào) | 9999 |
| `hours_since_last_screen` | `event_name IN ('screen_view', 'screen_view_ev')` | 9999 |
| `hours_since_last_click` | `event_name = 'click_btn_ev'` | 9999 |
| `hours_since_last_ad` | `event_name IN ('show_ad_ev', 'load_ad_ev', 'paid_ad_impression')` | 9999 |
| `hours_since_last_search` | `click_button_name IN ('Search', 'QuickSearchClicked')` | 9999 |
| `hours_since_last_engagement` | `event_name = 'user_engagement'` | 9999 |

---

## Section H — Screen Views (31 features)

**Nguồn cột**: `mapped_screen`, `event_date`
**Window**: `event_date ∈ [snap-7, snap)`

### Per-screen count (26 features): `countIf(mapped_screen = '<screen>' AND event_date ∈ [snap-7, snap))`

| Feature | Giá trị `mapped_screen` |
|---|---|
| `screen_VideoPlayer_cnt_7d` | `VideoPlayer` |
| `screen_AudioPlayerSong_cnt_7d` | `AudioPlayerSong` |
| `screen_AudioPlayerLyrics_cnt_7d` | `AudioPlayerLyrics` |
| `screen_MainAudioSongs_cnt_7d` | `MainAudioSongs` |
| `screen_AudioPlayerQueue_cnt_7d` | `AudioPlayerQueue` |
| `screen_PhotoDetail_cnt_7d` | `PhotoDetail` |
| `screen_AudioSelection_cnt_7d` | `AudioSelection` |
| `screen_FloatingPlayer_cnt_7d` | `FloatingPlayer` |
| `screen_MainVideoTabLocal_cnt_7d` | `MainVideoTabLocal` |
| `screen_MainAudioHome_cnt_7d` | `MainAudioHome` |
| `screen_Equalizer_cnt_7d` | `Equalizer` |
| `screen_AudioSearchAll_cnt_7d` | `AudioSearchAll` |
| `screen_AudioPlaylistsDetail_cnt_7d` | `AudioPlaylistsDetail` |
| `screen_LockScreen_cnt_7d` | `LockScreen` |
| `screen_VideoSelection_cnt_7d` | `VideoSelection` |
| `screen_FloatingVideo_cnt_7d` | `FloatingVideo` |
| `screen_MainMore_cnt_7d` | `MainMore` |
| `screen_ScanMusic_cnt_7d` | `ScanMusic` |
| `screen_MainAudioTabPlaylists_cnt_7d` | `MainAudioTabPlaylists` |
| `screen_MainAudioFolder_cnt_7d` | `MainAudioFolder` |
| `screen_MainAudio_RequestNotificationPermission_cnt_7d` | `MainAudio_RequestNotificationPermission` |
| `screen_ConfigTheme_cnt_7d` | `ConfigTheme` |
| `screen_AudioFolderDetail_cnt_7d` | `AudioFolderDetail` |
| `screen_VideoFolderDetail_cnt_7d` | `VideoFolderDetail` |
| `screen_MainAudioAlbum_cnt_7d` | `MainAudioAlbum` |
| `screen_AudioEditTag_cnt_7d` | `AudioEditTag` |

### Aggregate screen features (5 features):

| Feature | Công thức SQL |
|---|---|
| `unique_screen_cnt_7d` | `countDistinctIf(mapped_screen, event_date ∈ [snap-7, snap) AND mapped_screen IS NOT NULL AND != '')` |
| `home_ratio_7d` | `countIf(mapped_screen='MainAudioHome' AND ...) / countIf(mapped_screen IS NOT NULL AND != '' AND ...)` |
| `video_ratio_7d` | `countIf(mapped_screen IN ('VideoPlayer','MainVideoTabLocal','FloatingVideo','VideoSelection') AND ...) / total_screens_7d` |
| `lyrics_ratio_7d` | `countIf(mapped_screen='AudioPlayerLyrics' AND ...) / total_screens_7d` |
| `permission_screen_ratio_7d` | `countIf(mapped_screen LIKE '%Permission%' AND ...) / total_screens_7d` |

> `total_screens_7d` = `countIf(mapped_screen IS NOT NULL AND != '' AND event_date ∈ [snap-7, snap))`

---

## Section I — Button Clicks (34 features)

**Nguồn cột**: `click_button_name`, `event_date`
**Window**: `event_date ∈ [snap-7, snap)`

### Per-button count (33 features): `countIf(click_button_name = '<button>' AND event_date ∈ [snap-7, snap))`

| Feature | Giá trị `click_button_name` |
|---|---|
| `btn_Play_cnt_7d` | `Play` |
| `btn_Pause_cnt_7d` | `Pause` |
| `btn_Next_cnt_7d` | `Next` |
| `btn_Previous_cnt_7d` | `Previous` |
| `btn_Seek_cnt_7d` | `Seek` |
| `btn_Forward10s_cnt_7d` | `Forward10s` |
| `btn_Backward10s_cnt_7d` | `Backward10s` |
| `btn_Back_cnt_7d` | `Back` |
| `btn_Close_cnt_7d` | `Close` |
| `btn_Search_cnt_7d` | `Search` |
| `btn_QuickSearchClicked_cnt_7d` | `QuickSearchClicked` |
| `btn_Favourite_cnt_7d` | `Favourite` |
| `btn_Delete_cnt_7d` | `Delete` |
| `btn_Ok_cnt_7d` | `Ok` |
| `btn_Cancel_cnt_7d` | `Cancel` |
| `btn_Confirm_cnt_7d` | `Confirm` |
| `btn_TabVideo_cnt_7d` | `TabVideo` |
| `btn_TabSong_cnt_7d` | `TabSong` |
| `btn_TabLyric_cnt_7d` | `TabLyric` |
| `btn_TabAudio_cnt_7d` | `TabAudio` |
| `btn_TabPhoto_cnt_7d` | `TabPhoto` |
| `btn_Playlist_cnt_7d` | `Playlist` |
| `btn_Save_cnt_7d` | `Save` |
| `btn_Home_cnt_7d` | `Home` |
| `btn_MainMore_cnt_7d` | `MainMore` |
| `btn_PlayAsAudio_cnt_7d` | `PlayAsAudio` |
| `btn_Rotate_cnt_7d` | `Rotate` |
| `btn_ItemMore_cnt_7d` | `ItemMore` |
| `btn_More_cnt_7d` | `More` |
| `btn_RepeatOne_cnt_7d` | `RepeatOne` |
| `btn_RepeatAll_cnt_7d` | `RepeatAll` |
| `btn_RepeatOff_cnt_7d` | `RepeatOff` |

### Aggregate button feature (1 feature):

| Feature | Công thức SQL |
|---|---|
| `unique_button_cnt_7d` | `countDistinctIf(click_button_name, event_date ∈ [snap-7, snap) AND click_button_name IS NOT NULL AND != '')` |

---

## Section J — Search (5 features)

**Nguồn cột**: `click_button_name`, `mapped_screen`, `event_date`

| Feature | Công thức SQL | Window |
|---|---|---|
| `search_online_cnt_7d` | `countIf(click_button_name = 'Search' AND event_date ∈ [snap-7, snap))` | 7d |
| `search_quick_cnt_7d` | `countIf(click_button_name = 'QuickSearchClicked' AND event_date ∈ [snap-7, snap))` | 7d |
| `search_screen_cnt_7d` | `countIf(mapped_screen = 'AudioSearchAll' AND event_date ∈ [snap-7, snap))` | 7d |
| `used_search_7d` | `toUInt8(countIf(click_button_name IN ('Search','QuickSearchClicked') AND event_date ∈ [snap-7, snap)) > 0)` | Binary |
| `search_days_7d` | `countDistinctIf(event_date, click_button_name IN ('Search','QuickSearchClicked') AND event_date ∈ [snap-7, snap))` | Số ngày có search |

---

## Section K — Audio Behavior (5 features)

**Nguồn cột**: `mapped_screen`, `event_name`, `event_date`

| Feature | Công thức SQL | Window |
|---|---|---|
| `lyrics_screen_cnt_7d` | `countIf(mapped_screen = 'AudioPlayerLyrics' AND event_date ∈ [snap-7, snap))` | 7d |
| `audio_player_cnt_7d` | `countIf(mapped_screen = 'AudioPlayerSong' AND event_date ∈ [snap-7, snap))` | 7d |
| `playlist_cnt_7d` | `countIf(mapped_screen IN ('AudioPlaylistsDetail','MainAudioTabPlaylists') AND event_date ∈ [snap-7, snap))` | 7d |
| `queue_cnt_7d` | `countIf(mapped_screen = 'AudioPlayerQueue' AND event_date ∈ [snap-7, snap))` | 7d |
| `audio_screen_ratio_7d` | `countIf(mapped_screen IN ('AudioPlayerSong','AudioPlayerLyrics','AudioPlayerQueue') AND ...) / countIf(event_name IN ('screen_view','screen_view_ev') AND event_date ∈ [snap-7, snap))` | % screen audio |

---

## Section L — Video Behavior (3 features)

**Nguồn cột**: `mapped_screen`, `event_date`

| Feature | Công thức SQL | Window |
|---|---|---|
| `video_player_cnt_7d` | `countIf(mapped_screen = 'VideoPlayer' AND event_date ∈ [snap-7, snap))` | 7d |
| `video_tab_cnt_7d` | `countIf(mapped_screen = 'MainVideoTabLocal' AND event_date ∈ [snap-7, snap))` | 7d |
| `floating_video_cnt_7d` | `countIf(mapped_screen = 'FloatingVideo' AND event_date ∈ [snap-7, snap))` | 7d |

> `video_ratio_7d` nằm ở Section H (aggregate screen). Section L không lặp lại.

---

## Section M — Permission (4 features)

**Nguồn cột**: `mapped_screen`, `up_allow_notification`, `event_timestamp`

| Feature | Công thức SQL | Window |
|---|---|---|
| `seen_notification_permission` | `toUInt8(countIf(mapped_screen = 'MainAudio_RequestNotificationPermission') > 0)` | All-time |
| `seen_any_permission` | `toUInt8(countIf(mapped_screen LIKE '%Permission%') > 0)` | All-time (toàn bộ window quét) |
| `permission_screen_cnt_7d` | `countIf(mapped_screen LIKE '%Permission%' AND event_date ∈ [snap-7, snap))` | 7d |
| `notif_permission_status` | `ifNull(argMaxIf(up_allow_notification, event_timestamp, event_date < snap), '')` | Giá trị mới nhất |

---

## Section N — Ads (5 features)

**Nguồn cột**: `event_name`, `ep_revenue`, `unique_session_id`, `event_date`

| Feature | Công thức SQL | Window |
|---|---|---|
| `load_ad_cnt_7d` | `countIf(event_name = 'load_ad_ev' AND event_date ∈ [snap-7, snap))` | 7d |
| `show_ad_cnt_7d` | `countIf(event_name = 'show_ad_ev' AND event_date ∈ [snap-7, snap))` | 7d |
| `paid_ad_impression_cnt_7d` | `countIf(event_name = 'paid_ad_impression' AND event_date ∈ [snap-7, snap))` | 7d |
| `ads_per_session_7d` | `show_ad_cnt_7d / session_cnt_7d` (nếu `session_cnt_7d > 0`, else `0`) | Trung bình ad/session |
| `ad_revenue_7d` | `toFloat32(sumIf(ifNull(ep_revenue,0), event_date ∈ [snap-7, snap)))` | Tổng revenue (USD) |

---

## Section O — IAP / Subscription (2 features)

**Nguồn cột**: `event_name`

| Feature | Công thức SQL | Window |
|---|---|---|
| `iap_cnt_30d` | `countIf(event_name = 'iap_ev' AND event_date ∈ [snap-30, snap))` | 30 ngày |
| `payer_flag` | `toUInt8(countIf(event_name = 'iap_ev' AND event_date < snap) > 0)` | All-time (toàn bộ lịch sử trong window quét) |

> ~95% user miễn phí. `payer_flag = 1` là tín hiệu giữ chân rất mạnh.

---

## Section P — App Quality (4 features)

**Nguồn cột**: `event_name`, `event_date`

| Feature | Công thức SQL | Window |
|---|---|---|
| `app_exception_cnt_7d` | `countIf(event_name = 'app_exception' AND event_date ∈ [snap-7, snap))` | 7d |
| `app_clear_data_cnt_30d` | `countIf(event_name = 'app_clear_data' AND event_date ∈ [snap-30, snap))` | 30d |
| `app_update_cnt_30d` | `countIf(event_name = 'app_update' AND event_date ∈ [snap-30, snap))` | 30d |
| `app_exit_cnt_7d` | `countIf(event_name = 'app_exit' AND event_date ∈ [snap-7, snap))` | 7d |

---

## Section Q — Journey (9 features)

**Nguồn cột**: `mapped_screen`, `click_button_name`, `event_name`, `event_timestamp`, `event_date`

### First/Last screen & button (4 features):

| Feature | Công thức SQL |
|---|---|
| `first_screen` | `ifNull(argMinIf(mapped_screen, event_timestamp, mapped_screen IS NOT NULL AND != '' AND event_date < snap), '')` |
| `last_screen` | `ifNull(argMaxIf(mapped_screen, event_timestamp, mapped_screen IS NOT NULL AND != '' AND event_date < snap), '')` |
| `first_button` | `ifNull(argMinIf(click_button_name, event_timestamp, click_button_name IS NOT NULL AND != '' AND event_date < snap), '')` |
| `last_button` | `ifNull(argMaxIf(click_button_name, event_timestamp, click_button_name IS NOT NULL AND != '' AND event_date < snap), '')` |

### Journey flags (5 features): `toUInt8(A AND B)` = 1 nếu user **từng** thực hiện cả A và B

| Feature | Điều kiện A | Điều kiện B |
|---|---|---|
| `home_to_search_flag` | `countIf(mapped_screen='MainAudioHome' AND event_date < snap) > 0` | `countIf(mapped_screen='AudioSearchAll' AND event_date < snap) > 0` |
| `search_to_lyrics_flag` | `countIf(mapped_screen='AudioSearchAll' AND event_date < snap) > 0` | `countIf(mapped_screen='AudioPlayerLyrics' AND event_date < snap) > 0` |
| `search_to_video_flag` | `countIf(mapped_screen='AudioSearchAll' AND event_date < snap) > 0` | `countIf(mapped_screen='VideoPlayer' AND event_date < snap) > 0` |
| `lyrics_to_exit_flag` | `countIf(mapped_screen='AudioPlayerLyrics' AND event_date < snap) > 0` | `countIf(event_name='app_exit' AND event_date < snap) > 0` |
| `permission_to_exit_flag` | `countIf(mapped_screen LIKE '%Permission%' AND event_date < snap) > 0` | `countIf(event_name='app_exit' AND event_date < snap) > 0` |

> Các flag này là **all-time** (toàn bộ lịch sử trong window quét), không giới hạn 7d.

---

## Section R — Funnel Depth (8 features)

**Nguồn cột**: `mapped_screen`, `event_date`
Điều kiện chung: `event_date < snap`

| Feature | Công thức SQL | Milestone |
|---|---|---|
| `visited_home` | `toUInt8(countIf(mapped_screen='MainAudioHome' AND event_date < snap) > 0)` | Đã vào trang chủ audio |
| `visited_player` | `toUInt8(countIf(mapped_screen IN ('AudioPlayerSong','AudioPlayerLyrics','VideoPlayer') AND event_date < snap) > 0)` | Đã nghe/xem |
| `visited_lyrics` | `toUInt8(countIf(mapped_screen='AudioPlayerLyrics' AND event_date < snap) > 0)` | Đã xem lyrics |
| `visited_search` | `toUInt8(countIf(mapped_screen='AudioSearchAll' AND event_date < snap) > 0)` | Đã dùng search |
| `visited_video` | `toUInt8(countIf(mapped_screen IN ('VideoPlayer','MainVideoTabLocal') AND event_date < snap) > 0)` | Đã xem video |
| `visited_playlist` | `toUInt8(countIf(mapped_screen IN ('AudioPlaylistsDetail','MainAudioTabPlaylists') AND event_date < snap) > 0)` | Đã dùng playlist |
| `visited_scan_music` | `toUInt8(countIf(mapped_screen='ScanMusic' AND event_date < snap) > 0)` | Đã scan nhạc từ máy |
| `funnel_depth` | `visited_home + visited_player + visited_lyrics + visited_search + visited_playlist` | Tổng 5 milestone (0–5) |

---

## Section T — Risk Scores / Target Encoding (4 features)

**Nguồn**: bảng `android_music_v2.risk_baseline` — được build bằng `build_risk_scores()` **sau** khi build features.

### Cách tính:
1. Tính uninstall rate lịch sử: `avg(label_uninstall_7d)` GROUP BY từng giá trị của cột, trên `snapshot_date < cutoff`
2. Lưu vào `risk_baseline` (ReplacingMergeTree)
3. Đọc rates vào Python → sinh câu `ALTER TABLE UPDATE ... CASE WHEN col='v1' THEN r1 WHEN ... ELSE -1`
4. Chạy mutation đồng bộ (`mutations_sync=1`)

| Feature | Categorical gốc | Ghi chú |
|---|---|---|
| `country_uninstall_rate` | `country` | 206 giá trị |
| `campaign_uninstall_rate` | `campaign` | 3 giá trị |
| `media_source_uninstall_rate` | `media_source` | 2 giá trị |
| `app_version_uninstall_rate` | `app_version` | 49 giá trị |

> Giá trị `-1` = không có đủ sample (< 100 users). Cần impute trước khi training.
> Cutoff = ngày snapshot đầu tiên (`2026-04-14`) để tránh data leakage.

---

## Label

**Nguồn cột**: `event_name`, `event_date`

```sql
toUInt8(countIf(event_name = 'app_remove'
    AND event_date >= toDate('{snap}')
    AND event_date < toDate('{snap}') + 7) > 0)  AS label_uninstall_7d
```

| Snapshot | Users | Xóa app | Rate |
|---|---|---|---|
| 2026-04-14 | 149,564 | 14,675 | 9.81% |
| 2026-04-21 | 198,649 | 12,154 | 6.12% |
| 2026-04-28 | 234,697 | 11,326 | 4.83% |
| 2026-05-05 | 261,612 | 11,192 | 4.28% |
| 2026-05-12 | 246,003 | 11,133 | 4.53% |
| 2026-05-19 | 231,008 | 9,541 | 4.13% |
| 2026-05-26 | 222,883 | 9,278 | 4.16% |
| 2026-06-02 | 208,202 | 8,039 | 3.86% |

Rate giảm theo thời gian vì snapshot đầu (14/04) gần ngày app ra mắt → nhiều user D0-D3 với rate cao.

---

## Tổng kết số lượng features

| Section | Tên | Số feature |
|---|---|---|
| A | Acquisition | 3 |
| B | Country / Language | 2 |
| C | Device | 2 |
| D | Install | 5 |
| E | Session | 9 |
| F | Engagement | 6 |
| G | Recency | 6 |
| H | Screen Views | 31 (26 per-screen + 5 aggregate) |
| I | Button Clicks | 34 (33 per-button + 1 aggregate) |
| J | Search | 5 |
| K | Audio | 5 |
| L | Video | 3 |
| M | Permission | 4 |
| N | Ads | 5 |
| O | IAP | 2 |
| P | Quality | 4 |
| Q | Journey | 9 |
| R | Funnel | 8 |
| T | Risk Scores | 4 |
| **TOTAL** | | **157 numerical + 10 categorical = 167** |

### 10 Categorical features (cần encoding):
`media_source`, `campaign`, `country`, `language`, `app_version`,
`first_screen`, `last_screen`, `first_button`, `last_button`, `notif_permission_status`

---

## Default values

| Nhóm feature | Default | Lý do |
|---|---|---|
| Count (7d/30d) | `0` | Không có event = không dùng |
| Recency | `9999` | Không bao giờ = rất lâu rồi |
| Ratio | `0.0` | Không có hoạt động = 0% |
| Trend | `1.0` | Không thay đổi = neutral |
| Risk scores | `-1` | Chưa đủ sample — impute trước training |
| Categorical | `''` | Không có giá trị |
