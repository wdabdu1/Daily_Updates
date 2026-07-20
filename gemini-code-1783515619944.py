from datetime import date
import hashlib
import os
import pandas as pd
import psycopg2
import streamlit as st

# --- PRODUCTION CLOUD DATABASE CONNECTION ---
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        st.error(
            "Missing Database Connection! Please add the 'DATABASE_URL' environment variable inside your Render dashboard."
        )
        st.stop()
    return psycopg2.connect(DATABASE_URL)


def init_db(force_drop=False):
    conn = get_db_connection()
    c = conn.cursor()

    if force_drop:
        c.execute(
            "DROP TABLE IF EXISTS audit_logs, financial_ledger, shipment_tasks, shipment_contents, shipments, order_items, product_catalog, master_orders, users, holiday_calendar, task_definitions, ref_lists, currency_rates CASCADE;"
        )

    # 1. Users Table
    c.execute("""CREATE TABLE IF NOT EXISTS users (
                    user_id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE, 
                    password TEXT, 
                    role VARCHAR(50),
                    scope_bu_id VARCHAR(50))""")

    # 2. Ref Lists Table
    c.execute("""CREATE TABLE IF NOT EXISTS ref_lists (
                    id SERIAL PRIMARY KEY,
                    category VARCHAR(50), 
                    item_name VARCHAR(100),
                    is_active BOOLEAN DEFAULT TRUE)""")

    # 3. Product Catalog Table
    c.execute("""CREATE TABLE IF NOT EXISTS product_catalog (
                    product_id SERIAL PRIMARY KEY,
                    bu_id VARCHAR(50),
                    brand_manuf VARCHAR(100),
                    category VARCHAR(100),
                    model_code VARCHAR(100) UNIQUE,
                    description TEXT)""")

    # 4. Master Orders Table
    c.execute("""CREATE TABLE IF NOT EXISTS master_orders (
                    order_id SERIAL PRIMARY KEY, 
                    po_number VARCHAR(50) UNIQUE, 
                    bu_id VARCHAR(50), 
                    division VARCHAR(100),
                    supplier_id VARCHAR(100), 
                    po_date DATE,
                    currency VARCHAR(20), 
                    incoterm VARCHAR(50), 
                    approval_type VARCHAR(50),
                    consignee VARCHAR(100),
                    offshore_company VARCHAR(100),
                    payment_terms VARCHAR(100),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)""")

    # 5. Order Items Table
    c.execute("""CREATE TABLE IF NOT EXISTS order_items (
                    item_id SERIAL PRIMARY KEY, 
                    order_id INTEGER REFERENCES master_orders(order_id) ON DELETE CASCADE, 
                    model_product VARCHAR(100), 
                    category VARCHAR(100),
                    item_type VARCHAR(100),
                    ordered_qty NUMERIC(15, 2), 
                    supplier_unit_price NUMERIC(15, 2))""")

    # 6. Task Definitions
    c.execute("""CREATE TABLE IF NOT EXISTS task_definitions (
                    task_def_id SERIAL PRIMARY KEY,
                    step_order INT,
                    task_name VARCHAR(100),
                    department VARCHAR(50),
                    sla_days INT)""")

    c.execute("SELECT COUNT(*) FROM task_definitions")
    if c.fetchone()[0] == 0:
        default_tasks = [
            (1, "ACD Approval", "Compliance", 2),
            (2, "SSMO License & Exemption", "Regulatory", 3),
            (3, "Customs Duty Assessment", "Customs", 2),
            (4, "Port Release & Payment", "Logistics", 2),
            (5, "Final Warehouse Delivery", "Operations", 1),
        ]
        for t in default_tasks:
            c.execute(
                "INSERT INTO task_definitions (step_order, task_name, department, sla_days) VALUES (%s, %s, %s, %s)",
                t,
            )

    # 7. Shipments Table
    c.execute("""CREATE TABLE IF NOT EXISTS shipments (
                    shipment_id SERIAL PRIMARY KEY,
                    shipment_ref VARCHAR(50),
                    order_id INTEGER REFERENCES master_orders(order_id) ON DELETE CASCADE,
                    bl_awb VARCHAR(100),
                    eta DATE,
                    status VARCHAR(50) DEFAULT 'In Clearance',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)""")

    # 8. Shipment Contents Table
    c.execute("""CREATE TABLE IF NOT EXISTS shipment_contents (
                    content_id SERIAL PRIMARY KEY,
                    shipment_id INTEGER REFERENCES shipments(shipment_id) ON DELETE CASCADE,
                    item_id INTEGER REFERENCES order_items(item_id),
                    shipped_qty NUMERIC(15, 2))""")

    # 9. Shipment Clearance Tasks Table
    c.execute("""CREATE TABLE IF NOT EXISTS shipment_tasks (
                    task_id SERIAL PRIMARY KEY,
                    shipment_id INTEGER REFERENCES shipments(shipment_id) ON DELETE CASCADE,
                    step_order INT,
                    task_name VARCHAR(100),
                    department VARCHAR(50),
                    status VARCHAR(50) DEFAULT 'Pending',
                    notes TEXT,
                    completed_at TIMESTAMP WITH TIME ZONE)""")

    # 10. Currency Rates Table
    c.execute("""CREATE TABLE IF NOT EXISTS currency_rates (
                    currency VARCHAR(20) PRIMARY KEY,
                    rate_to_usd NUMERIC(15, 6) DEFAULT 1.0,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)""")

    # Seed Admin user if missing
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        hashed = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute(
            "INSERT INTO users (username, password, role) VALUES ('admin', %s, 'Admin')",
            (hashed,),
        )

    # Seed reference dropdowns ONLY IF empty
    c.execute("SELECT COUNT(*) FROM ref_lists")
    if c.fetchone()[0] == 0:
        seed_ref = [
            ("BU", "Consumer Electronics"),
            ("BU", "Heavy Machinery"),
            ("Off Shore Companies", "Global Trading FZE"),
            ("Off Shore Companies", "Apex Holdings Ltd"),
            ("Consignee", "Primary Logistics Warehouse"),
            ("Consignee", "Regional Distribution Hub"),
            ("Div", "Retail Operations"),
            ("Div", "Industrial Sales"),
            ("Supplier", "Global Tech Offshore"),
            ("Supplier", "Industrial Parts LLC"),
            ("Brand/Manuf.", "Lenovo"),
            ("Brand/Manuf.", "Apple"),
            ("Brand/Manuf.", "Caterpillar"),
            ("Approval Type", "Standard"),
            ("Approval Type", "Director"),
            ("Payment Terms", "30 Days Net"),
            ("Payment Terms", "Letter of Credit"),
            ("INCOTERM", "FOB"),
            ("INCOTERM", "CIF"),
            ("ORIGINs", "China"),
            ("ORIGINs", "Germany"),
            ("ORIGINs", "USA"),
            ("Category", "Electronics"),
            ("Category", "Machinery"),
            ("Type", "Finished Good"),
            ("Type", "Spare Part"),
            ("CURRENCY", "USD"),
            ("CURRENCY", "EUR"),
            ("CURRENCY", "SDG"),
            ("Mode of Shipment", "Sea Freight"),
            ("Mode of Shipment", "Air Freight"),
            ("Shipping Lines", "Maersk"),
            ("Shipping Lines", "MSC"),
            ("Forwarders", "DHL Logistics"),
            ("Forwarders", "Kuehne + Nagel"),
            ("Sender Banks", "HSBC NY"),
            ("Receiving Banks", "Standard Chartered"),
            ("Tenor", "90 Days"),
        ]
        for r in seed_ref:
            c.execute(
                "INSERT INTO ref_lists (category, item_name) VALUES (%s, %s)",
                r,
            )

    # Seed default currency exchange rates
    c.execute("SELECT COUNT(*) FROM currency_rates")
    if c.fetchone()[0] == 0:
        default_rates = [("USD", 1.0), ("EUR", 0.92), ("SDG", 600.0)]
        for curr, r in default_rates:
            c.execute(
                "INSERT INTO currency_rates (currency, rate_to_usd) VALUES (%s, %s) ON CONFLICT (currency) DO NOTHING",
                (curr, r),
            )

    # Seed catalog items ONLY IF empty
    c.execute("SELECT COUNT(*) FROM product_catalog")
    if c.fetchone()[0] == 0:
        seed_catalog = [
            ("Consumer Electronics", "Lenovo", "Electronics", "LAP-100", "ThinkPad T14 Laptop"),
            ("Consumer Electronics", "Apple", "Electronics", "LAP-200", "MacBook Pro 16 Inch"),
            ("Heavy Machinery", "Caterpillar", "Machinery", "MOT-550", "Heavy Duty Motor Unit"),
        ]
        for p in seed_catalog:
            c.execute(
                "INSERT INTO product_catalog (bu_id, brand_manuf, category, model_code, description) VALUES (%s, %s, %s, %s, %s)",
                p,
            )

    conn.commit()
    conn.close()


