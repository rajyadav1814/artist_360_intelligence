import streamlit as st

def custom_selectbox(label: str, options: list, index: int = 0, key: str = None) -> str:
    """Render a custom HTML select with theme support for both dark and light modes."""
    is_dark = st.session_state.get("dark_mode", False)
    
    # Initialize session state if needed
    if key and key not in st.session_state:
        st.session_state[key] = options[index] if index < len(options) else options[0]
    
    # Get current value
    current_value = st.session_state.get(key, options[index] if index < len(options) else options[0])
    
    # Build option HTML
    options_html = ""
    for opt in options:
        selected = "selected" if opt == current_value else ""
        options_html += f'<option value="{opt}" {selected}>{opt}</option>'
    
    # Colors based on theme
    bg_color = "#FFFFFF" if not is_dark else "#161b27"
    text_color = "#1A1A1A" if not is_dark else "#e2e8f0"
    border_color = "#E9ECF2" if not is_dark else "rgba(41,52,85,.7)"
    hover_bg = "#F8F9FB" if not is_dark else "#1a2035"
    
    html_code = f"""
    <style>
    .custom-select-{key} {{
        width: 100%;
        padding: 8px 12px;
        border: 1px solid {border_color};
        border-radius: 8px;
        background: {bg_color};
        color: {text_color};
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell';
    }}
    .custom-select-{key}:hover {{
        background: {hover_bg};
        border-color: rgba(108, 92, 231, 0.3);
    }}
    .custom-select-{key}:focus {{
        outline: none;
        border-color: rgba(108, 92, 231, 0.6);
        box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.1);
    }}
    .custom-select-{key} option {{
        background: {bg_color};
        color: {text_color};
        padding: 8px 12px;
    }}
    </style>
    <label style="display: block; font-size: 14px; font-weight: 600; margin-bottom: 6px; color: {text_color}; letter-spacing: 0.02em;">
        {label}
    </label>
    <select class="custom-select-{key}" id="{key}" onchange="document.querySelector('input[name=\'{key}_val\']').value = this.value">
        {options_html}
    </select>
    <input type="hidden" name="{key}_val" value="{current_value}">
    """
    
    st.markdown(html_code, unsafe_allow_html=True)
    
    # For simplicity with Streamlit, we'll update session state through a form pattern
    # Return the current value - user needs to re-run to get new value
    return current_value
