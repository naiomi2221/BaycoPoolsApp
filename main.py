import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime
import streamlit as st
from geopy.distance import geodesic
import openrouteservice
from openrouteservice import convert
import folium
from streamlit_folium import st_folium
import hashlib

# -------------------------
# CONFIG
# -------------------------
TODAY = datetime.now().strftime("%A")

ST_EMAIL = st.secrets["EMAIL_USER"]
ST_PASS = st.secrets["EMAIL_PASS"]
OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))
SMTP_SERVER = "mail.spacemail.com"
SMTP_PORT = 465
ORS_API_KEY = st.secrets.get("ORS_API_KEY", "")

# -------------------------
# DATABASE SETUP
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
            cleaning_started INTEGER DEFAULT 0,
            assigned_to TEXT
        )
    ''')
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            role TEXT
        )
    ''')
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def add_user(username, password, role):
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?,?,?)",
              (username, hash_password(password), role))
    conn.commit()
    conn.close()

def verify_user(username, password):
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    c.execute("SELECT password_hash, role FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row and row[0] == hash_password(password):
        return row[1]  # Return role
    return None

def load_customers():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    c.execute("""
        SELECT id, name, address, email, lat, lon, COALESCE(service_day, ''), active, cleaning_started, assigned_to
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
            "cleaning_started": bool(r[8]),
            "assigned_to": r[9]
        }
        for r in rows
    ]

init_db()
# Example admin user (only runs if not exists)
add_user("admin", "admin123", "admin")
add_user("tech1", "tech123", "tech")

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
# LOGIN
# -------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["role"] = None
    st.session_state["username"] = None

if not st.session_state["logged_in"]:
    st.title("🔒 Bayco Pools Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        role = verify_user(username, password)
        if role:
            st.session_state["logged_in"] = True
            st.session_state["role"] = role
            st.session_state["username"] = username
            st.success(f"Logged in as {username} ({role})")
        else:
            st.error("Invalid username or password")
    st.stop()

# -------------------------
# MAIN APP AFTER LOGIN
# -------------------------
st.set_page_config(page_title="Bayco Pools", page_icon="assets/favicon.png")
st.title(f"🌊 Bayco Pools Manager - {st.session_state['username']}")

tab1, tab2 = st.tabs(["Today's Route", "Manage Clients"])

# -------------------------
# MANAGE CLIENTS - ONLY ADMIN
# -------------------------
if st.session_state["role"] == "admin":
    with tab2:
        st.subheader("Add / Edit Customers")
        all_customers = load_customers()
        for cust in all_customers:
            with st.expander(f"{cust['name']} ({'Active' if cust['active'] else 'Inactive'})"):
                is_active = st.checkbox("Active", value=cust["active"], key=f"active_{cust['id']}")
                if is_active != cust["active"]:
                    conn = sqlite3.connect("bayco.db")
                    conn.execute("UPDATE customers SET active=? WHERE id=?", (1 if is_active else 0, cust["id"]))
                    conn.commit()
                    conn.close()
                    st.success(f"{cust['name']} status updated.")

        # Form to add new customer
        with st.form("add_client", clear_on_submit=True):
            name = st.text_input("Customer Name")
            addr = st.text_input("Full Address")
            mail = st.text_input("Email")
            service_day = st.selectbox("Service Day", ["Monday","Tuesday","Wednesday","Thursday","Friday"])
            assigned_to = st.text_input("Assign to Tech (username)")
            submitted = st.form_submit_button("Save to Database")
            if submitted:
                from geopy.geocoders import Nominatim
                geolocator = Nominatim(user_agent="bayco_pools_app", timeout=10)
                loc = geolocator.geocode(addr)
                if loc:
                    conn = sqlite3.connect("bayco.db")
                    conn.execute(
                        "INSERT INTO customers (name,address,email,lat,lon,service_day,assigned_to) VALUES (?,?,?,?,?,?,?)",
                        (name, addr, mail, loc.latitude, loc.longitude, service_day, assigned_to)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Added {name}!")

# -------------------------
# TODAY'S ROUTE - TECH VIEW
# -------------------------
with tab1:
    st.subheader(f"🧹 Route for {TODAY}")
    all_customers = load_customers()
    # Only show active customers assigned to logged-in tech
    route_customers = [
        c for c in all_customers
        if c["service_day"] == TODAY and c["active"]
        and (st.session_state["role"] == "admin" or c["assigned_to"] == st.session_state["username"])
    ]

    if not route_customers:
        st.info("No customers scheduled for you today.")
    else:
        for c in route_customers:
            c["dist"] = geodesic(OFFICE_LOCATION, c["coords"]).miles

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

                # Directions (lon,lat)
                coords = [[OFFICE_LOCATION[1], OFFICE_LOCATION[0]], [cust["coords"][1], cust["coords"][0]]]
                try:
                    routes = ors_client.directions(coords)
                    steps = routes['routes'][0]['segments'][0]['steps']
                    st.markdown("**Directions:**")
                    for step in steps:
                        st.write(f"{step['instruction']} ({step['distance']:.0f} m)")

                    # Map visualization
                    route_coords = [(p[1], p[0]) for p in routes['routes'][0]['geometry']['coordinates']]
                    m = folium.Map(location=OFFICE_LOCATION, zoom_start=12)
                    folium.Marker(location=OFFICE_LOCATION, tooltip="Office", icon=folium.Icon(color="green")).add_to(m)
                    folium.Marker(location=cust["coords"], tooltip=cust["name"], icon=folium.Icon(color="red")).add_to(m)
                    folium.PolyLine(route_coords, color="blue", weight=4, opacity=0.7).add_to(m)
                    st_folium(m, width=700, height=400)

                except Exception as e:
                    st.error(f"Directions unavailable: {e}")

                if st.button("Finish & Email", key=f"finish_{i}"):
                    if send_report(cust["email"], cust["name"], notes, photo):
                        st.success(f"Sent to {cust['name']}!")
