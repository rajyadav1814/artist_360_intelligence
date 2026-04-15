import streamlit as st

def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg:#070b16; --surface:#12182a; --surface2:#1a2238; --surface3:#202947;
            --border:#293455; --accent:#4f8ef7; --accent2:#7c5cfc; --accent3:#22d3a0;
            --warn:#f5a623; --danger:#e84545; --text:#eef2ff; --text2:#97a3c5;
        }
        
        /* Smooth animations */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateX(-20px); }
            to { opacity: 1; transform: translateX(0); }
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        @keyframes shimmer {
            0% { background-position: -1000px 0; }
            100% { background-position: 1000px 0; }
        }
        
        .stApp { 
            background:linear-gradient(180deg,#060a15 0%,#091127 100%); 
            color:var(--text);
            animation: fadeIn 0.6s ease-out;
        }
        [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, header { background:transparent !important; }
        [data-testid="stDecoration"] { display:none; }
        .block-container {
            width: min(100%, 1680px);
            max-width: 1680px;
            padding-top: 1rem;
            padding-right: clamp(0.85rem, 1.8vw, 1.6rem);
            padding-left: clamp(0.85rem, 1.8vw, 1.6rem);
            padding-bottom: 2rem;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: clamp(0.75rem, 1.4vw, 1.1rem);
            align-items: stretch;
        }
        div[data-testid="column"] > div {
            width: 100%;
            height: 100%;
        }
        [data-testid="stSidebar"] {
            background:var(--surface); border-right:1px solid var(--border);
            animation: slideIn 0.4s ease-out;
        }
        [data-testid="stSidebarHeader"] {
            position: relative;
            min-height: 74px;
            padding: 1rem 3rem .9rem 1rem;
            border-bottom: 1px solid rgba(41,52,85,.7);
        }
        [data-testid="stSidebarHeader"]::before {
            content:"🎵";
            position:absolute; left:1rem; top:1rem;
            width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center;
            font-size:1.15rem; font-weight:900; color:#fff;
            background:linear-gradient(135deg, #4f8ef7 0%, #7c5cfc 55%, #22d3a0 100%);
            box-shadow:0 10px 24px rgba(79,142,247,.28);
        }
        [data-testid="stSidebarHeader"]::after {
            content:"Artist 360 Intelligence";
            position:absolute; left:4.25rem; top:1.35rem;
            right:3.25rem; color:var(--text); font-size:1.15rem; font-weight:800;
            letter-spacing:.2px; line-height:1.15;
        }
        [data-testid="stSidebarNav"] { padding-top:.6rem; }
        h1, h2, h3, h4, p, label, div, span { color:var(--text); }
        .brand-row { display:none; }
        .brand-logo {
            width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center;
            font-size:1.15rem; font-weight:900; color:#fff;
            background:linear-gradient(135deg, #4f8ef7 0%, #7c5cfc 55%, #22d3a0 100%);
            box-shadow:0 10px 24px rgba(79,142,247,.28);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .brand-logo:hover {
            transform: rotate(5deg) scale(1.1);
            box-shadow:0 15px 35px rgba(79,142,247,.4);
        }
        .sidebar-logo { font-size:1.2rem; font-weight:800; letter-spacing:.2px; line-height:1.15; }
        .sidebar-sub { color:var(--text2); font-size:.8rem; margin-top:.18rem; }
        .sidebar-badge {
            display:inline-block; margin-top:.45rem; padding:3px 8px; border-radius:999px;
            background:rgba(124,92,252,.18); color:#ddd6fe; font-size:.75rem; font-weight:700;
        }
        div[data-testid="stRadio"] > label { font-size:.82rem; font-weight:700; color:var(--text2) !important; }
        div[data-testid="stRadio"] [role="radiogroup"] label {
            background:transparent; border:1px solid transparent; border-radius:10px;
            padding:.35rem .45rem; margin:.1rem 0; transition:all .3s cubic-bezier(0.4, 0, 0.2, 1);
            cursor: pointer;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label:hover {
            background:rgba(79,142,247,.12); border-color:rgba(79,142,247,.25);
            transform: translateX(4px);
        }
        div[data-testid="stRadio"] [role="radiogroup"] label[data-checked="true"] {
            background:rgba(79,142,247,.18); border-color:rgba(79,142,247,.4);
        }
        div[data-testid="stRadio"] [role="radiogroup"] label > div:first-child {
            display:none !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label p {
            margin-left:0 !important; font-weight:600;
        }
        .page-title { font-size:2rem; font-weight:800; letter-spacing:-.03em; margin-bottom:.25rem; }
        .page-meta { color:var(--text2); font-size:.95rem; margin-bottom:1rem; }
        .dashboard-card {
            background:rgba(18,24,42,.96); border:1px solid var(--border); border-radius:16px;
            padding:clamp(0.9rem, 1.2vw, 1.1rem); box-shadow:0 12px 32px rgba(0,0,0,.22);
            margin-bottom:1rem; transition: all 0.3s ease;
            animation: fadeIn 0.7s ease-out; min-height: 100%;
        }
        .dashboard-card:hover {
            box-shadow:0 18px 42px rgba(0,0,0,.35);
            border-color: rgba(79,142,247,.3);
        }
        .section-title { 
            font-size:1rem; font-weight:700; margin-bottom:.2rem;
            display: flex; align-items: center; gap: 0.5rem;
        }
        .section-sub { color:var(--text2); font-size:.82rem; margin-bottom:.9rem; }
        
        /* Interactive buttons */
        .action-btn {
            display: inline-flex; align-items: center; gap: 0.5rem;
            padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.85rem;
            font-weight: 600; cursor: pointer; transition: all 0.3s ease;
            border: 1px solid var(--border); background: var(--surface2);
            color: var(--text); text-decoration: none;
        }
        .action-btn:hover {
            background: rgba(79,142,247,.15);
            border-color: var(--accent);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(79,142,247,.2);
        }
        .action-btn-primary {
            background: linear-gradient(135deg, #4f8ef7, #7c5cfc);
            border-color: transparent;
        }
        .action-btn-primary:hover {
            background: linear-gradient(135deg, #6fa3f9, #9175fd);
            box-shadow: 0 6px 20px rgba(79,142,247,.4);
        }
        .kpi-card {
            background:linear-gradient(180deg, rgba(19,26,45,1) 0%, rgba(16,21,37,1) 100%);
            border:1px solid var(--border); border-radius:14px; padding:1rem 1rem .9rem 1rem;
            min-height:clamp(108px, 12vw, 132px); position:relative; overflow:hidden; height: 100%;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            animation: fadeIn 0.6s ease-out;
        }
        .kpi-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 28px rgba(79,142,247,.2);
            border-color: rgba(79,142,247,.4);
        }
        .kpi-card::before {
            content:''; position:absolute; top:0; left:0; right:0; height:3px;
            background:linear-gradient(90deg,var(--accent),var(--accent2));
            transition: height 0.3s ease;
        }
        .kpi-card:hover::before {
            height: 4px;
        }
        .kpi-green::before { background:linear-gradient(90deg,var(--accent3),#16a34a); }
        .kpi-amber::before { background:linear-gradient(90deg,var(--warn),#f97316); }
        .kpi-red::before { background:linear-gradient(90deg,var(--danger),#be123c); }
        .kpi-label { 
            color:var(--text2); font-size:.76rem; text-transform:uppercase; 
            letter-spacing:.08em; margin-bottom: 0.5rem;
        }
        .kpi-value { 
            font-size:2rem; font-weight:800; margin-top:.35rem;
            background: linear-gradient(135deg, #eef2ff 0%, #97a3c5 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .kpi-delta { color:var(--text2); font-size:.78rem; margin-top:.2rem; }
        
        /* Progress bars */
        .progress-bar {
            width: 100%; height: 6px; background: rgba(151,163,197,.15);
            border-radius: 999px; overflow: hidden; margin-top: 0.5rem;
        }
        .progress-fill {
            height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent3));
            border-radius: 999px; transition: width 1.5s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .table-wrap { overflow-x:auto; }
        table.leader-table { width:100%; border-collapse:collapse; font-size:.92rem; }
        .leader-table thead th {
            text-align:left; padding:.7rem .75rem; color:var(--text2); font-size:.73rem;
            letter-spacing:.06em; text-transform:uppercase; border-bottom:1px solid var(--border);
        }
        .leader-table tbody td {
            padding:.72rem .75rem; border-bottom:1px solid rgba(41,52,85,.72); vertical-align:middle;
        }
        .leader-table tbody tr:hover { 
            background:rgba(79,142,247,.10); 
            transform: scale(1.01);
            box-shadow: 0 4px 12px rgba(79,142,247,.15);
        }
        .leader-table tbody tr {
            transition: all 0.2s ease;
        }
        .pos-cell { color:#dbe4ff; font-weight:800; width:44px; }
        .artist-cell { font-weight:700; }
        .muted { color:var(--text2); }
        .num-cell { text-align:right; font-variant-numeric:tabular-nums; }
        .country-pill {
            display:inline-block; padding:2px 8px; border-radius:999px; background:rgba(34,211,160,.12);
            color:#8ff0cf; font-size:.75rem; font-weight:700;
        }
        .badge { 
            display:inline-block; padding:3px 8px; border-radius:999px; 
            font-size:.72rem; font-weight:800; transition: all 0.2s ease;
            cursor: default;
        }
        .badge:hover {
            transform: scale(1.1);
        }
        .badge-up { background:rgba(34,211,160,.14); color:#8ff0cf; }
        .badge-up:hover { background:rgba(34,211,160,.25); }
        .badge-dn { background:rgba(232,69,69,.14); color:#ff9c9c; }
        .badge-dn:hover { background:rgba(232,69,69,.25); }
        .badge-same { background:rgba(151,163,197,.14); color:#c4d0f3; }
        .badge-new { 
            background:rgba(79,142,247,.16); color:#b7d4ff;
            animation: pulse 2s infinite;
        }
        
        /* Tooltip styles */
        .tooltip {
            position: relative;
            display: inline-block;
        }
        .tooltip .tooltiptext {
            visibility: hidden;
            background-color: rgba(18,24,42,0.98);
            color: var(--text);
            text-align: center;
            border-radius: 8px;
            padding: 8px 12px;
            position: absolute;
            z-index: 1000;
            bottom: 125%;
            left: 50%;
            margin-left: -60px;
            opacity: 0;
            transition: opacity 0.3s;
            border: 1px solid var(--border);
            box-shadow: 0 8px 20px rgba(0,0,0,.4);
            font-size: 0.8rem;
        }
        .tooltip:hover .tooltiptext {
            visibility: visible;
            opacity: 1;
        }
        textarea, input, [data-baseweb="select"] > div {
            background:var(--surface2) !important; color:var(--text) !important; border-color:var(--border) !important;
        }
        div[data-testid="stMetric"] {
            background:transparent; border:none; padding:0; box-shadow:none;
        }
        div[data-testid="stMetric"] label { color:var(--text2) !important; }
        .status-good { color:#22c55e; font-weight:700; }
        .small-note { color:var(--text2); font-size:.82rem; }
        .run-log { display:flex; flex-direction:column; gap:.55rem; }
        .run-item {
            display:grid; grid-template-columns: 1.35fr 1fr .5fr .55fr; gap:.6rem;
            align-items:center; padding:.7rem .85rem; background:rgba(17,24,39,.55);
            border:1px solid rgba(41,52,85,.7); border-radius:10px; font-size:.84rem;
        }
        .run-date { color:var(--text); font-weight:600; }
        .run-source, .run-rows { color:var(--text2); }
        .run-dot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:8px; }
        .dot-ok { background:#22c55e; }
        .dot-partial { background:#f5a623; }
        .dot-fail { background:#e84545; }
        .status-pill { 
            display:inline-block; padding:2px 8px; border-radius:999px; 
            font-size:.72rem; font-weight:700; transition: all 0.2s ease;
        }
        .pill-ok { background:rgba(34,197,94,.14); color:#8ff0cf; }
        .pill-ok:hover { background:rgba(34,197,94,.25); }
        .pill-partial { background:rgba(245,166,35,.14); color:#ffd089; }
        .pill-fail { background:rgba(232,69,69,.14); color:#ff9c9c; }
        
        /* Live indicator */
        .live-indicator {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 4px 10px;
            background: rgba(34,211,160,.12);
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 700;
            color: #8ff0cf;
        }
        .live-dot {
            width: 6px;
            height: 6px;
            background: #22d3a0;
            border-radius: 50%;
            animation: pulse 2s ease-in-out infinite;
        }
        
        /* Loading skeleton */
        .skeleton {
            background: linear-gradient(90deg, rgba(151,163,197,.1) 25%, rgba(151,163,197,.2) 50%, rgba(151,163,197,.1) 75%);
            background-size: 200% 100%;
            animation: shimmer 1.5s infinite;
            border-radius: 8px;
        }
        
        /* Expandable section */
        .expandable {
            overflow: hidden;
            transition: max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        /* Comparison mode highlight */
        .comparison-highlight {
            border: 2px solid var(--accent);
            background: rgba(79,142,247,.08);
            animation: pulse 1.5s ease-in-out 3;
        }
        
        /* Interactive tabs */
        .stTabs {
            width: 100%;
            border-bottom: none !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            display: grid !important;
            grid-template-columns: repeat(auto-fit, minmax(min(180px, 100%), 1fr));
            grid-auto-flow: row;
            gap: 10px;
            width: 100%;
            background: transparent;
            border-bottom: none !important;
            overflow: visible;
            align-items: stretch;
        }
        .stTabs [data-baseweb="tab-border"] {
            display: none !important;
        }
        .stTabs [data-baseweb="tab-highlight"] {
            display: none !important;
        }
        .stTabs > div > div {
            border-bottom: none !important;
            gap: 10px;
            width: 100%;
        }
        .stTabs [data-baseweb="tab"] {
            width: 100%;
            min-width: 0 !important;
            justify-content: center;
            background: var(--surface2);
            border-radius: 10px;
            color: var(--text2);
            border: 1px solid var(--border);
            padding: 0.5rem 0.65rem !important;
            min-height: 44px;
            height: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            transition: all 0.3s ease;
            border-bottom: 1px solid var(--border) !important;
        }
        .stTabs [data-baseweb="tab"] p {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: .86rem;
        }
        .stTabs [data-baseweb="tab-panel"] {
            width: 100%;
            padding-top: 0.85rem;
        }
        .stTabs [data-baseweb="tab"]:hover {
            background: rgba(79,142,247,.12);
            border-color: rgba(79,142,247,.3);
            transform: translateY(-2px);
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(79,142,247,.2), rgba(124,92,252,.2));
            border-color: var(--accent);
            color: var(--text);
            border-bottom: 1px solid var(--accent) !important;
        }
        .stPlotlyChart, div[data-testid="stDataFrame"], div[data-testid="stTable"] {
            width: 100% !important;
        }
        
        /* Buttons enhancement */
        .stButton button {
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border-radius: 10px;
        }
        .stButton button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(79,142,247,.3);
        }
        
        /* Loading spinner */
        .stSpinner > div {
            border-color: var(--accent) transparent transparent transparent;
        }
        
        /* Toast notifications */
        .stToast {
            background: rgba(18,24,42,0.98) !important;
            border: 1px solid var(--accent) !important;
            border-radius: 12px !important;
        }

        @media (max-width: 1200px) {
            .block-container {
                max-width: 100%;
            }
            .page-title {
                font-size: 1.8rem;
            }
            .kpi-value {
                font-size: 1.75rem;
            }
            .stTabs [data-baseweb="tab-list"] {
                grid-template-columns: repeat(auto-fit, minmax(min(150px, 100%), 1fr));
            }
        }

        @media (max-width: 992px) {
            .block-container {
                padding-right: 0.9rem;
                padding-left: 0.9rem;
            }
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
            }
            div[data-testid="column"] {
                min-width: calc(50% - 0.55rem) !important;
                flex: 1 1 calc(50% - 0.55rem) !important;
            }
        }

        @media (max-width: 768px) {
            div[data-testid="column"] {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
            .page-title {
                font-size: 1.55rem;
            }
            .page-meta {
                font-size: 0.88rem;
            }
            .dashboard-card {
                padding: 0.9rem;
                border-radius: 14px;
            }
            .kpi-card {
                min-height: auto;
            }
            .kpi-value {
                font-size: 1.55rem;
            }
            .stTabs [data-baseweb="tab"] {
                min-height: 40px;
                padding: 0.4rem 0.45rem !important;
            }
            .stTabs [data-baseweb="tab"] p {
                font-size: 0.8rem;
            }
            .run-item {
                grid-template-columns: 1fr;
                gap: 0.35rem;
            }
        }
        
        /* Metric cards enhancement */
        [data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
            font-weight: 800 !important;
        }
        [data-testid="stMetricDelta"] {
            font-size: 0.85rem !important;
        }
        
        /* Expander animation */
        .streamlit-expanderHeader {
            transition: all 0.3s ease;
            border-radius: 8px;
        }
        .streamlit-expanderHeader:hover {
            background: rgba(79,142,247,.08);
        }
        
        /* Download button styling */
        .stDownloadButton button {
            background: linear-gradient(135deg, #22d3a0, #16a34a) !important;
            color: white !important;
            border: none !important;
        }
        .stDownloadButton button:hover {
            background: linear-gradient(135deg, #2ee4b0, #1fb556) !important;
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(34,211,160,.4) !important;
        }
        
        /* Selectbox hover */
        [data-baseweb="select"]:hover {
            border-color: var(--accent) !important;
        }
        
        /* Text input focus */
        input:focus, textarea:focus {
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 1px var(--accent) !important;
        }
        
        /* Slider styling */
        .stSlider [role="slider"] {
            background: linear-gradient(135deg, #4f8ef7, #7c5cfc) !important;
        }
        
        /* Toggle switch */
        [data-testid="stCheckbox"] input[type="checkbox"]:checked + div {
            background: linear-gradient(135deg, #4f8ef7, #7c5cfc) !important;
        }

        /* Global footer */
        .app-footer {
            margin-top: 2.5rem;
            padding: 1rem 0 0.25rem;
            border-top: 1px solid rgba(41,52,85,.7);
            text-align: center;
            color: var(--text2);
            font-size: 0.86rem;
            line-height: 1.7;
        }
        .app-footer a {
            color: #b7d4ff;
            text-decoration: none;
        }
        .app-footer a:hover {
            color: #ffffff;
            text-decoration: underline;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
