import hashlib
import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
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

    # Cleanup any existing duplicate entries in ref_lists
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

    # Seed Admin user if missing
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        hashed = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute(
            "INSERT INTO users (username, password, role) VALUES ('admin', %s, 'Admin')",
            (hashed,),
        )

    # Seed reference dropdowns ONLY IF ref_lists table is completely empty
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

    # Seed catalog items ONLY IF product_catalog table is empty
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

menu = ["Master Orders Dashboard", "Create Master Order"]
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
                       oi.ordered_qty, oi.supplier_unit_price, 
                       (oi.ordered_qty * oi.supplier_unit_price) as line_total
                FROM order_items oi
                JOIN master_orders mo ON oi.order_id = mo.order_id
                LEFT JOIN product_catalog pc ON oi.model_product = pc.model_code
                WHERE mo.po_number = %s
            """,
                conn,
                params=(selected_po,),
            )
            st.write(f"**Line Items for PO:** `{selected_po}`")
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

        # Get Catalog Products (distinct)
        conn = get_db_connection()
        catalog_df = pd.read_sql_query(
            "SELECT DISTINCT model_code, description, category, standard_unit_price FROM product_catalog ORDER BY model_code",
            conn,
        )
        conn.close()

        catalog_map = catalog_df.set_index("model_code").to_dict("index")
        catalog_codes = catalog_df["model_code"].tolist()

        # 1. Header Section
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

                    # Insert Header
                    cur.execute(
                        """
                        INSERT INTO master_orders (po_number, bu_id, supplier_id, currency, incoterm, approval_type)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING order_id;
                    """,
                        (po_number, bu_id, supplier_id, currency, incoterm, approval_type),
                    )
                    order_id = cur.fetchone()[0]

                    # Insert Items
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
