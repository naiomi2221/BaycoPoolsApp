import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime
import streamlit as st
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import openrouteservice
from openrouteservice import convert

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="Bayco Pools", page_icon="🌊", layout="wide")
TODAY = datetime.now().strftime("%A")
ST_EMAIL = st.secrets["EMAIL_USER"]
ST_PASS = st.secrets["EMAIL_PASS"]
OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))
ORS_API_KEY = st.secrets.get("ORS_API_KEY", "")

# -----------------------------
# DATABASE SETUP
# -----------------------------
def init_db():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)
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
    return {r[0]: {"password": r[1], "role": r[2]} for r in rows}

init_db()

# -----------------------------
# EMAIL FUNCTION
# -----------------------------
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
        with smtplib.SMTP_SSL("mail.spacemail.com", 465, timeout=20) as server:
            server.login(ST_EMAIL, ST_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

# -----------------------------
# STYLING FOR LOGIN
# -----------------------------
st.markdown(
    """
    <style>
    .app-bg {
        background-image: url('https://images.unsplash.com/photo-1507525428034-b723cf961d3e');
        background-size: cover;
        background-position: center;
        height: 100vh;
        width: 100vw;
        position: fixed;
        top: 0;
        left: 0;
        z-index: -1;
    }
    .login-container {
        position: relative;
        top: 20%;
        margin: auto;
        width: 350px;
        padding: 30px;
        background-color: rgba(255, 255, 255, 0.9);
        border-radius: 20px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    </style>
    <div class="app-bg"></div>
    """, unsafe_allow_html=True
)

# -----------------------------
# LOGIN SYSTEM
# -----------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["role"] = None
    st.session_state["username"] = None

users = load_users()

with st.container():
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.subheader("🌴 Welcome to Bayco Pools Manager 🌊")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_button = st.button("Login")
    st.markdown("</div>", unsafe_allow_html=True)

    if login_button:
        if username in users and password == users[username]["password"]:
            st.session_state["logged_in"] = True
            st.session_state["role"] = users[username]["role"]
            st.session_state["username"] = username
            st.success(f"Welcome, {username}!")
            st.experimental_rerun()
        else:
            st.error("Invalid username or password.")

# -----------------------------
# MAIN APP AFTER LOGIN
# -----------------------------
if st.session_state["logged_in"]:
    st.title(f"Hello, {st.session_state['username']}!")
    tabs = ["Today's Route"]
    if st.session_state["role"] == "admin":
        tabs.append("Manage Clients")
        tabs.append("Manage Users")
    tab1, tab2, tab3 = st.tabs(tabs + ["Logout"])

    # -------------------------
    # Today's Route
    # -------------------------
    if "Today's Route" in tabs:
        with tab1:
            st.subheader(f"🧹 Route for {TODAY}")
            all_customers = load_customers()
            route_customers = [c for c in all_customers if c["service_day"] == TODAY and c["active"]]

            if not route_customers:
                st.info(f"No customers scheduled for {TODAY}.")
            else:
                for c in route_customers:
                    c["dist"] = geodesic(OFFICE_LOCATION, c["coords"]).miles
                route = sorted(route_customers, key=lambda x: x["dist"], reverse=True)
                ors_client = openrouteservice.Client(key=ORS_API_KEY)
                for i, cust in enumerate(route):
                    with st.expander(f"📍 {cust['name']} ({round(cust['dist'],1)} mi)"):
                        st.write(f"**Address:** {cust['address']}")
                        notes = st.text_area("Notes", key=f"notes_{i}")
                        photo = st.file_uploader("Upload Pool Photo", type=["jpg","png"], key=f"img_{i}")

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
                            if send_report(cust["email"], cust["name"], notes, photo):
                                st.success(f"Sent to {cust['name']}!")

    # -------------------------
    # Manage Clients (Admin only)
    # -------------------------
    if st.session_state["role"] == "admin" and "Manage Clients" in tabs:
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
                st.subheader("Add New Customer")
                name = st.text_input("Customer Name")
                addr = st.text_input("Full Address")
                email = st.text_input("Email")
                service_day = st.selectbox("Service Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
                submitted = st.form_submit_button("Add Customer")
                if submitted:
                    if not name or not addr or not email:
                        st.error("All fields are required!")
                    else:
                        geolocator = Nominatim(user_agent="bayco_pools_app", timeout=10)
                        loc = geolocator.geocode(addr)
                        if loc:
                            conn = sqlite3.connect("bayco.db")
                            conn.execute(
                                "INSERT INTO customers (name, address, email, lat, lon, service_day) VALUES (?,?,?,?,?,?)",
                                (name, addr, email, loc.latitude, loc.longitude, service_day)
                            )
                            conn.commit()
                            conn.close()
                            st.success(f"{name} added successfully!")
                        else:
                            st.error("Address not found.")

    # -------------------------
    # Manage Users (Admin only)
    # -------------------------
    if st.session_state["role"] == "admin" and "Manage Users" in tabs:
        with tab3:
            st.subheader("Add New User")
            with st.form("add_user", clear_on_submit=True):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                role = st.selectbox("Role", ["admin", "tech"])
                submitted = st.form_submit_button("Add User")
                if submitted:
                    if not username or not password:
                        st.error("All fields are required!")
                    else:
                        conn = sqlite3.connect("bayco.db")
                        try:
                            conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (username, password, role))
                            conn.commit()
                            st.success(f"User {username} added!")
                        except sqlite3.IntegrityError:
                            st.error("Username already exists!")
                        finally:
                            conn.close()

    # -------------------------
    # Logout
    # -------------------------
    if "Logout" in tabs:
        with tab3 if st.session_state["role"]=="admin" else tab2:
            if st.button("Logout"):
                st.session_state["logged_in"] = False
                st.session_state["role"] = None
                st.session_state["username"] = None
                st.experimental_rerun()
