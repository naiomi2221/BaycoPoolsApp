import streamlit as st
from datetime import datetime
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import openrouteservice
from openrouteservice import convert
import smtplib
from email.message import EmailMessage
from supabase import create_client, Client

# -------------------------
# CONFIG & CONSTANTS
# -------------------------
TODAY = datetime.now().strftime("%A")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ADMIN_USERNAME = st.secrets["ADMIN_USERNAME"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

ST_EMAIL = st.secrets["EMAIL_USER"]
ST_PASS = st.secrets["EMAIL_PASS"]
OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))
ORS_API_KEY = st.secrets.get("ORS_API_KEY", "")

SMTP_SERVER = "mail.spacemail.com"
SMTP_PORT = 465

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
# LOGIN SCREEN
# -------------------------
def show_login():
    st.markdown(
        """
        <style>
        .login-container {
            background:
            linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)),
            url("baycopoolbackground.png");
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
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["user_role"] = "admin"
            st.experimental_rerun()
        else:
            st.error("Invalid credentials")

    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------
# LOAD CUSTOMERS FROM SUPABASE
# -------------------------
def load_customers():
    response = supabase.table("customers").select("*").execute()
    if response.error:
        st.error(f"Error loading customers: {response.error.message}")
        return []
    return response.data

def add_customer(name, address, email, lat, lon, service_day):
    supabase.table("customers").insert({
        "name": name,
        "address": address,
        "email": email,
        "lat": lat,
        "lon": lon,
        "service_day": service_day,
        "active": True,
        "cleaning_started": False
    }).execute()

def update_customer_status(customer_id, field, value):
    supabase.table("customers").update({field: value}).eq("id", customer_id).execute()

# -------------------------
# STREAMLIT APP
# -------------------------
st.set_page_config(page_title="Bayco Pools", page_icon="assets/favicon.png")
st.title("🌊 Bayco Pools Manager")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    show_login()
    st.stop()

# -------------------------
# SIDEBAR INFO
# -------------------------
st.sidebar.subheader(f"Logged in as {st.session_state['username']} ({st.session_state['user_role']})")

# -------------------------
# TABS
# -------------------------
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
                update_customer_status(cust["id"], "active", is_active)
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
                geolocator = Nominatim(user_agent="bayco_pools_app", timeout=10)
                loc = geolocator.geocode(addr)
                if loc:
                    add_customer(name, addr, mail, loc.latitude, loc.longitude, service_day)
                    st.success(f"Added {name}!")
                else:
                    st.error("Address not found.")

# -------------------------
# TODAY'S ROUTE
# -------------------------
with tab1:
    st.subheader(f"🧹 Route for {TODAY}")
    all_customers = load_customers()
    route_customers = [c for c in all_customers if c["service_day"] == TODAY and c["active"]]

    if not route_customers:
        st.info(f"No customers scheduled for {TODAY}.")
    else:
        for c in route_customers:
            c["dist"] = geodesic(OFFICE_LOCATION, (c["lat"], c["lon"])).miles

        route = sorted(route_customers, key=lambda x: x["dist"], reverse=True)
        ors_client = openrouteservice.Client(key=ORS_API_KEY)

        for i, cust in enumerate(route):
            with st.expander(f"📍 {cust['name']} ({round(cust['dist'],1)} mi)"):
                st.write(f"**Address:** {cust['address']}")
                st.write(f"**Email:** {cust['email']}")
                notes = st.text_area("Notes", key=f"notes_{i}")
                photo = st.file_uploader("Upload Pool Photo", type=["jpg","png"], key=f"img_{i}")

                if st.button("Start Cleaning", key=f"start_{i}"):
                    update_customer_status(cust["id"], "cleaning_started", True)
                    st.success(f"Started cleaning {cust['name']}!")

                # Generate directions
                coords = [(OFFICE_LOCATION[0], OFFICE_LOCATION[1]), (cust["lat"], cust["lon"])]
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
