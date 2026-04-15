import streamlit as st
import pandas as pd
from html import escape
from src.ui.components import fmt_short

def render_debut_artist_chart(leaderboard: pd.DataFrame) -> None:
    if leaderboard.empty:
        st.warning("No artist data available yet.")
        return

    sorted_artists = leaderboard.sort_values("rank").dropna(subset=["name", "rank"]).copy()
    
    sorted_artists["rank"] = sorted_artists["rank"].astype(int)
    sorted_artists["display_label"] = sorted_artists["name"]
    artist_options = sorted_artists["display_label"].tolist()
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 2])
    with col1:
        selected_label = st.selectbox(
            "🎤 Select an Artist",
            artist_options,
            index=0 if artist_options else None,
        )
    
    if not selected_label:
        st.info("Please select an artist from the dropdown above.")
        return
    
    selected_artist = selected_label.split(" - ", 1)[1] if " - " in selected_label else selected_label
    
    artist_data = leaderboard[leaderboard["name"] == selected_artist]
    
    if artist_data.empty:
        st.warning(f"No data found for {selected_artist}.")
        return
    
    row = artist_data.iloc[0]
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        rank_val = int(row.get("rank")) if pd.notna(row.get("rank")) else 0
        st.metric("📊 Current Rank", f"{rank_val}")
    with kpi2:
        songs_val = row.get("songs_count")
        st.metric("🎵 Songs", int(songs_val) if pd.notna(songs_val) else 0)
    with kpi3:
        albums_val = row.get("albums_count")
        st.metric("💿 Albums", int(albums_val) if pd.notna(albums_val) else 0)
    with kpi4:
        countries_val = row.get("countries_count")
        st.metric("🌎 LATAM Countries", int(countries_val) if pd.notna(countries_val) else 0)
    
    kpi5, kpi6, kpi7, kpi8 = st.columns(4)
    with kpi5:
        ml_val = row.get("monthly_listeners")
        st.metric("👥 Monthly Listeners", fmt_short(ml_val) if pd.notna(ml_val) else "—")
    with kpi6:
        peak_val = row.get("peak_listeners")
        st.metric("🚀 Peak Listeners", fmt_short(peak_val) if pd.notna(peak_val) else "—")
    with kpi7:
        points_val = row.get("total_points")
        st.metric("⭐ Total Points", fmt_short(points_val) if pd.notna(points_val) else "—")
    with kpi8:
        trend_change = str(row.get("rank_change") or "=").strip()
        st.metric("📈 Trend", trend_change)

    st.markdown("<br>", unsafe_allow_html=True)
    
    with st.expander("📋 Artist Profile Details", expanded=True):
        profile_title = str(row.get("page_title") or "").strip()
        profile_snapshot = str(row.get("snapshot_text") or "").strip()
        
        if profile_title:
            st.markdown(f"#### 🪪 {escape(profile_title)}")
        if profile_snapshot:
            st.caption(profile_snapshot)
        
        meta_left, meta_right = st.columns(2)
        with meta_left:
            st.markdown(f"**🌍 Top Country:** {escape(str(row.get('display_country') or '—'))}")
            st.markdown(f"**🎵 Top Song:** {escape(str(row.get('top_song') or '—'))}")
    
    songs_items = [item.strip() for item in str(row.get("top_songs") or "").split("\n") if item.strip()]
    albums_items = [item.strip() for item in str(row.get("top_albums") or "").split("\n") if item.strip()]
    countries_items = [item.strip() for item in str(row.get("top_countries") or "").split("\n") if item.strip()]
    top_n_count = len(songs_items)

    with st.expander("🎵 Top Tracks, Albums & Countries", expanded=True):
        col_songs, col_albums, col_countries = st.columns(3)

        with col_songs:
            st.markdown(f"#### 🎵 Top {top_n_count} Tracks" if top_n_count else "#### 🎵 Top Songs")
            if songs_items:
                for idx, item in enumerate(songs_items, start=1):
                    st.markdown(f"{idx}. {escape(item)}")
            else:
                st.caption("No songs available.")

        with col_albums:
            st.markdown("#### 💿 Top Albums")
            if albums_items:
                for idx, item in enumerate(albums_items, start=1):
                    st.markdown(f"{idx}. {escape(item)}")
            else:
                st.caption("No albums available.")

        with col_countries:
            st.markdown("#### 🗺️ Top Countries")
            if countries_items:
                for idx, item in enumerate(countries_items, start=1):
                    st.markdown(f"{idx}. {escape(item)}")
            else:
                st.caption("No countries available.")
    
    with st.expander("📊 Performance Summary", expanded=True):
        songs_s = row.get("songs_count")
        albums_s = row.get("albums_count")
        countries_s = row.get("countries_count")
        summary_data = {
            "Metric": ["Rank", "Monthly Listeners", "Peak Listeners", "Songs", "Albums", "LATAM Countries", "Total Points"],
            "Value": [
                str(rank_val),
                str(fmt_short(row.get("monthly_listeners"))) if pd.notna(row.get("monthly_listeners")) else "—",
                str(fmt_short(row.get("peak_listeners"))) if pd.notna(row.get("peak_listeners")) else "—",
                str(int(songs_s)) if pd.notna(songs_s) else "0",
                str(int(albums_s)) if pd.notna(albums_s) else "0",
                str(int(countries_s)) if pd.notna(countries_s) else "0",
                str(fmt_short(row.get("total_points"))) if pd.notna(row.get("total_points")) else "—",
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
