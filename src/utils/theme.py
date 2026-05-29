"""
Theme management module for Artist 360° Intelligence.

Provides light/dark mode switching with:
- Streamlit session state management
- localStorage persistence
- System preference detection (prefers-color-scheme)
- Smooth CSS transitions
- Full CSS variable sets for both themes
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as st_components

# ── CSS custom properties for both themes ──────────────────────────────────

DARK_CSS_VARS = {
    # Background layers
    "--bg": "#050816",
    "--bg-gradient-start": "#050816",
    "--bg-gradient-mid": "#081322",
    "--bg-gradient-end": "#07111f",
    # Surfaces
    "--surface": "#0b1220",
    "--surface2": "#111a2e",
    "--surface3": "#17233a",
    "--surface-card": "linear-gradient(180deg, rgba(17,26,46,.96), rgba(11,18,32,.98))",
    "--surface-kpi": "#111827",
    "--surface-table-header": "rgba(9,17,39,0.95)",
    "--surface-table-row-alt": "rgba(255,255,255,.02)",
    "--surface-header-box": "linear-gradient(120deg, rgba(7,14,28,.92) 0%, rgba(9,18,36,.96) 62%, rgba(12,41,58,.88) 100%)",
    # Borders
    "--border": "#23314f",
    "--border-light": "rgba(41,52,85,.72)",
    "--border-card": "rgba(73, 104, 160, 0.38)",
    "--border-kpi": "#1e2d47",
    # Accent colors
    "--accent": "#22d3ee",
    "--accent2": "#34d399",
    "--accent3": "#f59e0b",
    "--accent-gradient": "linear-gradient(90deg, #22d3ee, #34d399)",
    "--accent-blue": "#4f8ef7",
    "--accent-purple": "#7c5cfc",
    "--accent-brand": "linear-gradient(135deg, #4f8ef7 0%, #7c5cfc 55%, #22d3a0 100%)",
    "--accent-blue-rgb": "79, 142, 247",
    # Text colors
    "--text": "#f8fbff",
    "--text2": "#a2b0d0",
    "--text3": "#dbe4ff",
    "--text-heading": "#ffffff",
    "--text-kpi-gradient": "linear-gradient(135deg, #eef2ff 0%, #97a3c5 100%)",
    # Status colors
    "--success": "#22c55e",
    "--success-bg": "rgba(34,211,160,.12)",
    "--success-text": "#8ff0cf",
    "--warning": "#fbbf24",
    "--warning-bg": "rgba(245,166,35,.14)",
    "--warning-text": "#ffd089",
    "--danger": "#fb7185",
    "--danger-bg": "rgba(232,69,69,.14)",
    "--danger-text": "#ff9c9c",
    "--info-bg": "rgba(79,142,247,.16)",
    "--info-text": "#b7d4ff",
    "--up-bg": "rgba(34,211,160,.14)",
    "--up-text": "#8ff0cf",
    "--down-bg": "rgba(232,69,69,.14)",
    "--down-text": "#ff9c9c",
    # Shadows
    "--shadow-sm": "0 14px 30px rgba(3, 9, 22, 0.35)",
    "--shadow-md": "0 18px 42px rgba(0,0,0,.24)",
    "--shadow-lg": "0 25px 60px rgba(0,0,0,0.8)",
    "--shadow-hover": "0 18px 42px rgba(0,0,0,.35)",
    # Tooltip
    "--tooltip-bg": "rgba(13, 20, 38, 0.99)",
    "--tooltip-border": "rgba(79, 142, 247, 0.4)",
    # Misc
    "--scrollbar-thumb": "rgba(79, 142, 247, 0.4)",
    "--graph-card-bg": "linear-gradient(180deg, rgba(17, 28, 47, 0.92), rgba(10, 17, 31, 0.95))",
    "--loader-bg": "#07101f",
}

LIGHT_CSS_VARS = {
    # Background layers
    "--bg": "#f8fafc",
    "--bg-gradient-start": "#f0f4f8",
    "--bg-gradient-mid": "#eef2f6",
    "--bg-gradient-end": "#e8edf2",
    # Surfaces
    "--surface": "#ffffff",
    "--surface2": "#f1f5f9",
    "--surface3": "#e2e8f0",
    "--surface-card": "linear-gradient(180deg, rgba(255,255,255,.98), rgba(248,250,252,.99))",
    "--surface-kpi": "#ffffff",
    "--surface-table-header": "rgba(241,245,249,0.95)",
    "--surface-table-row-alt": "rgba(0,0,0,.02)",
    "--surface-header-box": "linear-gradient(120deg, rgba(255,255,255,.95) 0%, rgba(248,250,252,.98) 62%, rgba(240,244,248,.92) 100%)",
    # Borders
    "--border": "#d1d5db",
    "--border-light": "rgba(0,0,0,.1)",
    "--border-card": "rgba(148,163,184,0.38)",
    "--border-kpi": "#d1d5db",
    # Accent colors
    "--accent": "#2563eb",
    "--accent2": "#059669",
    "--accent3": "#d97706",
    "--accent-gradient": "linear-gradient(90deg, #2563eb, #059669)",
    "--accent-blue": "#2563eb",
    "--accent-purple": "#7c3aed",
    "--accent-brand": "linear-gradient(135deg, #2563eb 0%, #7c3aed 55%, #059669 100%)",
    "--accent-blue-rgb": "37, 99, 235",
    # Text colors
    "--text": "#1e293b",
    "--text2": "#64748b",
    "--text3": "#334155",
    "--text-heading": "#0f172a",
    "--text-kpi-gradient": "linear-gradient(135deg, #1e293b 0%, #64748b 100%)",
    # Status colors
    "--success": "#16a34a",
    "--success-bg": "rgba(22,163,74,.12)",
    "--success-text": "#15803d",
    "--warning": "#d97706",
    "--warning-bg": "rgba(217,119,6,.14)",
    "--warning-text": "#b45309",
    "--danger": "#dc2626",
    "--danger-bg": "rgba(220,38,38,.14)",
    "--danger-text": "#b91c1c",
    "--info-bg": "rgba(37,99,235,.14)",
    "--info-text": "#1d4ed8",
    "--up-bg": "rgba(22,163,74,.14)",
    "--up-text": "#15803d",
    "--down-bg": "rgba(220,38,38,.14)",
    "--down-text": "#b91c1c",
    # Shadows
    "--shadow-sm": "0 4px 12px rgba(0, 0, 0, 0.08)",
    "--shadow-md": "0 8px 24px rgba(0,0,0,.1)",
    "--shadow-lg": "0 16px 48px rgba(0,0,0,0.15)",
    "--shadow-hover": "0 12px 32px rgba(0,0,0,.15)",
    # Tooltip
    "--tooltip-bg": "rgba(255, 255, 255, 0.99)",
    "--tooltip-border": "rgba(37, 99, 235, 0.4)",
    # Misc
    "--scrollbar-thumb": "rgba(37, 99, 235, 0.3)",
    "--graph-card-bg": "linear-gradient(180deg, rgba(255,255,255,.95), rgba(248,250,252,.97))",
    "--loader-bg": "#f0f4f8",
}


def get_css_vars_block(theme: str) -> str:
    """Return CSS variable declarations for the given theme."""
    vars_map = DARK_CSS_VARS if theme == "dark" else LIGHT_CSS_VARS
    lines = "\n".join(f"    {k}: {v};" for k, v in vars_map.items())
    return lines


def init_theme() -> None:
    """
    Initialize theme state in session.
    Must be called once at app startup after set_page_config.
    Priority: saved preference → system preference → dark (default).
    """
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"  # fallback

    if "theme_initialized" not in st.session_state:
        st.session_state.theme_initialized = True


def get_theme_initialization_script() -> str:
    """
    Returns a JavaScript snippet that:
    1. Reads the saved theme from localStorage
    2. Falls back to system preference (prefers-color-scheme)
    3. Stores the resolved theme back into session via Streamlit event
    4. Applies the theme class to <html> element
    """
    return """
    <script>
    (function() {
        try {
            // Read saved preference
            let theme = localStorage.getItem('artist360_theme');
            
            // Check system preference if no saved preference
            if (!theme || theme === 'system') {
                const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                theme = prefersDark ? 'dark' : 'light';
            }
            
            // Validate
            if (theme !== 'dark' && theme !== 'light') {
                theme = 'dark';
            }
            
            // Store in localStorage
            localStorage.setItem('artist360_theme', theme);
            
            // Apply theme to document
            document.documentElement.setAttribute('data-theme', theme);
            document.body.setAttribute('data-theme', theme);
            
            // Listen for system preference changes
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
                const saved = localStorage.getItem('artist360_theme');
                if (saved === 'system') {
                    const newTheme = e.matches ? 'dark' : 'light';
                    document.documentElement.setAttribute('data-theme', newTheme);
                    document.body.setAttribute('data-theme', newTheme);
                }
            });
        } catch(e) {
            console.warn('Theme initialization failed:', e);
        }
    })();
    </script>
    """


def get_theme_switcher_script() -> str:
    """
    JavaScript to toggle theme and persist to localStorage.
    Called when user clicks the toggle button.
    """
    return """
    <script>
    function toggleTheme() {
        const html = document.documentElement;
        const current = html.getAttribute('data-theme') || 'dark';
        const next = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        document.body.setAttribute('data-theme', next);
        localStorage.setItem('artist360_theme', next);
        // Trigger Streamlit rerun via custom event
        const event = new Event('theme-changed');
        window.dispatchEvent(event);
    }
    </script>
    """


def render_theme_toggle() -> None:
    """
    Render the theme toggle button in the sidebar.
    Must be called inside the `with st.sidebar:` block.
    Uses st_components.html() for JS persistence so <script> tags execute.
    """
    current = st.session_state.get("theme", "dark")

    # CSS for the toggle button
    st.markdown(
        f"""
        <style>
        .theme-toggle-container {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.6rem 0.85rem;
            margin: 0.5rem 0 0.25rem 0;
            border-radius: 12px;
            background: var(--surface2);
            border: 1px solid var(--border);
            transition: all 0.3s ease;
        }}
        .theme-toggle-container:hover {{
            border-color: var(--accent);
        }}
        .theme-toggle-label {{
            font-size: 0.82rem;
            font-weight: 700;
            color: var(--text2);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .theme-toggle-label .toggle-icon {{
            font-size: 1.1rem;
        }}
        .theme-toggle-btn {{
            display: flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            border: 1px solid var(--border);
            background: var(--surface);
            color: var(--text);
            font-size: 0.78rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
            min-width: 80px;
            justify-content: center;
        }}
        .theme-toggle-btn:hover {{
            background: rgba(var(--accent-blue-rgb), 0.1);
            border-color: var(--accent);
            transform: scale(1.03);
        }}
        .theme-toggle-btn:active {{
            transform: scale(0.95);
        }}
        .theme-toggle-btn .btn-icon {{
            font-size: 1rem;
            transition: transform 0.35s ease;
        }}
        .theme-toggle-btn:hover .btn-icon {{
            transform: rotate(15deg);
        }}
        </style>

        <div class="theme-toggle-container">
            <span class="theme-toggle-label">
                <span class="toggle-icon">🎨</span> Theme
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Use columns for the toggle button to handle rerun cleanly
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        is_dark = current == "dark"
        btn_label = "🌙 Dark" if is_dark else "☀️ Light"
        if st.button(
            btn_label,
            key="theme_toggle_btn",
            use_container_width=True,
            type="secondary",
        ):
            new_theme = "light" if is_dark else "dark"
            st.session_state.theme = new_theme
            # Save to localStorage and update data-theme attribute
            # Using st_components.html() so <script> tags actually execute
            save_js = f"""
            <script>
            try {{
                localStorage.setItem('artist360_theme', '{new_theme}');
                document.documentElement.setAttribute('data-theme', '{new_theme}');
                document.body.setAttribute('data-theme', '{new_theme}');
            }} catch(e) {{}}
            </script>
            """
            st_components.html(save_js, height=0, width=0)
            st.rerun()


def get_transition_css() -> str:
    """Return CSS for smooth theme transitions."""
    return """
    /* Smooth theme transitions */
    *, *::before, *::after {
        transition: background-color 0.35s cubic-bezier(0.4, 0, 0.2, 1),
                    border-color 0.3s cubic-bezier(0.4, 0, 0.2, 1),
                    color 0.3s cubic-bezier(0.4, 0, 0.2, 1),
                    box-shadow 0.3s cubic-bezier(0.4, 0, 0.2, 1),
                    fill 0.3s ease,
                    stroke 0.3s ease;
    }
    """


def inject_theme_js() -> None:
    """Inject JavaScript for theme initialization and persistence.
    Uses st_components.html() so that <script> tags are NOT stripped by Streamlit.
    """
    js = get_theme_initialization_script() + get_theme_switcher_script()
    st_components.html(js, height=0, width=0)


def apply_theme_css(theme: str = "dark") -> str:
    """
    Returns the complete theme CSS string with CSS variable definitions
    for both light and dark modes, plus all UI component styles.
    
    The `theme` param controls which set of CSS vars is applied to plain `:root`
    (used on initial render before JS sets data-theme on <html>).
    Uses `html[data-theme="..."]` selectors for JS-powered runtime switching.
    """
    dark_vars = get_css_vars_block("dark")
    light_vars = get_css_vars_block("light")
    initial_vars = dark_vars if theme == "dark" else light_vars

    return f"""
    <style>
    /* ── CSS Variable Definitions ──────────────────────────────────── */
    /* Initial theme based on session state (before JS runs) */
    :root {{
    {initial_vars}
    }}

    /* JS-powered theme switching via data-theme attribute */
    html[data-theme="dark"] {{
    {dark_vars}
    }}

    html[data-theme="light"] {{
    {light_vars}
    }}

    /* ── Smooth transitions ────────────────────────────────────────── */
    {get_transition_css()}

    /* ── Base App Styles ──────────────────────────────────────────── */
    @keyframes fadeIn {{
        from {{ opacity: 0; transform: translateY(10px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes slideIn {{
        from {{ opacity: 0; transform: translateX(-20px); }}
        to {{ opacity: 1; transform: translateX(0); }}
    }}
    @keyframes pulse {{
        0%, 100% {{ transform: scale(1); }}
        50% {{ transform: scale(1.05); }}
    }}
    @keyframes shimmer {{
        0% {{ background-position: -1000px 0; }}
        100% {{ background-position: 1000px 0; }}
    }}

    .stApp {{ 
        background:
            radial-gradient(circle at top left, rgba(var(--accent-blue-rgb),.16), transparent 26%),
            radial-gradient(circle at top right, rgba(52,211,153,.13), transparent 24%),
            linear-gradient(180deg, var(--bg-gradient-start) 0%, var(--bg-gradient-mid) 52%, var(--bg-gradient-end) 100%); 
        color: var(--text);
        animation: fadeIn 0.6s ease-out;
    }}

    html[data-theme="light"] .stApp {{
        background:
            radial-gradient(circle at top left, rgba(var(--accent-blue-rgb),.08), transparent 26%),
            radial-gradient(circle at top right, rgba(5,150,105,.06), transparent 24%),
            linear-gradient(180deg, var(--bg-gradient-start) 0%, var(--bg-gradient-mid) 52%, var(--bg-gradient-end) 100%);
    }}

    [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, header {{ background: transparent !important; }}
    [data-testid="stDecoration"] {{ display: none; }}

    .block-container {{
        width: min(100%, 1680px);
        max-width: 1680px;
        padding-top: 3.5rem;
        padding-right: clamp(0.85rem, 1.8vw, 1.6rem);
        padding-left: clamp(0.85rem, 1.8vw, 1.6rem);
        padding-bottom: 6rem;
    }}

    div[data-testid="stHorizontalBlock"] {{
        gap: clamp(0.75rem, 1.4vw, 1.1rem);
        align-items: stretch;
    }}

    div[data-testid="column"] > div {{
        width: 100%;
        height: 100%;
    }}

    /* ── Sidebar ──────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {{
        background: var(--surface);
        border-right: 1px solid var(--border);
        animation: slideIn 0.4s ease-out;
    }}

    [data-testid="stSidebarHeader"] {{
        position: sticky;
        top: 0;
        z-index: 100;
        min-height: 74px;
        padding: 1rem 3rem .9rem 1rem;
        border-bottom: 1px solid var(--border-light);
        background: var(--surface) !important;
        backdrop-filter: blur(12px);
    }}

    [data-testid="stSidebarHeader"]::before {{
        content:"🎵";
        position:absolute; left:1rem; top:1rem;
        width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center;
        font-size:1.15rem; font-weight:900; color:#fff;
        background: var(--accent-brand);
        box-shadow:0 10px 24px rgba(var(--accent-blue-rgb),.28);
    }}

    [data-testid="stSidebarHeader"]::after {{
        content:"Artist 360° Intelligence";
        position:absolute; left:4.25rem; top:1.35rem;
        right:3.25rem; color:var(--text-heading); font-size:1.15rem; font-weight:800;
        letter-spacing:.2px; line-height:1.15;
    }}

    [data-testid="stSidebarNav"] {{ padding-top: .75rem; }}

    [data-testid="stSidebarNav"] ul {{ padding-left: 0 !important; margin: 0 !important; }}
    [data-testid="stSidebarNav"] li {{ list-style: none !important; margin: 0 !important; padding: 0 !important; }}

    [data-testid="stSidebarNav"] a {{
        display: flex !important;
        align-items: center !important;
        gap: 14px !important;
        padding: 11px 16px !important;
        border-radius: 12px !important;
        line-height: 1 !important;
        min-height: 46px !important;
        color: var(--text) !important;
        text-decoration: none !important;
        transition: all 0.2s ease !important;
    }}

    [data-testid="stSidebarNav"] a:hover {{
        background: rgba(var(--accent-blue-rgb), 0.12) !important;
        color: var(--accent) !important;
    }}

    [data-testid="stSidebarNav"] a[aria-current="page"] {{
        background: rgba(var(--accent-blue-rgb), 0.2) !important;
        color: var(--accent) !important;
    }}

    [data-testid="stSidebarNav"] a > span:first-child,
    [data-testid="stSidebarNav"] a [data-testid="stIconMaterial"],
    [data-testid="stSidebarNav"] a .material-symbols-rounded,
    [data-testid="stSidebarNav"] a .material-icons {{
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 26px !important;
        height: 26px !important;
        font-size: 22px !important;
        line-height: 1 !important;
        flex-shrink: 0 !important;
        margin: 0 !important;
        transform: translateY(0) !important;
        color: inherit !important;
    }}

    [data-testid="stSidebarNav"] a span:last-child,
    [data-testid="stSidebarNav"] a p {{
        display: inline-flex !important;
        align-items: center !important;
        line-height: 1.2 !important;
        margin: 0 !important;
        padding: 0 !important;
        font-size: 16px !important;
        font-weight: 650 !important;
        color: inherit !important;
    }}

    [data-testid="stSidebarNav"] a svg {{
        color: inherit !important;
        fill: currentColor !important;
    }}

    h1, h2, h3, h4, p, label, div, span {{ color: var(--text); }}

    .brand-row {{ display: none; }}

    .brand-logo {{
        width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center;
        font-size:1.15rem; font-weight:900; color:#fff;
        background: var(--accent-brand);
        box-shadow:0 10px 24px rgba(var(--accent-blue-rgb),.28);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }}

    .brand-logo:hover {{
        transform: rotate(5deg) scale(1.1);
        box-shadow:0 15px 35px rgba(var(--accent-blue-rgb),.4);
    }}

    .sidebar-logo {{ font-size:1.2rem; font-weight:800; letter-spacing:.2px; line-height:1.15; color: var(--text-heading); }}
    .sidebar-sub {{ color:var(--text2); font-size:.8rem; margin-top:.18rem; }}

    .sidebar-badge {{
        display:inline-block; margin-top:.45rem; padding:3px 8px; border-radius:999px;
        background:rgba(124,92,252,.18); color:#ddd6fe; font-size:.75rem; font-weight:700;
    }}

    /* ── Radio Buttons ─────────────────────────────────────────────── */
    div[data-testid="stRadio"] > label {{ font-size:.82rem; font-weight:700; color:var(--text2) !important; }}

    div[data-testid="stRadio"] [role="radiogroup"] label {{
        background:transparent; border:1px solid transparent; border-radius:10px;
        padding:.35rem .45rem; margin:.1rem 0; transition:all .3s cubic-bezier(0.4, 0, 0.2, 1);
        cursor: pointer;
    }}

    div[data-testid="stRadio"] [role="radiogroup"] label:hover {{
        background:rgba(var(--accent-blue-rgb),.12); border-color:rgba(var(--accent-blue-rgb),.25);
        transform: translateX(4px);
    }}

    div[data-testid="stRadio"] [role="radiogroup"] label[data-checked="true"] {{
        background:rgba(var(--accent-blue-rgb),.18); border-color:rgba(var(--accent-blue-rgb),.4);
    }}

    div[data-testid="stRadio"] [role="radiogroup"] label > div:first-child {{
        display:none !important;
    }}

    div[data-testid="stRadio"] [role="radiogroup"] label p {{
        margin-left:0 !important; font-weight:600;
    }}

    /* ── Page Header ───────────────────────────────────────────────── */
    .page-title {{ font-size:2rem; font-weight:800; letter-spacing:-.03em; margin-bottom:.25rem; }}
    .page-meta {{ color:var(--text2); font-size:.95rem; margin-bottom:1rem; }}

    .page-header-box {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        flex-wrap: wrap;
        margin-bottom: 1rem;
        padding: 1.15rem 1.25rem;
        border-radius: 16px;
        border: 1px solid rgba(var(--accent-blue-rgb),.28);
        background: var(--surface-header-box);
        box-shadow: var(--shadow-md), inset 0 1px 0 rgba(255,255,255,.03);
        position: relative;
        overflow: hidden;
    }}

    .page-header-box::after {{
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(90deg, rgba(var(--accent-blue-rgb),.07), rgba(5,150,105,.06));
        pointer-events: none;
    }}

    .page-header-content {{
        min-width: 320px;
        position: relative;
        z-index: 1;
    }}

    .page-header-badge {{
        position: relative;
        z-index: 1;
    }}

    /* ── Dashboard Cards ───────────────────────────────────────────── */
    .dashboard-card:hover {{
        box-shadow: var(--shadow-hover);
        border-color: rgba(var(--accent-blue-rgb),.3);
    }}

    .section-title {{ 
        font-size:1rem; font-weight:700; margin-bottom:.2rem;
        display: flex; align-items: center; gap: 0.5rem;
    }}

    .section-sub {{ color:var(--text2); font-size:.82rem; margin-bottom:1rem; }}

    .dashboard-card {{
        background: var(--surface-card);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 1rem 1.15rem;
        transition: all 0.25s ease;
        box-shadow: var(--shadow-sm);
        margin-bottom: 1.5rem;
    }}

    .dashboard-card a {{
        color: inherit;
        text-decoration: none;
    }}

    .artist-link {{
        color: var(--text);
        text-decoration: none;
        font-weight: 700;
    }}

    .artist-link:hover {{
        color: var(--text-heading);
        text-decoration: underline;
    }}

    /* ── Tables ────────────────────────────────────────────────────── */
    .table-wrap {{ margin-top: 1rem; overflow-x:auto; overflow-y:auto; max-height:620px; }}

    .leader-table {{ width:100%; border-collapse:collapse; font-size:.92rem; }}

    .leader-table thead th {{
        text-align:left; padding:.85rem .85rem; color:var(--text2); font-size:.72rem;
        letter-spacing:.06em; text-transform:uppercase; border-bottom:1px solid var(--border);
    }}

    .leader-table tbody td {{
        padding:.75rem .85rem; border-bottom:1px solid var(--border-light); vertical-align:middle;
    }}

    .leader-table tbody tr:nth-child(even) {{
        background: var(--surface-table-row-alt);
    }}

    .leader-table tbody tr:hover {{ 
        background: rgba(var(--accent-blue-rgb),.08); 
        transform: scale(1.004);
        box-shadow: 0 8px 20px rgba(var(--accent-blue-rgb),.08);
    }}

    .leader-table tbody tr {{
        transition: all 0.18s ease;
    }}

    .pos-cell {{ color:var(--text3); font-weight:800; width:46px; }}
    .artist-cell {{ font-weight:700; }}
    .num-cell {{ text-align:left; font-variant-numeric:tabular-nums; }}
    .muted {{ color:var(--text2); }}

    .country-pill {{
        display:inline-block; padding:4px 10px; border-radius:999px; background:var(--up-bg);
        color:var(--up-text); font-size:.75rem; font-weight:700;
    }}

    .badge {{ 
        display:inline-block; padding:6px 10px; border-radius:999px; 
        font-size:.72rem; font-weight:800; transition: all 0.2s ease;
        cursor: default;
    }}

    .badge:hover {{
        transform: scale(1.05);
    }}

    .badge-up {{ background:var(--up-bg); color:var(--up-text); }}
    .badge-up:hover {{ background:rgba(var(--accent-blue-rgb),.25); }}
    .badge-dn {{ background:var(--down-bg); color:var(--down-text); }}
    .badge-dn:hover {{ background:rgba(232,69,69,.25); }}
    .badge-same {{ background:rgba(151,163,197,.14); color:var(--text2); }}
    .badge-new {{ 
        background: var(--info-bg); color: var(--info-text);
        animation: pulse 2s infinite;
    }}

    /* ── Action Buttons ────────────────────────────────────────────── */
    .action-btn {{
        display: inline-flex; align-items: center; gap: 0.5rem;
        padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.85rem;
        font-weight: 600; cursor: pointer; transition: all 0.3s ease;
        border: 1px solid var(--border); background: var(--surface2);
        color: var(--text); text-decoration: none;
    }}

    .action-btn:hover {{
        background: rgba(var(--accent-blue-rgb),.15);
        border-color: var(--accent);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(var(--accent-blue-rgb),.2);
    }}

    .action-btn-primary {{
        background: linear-gradient(135deg, #4f8ef7, #7c5cfc);
        border-color: transparent;
        color: #fff;
    }}

    .action-btn-primary:hover {{
        background: linear-gradient(135deg, #6fa3f9, #9175fd);
        box-shadow: 0 6px 20px rgba(var(--accent-blue-rgb),.4);
    }}

    /* ── KPI Cards ─────────────────────────────────────────────────── */
    .kpi-card {{
        background: var(--surface-kpi);
        border: 1px solid var(--border-kpi);
        border-radius: 12px;
        padding: 24px 20px 18px;
        min-height: 158px;
        width: 100%;
        position: relative; 
        overflow: visible; 
        height: 100%;
        display: flex;
        flex-direction: column;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        animation: fadeIn 0.6s ease-out;
    }}

    .kpi-card:hover {{
        transform: translateY(-4px);
        box-shadow: var(--shadow-hover);
        border-color: rgba(var(--accent-blue-rgb),.3);
        z-index: 1000;
    }}

    .kpi-card::before {{
        content:''; position:absolute; top:0; left:0; right:0; height:4px;
        border-radius: 12px 12px 0 0;
        background: var(--accent-gradient);
        transition: height 0.3s ease;
    }}

    .kpi-card:hover::before {{
        height: 5px;
    }}

    .kpi-green::before {{ background: linear-gradient(90deg, var(--accent3), #16a34a); }}
    .kpi-amber::before {{ background: linear-gradient(90deg, var(--warning), #f97316); }}
    .kpi-red::before {{ background: linear-gradient(90deg, var(--danger), #be123c); }}

    .kpi-label {{ 
        color:var(--text2); font-size:.76rem; text-transform:uppercase; 
        letter-spacing:.08em; margin-bottom: 0.5rem;
    }}

    .kpi-value {{ 
        font-size:2rem; font-weight:800; margin-top:.35rem;
        background: var(--text-kpi-gradient);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}

    .kpi-delta {{ color:var(--text2); font-size:.78rem; margin-top:.2rem; }}

    /* ── Progress Bars ─────────────────────────────────────────────── */
    .progress-bar {{
        width: 100%; height: 6px; background: rgba(151,163,197,.15);
        border-radius: 999px; overflow: hidden; margin-top: auto;
    }}

    .progress-fill {{
        height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2));
        border-radius: 999px; transition: width 1.5s cubic-bezier(0.4, 0, 0.2, 1);
    }}

    /* ── Graph Cards ───────────────────────────────────────────────── */
    .graph-card {{
        width: 100%;
        box-sizing: border-box;
        padding: 10px 10px 6px 10px;
        border-radius: 16px;
        border: 1px solid var(--border-card);
        background: var(--graph-card-bg);
        box-shadow: var(--shadow-sm);
    }}

    .plotly-html-chart {{ width: 100%; }}
    .plotly-html-chart .js-plotly-plot,
    .plotly-html-chart .plot-container,
    .plotly-html-chart .svg-container {{ width: 100% !important; }}

    /* ── Tooltips ──────────────────────────────────────────────────── */
    .tooltip {{
        position: relative;
        display: inline-block;
    }}

    .tooltip .tooltiptext {{
        visibility: hidden;
        width: 360px;
        background-color: var(--tooltip-bg);
        backdrop-filter: blur(12px);
        color: var(--text);
        text-align: left;
        border-radius: 12px;
        padding: 16px 20px;
        position: absolute;
        z-index: 99999;
        top: 100%;
        left: 50%;
        transform: translateX(-50%) translateY(0);
        opacity: 0;
        transition: opacity 0.3s ease, transform 0.3s ease;
        border: 1px solid var(--tooltip-border);
        box-shadow: var(--shadow-lg);
        font-size: 0.86rem;
        line-height: 1.6;
        pointer-events: auto;
        max-height: 320px;
        overflow-y: auto;
        overscroll-behavior: contain;
        scrollbar-width: thin;
        scrollbar-color: var(--accent) transparent;
    }}

    .tooltip:hover .tooltiptext {{
        visibility: visible; 
        opacity: 1; 
        transform: translateX(-50%) translateY(10px);
    }}

    .tooltip .tooltiptext::after {{
        content: ""; position: absolute; bottom: 100%; left: 50%;
        margin-left: -10px; border-width: 10px; border-style: solid;
        border-color: transparent transparent var(--tooltip-bg) transparent;
    }}

    .tooltip .tooltiptext::before {{
        content: "";
        position: absolute;
        bottom: 100%;
        left: 0;
        width: 100%;
        height: 25px;
        background: transparent;
    }}

    /* Prevent Streamlit from clipping tooltips */
    [data-testid="stHorizontalBlock"], [data-testid="column"], [data-testid="stVerticalBlock"], [data-testid="stVerticalBlockBorderWrapper"] {{
        overflow: visible !important;
    }}

    .tooltip .tooltiptext::-webkit-scrollbar {{
        width: 5px;
    }}
    .tooltip .tooltiptext::-webkit-scrollbar-track {{
        background: transparent;
    }}
    .tooltip .tooltiptext::-webkit-scrollbar-thumb {{
        background: var(--scrollbar-thumb);
        border-radius: 10px;
    }}

    /* ── Form Elements ─────────────────────────────────────────────── */
    textarea, input, [data-baseweb="select"] > div {{
        background: var(--surface2) !important;
        color: var(--text) !important;
        border-color: var(--border) !important;
    }}

    div[data-testid="stMetric"] {{
        background: transparent; border:none; padding:0; box-shadow:none;
    }}

    div[data-testid="stMetric"] label {{ color: var(--text2) !important; }}

    /* ── Status Indicators ─────────────────────────────────────────── */
    .status-good {{ color: var(--success); font-weight:700; }}
    .small-note {{ color: var(--text2); font-size:.82rem; }}

    .run-log {{ display:flex; flex-direction:column; gap:.55rem; }}

    .run-item {{
        display:grid; grid-template-columns: 1.35fr 1fr .5fr .55fr; gap:.6rem;
        align-items:center; padding:.7rem .85rem; background:var(--surface2);
        border:1px solid var(--border); border-radius:10px; font-size:.84rem;
    }}

    .run-date {{ color:var(--text); font-weight:600; }}
    .run-source, .run-rows {{ color:var(--text2); }}

    .run-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:8px; }}
    .dot-ok {{ background:var(--success); }}
    .dot-partial {{ background:#f5a623; }}
    .dot-fail {{ background:#e84545; }}

    .status-pill {{ 
        display:inline-block; padding:2px 8px; border-radius:999px; 
        font-size:.72rem; font-weight:700; transition: all 0.2s ease;
    }}

    .pill-ok {{ background:var(--success-bg); color:var(--success-text); }}
    .pill-ok:hover {{ background:rgba(34,197,94,.25); }}
    .pill-partial {{ background:var(--warning-bg); color:var(--warning-text); }}
    .pill-fail {{ background:var(--down-bg); color:var(--down-text); }}

    /* ── Live Indicator ────────────────────────────────────────────── */
    .live-indicator {{
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 4px 10px;
        background: var(--success-bg);
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 700;
        color: var(--success-text);
    }}

    .live-dot {{
        width: 6px;
        height: 6px;
        background: var(--success);
        border-radius: 50%;
        animation: pulse 2s ease-in-out infinite;
    }}

    /* ── Expandable ────────────────────────────────────────────────── */
    .expandable {{
        overflow: hidden;
        transition: max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }}

    /* ── Comparison Highlight ──────────────────────────────────────── */
    .comparison-highlight {{
        border: 2px solid var(--accent);
        background: rgba(var(--accent-blue-rgb),.08);
        animation: pulse 1.5s ease-in-out 3;
    }}

    /* ── Tabs ──────────────────────────────────────────────────────── */
    .stTabs {{
        width: 100%;
        border-bottom: none !important;
    }}

    .stTabs [data-baseweb="tab-list"] {{
        display: grid !important;
        grid-template-columns: repeat(auto-fit, minmax(min(180px, 100%), 1fr));
        grid-auto-flow: row;
        gap: 10px;
        width: 100%;
        background: transparent;
        border-bottom: none !important;
        overflow: visible;
    }}

    /* ── Expander Overrides ────────────────────────────────────────── */
    .streamlit-expanderHeader {{
        color: var(--text) !important;
        font-weight: 600 !important;
    }}

    /* ── Comparison Table ──────────────────────────────────────────── */
    .cmp-table-wrap {{ overflow-x: auto; margin: 1rem 0; }}
    .cmp-table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
    .cmp-table th {{
        text-align: left; padding: .75rem .85rem; color: var(--text2);
        font-size: .72rem; letter-spacing: .06em; text-transform: uppercase;
        border-bottom: 1px solid var(--border);
    }}
    .cmp-table td {{
        padding: .65rem .85rem; border-bottom: 1px solid var(--border-light);
    }}
    .cmp-table tbody tr:hover {{ background: rgba(var(--accent-blue-rgb),.06); }}
    .cmp-warning {{ color: var(--text2); font-size: .95rem; padding: 2rem 0; text-align: center; }}

    /* ── Debut Report Loader ───────────────────────────────────────── */
    #dr-loader {{
        background: var(--loader-bg);
    }}
    #dr-loader .dr-title {{
        color: var(--text-heading);
    }}
    #dr-loader .dr-sub {{
        color: var(--text2);
    }}
    </style>
    """