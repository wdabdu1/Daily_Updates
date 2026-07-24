import streamlit as st
import pandas as pd

# Page Configuration
st.set_page_config(page_title="Purchase Order & Shipment Manager", layout="wide")


# -----------------------------------------------------------------------------
# HELPER FUNCTIONS (Fat-Finger Prevention & Formatting)
# -----------------------------------------------------------------------------
def parse_formatted_float(val_str: str) -> float:
    """Safely converts input strings containing commas or currency symbols to float."""
    if not val_str:
        return 0.0
    cleaned = str(val_str).replace(",", "").replace("$", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def live_comma_input(label: str, key: str, default_val: float = 0.0) -> float:
    """
    Renders a text_input that accepts comma-formatted numbers,
    prevents conversion errors, and displays formatted feedback live.
    """
    initial_str = f"{default_val:,.2f}" if default_val else "0.00"
    raw_input = st.text_input(label, value=initial_str, key=key)
    parsed_val = parse_formatted_float(raw_input)
    st.caption(f"💡 Recognized Value: **${parsed_val:,.2f}**")
    return parsed_val


# -----------------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# -----------------------------------------------------------------------------
if "master_orders" not in st.session_state:
    st.session_state.master_orders = []

if "shipment_items" not in st.session_state:
    st.session_state.shipment_items = [
        {"Item ID": "ITEM-101", "Description": "Pump Spare Part", "Qty": 10, "Unit Price ($)": 150.00},
        {"Item ID": "ITEM-102", "Description": "Flange Adapter", "Qty": 25, "Unit Price ($)": 45.00}
    ]

st.title("📦 Purchase Order & Logistics Workflow System")

# -----------------------------------------------------------------------------
# MAIN TABS LAYOUT
# -----------------------------------------------------------------------------
tab_master, tab_line_entry, tab_registry = st.tabs([
    "📋 Master Purchase Order", 
    "📑 Line Item Entry", 
    "🗂️ Order registry"
])

# =============================================================================
# TAB 1: MASTER PURCHASE ORDER
# =============================================================================
with tab_master:
    st.header("Master Purchase Order Entry")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Explicit unique keys prevent StreamlitDuplicateElementId errors
        po_number = st.text_input("PO Number", key="mpo_po_number_input")
        supplier = st.text_input("Supplier Name", key="mpo_supplier_input")
        
        # Fixed Line 1323 Duplicate ID error by giving a explicit unique key
        mot_ref_no = st.text_input("MOT Ref No", key="mpo_mot_ref_no_input")

    with col2:
        st.subheader("SSMO Cost Calculation (SDG → USD)")
        
        # Live formatted inputs to prevent numeric typing errors
        ssmo_cost_sdg = live_comma_input("SSMO Cost (SDG)", key="ssmo_cost_sdg_input", default_val=1000000.00)
        sdg_to_usd_rate = st.number_input(
            "Exchange Rate (1 SDG to USD)", 
            min_value=0.0, 
            value=0.0016, 
            format="%.6f", 
            key="sdg_usd_rate_input"
        )
        
        # Calculate USD Equivalent
        ssmo_cost_usd = ssmo_cost_sdg * sdg_to_usd_rate
        st.metric("SSMO Cost Equivalent (USD)", f"${ssmo_cost_usd:,.2f}")

    st.markdown("---")
    
    # Save Master Order Action
    if st.button("Save Master Order", key="btn_save_master_order"):
        if not po_number:
            st.warning("Please enter a valid PO Number before saving.")
        else:
            new_master_order = {
                "PO Number": po_number,
                "Supplier": supplier,
                "MOT Ref No": mot_ref_no,
                "SSMO Cost (SDG)": f"{ssmo_cost_sdg:,.2f}",
                "SSMO Cost (USD)": f"${ssmo_cost_usd:,.2f}"
            }
            st.session_state.master_orders.append(new_master_order)
            st.success("Order created.")


# =============================================================================
# TAB 2: LINE ITEM ENTRY & FORWARDER GROUP
# =============================================================================
with tab_line_entry:
    st.header("Line Item Entry & Shipping Workflow")
    
    # Forwarder Group Section
    st.subheader("Forwarder Group")
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        base_freight_cost = live_comma_input("Current Freight Base Rate ($)", key="fwd_base_rate_input", default_val=2500.00)
    with col_f2:
        current_surcharges = live_comma_input("Current Surcharges / Fees ($)", key="fwd_surcharges_input", default_val=350.00)
    with col_f3:
        # Calculate $ actual shipping Cost
        actual_shipping_cost = base_freight_cost + current_surcharges
        st.metric(label="Actual Shipping Cost ($)", value=f"${actual_shipping_cost:,.2f}")

    st.markdown("---")
    
    # Active Line Items Table
    st.subheader("Current Line Items in Shipment")
    if st.session_state.shipment_items:
        df_shipment = pd.DataFrame(st.session_state.shipment_items)
        st.dataframe(df_shipment, use_container_width=True)
    else:
        st.info("No items currently in shipment table.")

    # Create Shipment & Initialise Workflow Button
    if st.button("Create Shipment & Initialise Workflow tasks", key="btn_create_shipment_workflow"):
        st.success("Shipment is Created")
        # Clear table
        st.session_state.shipment_items = []
        st.rerun()


# =============================================================================
# TAB 3: ORDER REGISTRY
# =============================================================================
with tab_registry:
    st.header("Order registry")
    
    # User selection for View Mode
    registry_view = st.radio(
        "Select Registry View:",
        options=["Master orders", "By Line item select from Master orders"],
        horizontal=True,
        key="registry_view_toggle"
    )
    
    st.markdown("---")
    
    if registry_view == "Master orders":
        st.subheader("Master Orders Overview")
        if st.session_state.master_orders:
            df_masters = pd.DataFrame(st.session_state.master_orders)
            st.dataframe(df_masters, use_container_width=True)
        else:
            st.info("No Master Orders found. Create one in the 'Master Purchase Order' tab.")
            
    elif registry_view == "By Line item select from Master orders":
        st.subheader("Detailed Line Items by Master Order")
        
        if st.session_state.master_orders:
            po_options = [order["PO Number"] for order in st.session_state.master_orders]
            selected_po = st.selectbox("Select Master Order (PO):", options=po_options, key="registry_po_select")
            
            # Detailed view table for selected Master Order
            st.write(f"Displaying Line Items for **PO: {selected_po}**")
            
            line_item_details = pd.DataFrame([
                {"PO Number": selected_po, "Line Item ID": "L-101", "Item Description": "Hydraulic Valve", "Qty": 5, "Unit Price ($)": "250.00"},
                {"PO Number": selected_po, "Line Item ID": "L-102", "Item Description": "Pressure Gauge", "Qty": 12, "Unit Price ($)": "85.00"}
            ])
            st.dataframe(line_item_details, use_container_width=True)
        else:
            st.info("No Master Orders available to select from.")