# Initialize Schema
try:
    init_db(force_drop=False)
except Exception as e:
    st.error(f"Database sync check: {e}")


# --- DYNAMIC INTERFACE UTILITIES ---
def get_ref_list(category):
    conn = get_db_connection()
    df = pd.read_sql_query(
        "SELECT DISTINCT item_name FROM ref_lists WHERE category=%s AND is_active=TRUE ORDER BY item_name",
        conn,
        params=(category,),
    )
    conn.close()
    return df["item_name"].tolist()


def add_ref_item(category, val):
    if val:
        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO ref_lists (category, item_name) VALUES (%s, %s)",
                (category, val),
            )
            conn.commit()
        except Exception:
            pass
        conn.close()


def get_fx_rates():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT currency, rate_to_usd FROM currency_rates", conn)
    conn.close()
    rates = dict(zip(df["currency"], df["rate_to_usd"]))
    rates["USD"] = 1.0
    return rates


# --- APP LAYOUT & CONFIG ---
st.set_page_config(layout="wide", page_title="Corporate Supply Chain Tracker")
st.title("🚢 Corporate Supply Chain Tracker")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.subheader("User Authentication")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        hashed = hashlib.sha256(password.encode()).hexdigest()
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT role FROM users WHERE username=%s AND password=%s",
            (username, hashed),
        )
        user = c.fetchone()
        conn.close()
        if user:
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["role"] = user[0]
            st.rerun()
        else:
            st.error("Invalid username or password")
    st.stop()

