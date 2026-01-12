import sqlite3
import smtplib
from geopy.geocoders import Nominatim
from email.message import EmailMessage
from geopy.distance import geodesic
import streamlit as st
from datetime import datetime

# -------------------------
# Constants
# -------------------------
show_inactive = st.checkbox("Show inactive customers", False)
TODAY = datetime.now().strftime("%A")
geolocator = Nominatim(user_agent="bayco_pools_app", timeout=10)
ST_EMAIL = st.secrets["EMAIL_USER"]
ST_PASS = st.secrets["EMAIL_PASS"]

off_str = st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350")
OFFICE_LOCATION = tuple(map(float, off_str.split(",")))

SMTP_SERVER = "mail.spacemail.com"
SMTP_PORT = 465

# -------------------------
# Database
# -------------------------
def init_db():
    conn = sqlite3.connect('bayco.db')
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
            active INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()


def load_customers():
    conn = sqlite3.connect("bayco.db")
    c = conn.cursor()
    c.execute("""
        SELECT id, name, address, email, lat, lon, COALESCE(service_day, '') as service_day, active
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
            "active": bool(r[7])
        }
        for r in rows
    ]

init_db()

# -------------------------
# Email
# -------------------------
def send_report(to_email, name, notes, photo_file):
    msg = EmailMessage()
    msg["Subject"] = f"Bayco Pools Service Report: {name}"
    msg["From"] = ST_EMAIL
    msg["To"] = to_email
    msg.set_content(
        f"Hi {name},\n\nYour pool service is complete!\n\nNotes:\n{notes}\n\nHave a great day!"
    )

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
# Streamlit App
# -------------------------
st.set_page_config(page_title="Bayco Pools", page_icon="assets/favicon.png")
st.title("🌊 Bayco Pools Manager")

# Track which tab is active
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "tab1"

tab1, tab2 = st.tabs(["Today's Route", "Manage Clients"])

# -------------------------
# Manage Clients Tab
# -------------------------
with tab2:
    st.subheader("Add New Client")
    customers = load_customers()
    for cust in customers:
        with st.expander(cust["name"]):
            is_active = st.toggle(
                "Active",
                value=cust["active"],
                key=f"active_{cust['id']}"
            )
            if is_active != cust["active"]:
                conn = sqlite3.connect("bayco.db")
                conn.execute(
                    "UPDATE customers SET active=? WHERE id=?",
                    (1 if is_active else 0, cust["id"])
                )
                conn.commit()
                conn.close()
                st.success("Status Updated.")
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
                    conn = sqlite3.connect('bayco.db')
                    conn.execute(
                        "INSERT INTO customers (name, address, email, lat, lon, service_day) VALUES (?,?,?,?,?,?)",
                        (name, addr, mail, loc.latitude, loc.longitude, service_day)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Added {name}!")
                    # Switch to Today's Route tab automatically
                    st.session_state["active_tab"] = "tab1"

                else:
                    st.error("Address not found.")

# -------------------------
# Today's Route Tab
# -------------------------
if st.session_state["active_tab"] == "tab1":
    with tab1:
        st.subheader(f"🧹 Route for {TODAY}")
        all_customers = load_customers()
        customers_today = [c for c in all_customers if c["service_day"] == TODAY]

        if not customers_today:
            st.info(f"No customers scheduled for {TODAY}.")
        else:
            # Compute distance from office
            for c in customers_today:
                c["dist"] = geodesic(OFFICE_LOCATION, c["coords"]).miles

            # Sort by distance (furthest first)
            route = sorted(customers_today, key=lambda x: x["dist"], reverse=True)

            for i, cust in enumerate(route):
                with st.expander(f"📍 {cust['name']} ({round(cust['dist'],1)} mi)"):
                    st.write(f"**Address:** {cust['address']}")
                    st.write(f"**Email:** {cust['email']}")
                    notes = st.text_area("Notes", key=f"notes_{i}")
                    photo = st.file_uploader("Upload Pool Photo", type=["jpg","png"], key=f"img_{i}")

                    if st.button("Finish & Email", key=f"btn_{i}"):
                        if send_report(cust["email"], cust["name"], notes, photo):
                            st.success(f"Sent to {cust['name']}!")
