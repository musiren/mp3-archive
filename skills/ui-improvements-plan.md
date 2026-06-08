# Android UI Improvements — Plan

Polish the Android (KivyMD) app's list/tree selection flow and the player tab.
All work is on the `android-ui-improvements` branch; verified on-device
(Galaxy SM-S928N). Desktop UI is untouched.

## Requirements

### List / Tree tabs — selection & add-to-queue
1. Hide the per-row selection circle (○) by default.
2. Add a top-bar **check icon** that toggles selection mode (the ○ appears
   per row while on).
3. Tapping the check icon also offers **전체 선택** (select all) — and
   선택 해제 / 선택 종료.
4. When ≥1 song is selected, show a **재생목록에 추가** button that adds the
   selected songs to the queue.
5. The 트리 view behaves the same; selecting a **directory** adds every song
   under it (recursively) to the selection / queue.

### Player tab
1. Toggle to **show/hide the album art**.
2. **Reduce the vertical spacing** around the progress bar, volume, transport
   icons, and queue-toolbar rows.
3. Remove the queue row's **✕**; add **제거** to the row's long-press menu to
   delete it from the queue.
4. **Drag** queue rows to reorder them.

## Approach (staged)

- **Stage A — Player tab (lower risk):** tighten paddings/heights; add an
  album-art visibility toggle (`_show_art` preference honoured by
  `_show_now_art`); remove the QueueRow ✕ and give QueueRow a long-press menu
  with 제거 (and 재생). Build + verify.
- **Stage B — List selection mode:** add a `selection_mode` BooleanProperty on
  the app; the row's right check widget shows only in selection mode (opacity/
  disabled bound to `app.selection_mode`). Toolbar check icon enters selection
  mode and opens a dropdown (전체 선택 / 선택 해제 / 선택 종료). A bottom
  "재생목록에 추가 (N)" bar appears when the selection is non-empty and adds the
  selected paths to the queue, then exits selection mode. Build + verify.
- **Stage C — Tree selection + folder add:** give tree file rows the same ○ in
  selection mode; selecting a folder row selects every file under it
  (`tree_util.files_under_folder`). The add button enqueues all selected. Build
  + verify.
- **Stage D — Queue drag-reorder (hardest):** KivyMD's RecycleView has no
  built-in drag reorder. Implement a long-press-grab drag on QueueRow (or a
  drag handle): track `on_touch_move`, compute the target index from the y
  offset over `dp(60)` rows, reorder `PlayQueue.items` + the current index, and
  re-sync the queue to the service. If a robust drag proves infeasible in the
  time budget, fall back to up/down move buttons in the long-press menu and
  note it. Build + verify.

## Risks / notes
- **Drag-reorder** is the main risk (no framework support; touch handling in a
  recycled list is fiddly). Tackled last and in isolation.
- Selection-circle hiding: KivyMD list items bake their right widget, so it is
  hidden via opacity/disabled (a small right gap remains when off) rather than
  removed from the tree.
- Each queue mutation (reorder/remove) must `_sync_queue()` to the background
  service so it keeps the same order/auto-advance.
- On-device verification per stage (phone connected); push only on explicit
  user approval.