# --- NAVIGATION ---
st.sidebar.write(
    f"User: **{st.session_state['username']}** ({st.session_state['role']})"
)
if st.sidebar.button("Logout"):
    st.session_state["logged_in"] = False
    st.rerun()

menu = [
    "Master Orders Dashboard",
    "Create Master Order",
    "Shipments & Task Manager",
]
if st.session_state["role"] == "Admin":
    menu.append("Settings & Product Catalog")

choice = st.sidebar.selectbox("Navigation Menu", menu)

# --- 1. MASTER ORDERS DASHBOARD ---
if choice == "Master Orders Dashboard":
    st.subheader("📦 Master Orders Overview")
    fx_rates = get_fx_rates()

    conn = get_db_connection()
    orders_df = pd.read_sql_query(
        """
        SELECT mo.po_number AS "PO Number", 
               mo.po_date AS "PO Date", 
               mo.bu_id AS "BU", 
               mo.division AS "Division", 
               mo.supplier_id AS "Supplier", 
               mo.consignee AS "Consignee", 
               mo.offshore_company AS "Offshore Company", 
               mo.incoterm AS "Incoterm", 
               mo.payment_terms AS "Payment Terms", 
               mo.approval_type AS "Approval Type",
               COUNT(oi.item_id) AS "Total Line Items",
               COALESCE(SUM(oi.ordered_qty * oi.supplier_unit_price), 0) AS "Total Order Value",
               mo.currency AS "Currency"
        FROM master_orders mo
        LEFT JOIN order_items oi ON mo.order_id = oi.order_id
        GROUP BY mo.order_id, mo.po_number, mo.po_date, mo.bu_id, mo.division, mo.supplier_id, 
                 mo.consignee, mo.offshore_company, mo.currency, mo.incoterm, mo.payment_terms, mo.approval_type
        ORDER BY mo.order_id DESC
    """,
        conn,
    )

    if orders_df.empty:
        st.info("No Master Orders found. Use 'Create Master Order' to add one.")
    else:
        # Calculate Value ($) based on FX rates
        values_usd = []
        for _, row in orders_df.iterrows():
            curr = row["Currency"] if row["Currency"] in fx_rates else "USD"
            rate = float(fx_rates.get(curr, 1.0))
            rate = rate if rate > 0 else 1.0
            values_usd.append(float(row["Total Order Value"]) / rate)

        orders_df["Value ($)"] = values_usd

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Master Orders", len(orders_df))
        total_val_usd = sum(values_usd)
        m2.metric("Total Value Managed (USD)", f"${total_val_usd:,.2f}")
        m3.metric("Total Line Items", int(orders_df["Total Line Items"].sum()))

        st.markdown("---")
        
        # Clean Table with '#' sequence column and correct column ordering
        view_orders_df = orders_df.copy()
        view_orders_df.insert(0, "#", range(1, 1 + len(view_orders_df)))
        
        st.dataframe(
            view_orders_df,
            column_config={
                "#": st.column_config.NumberColumn("#", format="%d"),
                "Total Order Value": st.column_config.NumberColumn("Total Order Value", format="%,.2f"),
                "Currency": st.column_config.TextColumn("Currency"),
                "Value ($)": st.column_config.NumberColumn("Value ($)", format="$%,.2f"),
                "Total Line Items": st.column_config.NumberColumn("Total Line Items", format="%d"),
            },
            use_container_width=True,
            hide_index=True
        )

        selected_po = st.selectbox(
            "Select PO to View Line Items", orders_df["PO Number"].tolist()
        )
        if selected_po:
            items_df = pd.read_sql_query(
                """
                SELECT oi.model_product AS "Model / Product", 
                       oi.category AS "Category", 
                       oi.item_type AS "Type",
                       oi.ordered_qty AS "Ordered Qty", 
                       oi.supplier_unit_price AS "Unit Price", 
                       (oi.ordered_qty * oi.supplier_unit_price) AS "Line Total",
                       mo.currency AS "Currency"
                FROM order_items oi
                JOIN master_orders mo ON oi.order_id = mo.order_id
                WHERE mo.po_number = %s
                ORDER BY oi.item_id ASC
            """,
                conn,
                params=(selected_po,),
            )
            
            po_curr = items_df["Currency"].iloc[0] if not items_df.empty else "USD"
            rate = float(fx_rates.get(po_curr, 1.0))
            rate = rate if rate > 0 else 1.0

            items_df["Value ($)"] = items_df["Line Total"] / rate
            items_df.insert(0, "#", range(1, 1 + len(items_df)))
            
            st.write(f"**Baseline Order Details for PO:** `{selected_po}`")
            st.dataframe(
                items_df,
                column_config={
                    "#": st.column_config.NumberColumn("#", format="%d"),
                    "Ordered Qty": st.column_config.NumberColumn("Ordered Qty", format="%,.2f"),
                    "Unit Price": st.column_config.NumberColumn("Unit Price", format="%,.2f"),
                    "Line Total": st.column_config.NumberColumn("Line Total", format="%,.2f"),
                    "Value ($)": st.column_config.NumberColumn("Value ($)", format="$%,.2f"),
                },
                use_container_width=True,
                hide_index=True
            )

    conn.close()

