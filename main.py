import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime
import streamlit as st
from geopy.distance import geodesic
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

ORS_API_KEY = st.secrets.get("ORS_API_KEY", "")  # Put your OpenRouteService API key in secrets.toml

# -------------------------
# DATABASE FUNCTIONS
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
# STREAMLIT APP
# -------------------------
st.set_page_config(page_title="Bayco Pools", page_icon="assets/favicon.png")
st.title("🌊 Bayco Pools Manager")

if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "tab1"

tab1, tab2 = st.tabs(["Today's Route", "Manage Clients"])

# -------------------------
# MANAGE CLIENTS
# -------------------------
with tab2:
    st.subheader("Add New Client")
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
                from geopy.geocoders import Nominatim
                geolocator = Nominatim(user_agent="bayco_pools_app", timeout=10)
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
                    st.session_state["active_tab"] = "tab1"
                else:
                    st.error("Address not found.")

# -------------------------
# TODAY'S ROUTE
# -------------------------
if st.session_state["active_tab"] == "tab1":
    with tab1:
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

            # Initialize ORS client
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

                    # Generate directions
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

