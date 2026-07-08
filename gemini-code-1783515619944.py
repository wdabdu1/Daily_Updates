import streamlit as st
import sqlite3
from datetime import datetime

# -------------------------------------------------------------------
# 1. DATABASE SETUP
# -------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('shipments.db')
    c = conn.cursor()
    # Create shipments table
    c.execute('''
        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_number TEXT UNIQUE,
            carrier TEXT,
            recipient TEXT,
            status TEXT,
            last_updated TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    return sqlite3.connect('shipments.db')

# -------------------------------------------------------------------
# 2. APP LAYOUT & DASHBOARD
# -------------------------------------------------------------------
st.set_page_config(page_title="Shipment Tracker", layout="wide")
st.title("📦 Internal Shipment Tracker")

# Sidebar for Navigation
menu = ["Dashboard & View", "Add New Shipment", "Update Status"]
choice = st.sidebar.selectbox("Navigation", menu)

# -------------------------------------------------------------------
# PAGE 1: DASHBOARD & VIEW
# -------------------------------------------------------------------
if choice == "Dashboard & View":
    st.subheader("Overview")
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get stats for KPI cards
    c.execute("SELECT COUNT(*) FROM shipments")
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM shipments WHERE status = 'In Transit'")
    in_transit = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM shipments WHERE status = 'Delivered'")
    delivered = c.fetchone()[0]
    
    # Display metrics side-by-side
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Shipments", total)
    col2.metric("🚚 In Transit", in_transit)
    col3.metric("✅ Delivered", delivered)
    
    st.markdown("---")
    st.subheader("All Active Shipments")
    
    # Display table of shipments
    c.execute("SELECT tracking_number, carrier, recipient, status, last_updated FROM shipments")
    data = c.fetchall()
    conn.close()
    
    if data:
        st.table([{"Tracking #": r[0], "Carrier": r[1], "Recipient": r[2], "Status": r[3], "Last Updated": r[4]} for r in data])
    else:
        st.info("No shipments found. Use the sidebar to add one!")

# -------------------------------------------------------------------
# PAGE 2: ADD NEW SHIPMENT
# -------------------------------------------------------------------
elif choice == "Add New Shipment":
    st.subheader("Register a New Package")
    
    with st.form("add_form", clear_on_submit=True):
        tracking_number = st.text_input("Tracking Number / Order ID")
        carrier = st.selectbox("Carrier", ["FedEx", "UPS", "DHL", "USPS", "Internal Delivery"])
        recipient = st.text_input("Recipient Name")
        status = st.selectbox("Initial Status", ["Pending", "Shipped", "In Transit"])
        
        submitted = st.form_submit_button("Save Shipment")
        
        if submitted:
            if tracking_number and recipient:
                try:
                    conn = get_db_connection()
                    c = conn.cursor()
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    c.execute(
                        "INSERT INTO shipments (tracking_number, carrier, recipient, status, last_updated) VALUES (?, ?, ?, ?, ?)",
                        (tracking_number, carrier, recipient, status, now)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Shipment {tracking_number} added successfully!")
                except sqlite3.IntegrityError:
                    st.error("This tracking number already exists!")
            else:
                st.warning("Please fill in all fields.")

# -------------------------------------------------------------------
# PAGE 3: UPDATE STATUS
# -------------------------------------------------------------------
elif choice == "Update Status":
    st.subheader("Update Shipment Progress")
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT tracking_number FROM shipments")
    tracking_numbers = [r[0] for r in c.fetchall()]
    conn.close()
    
    if not tracking_numbers:
        st.info("No shipments available to update.")
    else:
        selected_track = st.selectbox("Select Tracking Number", tracking_numbers)
        new_status = st.selectbox("New Status", ["Pending", "Shipped", "In Transit", "Out for Delivery", "Delivered", "Delayed"])
        
        if st.button("Update Status"):
            conn = get_db_connection()
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.execute(
                "UPDATE shipments SET status = ?, last_updated = ? WHERE tracking_number = ?",
                (new_status, now, selected_track)
            )
            conn.commit()
            conn.close()
            st.success(f"Updated {selected_track} to {new_status}!")