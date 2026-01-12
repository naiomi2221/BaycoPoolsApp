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

ST_EMAIL = st.secrets["EMAIL_USER"]
ST_PASS = st.secrets["EMAIL_PASS"]
OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))
ORS_API_KEY = st.secrets.get("ORS_API_KEY", "")

SMTP_SERVER = "mail.spacemail.com"
SMTP_PORT = 465

# -------------------------
# DATABASE FUNCTIONS
# -------------------------
def init_db():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()

    # Customers table
    c.execute("""
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

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    # Ensure at least one admin exists
    c.execute("SELECT * FROM users WHERE role='admin'")
    if not c.fetchall():
        admin_user = st.secrets.get("ADMIN_USER", "admin")
        admin_pass = st.secrets.get("ADMIN_PASSWORD", "changeme123")
        c.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)",
                  (admin_user, admin_pass, "admin"))

    conn.commit()
    conn.close()

def load_users():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    try:
        c.execute("SELECT username, password, role FROM users")
        rows = c.fetchall()
        return {r[0]: {"password": r[1], "role": r[2]} for r in rows}
    except sqlite3.OperationalError:
        return {}
    finally:
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
        }
        for r in rows
    ]

init_db()
users = load_users()

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
# GEOCODER HELPER
# -------------------------
def safe_geocode(address, retries=3):
    geolocator = Nominatim(user_agent="bayco_pools_app", timeout=10)
    for i in range(retries):
        try:
            return geolocator.geocode(address)
        except:
            time.sleep(2)
    return None

# -------------------------
# LOGIN PAGE
# -------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["user_role"] = None
    st.session_state["username"] = None

# Display island oasis background
st.markdown("""
    <style>
    .stApp {
        background-image: url('https://images.unsplash.com/photo-1507525428034-b723cf961d3e');
        background-size: cover;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }
    .login-box {
        background-color: rgba(255, 255, 255, 0.85);
        padding: 2rem;
        border-radius: 15px;
        max-width: 400px;
        margin: auto;
        margin-top: 10%;
    }
    </style>
""", unsafe_allow_html=True)

if not st.session_state["logged_in"]:
    with st.container():
        st.markdown('<div class="login-box">', unsafe_allow_html=True)
        st.subheader("🌴 Bayco Pools Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_btn = st.button("Login")
        st.markdown('</div>', unsafe_allow_html=True)

        if login_btn:
            if username in users and users[username]["password"] == password:
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.session_state["user_role"] = users[username]["role"]
                st.experimental_rerun()
            else:
                st.error("Invalid username or password")
else:
    # -------------------------
    # MAIN APP
    # -------------------------
    st.sidebar.subheader(f"Logged in as {st.session_state['username']} ({st.session_state['user_role']})")
    if st.sidebar.button("Logout"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = None
        st.session_state["user_role"] = None
        st.experimental_rerun()

    st.title("🌊 Bayco Pools Manager")
    if "active_tab" not in st.session_state:
        st.session_state["active_tab"] = "tab1"

    tab1, tab2, tab3 = st.tabs(["Today's Route", "Manage Customers", "Admin"])

    # -------------------------
    # MANAGE CUSTOMERS
    # -------------------------
    if st.session_state["active_tab"] == "tab2" or st.session_state["active_tab"] == "tab1":
        with tab2:
            st.subheader("Add / Manage Customers")
            all_customers = load_customers()
            for cust in all_customers:
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
                        loc = safe_geocode(addr)
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
    # TODAY'S ROUTE
    # -------------------------
    if st.session_state["active_tab"] == "tab1":
        with tab1:
            st.subheader(f"🧹 Route for {TODAY}")
            all_customers = load_customers()
            route_customers = [c for c in all_customers if c["service_day"] == TODAY and c["active"]]

            if not route_customers:
                st.info(f"No customers scheduled for {TODAY}.")
            else:
                # Distance from office
                for c in route_customers:
                    c["dist"] = geodesic(OFFICE_LOCATION, c["coords"]).miles

                # Furthest first
                route = sorted(route_customers, key=lambda x: x["dist"], reverse=True)
                ors_client = openrouteservice.Client(key=ORS_API_KEY)

                for i, cust in enumerate(route):
                    with st.expander(f"📍 {cust['name']} ({round(cust['dist'],1)} mi)"):
                        st.write(f"**Address:** {cust['address']}")
                        st.write(f"**Email:** {cust['email']}")
                        notes = st.text_area("Notes", key=f"notes_{i}")
                        photo = st.file_uploader("Upload Pool Photo", type=["jpg","png"], key=f"img_{i}")

                        if st.button("Start Cleaning", key=f"start_{i}"):
                            conn = sqlite3.connect("bayco.db")
                            conn.execute("UPDATE customers SET cleaning_started=1 WHERE id=?", (cust["id"],))
                            conn.commit()
                            conn.close()
                            st.success(f"Started cleaning {cust['name']}!")

                        coords = [OFFICE_LOCATION, cust["coords"]]
                        try:
                            routes = ors_client.directions(coords)
                            steps = routes['routes'][0]['segments'][0]['steps']
                            st.markdown("**Directions:**")
                            for step in steps:
                                st.write(f"{step['instruction']} ({step['distance']:.0f} m)")
                        except Exception as e:
                            st.error(f"Directions unavailable: {e}")

                        if st.button("Finish & Email", key=f"finish_{i}"):
                            if send_report(cust["email"], cust["name"], notes, photo):
                                st.success(f"Sent to {cust['name']}!")

    # -------------------------
    # ADMIN TAB
    # -------------------------
    if st.session_state["user_role"] == "admin":
        with tab3:
            st.subheader("Admin: Manage Users")
            all_users = load_users()
            for username, uinfo in all_users.items():
                st.write(f"**{username}** - Role: {uinfo['role']}")

            st.markdown("### Add New User")
            with st.form("add_user", clear_on_submit=True):
                new_user = st.text_input("Username")
                new_pass = st.text_input("Password", type="password")
                role = st.selectbox("Role", ["tech","admin"])
                submit_user = st.form_submit_button("Add User")
                if submit_user:
                    conn = sqlite3.connect("bayco.db")
                    try:
                        conn.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",
                                     (new_user, new_pass, role))
                        conn.commit()
                        st.success(f"Added {new_user} as {role}")
                    except sqlite3.IntegrityError:
                        st.error("Username already exists")
                    conn.close()