# --- 2. CREATE MASTER ORDER FORM ---
elif choice == "Create Master Order":
    if st.session_state["role"] == "Viewer":
        st.error("Action denied: Viewer role cannot create orders.")
    else:
        st.subheader("📝 Create New Master Order")

        bu_options = get_ref_list("BU")
        div_options = get_ref_list("Div")
        supplier_options = get_ref_list("Supplier")
        consignee_options = get_ref_list("Consignee")
        offshore_options = get_ref_list("Off Shore Companies")
        payment_options = get_ref_list("Payment Terms")
        incoterm_options = get_ref_list("INCOTERM")
        currency_options = get_ref_list("CURRENCY")
        approval_options = get_ref_list("Approval Type")
        type_options = get_ref_list("Type")

        st.markdown("### 1. Header Details")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            selected_bu = st.selectbox(
                "Business Unit (BU) *", bu_options if bu_options else ["Default BU"]
            )
            po_number = st.text_input("PO Number *")
            consignee = st.selectbox(
                "Consignee", consignee_options if consignee_options else ["Default Consignee"]
            )
            incoterm = st.selectbox(
                "Incoterm", incoterm_options if incoterm_options else ["FOB", "CIF"]
            )
        with c2:
            division = st.selectbox(
                "Division", div_options if div_options else ["Default Div"]
            )
            po_date = st.date_input("PO Date *", value=date.today())
            offshore_company = st.selectbox(
                "Off Shore Company", offshore_options if offshore_options else ["Default Offshore"]
            )
            currency = st.selectbox(
                "Currency", currency_options if currency_options else ["USD", "EUR"]
            )
        with c3:
            supplier_id = st.selectbox(
                "Supplier *", supplier_options if supplier_options else ["Default Supplier"]
            )
            approval_type = st.selectbox(
                "Approval Type", approval_options if approval_options else ["Standard"]
            )
            payment_terms = st.selectbox(
                "Payment Terms", payment_options if payment_options else ["30 Days Net"]
            )

        conn = get_db_connection()
        catalog_df = pd.read_sql_query(
            "SELECT model_code, category, description FROM product_catalog WHERE bu_id = %s ORDER BY model_code",
            conn,
            params=(selected_bu,),
        )
        conn.close()

        catalog_codes = catalog_df["model_code"].tolist() if not catalog_df.empty else []

        st.markdown("---")
        st.markdown(f"### 2. Line Items (Filtered for BU: `{selected_bu}`)")

        if not catalog_codes:
            st.warning(f"No product catalog entries found under '{selected_bu}'. Add products under 'Settings & Product Catalog' first.")

        default_items = pd.DataFrame(
            [
                {
                    "Model Product Code": catalog_codes[0] if catalog_codes else "",
                    "Type": type_options[0] if type_options else "Finished Good",
                    "Ordered Qty": 1.0,
                    "Unit Price": 0.0,
                }
            ]
        )

        edited_df = st.data_editor(
            default_items,
            num_rows="dynamic",
            column_config={
                "Model Product Code": st.column_config.SelectboxColumn(
                    "Model / Product Code",
                    options=catalog_codes if catalog_codes else ["N/A"],
                    required=True,
                ),
                "Type": st.column_config.SelectboxColumn(
                    "Type",
                    options=type_options if type_options else ["Finished Good"],
                ),
                "Ordered Qty": st.column_config.NumberColumn(
                    "Ordered Qty", min_value=1.0, default=1.0, format="%,.2f"
                ),
                "Unit Price": st.column_config.NumberColumn(
                    f"Unit Price ({currency})", min_value=0.0, format="%,.2f"
                ),
            },
            use_container_width=True,
        )

        if st.button("💾 Submit Master Order", type="primary"):
            if not po_number:
                st.error("PO Number is required!")
            else:
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()

                    cur.execute(
                        """
                        INSERT INTO master_orders (po_number, bu_id, division, supplier_id, po_date, 
                                                   consignee, offshore_company, currency, incoterm, approval_type, payment_terms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING order_id;
                    """,
                        (po_number, selected_bu, division, supplier_id, po_date, 
                         consignee, offshore_company, currency, incoterm, approval_type, payment_terms),
                    )
                    order_id = cur.fetchone()[0]

                    for _, row in edited_df.iterrows():
                        model_code = row["Model Product Code"]
                        itype = row["Type"]
                        qty = row["Ordered Qty"]
                        price = row["Unit Price"]
                        
                        cat_res = catalog_df[catalog_df["model_code"] == model_code]
                        item_cat = cat_res["category"].values[0] if not cat_res.empty else ""

                        if model_code:
                            cur.execute(
                                """
                                INSERT INTO order_items (order_id, model_product, category, item_type, ordered_qty, supplier_unit_price)
                                VALUES (%s, %s, %s, %s, %s, %s);
                            """,
                                (order_id, model_code, item_cat, itype, qty, price),
                            )

                    conn.commit()
                    conn.close()
                    st.success(f"Master Order **{po_number}** created successfully!")
                except Exception as ex:
                    st.error(f"Failed to save order: {ex}")

