import streamlit as st
from datetime import datetime
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from email.message import EmailMessage
import smtplib
from supabase import create_client, Client

# -------------------------
# CONFIG
# -------------------------
TODAY = datetime.now().strftime("%A")

# Secrets from Streamlit Cloud
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
ORS_API_KEY = st.secrets.get("ORS_API_KEY", "")
EMAIL_USER = st.secrets["EMAIL_USER"]
EMAIL_PASS = st.secrets["EMAIL_PASS"]
OFFICE_LOCATION = tuple(map(float, st.secrets.get("OFFICE_LOCATION", "30.2127,-85.8350").split(",")))

# Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SMTP_SERVER = "mail.spacemail.com"
SMTP_PORT = 465

# -------------------------
# EMAIL FUNCTION
# -------------------------
def send_report(to_email, name, notes, photo_file):
    msg = EmailMessage()
    msg["Subject"] = f"Bayco Pools Service Report: {name}"
    msg["From"] = EMAIL_USER
    msg["To"] = to_email
    msg.set_content(f"Hi {name},\n\nYour pool service is complete!\n\nNotes:\n{notes}\n\nHave a great day!")

    if photo_file and photo_file.type:
        file_data = photo_file.read()
        photo_file.seek(0)
        maintype, subtype = photo_file.type.split("/")
        msg.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=photo_file.name)

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

# -------------------------
# LOAD CUSTOMERS
# -------------------------
def load_customers():
    response = supabase.table("customers").select("*").execute()
    if response.error:
        st.error(f"Error loading customers: {response.error}")
        return []
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "address": r["address"],
            "email": r["email"],
            "coords": (r["lat"], r["lon"]),
            "service_day": r["service_day"],
            "active": r["active"],
            "cleaning_started": r["cleaning_started"]
        }
        for r in response.data
    ]

# -------------------------
# LOGIN
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
        """,
        unsafe_allow_html=True
    )
    st.markdown('<div class="login-container">', unsafe_allow_html=True)

    st.subheader("🌴 Bayco Pools Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_button = st.button("Login")

    if login_button:
        # Authenticate against Supabase "users" table
        response = supabase.table("users").select("*").eq("username", username).execute()
        if response.data and response.data[0]["password"] == password:
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["user_role"] = response.data[0]["role"]
            st.session_state["active_tab"] = "route"  # ✅ Directly jump to route page
        else:
            st.error("Invalid credentials")

    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------
# STREAMLIT APP
# -------------------------
st.set_page_config(page_title="Bayco Pools", page_icon="assets/favicon.png")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "route"

# Show login if not logged in
if not st.session_state["logged_in"]:
    show_login()
else:
    st.sidebar.subheader(f"Logged in as {st.session_state['username']} ({st.session_state['user_role']})")

    # Tabs or sections
    active_tab = st.session_state["active_tab"]

    if active_tab == "route":
        st.subheader(f"🧹 Route for {TODAY}")
        all_customers = load_customers()
        route_customers = [c for c in all_customers if c["service_day"] == TODAY and c["active"]]

        if not route_customers:
            st.info(f"No customers scheduled for {TODAY}.")
        else:
            for c in route_customers:
                c["dist"] = geodesic(OFFICE_LOCATION, c["coords"]).miles

            route_customers = sorted(route_customers, key=lambda x: x["dist"], reverse=True)

            for i, cust in enumerate(route_customers):
                with st.expander(f"📍 {cust['name']} ({round(cust['dist'],1)} mi)"):
                    st.write(f"**Address:** {cust['address']}")
                    st.write(f"**Email:** {cust['email']}")
                    notes = st.text_area("Notes", key=f"notes_{i}")
                    photo = st.file_uploader("Upload Pool Photo", type=["jpg","png"], key=f"img_{i}")

                    if st.button("Finish & Email", key=f"finish_{i}"):
                        if send_report(cust["email"], cust["name"], notes, photo):
                            st.success(f"Sent to {cust['name']}!")
