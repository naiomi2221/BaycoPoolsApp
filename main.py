import streamlit as st
from supabase import create_client, Client
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import webbrowser

# -------------------------
# CONFIG & SECRETS
# -------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))

ADMIN_USERNAME = st.secrets["ADMIN_USERNAME"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

ORS_API_KEY = st.secrets.get("ORS_API_KEY", "")  # optional for directions API

# -------------------------
# PAGE SETUP
# -------------------------
st.set_page_config(page_title="Bayco Pools", page_icon="assets/favicon.png")
st.markdown("""
<style>
body {
    background: linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)),
                url("baycopoolbackground.png") center/cover no-repeat;
    color: white;
}
</style>
""", unsafe_allow_html=True)

# -------------------------
# LOGIN
# -------------------------
# -------------------------
# LOGIN
# -------------------------
def show_login():
    st.markdown('<div style="max-width:400px;margin:5vh auto;padding:2rem;background:rgba(0,0,0,0.5);border-radius:10px;">', unsafe_allow_html=True)
    st.subheader("🌴 Bayco Pools Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_button = st.button("Login")

    if login_button:
        # Check against your secrets
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            try:
                # --- THIS IS THE KEY STEP ---
                # This authenticates the 'supabase' client globally for the rest of the script
                supabase.auth.sign_in_with_password({
                    "email": EMAIL_USER, 
                    "password": EMAIL_PASS
                })
                
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.session_state["user_role"] = "admin"
                st.rerun()
                
            except Exception as e:
                st.error(f"Supabase Auth Error: {e}")
        else:
            st.error("Invalid credentials")
    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------
# HELPER FUNCTIONS
# -------------------------
def load_customers():
    try:
        response = supabase.table("customers").select("*").execute()
        if response.data is None:
            return []
        return response.data
    except Exception as e:
        st.error(f"Error loading customers: {e}")
        return []

def add_customer(name, address, email, service_day):
    geolocator = Nominatim(user_agent="bayco_pools_app", timeout=10)
    loc = geolocator.geocode(address)
    if not loc:
        st.error("Address not found.")
        return False

    customer_data = {
        "name": name,
        "address": address,
        "email": email,
        "lat": loc.latitude,
        "lon": loc.longitude,
        "service_day": service_day,
        "active": True,
        "cleaning_started": False
    }

    try:
        response = supabase.table("customers").insert(customer_data).execute()
        if response.status_code != 201 and response.data is None:
            st.error(f"Failed to add customer: {response}")
            return False
        return True
    except Exception as e:
        st.error(f"Supabase error: {e}")
        return False

def open_map(lat, lon):
    url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
    webbrowser.open_new_tab(url)

# -------------------------
# SIDEBAR
# -------------------------
st.sidebar.subheader(f"Logged in as {st.session_state['username']} ({st.session_state['user_role']})")

# -------------------------
# TABS
# -------------------------
tab_route, tab_add = st.tabs(["Today's Route", "Add Customer"])

# -------------------------
# ADD CUSTOMER TAB
# -------------------------
with tab_add:
    st.subheader("Add New Customer")
    with st.form("add_client_form", clear_on_submit=True):
        name = st.text_input("Customer Name")
        address = st.text_input("Full Address")
        email = st.text_input("Email")
        service_day = st.selectbox(
            "Service Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        )
        submitted = st.form_submit_button("Save Customer")
        if submitted:
            if add_customer(name, address, email, service_day):
                st.success(f"Customer '{name}' added successfully!")

# -------------------------
# ROUTE TAB
# -------------------------
import datetime
TODAY = datetime.datetime.now().strftime("%A")

with tab_route:
    st.subheader(f"🧹 Route for {TODAY}")
    all_customers = load_customers()
    todays_customers = [
        c for c in all_customers if c["service_day"] == TODAY and c.get("active", True)
    ]

    if not todays_customers:
        st.info("No customers scheduled for today.")
    else:
        for c in todays_customers:
            c_coords = (c["lat"], c["lon"])
            distance_mi = geodesic(OFFICE_LOCATION, c_coords).miles
            with st.expander(f"{c['name']} ({round(distance_mi,1)} mi)"):
                st.write(f"**Address:** {c['address']}")
                st.write(f"**Email:** {c['email']}")
                if st.button("Open Map", key=f"map_{c['id']}"):
                    open_map(c["lat"], c["lon"])
