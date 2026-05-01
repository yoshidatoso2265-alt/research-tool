import asyncio
import io
import sys
import threading
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd

# Windows + Streamlit + Playwright の subprocess 問題回避
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass


def run_async_in_thread(coro):
    """別スレッドで新規 event loop を作って async関数を実行する。
    Streamlit の event loop と Playwright subprocess の競合を避ける。"""
    result = {"value": None, "error": None}

    def target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result["value"] = loop.run_until_complete(coro)
        except Exception as e:
            result["error"] = e
        finally:
            loop.close()

    t = threading.Thread(target=target)
    t.start()
    t.join()
    if result["error"]:
        raise result["error"]
    return result["value"]

sys.path.insert(0, str(Path(__file__).parent))

from core.aggregator import aggregate, filter_items
from core.models import Item
from core.shipping import estimate_all_carriers
from core.shipping_mercari import (
    list_methods as mercari_methods,
    get_size_options as mercari_size_options,
    get_method_spec as mercari_spec,
)
from core.size_extract import extract_size_info, extract_prefecture, PREFECTURES
from core.history import save_history, list_history, load_history

_ICON_PATH = Path(__file__).parent / "77fb3257-fbd1-42b8-adf9-94b19e8812fe.png"
st.set_page_config(
    page_title="中古11サイト横断リサーチ",
    layout="wide",
    page_icon=str(_ICON_PATH) if _ICON_PATH.exists() else "🔎",
)

# モバイル対応CSS: 狭い画面で columns を自動的に縦積みにし、画像と文字を読みやすく
st.markdown("""
<style>
@media (max-width: 768px) {
    /* メイン領域のパディング縮小 */
    .block-container { padding-left: 0.5rem !important; padding-right: 0.5rem !important; padding-top: 1rem !important; }
    /* カード内画像のサイズ調整 */
    [data-testid="stImage"] img { max-width: 100% !important; height: auto !important; }
    /* h3 タイトル小さく */
    h3 { font-size: 1.1rem !important; line-height: 1.3 !important; }
    /* メトリックフォント小さく */
    [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.7rem !important; }
}
/* 全体: カード間の余白を少し詰める */
[data-testid="stVerticalBlockBorderWrapper"] { margin-bottom: 0.5rem; }
</style>
""", unsafe_allow_html=True)

st.title("🔎 中古サイト横断リサーチ")
st.caption("型番を入れるとヤフオク・メルカリ・ジモティー他を横断検索 → 安い順に表示")

SHIPPING_SIZES = [60, 80, 100, 120, 140, 160, 170, 180, 200]

ALL_SITES = [
    "ヤフオク", "ハードオフ", "ジモティー", "セカンドストリート",
    "駿河屋", "ブックオフ", "メルカリ", "ラクマ", "PayPayフリマ",
    "キタムラ",
]

