import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime
import streamlit as st
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import openrouteservice

# -------------------------
# SESSION STATE INIT
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
# CONFIG & CONSTANTS
# -------------------------
TODAY = datetime.now().strftime("%A")

ST_EMAIL = st.secrets["EMAIL_USER"]
ST_PASS = st.secrets["EMAIL_PASS"]
OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))
ORS_API_KEY = st.secrets.get("ORS_API_KEY", "")

SMTP_SERVER = "mail.spacemail.com"
SMTP_PORT = 465

# -------------------------
# DATABASE INIT
# -------------------------
def init_db():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    ''')
    conn.commit()
    conn.close()

def load_customers():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    c.execute("""
        SELECT id, name, address, email, lat, lon, COALESCE(service_day,''), active, cleaning_started
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
        } for r in rows
    ]

def load_users():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    c.execute("SELECT username, password, role FROM users")
    rows = c.fetchall()
    conn.close()
    return {u: {"password": p, "role": r} for u, p, r in rows}

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
# LOGIN SCREEN OVERLAY
# -------------------------
def show_login():
    st.markdown(
        """
        <style>
        .login-container {
            background-image: url('https://i.ibb.co/9vZ3xVJ/island-oasis.jpg');
            background-size: cover;
            background-position: center;
            padding: 3rem;
            border-radius: 1rem;
            opacity: 0.85;
        }
        </style>
        """, unsafe_allow_html=True
    )
    st.markdown('<div class="login-container">', unsafe_allow_html=True)

    st.subheader("🌴 Bayco Pools Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_button = st.button("Login")

    if login_button:
        users = load_users()
        if username in users and password == users[username]["password"]:
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["user_role"] = users[username]["role"]
            st.experimental_rerun()
        else:
            st.error("Invalid credentials")

    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------
# MAIN APP (UNCHANGED)
# -------------------------
def show_main_app():
    st.sidebar.subheader(f"Logged in as {st.session_state['username']} ({st.session_state['user_role']})")
    
    # Your existing tabs, customer forms, route calculations, ORS directions, email sending
    # EVERYTHING BELOW THIS STAYS EXACTLY THE SAME AS YOUR ORIGINAL CODE
    # (You don’t need me to rewrite it since you wanted everything else unchanged)
    pass  # Placeholder for your full existing app code

# -------------------------
# RUN APP
# -------------------------
if not st.session_state["logged_in"]:
    show_login()
else:
    show_main_app()
