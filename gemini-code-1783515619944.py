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
            "DROP TABLE IF EXISTS audit_logs, financial_ledger, shipment_tasks, shipment_contents, shipments, order_items, product_catalog, master_orders, users, holiday_calendar, task_definitions, ref_lists CASCADE;"
        )

    # 1. Users Table
    c.execute("""CREATE TABLE IF NOT EXISTS users (
                    user_id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE, 
                    password TEXT, 
                    role VARCHAR(50),
                    scope_bu_id VARCHAR(20))""")

    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password TEXT;")

    # 2. Master Dropdowns / Ref Lists
    c.execute("""CREATE TABLE IF NOT EXISTS ref_lists (
                    id SERIAL PRIMARY KEY,
                    category VARCHAR(50), 
                    item_name VARCHAR(100),
                    is_active BOOLEAN DEFAULT TRUE)""")

    c.execute("""
        DELETE FROM ref_lists a USING ref_lists b 
        WHERE a.id < b.id AND a.category = b.category AND a.item_name = b.item_name;
    """)

    # 3. Product Catalog
    c.execute("""CREATE TABLE IF NOT EXISTS product_catalog (
                    product_id SERIAL PRIMARY KEY,
                    model_code VARCHAR(50) UNIQUE,
                    description TEXT,
                    category VARCHAR(50),
                    standard_unit_price NUMERIC(15, 2))""")

    # 4. Master Orders
    c.execute("""CREATE TABLE IF NOT EXISTS master_orders (
                    order_id SERIAL PRIMARY KEY, 
                    po_number VARCHAR(50) UNIQUE, 
                    bu_id VARCHAR(20), 
                    supplier_id VARCHAR(100), 
                    currency VARCHAR(10), 
                    incoterm VARCHAR(20), 
                    approval_type VARCHAR(50), 
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)""")

    # 5. Order Items
    c.execute("""CREATE TABLE IF NOT EXISTS order_items (
                    item_id SERIAL PRIMARY KEY, 
                    order_id INTEGER REFERENCES master_orders(order_id) ON DELETE CASCADE, 
                    model_product VARCHAR(100), 
                    ordered_qty NUMERIC(15, 2), 
                    supplier_unit_price NUMERIC(15, 2))""")

    # 6. Task Definitions (Standard clearance workflow steps)
    c.execute("""CREATE TABLE IF NOT EXISTS task_definitions (
                    task_def_id SERIAL PRIMARY KEY,
                    step_order INT UNIQUE,
                    task_name VARCHAR(100),
                    department VARCHAR(50),
                    sla_days INT)""")

    # Seed Task Definitions if empty
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
                    shipment_ref VARCHAR(50) UNIQUE,
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
            ("Supplier", "Global Tech Offshore"),
            ("Supplier", "Industrial Parts LLC"),
            ("Currency", "USD"),
            ("Currency", "EUR"),
            ("Incoterm", "FOB"),
            ("Incoterm", "CIF"),
            ("Approval", "Standard"),
            ("Approval", "Director"),
        ]
        for r in seed_ref:
            c.execute(
                "INSERT INTO ref_lists (category, item_name) VALUES (%s, %s)",
                r,
            )

    # Seed catalog items ONLY IF empty
    c.execute("SELECT COUNT(*) FROM product_catalog")
    if c.fetchone()[0] == 0:
        seed_catalog = [
            ("LAP-100", "ThinkPad T14", "Electronics", 1200.00),
            ("LAP-200", "MacBook Pro", "Electronics", 2000.00),
            ("MOT-550", "Heavy Duty Motor", "Machinery", 4500.00),
        ]
        for p in seed_catalog:
            c.execute(
                "INSERT INTO product_catalog (model_code, description, category, standard_unit_price) VALUES (%s, %s, %s, %s)",
                p,
            )

    conn.commit()
    conn.close()


# Safe initial build check
try:
    init_db(force_drop=False)
except Exception as e:
    st.error(f"Database sync roadblock: {e}")


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


# --- SECURITY GATE ---
st.set_page_config(layout="wide", page_title="Corporate Supply Chain Tracker")
st.title("🚢 Corporate Supply Chain Tracker (Neon Cloud Live)")

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

# --- SIDEBAR NAV ---
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

