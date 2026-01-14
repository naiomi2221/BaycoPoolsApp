import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime
import streamlit as st
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import openrouteservice
import base64

# -------------------------------------------------
# STREAMLIT CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Bayco Pools",
    page_icon="🏝️",
    layout="wide"
)

# -------------------------------------------------
# SECRETS (CLOUD ONLY)
# -------------------------------------------------
ADMIN_USERNAME = st.secrets["ADMIN_USERNAME"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]
TECHS = st.secrets["TECHS"]

EMAIL_USER = st.secrets["EMAIL_USER"]
EMAIL_PASS = st.secrets["EMAIL_PASS"]
ORS_API_KEY = st.secrets["ORS_API_KEY"]
OFFICE_LOCATION = tuple(map(float, st.secrets["OFFICE_LOCATION"].split(",")))

TODAY = datetime.now().strftime("%A")

# -------------------------------------------------
# DATABASE (DATA ONLY — NO AUTH)
# -------------------------------------------------
def get_db():
    return sqlite3.connect("bayco.db", check_same_thread=False)

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            email TEXT,
            lat REAL,
            lon REAL,
            service_day TEXT,
            active INTEGER DEFAULT 1,
            cleaning_started INTEGER DEFAULT 0
        )
    """)
    db.commit()
    db.close()

init_db()

# -------------------------------------------------
# BACKGROUND IMAGE (PNG, SEMI-TRANSPARENT)
# -------------------------------------------------
def set_background(png_file):
    with open(png_file, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    st.markdown(
        f"""
        <style>
        .stApp {{
            background:
            linear-gradient(rgba(0,0,0,0.55), rgba(0,0,0,0.55)),
            url("data:image/png;base64,{encoded}");
            background-size: cover;
            background-position: center;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

set_background("baycopoolbackground.png")

# -------------------------------------------------
# AUTHENTICATION
# -------------------------------------------------
def authenticate(username, password):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return "admin"
    if username in TECHS and TECHS[username] == password:
        return "tech"
    return None

if "auth" not in st.session_state:
    st.session_state.auth = None
    st.session_state.user = None
    st.session_state.role = None

if st.session_state.auth is None:
    st.markdown("<h2 style='text-align:center;'>🌴 Bayco Pools Login</h2>", unsafe_allow_html=True)
    with st.form("login", clear_on_submit=False):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            role = authenticate(u, p)
            if role:
                st.session_state.auth = True
                st.session_state.user = u
                st.session_state.role = role
                st.rerun()
            else:
                st.error("Invalid credentials")
    st.stop()

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
st.sidebar.success(f"Logged in as {st.session_state.user} ({st.session_state.role})")
if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.rerun()

# -------------------------------------------------
# LOAD DATA
# -------------------------------------------------
def load_customers():
    db = get_db()
    rows = db.execute("""
        SELECT id, name, address, email, lat, lon, service_day, active, cleaning_started
        FROM customers
    """).fetchall()
    db.close()

    return [
        {
            "id": r[0],
            "name": r[1],
            "address": r[2],
            "email": r[3],
            "coords": (r[4], r[5]),
            "day": r[6],
            "active": bool(r[7]),
            "started": bool(r[8])
        } for r in rows
    ]

# -------------------------------------------------
# TABS
# -------------------------------------------------
tabs = st.tabs(["🧭 Today's Route", "👥 Clients"])

# -------------------------------------------------
# CLIENT MANAGEMENT (ADMIN ONLY)
# -------------------------------------------------
with tabs[1]:
    if st.session_state.role != "admin":
        st.info("Admins only")
    else:
        st.subheader("Add Client")

        with st.form("add_client", clear_on_submit=True):
            name = st.text_input("Name")
            addr = st.text_input("Address")
            email = st.text_input("Email")
            day = st.selectbox("Service Day", ["Monday","Tuesday","Wednesday","Thursday","Friday"])

            if st.form_submit_button("Save"):
                geo = Nominatim(user_agent="bayco_pools")
                loc = geo.geocode(addr)
                if not loc:
                    st.error("Address not found")
                else:
                    db = get_db()
                    db.execute("""
                        INSERT INTO customers (name,address,email,lat,lon,service_day)
                        VALUES (?,?,?,?,?,?)
                    """, (name,addr,email,loc.latitude,loc.longitude,day))
                    db.commit()
                    db.close()
                    st.success("Client added")

# -------------------------------------------------
# ROUTE TAB
# -------------------------------------------------
with tabs[0]:
    st.subheader(f"Route for {TODAY}")

    customers = [c for c in load_customers() if c["day"] == TODAY and c["active"]]

    if not customers:
        st.info("No scheduled clients")
    else:
        for c in customers:
            c["dist"] = geodesic(OFFICE_LOCATION, c["coords"]).miles

        customers.sort(key=lambda x: x["dist"], reverse=True)

        ors = openrouteservice.Client(key=ORS_API_KEY)

        for c in customers:
            with st.expander(f"📍 {c['name']} — {c['dist']:.1f} mi"):
                st.write(c["address"])

                if st.button("Start Cleaning", key=f"s{c['id']}"):
                    db = get_db()
                    db.execute("UPDATE customers SET cleaning_started=1 WHERE id=?", (c["id"],))
                    db.commit()
                    db.close()
                    st.success("Cleaning started")

                try:
                    route = ors.directions([OFFICE_LOCATION, c["coords"]])
                    steps = route["routes"][0]["segments"][0]["steps"]
                    for s in steps:
                        st.write(s["instruction"])
                except:
                    st.warning("Directions unavailable")