# --- 3. SHIPMENTS & TASK MANAGER ---
elif choice == "Shipments & Task Manager":
    st.subheader("🚚 Shipments & Sequential Clearance Manager")
    fx_rates = get_fx_rates()

    s_tab1, s_tab2 = st.tabs(["Create Partial or Full Shipment", "Clearance Task Engine"])

    # 1. Create Partial or Full Shipment
    with s_tab1:
        st.markdown("#### Create Partial or Full Shipment")
        conn = get_db_connection()
        po_df = pd.read_sql_query("SELECT order_id, po_number FROM master_orders ORDER BY order_id DESC", conn)
        conn.close()

        if po_df.empty:
            st.warning("No Master Orders available. Please create a Master Order first.")
        else:
            po_map = dict(zip(po_df["po_number"], po_df["order_id"]))
            selected_po_ref = st.selectbox("Select Master Order (PO #)", list(po_map.keys()))
            selected_order_id = po_map[selected_po_ref]

            conn = get_db_connection()
            items_df = pd.read_sql_query("""
                SELECT oi.item_id, mo.bu_id, mo.supplier_id, pc.brand_manuf, oi.model_product, 
                       oi.supplier_unit_price, mo.currency, oi.ordered_qty,
                       COALESCE(SUM(sc.shipped_qty), 0) as total_shipped,
                       (oi.ordered_qty - COALESCE(SUM(sc.shipped_qty), 0)) as remaining_qty
                FROM order_items oi
                JOIN master_orders mo ON oi.order_id = mo.order_id
                LEFT JOIN product_catalog pc ON oi.model_product = pc.model_code AND mo.bu_id = pc.bu_id
                LEFT JOIN shipment_contents sc ON oi.item_id = sc.item_id
                WHERE oi.order_id = %s
                GROUP BY oi.item_id, mo.bu_id, mo.supplier_id, pc.brand_manuf, oi.model_product, oi.supplier_unit_price, mo.currency, oi.ordered_qty
                ORDER BY oi.item_id ASC
            """, conn, params=(selected_order_id,))
            conn.close()

            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                bl_awb = st.text_input("BL / AWB Number *")
            with col_s2:
                shp_ref = st.text_input("Shipment Ref / Docket #", value=f"SHP-{selected_po_ref}")
            with col_s3:
                eta_date = st.date_input("Estimated Time of Arrival (ETA)", value=date.today())

            st.markdown("##### Allocate Quantities for this Shipment")
            
            allocation_data = []
            for idx, r in enumerate(items_df.itertuples(), start=1):
                balance = float(r.remaining_qty)
                alloc_qty = balance if balance > 0 else 0.0
                unit_price = float(r.supplier_unit_price)
                curr = r.currency if r.currency else "USD"
                rate = float(fx_rates.get(curr, 1.0))
                rate = rate if rate > 0 else 1.0

                line_total = alloc_qty * unit_price
                val_usd = line_total / rate

                allocation_data.append({
                    "#": idx,
                    "Item ID": r.item_id,
                    "BU": r.bu_id if r.bu_id else "",
                    "Supplier": r.supplier_id if r.supplier_id else "",
                    "Brand": r.brand_manuf if r.brand_manuf else "",
                    "Model/Product": r.model_product,
                    "Qty": alloc_qty,
                    "Unit Price": unit_price,
                    "Total": line_total,
                    "Currency": curr,
                    "Value ($)": val_usd,
                    "PO TTL Qty": float(r.ordered_qty),
                    "Rem. Qty": balance
                })

            alloc_df = pd.DataFrame(allocation_data)
            
            edited_alloc = st.data_editor(
                alloc_df,
                disabled=[
                    "#", "Item ID", "BU", "Supplier", "Brand", "Model/Product", 
                    "Unit Price", "Total", "Currency", "Value ($)", "PO TTL Qty", "Rem. Qty"
                ],
                column_config={
                    "Item ID": None,
                    "#": st.column_config.NumberColumn("#", format="%d"),
                    "Qty": st.column_config.NumberColumn("Qty", min_value=0.0, format="%,.2f"),
                    "Unit Price": st.column_config.NumberColumn("Unit Price", format="%,.2f"),
                    "Total": st.column_config.NumberColumn("Total", format="%,.2f"),
                    "Currency": st.column_config.TextColumn("Currency"),
                    "Value ($)": st.column_config.NumberColumn("Value ($)", format="$%,.2f"),
                    "PO TTL Qty": st.column_config.NumberColumn("PO TTL Qty", format="%,.2f"),
                    "Rem. Qty": st.column_config.NumberColumn("Rem. Qty", format="%,.2f"),
                },
                use_container_width=True,
                hide_index=True
            )

            if st.button("🚀 Create Shipment", type="primary"):
                if not bl_awb:
                    st.error("BL / AWB Number is required!")
                else:
                    try:
                        conn = get_db_connection()
                        cur = conn.cursor()

                        cur.execute("""
                            INSERT INTO shipments (shipment_ref, order_id, bl_awb, eta, status)
                            VALUES (%s, %s, %s, %s, 'In Clearance')
                            RETURNING shipment_id;
                        """, (shp_ref, selected_order_id, bl_awb, eta_date))
                        shipment_id = cur.fetchone()[0]

                        for _, row in edited_alloc.iterrows():
                            ship_qty = row["Qty"]
                            item_id = int(row["Item ID"])
                            if ship_qty > 0:
                                cur.execute("""
                                    INSERT INTO shipment_contents (shipment_id, item_id, shipped_qty)
                                    VALUES (%s, %s, %s);
                                """, (shipment_id, item_id, ship_qty))

                        cur.execute("SELECT step_order, task_name, department FROM task_definitions ORDER BY step_order ASC")
                        defs = cur.fetchall()

                        for idx, d in enumerate(defs):
                            step_ord, t_name, dept = d
                            initial_status = "In Progress" if idx == 0 else "Pending"
                            cur.execute("""
                                INSERT INTO shipment_tasks (shipment_id, step_order, task_name, department, status)
                                VALUES (%s, %s, %s, %s, %s);
                            """, (shipment_id, step_ord, t_name, dept, initial_status))

                        conn.commit()
                        conn.close()
                        st.success(f"Shipment created successfully for BL: **{bl_awb}**!")
                        st.rerun()
                    except Exception as e_shp:
                        st.error(f"Failed to create shipment: {e_shp}")

            # Display saved shipments table below button
            st.markdown("---")
            st.markdown(f"##### Saved Shipment Lines for PO `{selected_po_ref}`")
            
            conn = get_db_connection()
            saved_df = pd.read_sql_query("""
                SELECT s.bl_awb AS "BL / AWB",
                       mo.bu_id AS "BU",
                       mo.supplier_id AS "Supplier",
                       pc.brand_manuf AS "Brand",
                       oi.model_product AS "Model/Product",
                       sc.shipped_qty AS "Qty",
                       oi.supplier_unit_price AS "Unit Price",
                       (sc.shipped_qty * oi.supplier_unit_price) AS "Total",
                       mo.currency AS "Currency"
                FROM shipment_contents sc
                JOIN shipments s ON sc.shipment_id = s.shipment_id
                JOIN order_items oi ON sc.item_id = oi.item_id
                JOIN master_orders mo ON oi.order_id = mo.order_id
                LEFT JOIN product_catalog pc ON oi.model_product = pc.model_code AND mo.bu_id = pc.bu_id
                WHERE mo.order_id = %s
                ORDER BY s.shipment_id DESC, oi.item_id ASC
            """, conn, params=(selected_order_id,))
            conn.close()

            if saved_df.empty:
                st.info("No shipments registered yet for this PO.")
            else:
                saved_vals_usd = []
                for _, r in saved_df.iterrows():
                    curr = r["Currency"] if r["Currency"] in fx_rates else "USD"
                    rate = float(fx_rates.get(curr, 1.0))
                    rate = rate if rate > 0 else 1.0
                    saved_vals_usd.append(float(r["Total"]) / rate)

                saved_df["Value ($)"] = saved_vals_usd
                saved_df.insert(0, "#", range(1, 1 + len(saved_df)))
                
                st.dataframe(
                    saved_df,
                    column_config={
                        "#": st.column_config.NumberColumn("#", format="%d"),
                        "Qty": st.column_config.NumberColumn("Qty", format="%,.2f"),
                        "Unit Price": st.column_config.NumberColumn("Unit Price", format="%,.2f"),
                        "Total": st.column_config.NumberColumn("Total", format="%,.2f"),
                        "Currency": st.column_config.TextColumn("Currency"),
                        "Value ($)": st.column_config.NumberColumn("Value ($)", format="$%,.2f"),
                    },
                    use_container_width=True,
                    hide_index=True
                )

    # 2. Clearance Task Board Engine
    with s_tab2:
        st.markdown("#### Sequential Clearance Pipeline")
        conn = get_db_connection()
        shipments_df = pd.read_sql_query("""
            SELECT s.shipment_id, s.shipment_ref, s.bl_awb, s.eta, s.status, mo.po_number
            FROM shipments s
            JOIN master_orders mo ON s.order_id = mo.order_id
            ORDER BY s.shipment_id DESC
        """, conn)
        conn.close()

        if shipments_df.empty:
            st.info("No active shipments found. Create one under 'Create Partial or Full Shipment'.")
        else:
            shipments_df["display_label"] = shipments_df["bl_awb"] + " (PO: " + shipments_df["po_number"] + ")"
            selected_label = st.selectbox("Select Active Shipment / BL", shipments_df["display_label"].tolist())
            shp_row = shipments_df[shipments_df["display_label"] == selected_label].iloc[0]
            shp_id = int(shp_row["shipment_id"])

            st.info(f"**PO:** `{shp_row['po_number']}` | **BL/AWB:** `{shp_row['bl_awb']}` | **ETA:** `{shp_row['eta']}` | **Status:** `{shp_row['status']}`")

            conn = get_db_connection()
            tasks_df = pd.read_sql_query("""
                SELECT task_id, step_order, task_name, department, status, notes, completed_at
                FROM shipment_tasks
                WHERE shipment_id = %s
                ORDER BY step_order ASC
            """, conn, params=(shp_id,))
            conn.close()

            st.markdown("---")
            st.markdown("### Step-by-Step Task Workflow")

            previous_completed = True

            for _, task in tasks_df.iterrows():
                t_id = task["task_id"]
                step = task["step_order"]
                t_name = task["task_name"]
                dept = task["department"]
                status = task["status"]
                notes = task["notes"] if task["notes"] else ""
                completed_at = task["completed_at"]

                with st.expander(f"Step {step}: {t_name} ({dept}) - **{status}**", expanded=(status == "In Progress")):
                    if status == "Completed":
                        st.success(f"✅ Completed at: {completed_at}")
                        st.write(f"**Notes/Reference:** {notes}")
                        previous_completed = True
                    elif status == "In Progress" and previous_completed:
                        st.warning("⏳ Task is ready for clearance action.")
                        task_notes = st.text_area(f"Notes / Approval Reference for Step {step}", value=notes, key=f"note_{t_id}")
                        if st.button(f"Mark Step {step} as Completed", key=f"btn_{t_id}", type="primary"):
                            conn = get_db_connection()
                            cur = conn.cursor()

                            cur.execute("""
                                UPDATE shipment_tasks 
                                SET status = 'Completed', notes = %s, completed_at = CURRENT_TIMESTAMP
                                WHERE task_id = %s;
                            """, (task_notes, t_id))

                            cur.execute("""
                                UPDATE shipment_tasks
                                SET status = 'In Progress'
                                WHERE shipment_id = %s AND step_order = %s;
                            """, (shp_id, step + 1))

                            cur.execute("SELECT COUNT(*) FROM shipment_tasks WHERE shipment_id = %s AND status != 'Completed'", (shp_id,))
                            remaining_tasks = cur.fetchone()[0]
                            if remaining_tasks == 0:
                                cur.execute("UPDATE shipments SET status = 'Delivered' WHERE shipment_id = %s", (shp_id,))

                            conn.commit()
                            conn.close()
                            st.success(f"Step {step} marked as Completed!")
                            st.rerun()
                        previous_completed = False
                    else:
                        st.error("🔒 Locked: Complete the previous step first.")
                        previous_completed = False