# --- MASTER ORDERS DASHBOARD ---
if choice == "Master Orders Dashboard":
    st.subheader("📦 Master Orders Overview")
    conn = get_db_connection()
    orders_df = pd.read_sql_query(
        """
        SELECT mo.order_id, mo.po_number, mo.bu_id, mo.supplier_id, mo.currency, 
               mo.incoterm, mo.approval_type, mo.created_at,
               COUNT(oi.item_id) as total_items,
               COALESCE(SUM(oi.ordered_qty * oi.supplier_unit_price), 0) as total_order_value
        FROM master_orders mo
        LEFT JOIN order_items oi ON mo.order_id = oi.order_id
        GROUP BY mo.order_id
        ORDER BY mo.order_id DESC
    """,
        conn,
    )

    if orders_df.empty:
        st.info("No Master Orders found. Use 'Create Master Order' to add one.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Master Orders", len(orders_df))
        total_val = orders_df["total_order_value"].sum()
        m2.metric("Total Value Managed", f"${total_val:,.2f}")
        m3.metric("Total Line Items", int(orders_df["total_items"].sum()))

        st.markdown("---")
        st.dataframe(orders_df, use_container_width=True)

        selected_po = st.selectbox(
            "Select PO to View Line Items Detail", orders_df["po_number"].tolist()
        )
        if selected_po:
            items_df = pd.read_sql_query(
                """
                SELECT oi.item_id, oi.model_product, pc.description, pc.category, 
                       oi.ordered_qty, 
                       COALESCE(SUM(sc.shipped_qty), 0) as shipped_qty,
                       (oi.ordered_qty - COALESCE(SUM(sc.shipped_qty), 0)) as remaining_qty,
                       oi.supplier_unit_price, 
                       (oi.ordered_qty * oi.supplier_unit_price) as line_total
                FROM order_items oi
                JOIN master_orders mo ON oi.order_id = mo.order_id
                LEFT JOIN product_catalog pc ON oi.model_product = pc.model_code
                LEFT JOIN shipment_contents sc ON oi.item_id = sc.item_id
                WHERE mo.po_number = %s
                GROUP BY oi.item_id, oi.model_product, pc.description, pc.category, oi.ordered_qty, oi.supplier_unit_price
            """,
                conn,
                params=(selected_po,),
            )
            st.write(f"**Line Items & Shipping Balance for PO:** `{selected_po}`")
            st.dataframe(items_df, use_container_width=True)

    conn.close()