with st.sidebar:
    st.header("🔍 検索")
    keyword = st.text_input("型番", value="Panasonic NR-B18C2", placeholder="例: PSP-3000")

    with st.expander("🌐 検索サイト選択", expanded=False):
        # 初期化: 各サイトのチェック状態がなければ全ONで初期化
        for s in ALL_SITES:
            if f"site_{s}" not in st.session_state:
                st.session_state[f"site_{s}"] = True

        def _toggle_all():
            # 現在全てONなら全OFF、それ以外は全ON
            all_on = all(st.session_state.get(f"site_{s}", True) for s in ALL_SITES)
            for s in ALL_SITES:
                st.session_state[f"site_{s}"] = not all_on

        st.button("全選択 / 全解除", on_click=_toggle_all, use_container_width=True)
        selected_sites = []
        cols_sites = st.columns(2)
        for i, site_name in enumerate(ALL_SITES):
            with cols_sites[i % 2]:
                checked = st.checkbox(site_name, key=f"site_{site_name}")
                if checked:
                    selected_sites.append(site_name)

    exclude_text = st.text_area(
        "除外ワード（カンマ・改行で区切り）",
        value="ジャンク",
        height=120,
        help="この単語が商品名/説明に含まれる商品は除外。ひらがな・カタカナ・大小文字は同一視（例:「ジャンク」で「じゃんく」「ジャンク品」もヒット）",
    )
    exclude_words = [w.strip() for w in exclude_text.replace(",", "\n").splitlines() if w.strip()]
    _site_count = len(selected_sites) if selected_sites else len(ALL_SITES)
    run_btn = st.button(f"🔍 検索する（{_site_count}サイト横断）", type="primary", use_container_width=True)

    st.divider()
    st.header("💰 販売価格 → 利益試算")
    sell_price = st.number_input(
        "販売価格 (¥)", min_value=0, value=0, step=500,
        help="入力すると各商品カードに「利益見込み」がリアルタイム表示されます",
    )

    st.divider()
    st.header("📐 商品サイズ補完")
    st.caption("検索結果のサイズが説明文から拾えない時に一括指定")
    override_size = st.selectbox(
        "宅急便サイズ（共通指定）",
        ["自動判定", "60", "80", "100", "120", "140", "160", "170", "180", "200"],
        index=0,
    )
    override_3sides = st.number_input(
        "3辺合計cm（家財便ランク用）", min_value=0, max_value=400, value=0, step=10,
        help="冷蔵庫180Lなら約230cm目安",
    )

    st.divider()
    st.header("📦 送料計算ツール")
    st.caption("3辺合計を入れると宅急便サイズと家財便ランクが自動判定")
    calc_from = st.selectbox("発送元都道府県", PREFECTURES, index=PREFECTURES.index("東京都"))
    calc_to = st.selectbox("発送先都道府県", PREFECTURES, index=PREFECTURES.index("東京都"), key="calc_to")
    calc_3sides = st.slider("3辺合計(cm)", min_value=40, max_value=350, value=100, step=5)

    def _3sides_to_size_code(s3):
        for s in SHIPPING_SIZES:
            if s3 <= s:
                return s
        return SHIPPING_SIZES[-1] + 1

    derived_size = _3sides_to_size_code(calc_3sides)
    if derived_size > 200:
        st.caption(f"📏 3辺合計{calc_3sides}cm → 宅急便: 200超（取扱不可）")
    else:
        st.caption(f"📏 3辺合計{calc_3sides}cm → 宅急便: **{derived_size}サイズ**")

    if calc_from and calc_to:
        with st.expander("💴 4社送料試算", expanded=True):
            quote = estimate_all_carriers(
                calc_from, calc_to,
                size=min(derived_size, 200),
                sum_3sides_cm=calc_3sides,
            )
            for carrier, info in quote.items():
                if info["price"] is not None:
                    st.metric(carrier, f"¥{info['price']:,}", info["label"])
                else:
                    st.markdown(f"**{carrier}**: {info.get('note', '不可')}")

    st.divider()
    st.header("📦 メルカリ便 送料計算")
    st.caption("配送方法とサイズを選ぶと料金が表示されます（公式・全国一律）")

    _method_list = mercari_methods()
    _method_labels = {m["key"]: m["label"] for m in _method_list}
    _method_groups = {m["key"]: m["group"] for m in _method_list}
    method_key = st.selectbox(
        "配送方法", options=[m["key"] for m in _method_list],
        format_func=lambda k: _method_labels[k], key="mercari_method_key",
    )
    st.caption(f"📂 {_method_groups[method_key]}")

    _opts = mercari_size_options(method_key)
    _spec = mercari_spec(method_key)

    if len(_opts) == 1 and _opts[0]["size"] == "regulation":
        # 定額方式: サイズ選択不要
        opt = _opts[0]
        box_fee = _spec.get("box_fee") or 0
        total = opt["price"] + box_fee
        st.metric(_spec["name"], f"¥{total:,}", opt["label"])
        if box_fee:
            st.caption(f"内訳: 送料 ¥{opt['price']:,} + 専用箱 ¥{box_fee}（{_spec.get('note', '')}）")
        else:
            st.caption(_spec.get("note", ""))
    else:
        # サイズ階層方式（宅急便・ゆうパック・たのメル便）
        size_idx = st.selectbox(
            "サイズ",
            options=list(range(len(_opts))),
            format_func=lambda i: f"{_opts[i]['label']} → ¥{_opts[i]['price']:,}",
            key=f"mercari_size_{method_key}",
        )
        opt = _opts[size_idx]
        st.metric(_spec["name"], f"¥{opt['price']:,}", opt["label"])
        st.caption(_spec.get("note", ""))

    st.divider()
    st.header("📜 検索履歴")
    history = list_history()
    if not history:
        st.caption("まだ履歴はありません")
    else:
        for idx, h in enumerate(history[:15]):
            label = f"{h['keyword']} ({h['count']}件) - {h['datetime'][:16]}"
            def _load_h(file=h["file"], kw=h["keyword"]):
                items = load_history(file)
                st.session_state["items"] = items
                st.session_state["keyword"] = kw
                st.session_state["site_filter"] = None
            st.button(label, key=f"h_sb_{idx}_{h['file']}", on_click=_load_h, use_container_width=True)


