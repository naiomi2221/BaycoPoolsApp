import streamlit as st

# -------------------------
# CONFIG
# -------------------------
st.set_page_config(page_title="Bayco Pools Login", page_icon="🌴", layout="wide")

# Tropical background image (hosted URL, safe for Streamlit Cloud)
BACKGROUND_URL = "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1200&q=80"

# -------------------------
# USER SECRETS
# -------------------------
# Add these to your Streamlit Secrets:
# [USERS]
# admin_user = "Naiomi"
# admin_password = "Haley!5301"
# tech_user = "Tech1"
# tech_password = "TechPass123"

USERS = {
    st.secrets["USERS"]["admin_user"]: st.secrets["USERS"]["admin_password"],
    st.secrets["USERS"]["tech_user"]: st.secrets["USERS"]["tech_password"],
}

# -------------------------
# SESSION STATE
# -------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_role" not in st.session_state:
    st.session_state.user_role = None

# -------------------------
# LOGIN FUNCTION
# -------------------------
def login(username, password):
    if username in USERS and USERS[username] == password:
        st.session_state.logged_in = True
        # Simple role detection
        st.session_state.user_role = "admin" if "admin" in username.lower() else "tech"
        st.success(f"Welcome, {username}!")
    else:
        st.error("Invalid username or password")

# -------------------------
# LOGIN UI
# -------------------------
if not st.session_state.logged_in:
    st.image(BACKGROUND_URL, use_column_width=True)
    st.markdown("<h1 style='text-align:center; color:white;'>🌊 Bayco Pools Manager 🌴</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:white;'>Login below to access your dashboard</p>", unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            login(username, password)

# -------------------------
# DASHBOARD
# -------------------------
if st.session_state.logged_in:
    st.markdown(f"## Hello, {st.session_state.user_role.title()}! 🏖️")
    st.markdown("Use the sidebar to navigate your dashboard.")

    # Example sidebar
    if st.session_state.user_role == "admin":
        st.sidebar.header("Admin Menu")
        st.sidebar.button("Manage Clients")
        st.sidebar.button("View Routes")
    else:
        st.sidebar.header("Tech Menu")
        st.sidebar.button("Today's Route")