# --- CREATE MASTER ORDER FORM ---
elif choice == "Create Master Order":
    if st.session_state["role"] == "Viewer":
        st.error("Action denied: Viewer role cannot create orders.")
    else:
        st.subheader("📝 Create New Master Order")

        bu_options = get_ref_list("BU")
        supplier_options = get_ref_list("Supplier")
        currency_options = get_ref_list("Currency")
        incoterm_options = get_ref_list("Incoterm")
        approval_options = get_ref_list("Approval")

        conn = get_db_connection()
        catalog_df = pd.read_sql_query(
            "SELECT DISTINCT model_code, description, category, standard_unit_price FROM product_catalog ORDER BY model_code",
            conn,
        )
        conn.close()

        catalog_map = catalog_df.set_index("model_code").to_dict("index")
        catalog_codes = catalog_df["model_code"].tolist()

        st.markdown("### 1. Header Details")
        c1, c2, c3 = st.columns(3)
        with c1:
            po_number = st.text_input("PO Number *")
            bu_id = st.selectbox(
                "Business Unit", bu_options if bu_options else ["Default BU"]
            )
        with c2:
            supplier_id = st.selectbox(
                "Supplier", supplier_options if supplier_options else ["Default Supplier"]
            )
            currency = st.selectbox(
                "Currency", currency_options if currency_options else ["USD", "EUR"]
            )
        with c3:
            incoterm = st.selectbox(
                "Incoterm", incoterm_options if incoterm_options else ["FOB", "CIF"]
            )
            approval_type = st.selectbox(
                "Approval Type", approval_options if approval_options else ["Standard"]
            )

        st.markdown("---")
        st.markdown("### 2. Order Line Items")

        default_items = pd.DataFrame(
            [
                {
                    "Model Product Code": catalog_codes[0] if catalog_codes else "",
                    "Ordered Qty": 1.0,
                    "Unit Price ($)": float(
                        catalog_map[catalog_codes[0]]["standard_unit_price"]
                    )
                    if catalog_codes
                    else 0.0,
                }
            ]
        )

        edited_df = st.data_editor(
            default_items,
            num_rows="dynamic",
            column_config={
                "Model Product Code": st.column_config.SelectboxColumn(
                    "Model Product Code",
                    options=catalog_codes,
                    required=True,
                ),
                "Ordered Qty": st.column_config.NumberColumn(
                    "Ordered Qty", min_value=1, default=1
                ),
                "Unit Price ($)": st.column_config.NumberColumn(
                    "Unit Price ($)", min_value=0.0, format="$%.2f"
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
                        INSERT INTO master_orders (po_number, bu_id, supplier_id, currency, incoterm, approval_type)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING order_id;
                    """,
                        (po_number, bu_id, supplier_id, currency, incoterm, approval_type),
                    )
                    order_id = cur.fetchone()[0]

                    for _, row in edited_df.iterrows():
                        model_code = row["Model Product Code"]
                        qty = row["Ordered Qty"]
                        price = row["Unit Price ($)"]
                        if model_code:
                            cur.execute(
                                """
                                INSERT INTO order_items (order_id, model_product, ordered_qty, supplier_unit_price)
                                VALUES (%s, %s, %s, %s);
                            """,
                                (order_id, model_code, qty, price),
                            )

                    conn.commit()
                    conn.close()
                    st.success(
                        f"Master Order **{po_number}** (ID: {order_id}) created successfully!"
                    )
                except Exception as ex:
                    st.error(f"Failed to save order: {ex}")

# --- SHIPMENTS & TASK MANAGER ---
elif choice == "Shipments & Task Manager":
    st.subheader("🚚 Shipments & Sequential Clearance Manager")

    s_tab1, s_tab2 = st.tabs(["Create New Shipment", "Clearance Task Engine"])

    # 1. Create New Shipment
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

            # Fetch line items with calculated remaining quantity
            conn = get_db_connection()
            items_df = pd.read_sql_query("""
                SELECT oi.item_id, oi.model_product, oi.ordered_qty,
                       COALESCE(SUM(sc.shipped_qty), 0) as total_shipped,
                       (oi.ordered_qty - COALESCE(SUM(sc.shipped_qty), 0)) as remaining_qty
                FROM order_items oi
                LEFT JOIN shipment_contents sc ON oi.item_id = sc.item_id
                WHERE oi.order_id = %s
                GROUP BY oi.item_id, oi.model_product, oi.ordered_qty
            """, conn, params=(selected_order_id,))
            conn.close()

            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                shp_ref = st.text_input("Shipment Ref / Docket # *", value=f"SHP-{selected_po_ref}-1")
            with col_s2:
                bl_awb = st.text_input("BL / AWB Number *")
            with col_s3:
                eta_date = st.date_input("Estimated Time of Arrival (ETA)", value=date.today())

            st.markdown("##### Allocate Quantities for this Shipment")
            
            # Prepare interactive allocation table
            allocation_data = []
            for _, r in items_df.iterrows():
                allocation_data.append({
                    "Item ID": r["item_id"],
                    "Product Code": r["model_product"],
                    "Total Ordered": float(r["ordered_qty"]),
                    "Already Shipped": float(r["total_shipped"]),
                    "Remaining Balance": float(r["remaining_qty"]),
                    "Ship Quantity": float(r["remaining_qty"])  # default to remaining
                })

            alloc_df = pd.DataFrame(allocation_data)
            edited_alloc = st.data_editor(
                alloc_df,
                disabled=["Item ID", "Product Code", "Total Ordered", "Already Shipped", "Remaining Balance"],
                column_config={
                    "Ship Quantity": st.column_config.NumberColumn("Ship Quantity", min_value=0.0)
                },
                use_container_width=True
            )

            if st.button("🚀 Confirm & Dispatch Shipment", type="primary"):
                if not shp_ref or not bl_awb:
                    st.error("Shipment Ref and BL/AWB Number are required!")
                else:
                    try:
                        conn = get_db_connection()
                        cur = conn.cursor()

                        # Insert shipment header
                        cur.execute("""
                            INSERT INTO shipments (shipment_ref, order_id, bl_awb, eta, status)
                            VALUES (%s, %s, %s, %s, 'In Clearance')
                            RETURNING shipment_id;
                        """, (shp_ref, selected_order_id, bl_awb, eta_date))
                        shipment_id = cur.fetchone()[0]

                        # Insert shipment contents
                        for _, row in edited_alloc.iterrows():
                            ship_qty = row["Ship Quantity"]
                            item_id = int(row["Item ID"])
                            if ship_qty > 0:
                                cur.execute("""
                                    INSERT INTO shipment_contents (shipment_id, item_id, shipped_qty)
                                    VALUES (%s, %s, %s);
                                """, (shipment_id, item_id, ship_qty))

                        # Auto-generate task pipeline from task_definitions
                        cur.execute("SELECT step_order, task_name, department FROM task_definitions ORDER BY step_order ASC")
                        defs = cur.fetchall()

                        for idx, d in enumerate(defs):
                            step_ord, t_name, dept = d
                            # First step is 'In Progress', rest are 'Pending' (locked)
                            initial_status = "In Progress" if idx == 0 else "Pending"
                            cur.execute("""
                                INSERT INTO shipment_tasks (shipment_id, step_order, task_name, department, status)
                                VALUES (%s, %s, %s, %s, %s);
                            """, (shipment_id, step_ord, t_name, dept, initial_status))

                        conn.commit()
                        conn.close()
                        st.success(f"Shipment **{shp_ref}** created and clearance tasks initiated!")
                        st.rerun()
                    except Exception as e_shp:
                        st.error(f"Failed to create shipment: {e_shp}")

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
            st.info("No active shipments found. Create one under 'Create New Shipment'.")
        else:
            selected_shp_ref = st.selectbox("Select Active Shipment to Manage", shipments_df["shipment_ref"].tolist())
            shp_row = shipments_df[shipments_df["shipment_ref"] == selected_shp_ref].iloc[0]
            shp_id = int(shp_row["shipment_id"])

            st.info(f"**PO:** `{shp_row['po_number']}` | **BL/AWB:** `{shp_row['bl_awb']}` | **ETA:** `{shp_row['eta']}` | **Status:** `{shp_row['status']}`")

            # Fetch tasks for this shipment
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

            # Blocking Logic: Task N can only be updated if Task N-1 is 'Completed'
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

                            # Complete current task
                            cur.execute("""
                                UPDATE shipment_tasks 
                                SET status = 'Completed', notes = %s, completed_at = CURRENT_TIMESTAMP
                                WHERE task_id = %s;
                            """, (task_notes, t_id))

                            # Unlock next step if exists
                            cur.execute("""
                                UPDATE shipment_tasks
                                SET status = 'In Progress'
                                WHERE shipment_id = %s AND step_order = %s;
                            """, (shp_id, step + 1))

                            # If last step, mark shipment as Delivered
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

# --- SETTINGS & PRODUCT CATALOG ---
elif choice == "Settings & Product Catalog":
    st.subheader("⚙️ Control Settings & Product Catalog")

    tab1, tab2 = st.tabs(["Product Catalog", "Reference Lists"])

    with tab1:
        st.markdown("#### 📦 Product Catalog Management")
        conn = get_db_connection()
        p_df = pd.read_sql_query("SELECT DISTINCT * FROM product_catalog", conn)
        conn.close()
        st.dataframe(p_df, use_container_width=True)

        st.markdown("##### Add New Product to Catalog")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            m_code = st.text_input("Model Code")
        with col2:
            m_desc = st.text_input("Description")
        with col3:
            m_cat = st.text_input("Category")
        with col4:
            m_price = st.number_input("Standard Unit Price", min_value=0.0)

        if st.button("Add Product"):
            if m_code:
                conn = get_db_connection()
                cur = conn.cursor()
                try:
                    cur.execute(
                        """
                        INSERT INTO product_catalog (model_code, description, category, standard_unit_price)
                        VALUES (%s, %s, %s, %s)
                    """,
                        (m_code, m_desc, m_cat, m_price),
                    )
                    conn.commit()
                    st.success(f"Product '{m_code}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding product: {e}")
                finally:
                    conn.close()

    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            cat_choice = st.selectbox(
                "Select Category", ["BU", "Supplier", "Currency", "Incoterm", "Approval"]
            )
            new_val = st.text_input(f"Add New Entry to {cat_choice}")
            if st.button("Add Reference Item"):
                add_ref_item(cat_choice, new_val)
                st.success(f"Added '{new_val}' to {cat_choice}!")
                st.rerun()
        with col2:
            st.write(f"Current values for **{cat_choice}**:")
            st.write(get_ref_list(cat_choice))