# --- 4. SETTINGS & PRODUCT CATALOG ---
elif choice == "Settings & Product Catalog":
    st.subheader("⚙️ Control Settings & Product Catalog")

    tab1, tab2, tab3 = st.tabs(["Product Catalog", "Reference Lists", "Finance"])

    # TAB 1: Product Catalog
    with tab1:
        st.markdown("#### 📦 Product Catalog Management")
        conn = get_db_connection()
        p_df = pd.read_sql_query("SELECT bu_id AS \"BU\", brand_manuf AS \"Brand / Manufacturer\", category AS \"Category\", model_code AS \"Model / Product Code\", description AS \"Description\" FROM product_catalog ORDER BY bu_id, model_code", conn)
        conn.close()
        
        if not p_df.empty:
            p_df.insert(0, "#", range(1, 1 + len(p_df)))
            st.dataframe(
                p_df, 
                column_config={"#": st.column_config.NumberColumn("#", format="%d")},
                use_container_width=True, 
                hide_index=True
            )

        st.markdown("##### Add New Product to Catalog")
        bu_list = get_ref_list("BU")
        brand_list = get_ref_list("Brand/Manuf.")
        cat_list = get_ref_list("Category")

        c_p1, c_p2, c_p3, c_p4 = st.columns(4)
        with c_p1:
            p_bu = st.selectbox("Business Unit (BU)", bu_list if bu_list else ["Default BU"])
        with c_p2:
            p_brand = st.selectbox("Brand / Manufacturer", brand_list if brand_list else ["Default Brand"])
        with c_p3:
            p_cat = st.selectbox("Category", cat_list if cat_list else ["Default Category"])
        with c_p4:
            p_model = st.text_input("Model / Product Code *")

        p_desc = st.text_input("Description")

        if st.button("Add Product"):
            if p_model:
                conn = get_db_connection()
                cur = conn.cursor()
                try:
                    cur.execute(
                        """
                        INSERT INTO product_catalog (bu_id, brand_manuf, category, model_code, description)
                        VALUES (%s, %s, %s, %s, %s)
                    """,
                        (p_bu, p_brand, p_cat, p_model, p_desc),
                    )
                    conn.commit()
                    st.success(f"Product '{p_model}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding product: {e}")
                finally:
                    conn.close()

    # TAB 2: Reference Lists
    with tab2:
        st.markdown("#### Reference Lists Management")
        
        internal_defs = ["BU", "Off Shore Companies", "Consignee"]
        commercial_refs = [
            "Div", "Supplier", "Brand/Manuf.", "Approval Type", 
            "Payment Terms", "INCOTERM", "ORIGINs", "Category", 
            "Type", "CURRENCY", "Mode of Shipment", "Shipping Lines", 
            "Forwarders", "Sender Banks", "Receiving Banks", "Tenor"
        ]

        group_choice = st.radio("Reference Group", ["Internal Definitions", "Commercial / Operational References"], horizontal=True)
        active_cats = internal_defs if group_choice == "Internal Definitions" else commercial_refs

        col1, col2 = st.columns(2)
        with col1:
            cat_choice = st.selectbox("Select Category Header", active_cats)
            new_val = st.text_input(f"Add New Entry to {cat_choice}")
            if st.button("Add Reference Item"):
                add_ref_item(cat_choice, new_val)
                st.success(f"Added '{new_val}' to {cat_choice}!")
                st.rerun()
        with col2:
            st.write(f"Current values for **{cat_choice}**:")
            ref_items_df = pd.DataFrame(get_ref_list(cat_choice), columns=["Item Name"])
            if not ref_items_df.empty:
                ref_items_df.insert(0, "#", range(1, 1 + len(ref_items_df)))
                st.dataframe(ref_items_df, hide_index=True, use_container_width=True)

    # TAB 3: Finance & Exchange Rates
    with tab3:
        st.markdown("#### 💱 Currency & Exchange Rate Management")
        st.info("Define exchange rates relative to USD. **1 USD = X Local Currency**")

        conn = get_db_connection()
        rates_df = pd.read_sql_query("SELECT currency AS \"Currency\", rate_to_usd AS \"1 USD Equivalent Rate\", updated_at AS \"Last Updated\" FROM currency_rates ORDER BY currency", conn)
        conn.close()

        if not rates_df.empty:
            rates_df.insert(0, "#", range(1, 1 + len(rates_df)))
            st.dataframe(
                rates_df,
                column_config={
                    "#": st.column_config.NumberColumn("#", format="%d"),
                    "1 USD Equivalent Rate": st.column_config.NumberColumn("1 USD Equivalent Rate", format="%,.4f")
                },
                use_container_width=True,
                hide_index=True
            )

        st.markdown("##### Update / Add Exchange Rate")
        avail_currencies = get_ref_list("CURRENCY")
        if "USD" not in avail_currencies:
            avail_currencies.append("USD")

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            sel_curr = st.selectbox("Select Currency", avail_currencies)
        with col_f2:
            curr_rate = st.number_input(f"1 USD = how much {sel_curr}?", min_value=0.000001, value=1.0, format="%.4f")

        if st.button("Save Exchange Rate"):
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO currency_rates (currency, rate_to_usd, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (currency) 
                    DO UPDATE SET rate_to_usd = EXCLUDED.rate_to_usd, updated_at = CURRENT_TIMESTAMP;
                """, (sel_curr, curr_rate))
                conn.commit()
                st.success(f"Exchange rate updated: **1 USD = {curr_rate:,.4f} {sel_curr}**")
                st.rerun()
            except Exception as e_fx:
                st.error(f"Error saving exchange rate: {e_fx}")
            finally:
                conn.close()
