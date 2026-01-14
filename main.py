import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime
import streamlit as st
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import openrouteservice
from openrouteservice import convert
import time

# -------------------------
# CONFIG & CONSTANTS
# -------------------------
TODAY = datetime.now().strftime("%A")

# Admin login
ADMIN_USERNAME = "Naiomi"
ADMIN_PASSWORD = "Haley!5301"

# Supabase / other secrets would go here
ST_EMAIL = st.secrets["EMAIL_USER"]
ST_PASS = st.secrets["EMAIL_PASS"]
OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))
ORS_API_KEY = st.secrets.get("ORS_API_KEY", "")

SMTP_SERVER = "mail.spacemail.com"
SMTP_PORT = 465

# -------------------------
# SESSION STATE INIT (FIXED)
# -------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "user_role" not in st.session_state:
    st.session_state["user_role"] = ""
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "tab1"

# -------------------------
# DATABASE INIT
# -------------------------
def init_db():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    # Customers table
    c.execute('''
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
    ''')
    conn.commit()
    conn.close()


def load_customers():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    c.execute("""
        SELECT id, name, address, email, lat, lon, COALESCE(service_day, ''), active, cleaning_started
        FROM customers
    """)
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "name": r[1],
            "address": r[2],
            "email": r[3],
            "coords": (r[4], r[5]),
            "service_day": r[6],
            "active": bool(r[7]),
            "cleaning_started": bool(r[8])
        }
        for r in rows
    ]


init_db()

# -------------------------
# EMAIL FUNCTION
# -------------------------
def send_report(to_email, name, notes, photo_file):
    msg = EmailMessage()
    msg["Subject"] = f"Bayco Pools Service Report: {name}"
    msg["From"] = ST_EMAIL
    msg["To"] = to_email
    msg.set_content(f"Hi {name},\n\nYour pool service is complete!\n\nNotes:\n{notes}\n\nHave a great day!")

    if photo_file and photo_file.type:
        file_data = photo_file.read()
        photo_file.seek(0)
        maintype, subtype = photo_file.type.split("/")
        msg.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=photo_file.name)

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
            server.login(ST_EMAIL, ST_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

# -------------------------
# LOGIN SCREEN OVERLAY (FIXED)
# -------------------------
# -------------------------
# LOGIN SCREEN OVERLAY
# -------------------------
def show_login():
    # CSS for semi-transparent PNG background
    st.markdown(
        """
        <style>
        .login-container {
            background: linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)), 
                        url('baycopoolbackground.png');
            background-size: cover;
            background-position: center;
            padding: 4rem;
            border-radius: 1rem;
            color: white;
            max-width: 400px;
            margin: 10vh auto;
            box-shadow: 0 8px 32px 0 rgba(0,0,0,0.37);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
        }
        .login-container input, .login-container button {
            margin-bottom: 1rem;
            width: 100%;
            padding: 0.5rem;
            border-radius: 0.3rem;
            border: none;
        }
        .login-container button {
            background-color: #1E90FF;
            color: white;
            font-weight: bold;
            cursor: pointer;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Wrap in a div
    st.markdown('<div class="login-container">', unsafe_allow_html=True)

    st.subheader("🌴 Bayco Pools Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_button = st.button("Login")

    if login_button:
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            # Set session state
            st.session_state["logged_in"] = True
            st.session_state["username"] = ADMIN_USERNAME
            st.session_state["user_role"] = "admin"
            # Set a flag to safely rerun
            st.session_state["rerun_flag"] = True
        else:
            st.error("Invalid credentials")

    st.markdown('</div>', unsafe_allow_html=True)


# -------------------------
# MAIN APP LOGIN CHECK
# -------------------------
if not st.session_state.get("logged_in", False):
    show_login()
    # Safely rerun after login function exits
    if st.session_state.get("rerun_flag", False):
        st.session_state["rerun_flag"] = False
        st.experimental_rerun()
    st.stop()


# -------------------------
# STREAMLIT APP
# -------------------------
st.set_page_config(page_title="Bayco Pools", page_icon="assets/favicon.png")
st.title("🌊 Bayco Pools Manager")

# -------------------------
# SHOW LOGIN IF NOT LOGGED IN
# -------------------------
if not st.session_state["logged_in"]:
    show_login()
    st.stop()  # Stop app until login successful

# -------------------------
# SIDEBAR USER INFO
# -------------------------
st.sidebar.subheader(f"Logged in as {st.session_state['username']} ({st.session_state['user_role']})")

# -------------------------
# YOUR APP LOGIC CONTINUES HERE
# (Tabs, customer management, emailing, ORS, etc.)
# -------------------------