def estimate_item_shipping(item: Item, override_size=None, override_3sides=None, dest_pref="東京都"):
    pref = extract_prefecture(item.location) or extract_prefecture(item.description) or extract_prefecture(item.title)
    if not pref:
        return None, None, None
    sz_auto, s3_auto = extract_size_info(item.title, item.description)
    sz = override_size if override_size else sz_auto
    s3 = override_3sides if override_3sides else s3_auto
    if sz is None and s3 is None:
        return pref, None, {}
    quote = estimate_all_carriers(pref, dest_pref, size=sz, sum_3sides_cm=s3)
    return pref, (sz, s3), quote


def render_items(items, keyword: str):
    if not items:
        st.warning("販売中の該当商品が見つかりませんでした。")
        return

    site_counts = {}
    for it in items:
        site_counts[it.site] = site_counts.get(it.site, 0) + 1

    col1, col2, col3, col4, col5 = st.columns(5)
    prices = [i.price for i in items if i.price]
    col1.metric("総件数", f"{len(items)}件")
    col2.metric("最安", f"¥{min(prices):,}")
    col3.metric("最高", f"¥{max(prices):,}")
    col4.metric("平均", f"¥{sum(prices)//len(prices):,}")
    col5.metric("中央値", f"¥{sorted(prices)[len(prices)//2]:,}")

    # Excel ダウンロードボタン (オンデマンド)
    cols_dl = st.columns([5, 2])
    with cols_dl[1]:
        buf = io.BytesIO()
        rows = []
        for rank, it in enumerate(items, start=1):
            rows.append({
                "順位": rank, "サイト": it.site, "タイトル": it.title,
                "価格": it.price, "状態": it.condition or "",
                "発送元": it.location or "",
                "画像URL": it.image_url or "", "商品リンク": it.item_url,
            })
        pd.DataFrame(rows).to_excel(buf, index=False, sheet_name="ranking")
        buf.seek(0)
        st.download_button(
            "📥 この結果をExcelダウンロード",
            data=buf.getvalue(),
            file_name=f"{keyword.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.subheader("📊 サイト別件数（クリックで絞り込み）")
    selected_site = st.session_state.get("site_filter")

    # 列数を常に8固定にすることで、絞り込み変更時のDOM不整合(removeChildエラー)を軽減
    SLOT_COUNT = 8
    site_btn_cols = st.columns(SLOT_COUNT)
    sorted_sites = sorted(site_counts.items(), key=lambda x: -x[1])
    slots = [("__all__", len(items))] + sorted_sites
    for slot_idx in range(SLOT_COUNT):
        with site_btn_cols[slot_idx]:
            if slot_idx < len(slots):
                site_id, count = slots[slot_idx]
                if site_id == "__all__":
                    is_sel = selected_site is None
                    label = f"{'✅ ' if is_sel else ''}全サイト ({count})"
                    st.button(
                        label, key=f"flt_slot_{slot_idx}",
                        use_container_width=True,
                        type="primary" if is_sel else "secondary",
                        on_click=lambda: st.session_state.update(site_filter=None),
                    )
                else:
                    is_sel = selected_site == site_id
                    label = f"{'✅ ' if is_sel else ''}{site_id} ({count})"
                    st.button(
                        label, key=f"flt_slot_{slot_idx}",
                        use_container_width=True,
                        type="primary" if is_sel else "secondary",
                        on_click=lambda s=site_id: st.session_state.update(site_filter=s),
                    )
            else:
                st.empty()

    if selected_site:
        items_view = [it for it in items if it.site == selected_site]
        st.caption(f"🔍 絞り込み中: {selected_site} ({len(items_view)}件)")
    else:
        items_view = items

    st.subheader("🏆 ランキング（安い順）")
    avg = sum(prices) / len(prices)

    for rank, it in enumerate(items_view, start=1):
        with st.container(border=True):
            cols = st.columns([1, 5, 2])
            with cols[0]:
                if it.image_url:
                    try:
                        st.image(it.image_url, width=140)
                    except Exception:
                        st.caption("画像読込失敗")
                else:
                    st.caption("画像なし")
            with cols[1]:
                rank_color = "🟢" if rank <= 3 else "🥈" if rank <= 10 else "🥉" if rank <= 20 else "・"
                st.markdown(f"**{rank_color} {rank}位 / {it.site}**")
                st.markdown(f"### {it.title or '(タイトル不明)'}")

                # 発送方法・発送サイズをタイトル直下に
                ovr_sz = int(override_size) if override_size != "自動判定" else None
                ovr_s3 = override_3sides if override_3sides > 0 else None
                pref, sz_info, quote = estimate_item_shipping(it, override_size=ovr_sz, override_3sides=ovr_s3)

                shipping_info_parts = []
                if it.shipping_method:
                    shipping_info_parts.append(f"📮 **発送方法**: {it.shipping_method}")
                if sz_info and sz_info[0]:
                    sz_text = f"{sz_info[0]}サイズ"
                    if sz_info[1] and sz_info[1] != sz_info[0]:
                        sz_text += f" (3辺合計~{sz_info[1]}cm)"
                    shipping_info_parts.append(f"📏 **発送サイズ**: {sz_text}")
                if shipping_info_parts:
                    st.markdown(" ｜ ".join(shipping_info_parts))

                if it.description:
                    st.caption(it.description[:200])
                badges = []
                if it.price and it.price < avg * 0.7:
                    badges.append("🔥 **狙い目**")
                elif it.price and it.price > avg * 1.3:
                    badges.append("💸 割高")
                badges.append(f"🏷️ {it.condition or '中古'}")
                if it.location:
                    badges.append(f"📍 {it.location}")
                st.markdown(" ｜ ".join(badges))
                if pref and quote:
                    parts = []
                    for carrier, info in quote.items():
                        if info["price"]:
                            parts.append(f"**{carrier}**: ¥{info['price']:,} ({info['label']})")
                    if parts:
                        st.markdown(f"🚚 **{pref}発 → 東京着（推定）**: " + " ｜ ".join(parts))
                elif pref:
                    st.caption(f"🚚 {pref}発（サイズ未判定で送料不明）")
            with cols[2]:
                st.markdown(f"## ¥{it.price:,}" if it.price else "## 価格不明")
                # 利益試算
                if sell_price > 0 and it.price:
                    profit = sell_price - it.price
                    profit_pct = (profit / sell_price * 100) if sell_price else 0
                    color = "🟢" if profit > 0 else "🔴"
                    st.markdown(
                        f"{color} **利益**: ¥{profit:,} ({profit_pct:.0f}%)\n\n"
                        f"<small>売価¥{sell_price:,} − 仕入¥{it.price:,}</small>",
                        unsafe_allow_html=True,
                    )
                st.markdown(f"[🛒 商品ページを開く]({it.item_url})")


# === メイン処理 ===
if run_btn and keyword:
    progress = st.empty()
    progress.info(f"「{keyword}」で{_site_count}サイトを検索中... 全件取得モードのため数分かかります")
    with st.spinner("検索実行中..."):
        sites_arg = selected_sites if selected_sites else None
        items = run_async_in_thread(aggregate(keyword, exclude_words=exclude_words, sites=sites_arg))
    progress.empty()

    # メルカリ Apify の上限到達を検知して通知
    try:
        from scrapers.mercari import last_status as _mercari_status
        if _mercari_status.get("rate_limited"):
            st.warning("⚠️ メルカリは今月の Apify 無料枠（$5）を使い切ったため取得できませんでした。来月初に自動的に再開されます。")
        elif _mercari_status.get("error_message") and not any(it.site == "メルカリ" for it in items):
            st.info(f"ℹ️ メルカリ取得不可: {_mercari_status['error_message']}")
    except Exception:
        pass

    if items:
        save_history(keyword, items)
    st.session_state["items"] = items
    st.session_state["keyword"] = keyword
    st.session_state["site_filter"] = None
    st.success(f"✅ 検索完了: {len(items)}件取得")

if "items" in st.session_state:
    # 履歴ロード時にも除外ワードをリアルタイムで適用
    items_filtered = filter_items(st.session_state["items"], exclude_words)
    if exclude_words:
        excluded_count = len(st.session_state["items"]) - len(items_filtered)
        if excluded_count > 0:
            st.caption(f"🚫 除外ワード適用: {' / '.join(exclude_words)} → {excluded_count}件除外")
    render_items(items_filtered, st.session_state.get("keyword", keyword))
else:
    st.info("👈 サイドバーで型番を入れて「検索する」を押すか、下の履歴から過去の検索を呼び出してください")
    history = list_history()
    if history:
        st.markdown("---")
        st.subheader("📜 履歴から呼び出し")
        for idx, h in enumerate(history[:20]):
            cols = st.columns([4, 1, 1, 1, 2])
            cols[0].markdown(f"**{h['keyword']}**")
            cols[1].markdown(f"{h['count']}件")
            cols[2].markdown(f"¥{h['min_price']:,}" if h.get("min_price") else "-")
            cols[3].markdown(h["datetime"][:10])
            with cols[4]:
                def _load_h2(file=h["file"], kw=h["keyword"]):
                    items = load_history(file)
                    st.session_state["items"] = items
                    st.session_state["keyword"] = kw
                    st.session_state["site_filter"] = None
                st.button("読み込み", key=f"h_main_{idx}_{h['file']}", on_click=_load_h2, use_container_width=True)
