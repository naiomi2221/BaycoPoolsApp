import streamlit as st
from datetime import datetime
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import smtplib
from email.message import EmailMessage
from supabase import create_client

# -------------------------
# CONFIG & CONSTANTS
# -------------------------
ST_EMAIL = st.secrets["EMAIL_USER"]
ST_PASS = st.secrets["EMAIL_PASS"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SMTP_SERVER = "mail.spacemail.com"
SMTP_PORT = 465

TODAY = datetime.now().strftime("%A")

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
        try:
            # Check credentials in Supabase 'users' table
            response = supabase.table("users").select("*").eq("username", username).execute()
            if response.data and response.data[0]["password"] == password:
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.session_state["user_role"] = response.data[0]["role"]
                st.success(f"Logged in as {username}")
            else:
                st.error("Invalid credentials")
        except Exception as e:
            st.error(f"Login error: {e}")

    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------
# CUSTOMER MANAGEMENT
# -------------------------
def load_customers():
    try:
        response = supabase.table("customers").select("*").execute()
        if response.status_code != 200:
            st.error(f"Error loading customers: Status {response.status_code}")
            return []
        return response.data
    except Exception as e:
        st.error(f"Failed to load customers: {e}")
        return []

def add_client_tab():
    st.subheader("Add New Client")
    with st.form("add_client_form"):
        name = st.text_input("Customer Name")
        address = st.text_input("Full Address")
        email = st.text_input("Email")
        service_day = st.selectbox("Service Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
        submitted = st.form_submit_button("Save to Database")

        if submitted:
            if not name or not address or not email:
                st.error("All fields are required.")
                return

            geolocator = Nominatim(user_agent="bayco_pools_app", timeout=10)
            location = geolocator.geocode(address)
            if not location:
                st.error("Address not found. Please enter a valid address.")
                return

            response = supabase.table("customers").insert({
                "name": name,
                "address": address,
                "email": email,
                "lat": location.latitude,
                "lon": location.longitude,
                "service_day": service_day,
                "active": True,
                "cleaning_started": False
            }).execute()

            if response.status_code in [200, 201]:
                st.success(f"Added customer {name}!")
            else:
                st.error(f"Failed to add customer: {response.data}")

# -------------------------
# ROUTE TAB
# -------------------------
def todays_route_tab():
    st.subheader(f"🧹 Route for {TODAY}")
    all_customers = load_customers()

    # Filter only active customers scheduled for today
    route_customers = [
        c for c in all_customers
        if c.get("service_day") == TODAY and c.get("active") is True
    ]

    if not route_customers:
        st.info(f"No customers scheduled for {TODAY}.")
        return

    # Compute distance from office
    for c in route_customers:
        c["dist"] = geodesic(OFFICE_LOCATION, (c["lat"], c["lon"])).miles

    route_customers.sort(key=lambda x: x["dist"], reverse=True)

    for cust in route_customers:
        st.markdown(f"### 📍 {cust['name']} ({round(cust['dist'],1)} mi)")
        st.write(f"**Address:** {cust['address']}")
        st.write(f"**Email:** {cust['email']}")

        notes = st.text_area("Notes", key=f"notes_{cust['id']}")
        photo = st.file_uploader("Upload Pool Photo", type=["jpg","png"], key=f"img_{cust['id']}")

        if st.button(f"Start Cleaning", key=f"start_{cust['id']}"):
            supabase.table("customers").update({"cleaning_started": True}).eq("id", cust["id"]).execute()
            st.success(f"Started cleaning {cust['name']}!")

        # Directions button
        office_str = f"{OFFICE_LOCATION[0]},{OFFICE_LOCATION[1]}"
        dest_str = f"{cust['lat']},{cust['lon']}"
        maps_url = f"https://www.google.com/maps/dir/{office_str}/{dest_str}/"
        st.markdown(f"[🗺️ Open directions in Google Maps]({maps_url})", unsafe_allow_html=True)

        if st.button(f"Finish & Email", key=f"finish_{cust['id']}"):
            if send_report(cust["email"], cust["name"], notes, photo):
                st.success(f"Sent to {cust['name']}!")

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

st.sidebar.subheader(f"Logged in as {st.session_state['username']} ({st.session_state['user_role']})")

tab1, tab2 = st.tabs(["Today's Route", "Manage Clients"])

with tab1:
    todays_route_tab()

with tab2:
    add_client_tab()
