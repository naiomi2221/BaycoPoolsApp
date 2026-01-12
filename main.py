import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime
import streamlit as st
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import hashlib
import openrouteservice
from openrouteservice import convert

# -------------------------
# CONFIG & CONSTANTS
# -------------------------
TODAY = datetime.now().strftime("%A")

ST_EMAIL = st.secrets["EMAIL_USER"]
ST_PASS = st.secrets["EMAIL_PASS"]
OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))
SMTP_SERVER = "mail.spacemail.com"
SMTP_PORT = 465
ORS_API_KEY = st.secrets.get("ORS_API_KEY", "")

geolocator = Nominatim(user_agent="bayco_pools_app", timeout=10)

# -------------------------
# DATABASE INITIALIZATION
# -------------------------
def init_db():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    ''')
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

init_db()

# -------------------------
# HELPER FUNCTIONS
# -------------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate(username, password):
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    hashed_pw = hash_password(password)
    c.execute("SELECT role FROM users WHERE username=? AND password=?", (username, hashed_pw))
    res = c.fetchone()
    conn.close()
    if res:
        return res[0]  # role
    return None

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
# STREAMLIT APP
# -------------------------
st.set_page_config(page_title="Bayco Pools", page_icon="assets/favicon.png")
st.title("🌊 Bayco Pools Manager")

# -------------------------
# LOGIN SCREEN
# -------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["role"] = None
    st.session_state["username"] = None

if not st.session_state["logged_in"]:
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        role = authenticate(username, password)
        if role:
            st.session_state["logged_in"] = True
            st.session_state["role"] = role
            st.session_state["username"] = username
            st.success(f"Logged in as {role}")
        else:
            st.error("Invalid username or password")
else:
    # -------------------------
    # MAIN APP TABS
    # -------------------------
    if "active_tab" not in st.session_state:
        st.session_state["active_tab"] = "route"

    tabs = ["Today's Route", "Manage Clients"]
    if st.session_state["role"] == "admin":
        tabs.append("Manage Users")
    tab_selection = st.radio("Select Tab", tabs)

    # -------------------------
    # MANAGE CLIENTS
    # -------------------------
    if tab_selection == "Manage Clients":
        st.subheader("Add / Edit Clients")
        customers = load_customers()
        for cust in customers:
            with st.expander(cust["name"]):
                is_active = st.checkbox("Active", value=cust["active"], key=f"active_{cust['id']}")
                if is_active != cust["active"]:
                    conn = sqlite3.connect("bayco.db")
                    conn.execute("UPDATE customers SET active=? WHERE id=?", (1 if is_active else 0, cust["id"]))
                    conn.commit()
                    conn.close()
                    st.success(f"{cust['name']} status updated.")

        with st.form("add_client", clear_on_submit=True):
            name = st.text_input("Customer Name")
            addr = st.text_input("Full Address")
            mail = st.text_input("Email")
            service_day = st.selectbox("Service Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
            submitted = st.form_submit_button("Save to Database")
            if submitted:
                if not name or not addr or not mail:
                    st.error("All fields are required.")
                else:
                    loc = geolocator.geocode(addr)
                    if loc:
                        conn = sqlite3.connect("bayco.db")
                        conn.execute(
                            "INSERT INTO customers (name, address, email, lat, lon, service_day) VALUES (?,?,?,?,?,?)",
                            (name, addr, mail, loc.latitude, loc.longitude, service_day)
                        )
                        conn.commit()
                        conn.close()
                        st.success(f"Added {name}!")
                    else:
                        st.error("Address not found.")

    # -------------------------
    # MANAGE USERS (ADMIN ONLY)
    # -------------------------
    if tab_selection == "Manage Users" and st.session_state["role"] == "admin":
        st.subheader("Add New User")
        with st.form("add_user"):
            new_username = st.text_input("Username")
            new_password = st.text_input("Password", type="password")
            role = st.selectbox("Role", ["admin", "tech"])
            submitted = st.form_submit_button("Add User")
            if submitted:
                if new_username and new_password:
                    hashed_pw = hash_password(new_password)
                    conn = sqlite3.connect("bayco.db")
                    conn.execute(
                        "INSERT INTO users (username, password, role) VALUES (?,?,?)",
                        (new_username, hashed_pw, role)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"User {new_username} added as {role}!")
                else:
                    st.error("All fields are required.")

    # -------------------------
    # TODAY'S ROUTE
    # -------------------------
    if tab_selection == "Today's Route":
        st.subheader(f"🧹 Route for {TODAY}")
        all_customers = load_customers()
        route_customers = [
            c for c in all_customers
            if c["service_day"] == TODAY and c["active"]
        ]

        if not route_customers:
            st.info(f"No customers scheduled for {TODAY}.")
        else:
            # Compute distance from office
            for c in route_customers:
                c["dist"] = geodesic(OFFICE_LOCATION, c["coords"]).miles

            # Sort by furthest distance
            route = sorted(route_customers, key=lambda x: x["dist"], reverse=True)

            ors_client = openrouteservice.Client(key=ORS_API_KEY)

            for i, cust in enumerate(route):
                with st.expander(f"📍 {cust['name']} ({round(cust['dist'],1)} mi)"):
                    st.write(f"**Address:** {cust['address']}")
                    st.write(f"**Email:** {cust['email']}")
                    notes = st.text_area("Notes", key=f"notes_{i}")
                    
                    if st.button("Start Cleaning", key=f"start_{i}"):
                        conn = sqlite3.connect("bayco.db")
                        conn.execute("UPDATE customers SET cleaning_started=1 WHERE id=?", (cust["id"],))
                        conn.commit()
                        conn.close()
                        st.success(f"Started cleaning {cust['name']}!")

                    # Directions
                    try:
                        coords = [OFFICE_LOCATION, cust["coords"]]
                        routes = ors_client.directions(coords)
                        steps = routes['routes'][0]['segments'][0]['steps']
                        st.markdown("**Directions:**")
                        for step in steps:
                            st.write(f"{step['instruction']} ({step['distance']:.0f} m)")
                    except Exception as e:
                        st.error(f"Directions unavailable: {e}")

                    if st.button("Finish & Email", key=f"finish_{i}"):
                        if send_report(cust["email"], cust["name"], notes, None):
                            st.success(f"Sent to {cust['name']}!")
