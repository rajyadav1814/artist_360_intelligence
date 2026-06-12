import streamlit as st

def custom_selectbox(label: str, options: list, index: int = 0, key: str = None) -> str:
    """Render a selectbox using standard Streamlit that works with Python backend."""
    is_dark = st.session_state.get("dark_mode", False)
    
    # Colors based on theme for injection
    bg_color = "#FFFFFF" if not is_dark else "#161b27"
    text_color = "#1A1A1A" if not is_dark else "#e2e8f0"
    border_color = "#E9ECF2" if not is_dark else "rgba(41,52,85,.7)"
    hover_bg = "#F8F9FB" if not is_dark else "#1a2035"
    
    # Inject specific CSS for this selectbox if possible, though Streamlit's 
    # [data-baseweb="select"] is already styled in the main app CSS.
    # We add a small targeted style block for extra polish.
    if key:
        st.markdown(f"""
        <style>
        /* Selectbox Container Style */
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
            background-color: {bg_color} !important;
            border: 1px solid {border_color} !important;
            border-radius: 8px !important;
            color: {text_color} !important;
            font-size: 14px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease !important;
            cursor: pointer !important;
            min-height: 40px !important;
        }}
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover {{
            background-color: {hover_bg} !important;
            border-color: rgba(108, 92, 231, 0.3) !important;
        }}
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within {{
            border-color: rgba(108, 92, 231, 0.6) !important;
            box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.1) !important;
        }}
        /* Label Style */
        div[data-testid="stSelectbox"] label p {{
            color: {text_color} !important;
            font-size: 14px !important;
            font-weight: 600 !important;
            letter-spacing: 0.02em !important;
        }}
        /* Inner Text Selected Value */
        div[data-testid="stSelectbox"] div[data-baseweb="select"] div[class*="singleValue"] {{
            color: {text_color} !important;
            font-size: 14px !important;
            font-weight: 500 !important;
        }}
        /* Dropdown options styling */
        div[data-baseweb="popover"] div[data-baseweb="menu"] {{
            background-color: {bg_color} !important;
            border: 1px solid {border_color} !important;
            border-radius: 8px !important;
            padding: 4px !important;
        }}
        div[data-baseweb="popover"] li[role="option"] {{
            background-color: {bg_color} !important;
            color: {text_color} !important;
            font-size: 14px !important;
            padding: 8px 12px !important;
            border-radius: 4px !important;
        }}
        div[data-baseweb="popover"] li[role="option"]:hover,
        div[data-baseweb="popover"] li[role="option"][aria-selected="true"] {{
            background-color: {hover_bg} !important;
            color: {text_color} !important;
        }}
        </style>
        """, unsafe_allow_html=True)

    # Use native st.selectbox to ensure selection actually updates python state and triggers a rerun
    return st.selectbox(label, options, index=index, key=key)

def custom_multiselect(label: str, options: list, default: list = None, key: str = None, **kwargs) -> list:
    """Render a multiselect using standard Streamlit with custom theme injection."""
    is_dark = st.session_state.get("dark_mode", False)
    
    # Colors based on theme for injection
    bg_color = "#FFFFFF" if not is_dark else "#161b27"
    text_color = "#1A1A1A" if not is_dark else "#e2e8f0"
    border_color = "#E9ECF2" if not is_dark else "rgba(41,52,85,.7)"
    hover_bg = "#F8F9FB" if not is_dark else "#1a2035"
    tag_bg = "rgba(251,113,133,0.15)" if not is_dark else "rgba(251,113,133,0.15)"
    tag_text = "#be123c" if not is_dark else "#fb7185"
    
    if key:
        st.markdown(f"""
        <style>
        /* MultiSelect Container Style */
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {{
            background-color: {bg_color} !important;
            border: 1px solid {border_color} !important;
            border-radius: 8px !important;
            color: {text_color} !important;
            font-size: 14px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease !important;
            cursor: pointer !important;
            min-height: 40px !important;
        }}
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div:hover {{
            background-color: {hover_bg} !important;
            border-color: rgba(108, 92, 231, 0.3) !important;
        }}
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div:focus-within {{
            border-color: rgba(108, 92, 231, 0.6) !important;
            box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.1) !important;
        }}
        /* Label Style */
        div[data-testid="stMultiSelect"] label p {{
            color: {text_color} !important;
            font-size: 14px !important;
            font-weight: 600 !important;
            letter-spacing: 0.02em !important;
        }}
        /* Selected Tags */
        div[data-testid="stMultiSelect"] span[data-baseweb="tag"] {{
            background-color: {tag_bg} !important;
            color: {tag_text} !important;
            border-radius: 6px !important;
            border: 1px solid rgba(251, 113, 133, 0.3) !important;
        }}
        div[data-testid="stMultiSelect"] span[data-baseweb="tag"] span {{
            color: {tag_text} !important;
        }}
        /* Inner Text / Placeholder for multiselect */
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] input {{
            color: {text_color} !important;
        }}
        /* Dropdown options styling */
        div[data-baseweb="popover"] div[data-baseweb="menu"] {{
            background-color: {bg_color} !important;
            border: 1px solid {border_color} !important;
            border-radius: 8px !important;
            padding: 4px !important;
        }}
        div[data-baseweb="popover"] li[role="option"] {{
            background-color: {bg_color} !important;
            color: {text_color} !important;
            font-size: 14px !important;
            padding: 8px 12px !important;
            border-radius: 4px !important;
        }}
        div[data-baseweb="popover"] li[role="option"]:hover,
        div[data-baseweb="popover"] li[role="option"][aria-selected="true"] {{
            background-color: {hover_bg} !important;
            color: {text_color} !important;
        }}
        </style>
        """, unsafe_allow_html=True)
        
    return st.multiselect(label, options, default=default, key=key, **kwargs)
