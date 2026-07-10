import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
import hashlib

# --- PRODUCTION CLOUD DATABASE SECURE FETCH ---
# Fetches the hidden URL string you saved in your Render Environment tab
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        st.error("Missing Database Connection! Please add the 'DATABASE_URL' environment variable inside your Render dashboard.")
        st.stop()
    return psycopg2.connect(DATABASE_URL)

def init_db(force_drop=False):
    conn = get_db_connection()
    c = conn.cursor()
    
    if force_drop:
        c.execute("DROP TABLE IF EXISTS shipments CASCADE;")
        c.execute("DROP TABLE IF EXISTS master_lists CASCADE;")
        c.execute("DROP TABLE IF EXISTS users CASCADE;")
    
    # 1. Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY, 
                    password TEXT, 
                    role TEXT)''')
    
    # 2. Master Dropdowns Table
    c.execute('''CREATE TABLE IF NOT EXISTS master_lists (
                    id SERIAL PRIMARY KEY,
                    list_type TEXT, 
                    item_value TEXT,
                    UNIQUE(list_type, item_value))''')
    
    # 3. Main Shipments Table (Cloud Optimized)
    c.execute('''CREATE TABLE IF NOT EXISTS shipments (
                    id SERIAL PRIMARY KEY, global_status TEXT, month TEXT, supplier TEXT, brand TEXT, cat TEXT, approval TEXT, model TEXT, type TEXT,
                    consignee TEXT, offshore_company TEXT, supplier_pi_no TEXT, supplier_pi_date TEXT, supplier_payment_terms TEXT, received_signed_pi_date TEXT, sent_signed_pi_date TEXT, 
                    bu_po_date TEXT, order_execution_date TEXT, latest_shipment_dt TEXT, incoterm TEXT, origin TEXT, ordered_qty NUMERIC, unit_price NUMERIC, total_value NUMERIC,
                    currency TEXT, bu_estimated_shipping_cost NUMERIC, actual_shipping_cost_usd NUMERIC, actual_shipping_cost_aed NUMERIC, amount_saved NUMERIC, forwarder_name TEXT, 
                    marine_insurance TEXT, draft_doc_recv_date TEXT, final_draft_documents TEXT, original_documents_rcvd_date TEXT, dhl_supplier_to_office TEXT, 
                    original_docs_sent_to_bank_date TEXT, dhl_office_to_adib TEXT, dhl_date_adib_to_ucb TEXT, dhl_adib_to_ucb TEXT, qty_shipped NUMERIC, unit_price_shipped NUMERIC,
                    total_shipped_value NUMERIC, supplier_invoice_no TEXT, supplier_invoice_date TEXT, etd TEXT, eta TEXT, logistics_status TEXT, b_l_no TEXT, bol_date TEXT, 
                    shipping_line TEXT, cntr_20ft TEXT, cntr_40ft TEXT, techuip_invoice_no TEXT, techuip_invoice_value NUMERIC, techuip_mot_approved_pi_no TEXT, techuip_mot_approved_pi_date TEXT,
                    mot_pi_quantity NUMERIC, approved_mot_unit_price_usd NUMERIC, approved_mot_total_price_usd NUMERIC, acd_cost_usd NUMERIC, due_date TEXT, due_amount NUMERIC, 
                    advance_payment NUMERIC, payment_date_adv TEXT, remaining_payment NUMERIC, payment_date_rem TEXT, remarks_finance TEXT, file_name TEXT, separator_no TEXT, 
                    orion_pr_no TEXT, orion_po_no TEXT, orion_sa TEXT, orion_grn TEXT, orion_bill_reg TEXT, orion_invoice_offshore1 TEXT, orion_invoice_offshore2 TEXT, 
                    inspection_no TEXT, grn_no TEXT, author TEXT, approved_by TEXT, remarks_general TEXT, mot TEXT)''')
    
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        hashed = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute("INSERT INTO users VALUES ('admin', %s, 'Admin')", (hashed,))
        seed_data = [
            ('global_status', 'In Progress'), ('global_status', 'Completed'),
            ('logistics_status', 'Pending'), ('logistics_status', 'Shipped'),
            ('currency', 'USD'), ('currency', 'AED')
        ]
        for item in seed_data:
            c.execute("INSERT INTO master_lists (list_type, item_value) VALUES (%s, %s) ON CONFLICT DO NOTHING", item)
            
    conn.commit()
    conn.close()

# Safe initial build check
try:
    init_db(force_drop=False)
except Exception as e:
    st.error(f"Database sync roadblock: {e}")

# --- DYNAMIC INTERFACE UTILITIES ---
def get_master_list(list_type):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT item_value FROM master_lists WHERE list_type=%s", conn, params=(list_type,))
    conn.close()
    return [""] + df['item_value'].tolist()

def add_master_item(list_type, val):
    if val:
        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO master_lists (list_type, item_value) VALUES (%s, %s) ON CONFLICT DO NOTHING", (list_type, val))
            conn.commit()
        except Exception:
            pass
        conn.close()

# --- SECURITY GATE ---
st.set_page_config(layout="wide", page_title="Global Shipment Tracker")
st.title("🚢 Corporate Shipment Supply Chain Tracker (Cloud Storage Live)")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.subheader("User Authentication")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        hashed = hashlib.sha256(password.encode()).hexdigest()
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT role FROM users WHERE username=%s AND password=%s", (username, hashed))
        user = c.fetchone()
        conn.close()
        if user:
            st.session_state['logged_in'] = True
            st.session_state['username'] = username
            st.session_state['role'] = user[0]
            st.rerun()
        else:
            st.error("Invalid username or password")
    st.stop()

# --- SIDEBAR NAV ---
st.sidebar.write(f"User: **{st.session_state['username']}** ({st.session_state['role']})")
if st.sidebar.button("Logout"):
    st.session_state['logged_in'] = False
    st.rerun()

menu = ["Dashboard View", "Add Shipment", "Bulk Upload (CSV/Excel)"]
if st.session_state['role'] == 'Admin':
    menu.append("Settings & Master Lists")

choice = st.sidebar.selectbox("Navigation Menu", menu)

# --- DASHBOARD DECK ---
if choice == "Dashboard View":
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM shipments ORDER BY id DESC", conn)
    conn.close()
    
    if df.empty:
        st.info("Cloud database is currently empty. Use 'Add Shipment' or 'Bulk Upload' to inject data rows.")
    else:
        # Dynamic Risk Engine Banner
        st.markdown("### 🔔 Operational Notifications")
        alerts = []
        for idx, row in df.iterrows():
            if row['logistics_status'] == 'Pending' and pd.notna(row['etd']) and row['etd'] != '':
                alerts.append(f"⚠️ **Delay Risk:** Shipment ID {row['id']} (Supplier: {row['supplier']}) is 'Pending' but has an ETD listed ({row['etd']}).")
            if row['logistics_status'] == 'Shipped' and (not row['b_l_no'] or row['b_l_no'] == ''):
                alerts.append(f"🛑 **Missing Documentation:** Shipment ID {row['id']} is 'Shipped' but has no B/L Number.")
            if pd.to_numeric(row['total_value'], errors='coerce') > 50000:
                alerts.append(f"💰 **High Value Alert:** Consignment ID {row['id']} exceeds $50,000 USD.")
        
        if alerts:
            for alert in alerts[:5]:
                st.warning(alert)
        else:
            st.success("✅ Clean Slate: No critical shipping or document discrepancies flagged.")
            
        st.markdown("---")
        
        # Reports Row
        st.markdown("### 📊 Executive Summary Reports")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Consignments", len(df))
        m2.metric("In Progress Status", len(df[df['global_status'] == 'In Progress']))
        
        total_val = pd.to_numeric(df['total_value'], errors='coerce').sum()
        total_saved = pd.to_numeric(df['amount_saved'], errors='coerce').sum()
        m3.metric("Total Value Managed ($)", f"${total_val:,.2f}")
        m4.metric("Total Shipping Cost Saved ($)", f"${total_saved:,.2f}")
        
        # Multi-filter block
        st.markdown("#### 🔍 Filter Panel")
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            filter_status = st.multiselect("Global Process Status", options=df['global_status'].unique())
        with f_col2:
            filter_supplier = st.multiselect("Filter by Supplier", options=df['supplier'].unique())
        with f_col3:
            filter_line = st.multiselect("Filter by Shipping Line", options=df['shipping_line'].unique())
            
        if filter_status: df = df[df['global_status'].isin(filter_status)]
        if filter_supplier: df = df[df['supplier'].isin(filter_supplier)]
        if filter_line: df = df[df['shipping_line'].isin(filter_line)]
            
        search_q = st.text_input("Global Keyword Search")
        if search_q:
            df = df[df.astype(str).apply(lambda x: x.str.contains(search_q, case=False)).any(axis=1)]
            
        st.markdown("#### 📦 Filtered Master Table View")
        st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export Current View to CSV Report", csv, "filtered_shipment_report.csv", "text/csv")

# --- MANUAL ENTRY FORM ---
elif choice == "Add Shipment":
    if st.session_state['role'] == 'Viewer':
        st.error("Action denied.")
    else:
        st.subheader("📝 Enter New Shipment Case Details")
        global_statuses = get_master_list('global_status')
        logistics_statuses = get_master_list('logistics_status')
        suppliers = get_master_list('supplier')
        brands = get_master_list('brand')
        forwarders = get_master_list('forwarder')
        lines = get_master_list('shipping_line')
        consignees = get_master_list('consignee')
        offshore_cos = get_master_list('offshore_company')
        currencies = get_master_list('currency')
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["1. Core Order Info", "2. Shipping & Logistics", "3. Document Custody & DHL", "4. Financial Matrix", "5. Orion ERP Sync"])
        
        with tab1:
            col1, col2, col3 = st.columns(3)
            with col1:
                g_status = st.selectbox("Global Process Status", global_statuses)
                month = st.text_input("Month")
                supplier = st.selectbox("Supplier", suppliers)
                brand = st.selectbox("Brand", brands)
            with col2:
                cat = st.text_input("Category (CAT)")
                approval = st.text_input("Approval Status")
                model = st.text_input("Model")
                item_type = st.text_input("Type")
            with col3:
                consignee = st.selectbox("Consignee", consignees)
                offshore_co = st.selectbox("Primary Offshore Company Involved", offshore_cos)
                ordered_qty = st.number_input("Ordered Qty", value=0.0)
                unit_price = st.number_input("Unit Price", value=0.0)
                total_value = st.number_input("Total Value", value=0.0)
                currency = st.selectbox("Currency", currencies)

        with tab2:
            col1, col2 = st.columns(2)
            with col1:
                log_status = st.selectbox("Logistics Status (Shipped/Pending)", logistics_statuses)
                incoterm = st.text_input("Incoterm")
                origin = st.text_input("Origin")
                forwarder = st.selectbox("Forwarder Name", forwarders)
                shipping_line = st.selectbox("Shipping Line", lines)
                bl_no = st.text_input("B/L No.")
                bol_date = st.text_input("BOL Date")
            with col2:
                etd = st.text_input("ETD")
                eta = st.text_input("ETA")
                cntr_20 = st.text_input("20 FT CNTR")
                cntr_40 = st.text_input("40 FT CNTR")
                bu_est_ship = st.number_input("BU Estimated Shipping Cost", value=0.0)
                act_ship_usd = st.number_input("Actual Shipping Cost USD", value=0.0)
                act_ship_aed = st.number_input("Actual Shipping Cost AED", value=0.0)
                amount_saved = bu_est_ship - act_ship_usd

        with tab3:
            col1, col2 = st.columns(2)
            with col1:
                draft_recv = st.text_input("Draft Doc Recv Date")
                final_draft = st.text_input("Final Draft Documents")
                orig_recv = st.text_input("Original Documents Rcvd Date")
                dhl_supp_office = st.text_input("DHL: Supplier to Office Tracking No.")
            with col2:
                docs_sent_bank_dt = st.text_input("Original Docs Sent to Bank Date")
                dhl_office_adib = st.text_input("DHL: Office to ADIB Tracking No.")
                dhl_dt_adib_ucb = st.text_input("DHL Date: ADIB to UCB")
                dhl_adib_ucb = st.text_input("DHL: ADIB to UCB Tracking No.")

        with tab4:
            col1, col2 = st.columns(2)
            with col1:
                supp_pi_no = st.text_input("Supplier PI No")
                supp_pi_date = st.text_input("Supplier PI Date")
                supp_pay_terms = st.text_input("Supplier Payment Terms")
                due_date = st.text_input("Due Date")
                due_amount = st.number_input("Due Amount", value=0.0)
            with col2:
                adv_payment = st.number_input("Advance Payment", value=0.0)
                rem_payment = st.number_input("Remaining Payment", value=0.0)
                techuip_inv = st.text_input("TECHUIP Invoice No.")
                techuip_val = st.number_input("TECHUIP Invoice Value $", value=0.0)

        with tab5:
            st.markdown("##### 🏢 Orion Routing Invoices")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Section A: Offshore Company 1**")
                orion_inv1 = st.text_input("Orion Invoice No (Offshore 1)")
                orion_pr = st.text_input("Orion PR No")
                orion_po = st.text_input("Orion PO No")
                orion_sa = st.text_input("Orion SA")
                orion_grn = st.text_input("Orion GRN")
            with col2:
                st.markdown("**Section B: Offshore Company 2**")
                orion_inv2 = st.text_input("Orion Invoice No (Offshore 2)")
                inspection_no = st.text_input("Inspection No.")
                grn_no = st.text_input("GRN No.")
                author = st.text_input("Author", value=st.session_state['username'])
                remarks_gen = st.text_area("General Remarks")

        if st.button("💾 Save Shipment Entry"):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO shipments (
                            global_status, month, supplier, brand, cat, approval, model, type, consignee, offshore_company,
                            ordered_qty, unit_price, total_value, currency, logistics_status, incoterm, origin, forwarder_name,
                            shipping_line, b_l_no, bol_date, etd, eta, cntr_20ft, cntr_40ft, bu_estimated_shipping_cost,
                            actual_shipping_cost_usd, actual_shipping_cost_aed, amount_saved, draft_doc_recv_date, final_draft_documents,
                            original_documents_rcvd_date, dhl_supplier_to_office, original_docs_sent_to_bank_date, dhl_office_to_adib,
                            dhl_date_adib_to_ucb, dhl_adib_to_ucb, supplier_pi_no, supplier_pi_date, supplier_payment_terms,
                            due_date, due_amount, advance_payment, remaining_payment, techuip_invoice_no, techuip_invoice_value,
                            orion_pr_no, orion_po_no, orion_sa, orion_grn, orion_invoice_offshore1, orion_invoice_offshore2, 
                            inspection_no, grn_no, author, remarks_general
                         ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                      (g_status, month, supplier, brand, cat, approval, model, item_type, consignee, offshore_co,
                       ordered_qty, unit_price, total_value, currency, log_status, incoterm, origin, forwarder,
                       shipping_line, bl_no, bol_date, etd, eta, cntr_20, cntr_40, bu_est_ship,
                       act_ship_usd, act_ship_aed, amount_saved, draft_recv, final_draft,
                       orig_recv, dhl_supp_office, docs_sent_bank_dt, dhl_office_adib,
                       dhl_dt_adib_ucb, dhl_adib_ucb, supp_pi_no, supp_pi_date, supp_pay_terms,
                       due_date, due_amount, adv_payment, rem_payment, techuip_inv, techuip_val,
                       orion_pr, orion_po, orion_sa, orion_grn, orion_inv1, orion_inv2, 
                       inspection_no, grn_no, author, remarks_gen))
            conn.commit()
            conn.close()
            st.success("Shipment added securely to Cloud Storage!")

# --- BULK UPLOAD ---
elif choice == "Bulk Upload (CSV/Excel)":
    if st.session_state['role'] == 'Viewer':
        st.error("Permission denied.")
    else:
        st.subheader("📥 Mass Excel / CSV Data Upload")
        uploaded_file = st.file_uploader("Choose a file", type=['csv', 'xlsx'])
        if uploaded_file is not None:
            try:
                uploaded_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                st.write("Preview of Uploaded Data:")
                st.dataframe(uploaded_df.head())
                
                if st.button("Confirm and Append to Cloud Storage"):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    # Columns configuration matching cloud schema
                    columns = [c for c in uploaded_df.columns if c in [
                        'global_status', 'month', 'supplier', 'brand', 'cat', 'approval', 'model', 'type', 'consignee', 'offshore_company',
                        'ordered_qty', 'unit_price', 'total_value', 'currency', 'logistics_status', 'orion_invoice_offshore1', 'orion_invoice_offshore2'
                    ]]
                    
                    for _, row in uploaded_df[columns].iterrows():
                        row_vals = [None if pd.isna(val) else val for val in row.values]
                        placeholders = ", ".join(["%s"] * len(columns))
                        sql = f"INSERT INTO shipments ({', '.join(columns)}) VALUES ({placeholders})"
                        cursor.execute(sql, row_vals)
                        
                    conn.commit()
                    conn.close()
                    st.success("Successfully processed and saved records to database cloud!")
            except Exception as e:
                st.error(f"Error parsing dataset parsing structure: {e}")

# --- SYSTEM SETTINGS PANEL ---
elif choice == "Settings & Master Lists":
    st.subheader("⚙️ Control Dashboard Master Lists")
    
    # SYSTEM RESET TRIGGER (FOR CLEAN REBOOTS FROM SCRATCH)
    st.markdown("### ⚠️ Danger Zone")
    st.markdown("Need to change headers, start an entirely new layout, or clear out experimental data? Use this button to clear the tables.")
    if st.button("💣 Nuke & Reset Database Structure"):
        try:
            init_db(force_drop=True)
            st.success("Cloud database successfully wiped clean! The app schema has been rebuilt from scratch.")
            st.rerun()
        except Exception as e:
            st.error(f"Reset failed: {e}")
            
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        list_choice = st.selectbox("Select List to Manage", [
            ('supplier', 'Suppliers List'), ('brand', 'Brands List'), ('forwarder', 'Forwarders List'),
            ('shipping_line', 'Shipping Lines List'), ('consignee', 'Consignees List'),
            ('offshore_company', 'Internal Offshore Companies'), ('global_status', 'Global System Process Statuses'),
            ('logistics_status', 'Logistics Step Statuses')
        ], format_func=lambda x: x[1])
        new_item = st.text_input(f"Add New Entry to {list_choice[1]}")
        if st.button("Add to Dropdowns"):
            add_master_item(list_choice[0], new_item)
            st.success(f"Added '{new_item}' successfully!")
    with col2:
        st.write("Current configured values:")
        st.write(get_master_list(list_choice[0])[1:])
