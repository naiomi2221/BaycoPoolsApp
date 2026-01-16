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
# Initialize session state variables if they don't exist
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))

ADMIN_USERNAME = st.secrets["ADMIN_USERNAME"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]
EMAIL_USER = st.secrets["EMAIL_USER"]
EMAIL_PASS = st.secrets["EMAIL_PASS"]
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
    
    user_input = st.text_input("Username")
    pass_input = st.text_input("Password", type="password")
    
    if st.button("Login"):
        try:
            # This line looks in YOUR table (public.users) for a match
            response = supabase.table("users").select("*").eq("username", user_input).eq("password", pass_input).execute()
            
            if response.data:
                user_record = response.data[0]
                st.session_state["logged_in"] = True
                st.session_state["username"] = user_record["username"]
                # We save the ID (1) so we know who is doing the work later
                st.session_state["user_id"] = user_record["id"] 
                st.success(f"Welcome, {user_input}!")
                st.rerun()
            else:
                st.error("Invalid Username or Password")
        except Exception as e:
            st.error(f"Login Error: {e}")
    st.markdown('</div>', unsafe_allow_html=True)

if not st.session_state["logged_in"]:
    show_login()
    st.stop()
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
tab_route, tab_add, tab_invoice = st.tabs(["Today's Route", "Add Customer", "Invoicing"])

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
# -------------------------
# INVOICING TAB
# -------------------------
with tab_invoice:
    st.subheader("Create New Invoice")
    
    # Load customers for the dropdown
    all_customers = load_customers()
    if not all_customers:
        st.warning("No customers found. Add a customer first.")
    else:
        # Create a dictionary to map Names to IDs
        cust_options = {c['name']: c['id'] for c in all_customers}
        
        with st.form("new_invoice_form"):
            selected_name = st.selectbox("Select Customer", options=list(cust_options.keys()))
            bill_amount = st.number_input("Service Fee ($)", min_value=0.0, value=85.0, step=5.0)
            create_btn = st.form_submit_button("Generate Invoice Record")
            
            if create_btn:
                invoice_data = {
                    "customer_id": cust_options[selected_name],
                    "amount": bill_amount,
                    "status": "Unpaid"
                }
                # Insert into your new invoices table
                res = supabase.table("invoices").insert(invoice_data).execute()
                st.success(f"Invoice created for {selected_name}!")

    st.divider()
    
    # --- VIEW UNPAID INVOICES ---
    st.subheader("Outstanding Payments")
    # This query joins the invoices and customers table so we can see the name
    try:
        unpaid_res = supabase.table("invoices").select("*, customers(name)").eq("status", "Unpaid").execute()
        unpaid_list = unpaid_res.data if unpaid_res.data else []
        
        if not unpaid_list:
            st.info("All caught up! No unpaid invoices.")
        else:
            for inv in unpaid_list:
                # Create a 3-column layout for a clean look
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{inv['customers']['name']}**")
                c2.write(f"${inv['amount']}")
                
                # Manual "Mark Paid" button (no fees!)
                if c3.button("Confirm Paid", key=f"paid_{inv['id']}"):
                    supabase.table("invoices").update({"status": "Paid"}).eq("id", inv['id']).execute()
                    st.toast(f"Payment recorded for {inv['customers']['name']}!")
                    st.rerun()
    except Exception as e:
        st.error(f"Error loading invoices: {e}")