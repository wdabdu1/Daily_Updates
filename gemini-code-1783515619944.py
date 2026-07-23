import json
import sqlite3
from datetime import date, datetime, timedelta
import pandas as pd
import streamlit as st

# --- STREAMLIT PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Supply Chain & Clearance Engine",
    page_icon="🚢",
    layout="wide",
)


# --- HELPERS: PARSING & FORMATTING ---
def parse_amount(val) -> float:
    """Parses numeric input with commas/currency symbols into a clean float."""
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = (
        str(val).replace(",", "").replace("SDG", "").replace("$", "").strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def format_amount(val) -> str:
    """Formats float into a comma-separated currency string (e.g. 100,000.00)."""
    num = parse_amount(val)
    return f"{num:,.2f}"


# --- DATABASE CONNECTION & INITIALIZATION ---
def get_db_connection():
    conn = sqlite3.connect("shipments.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Master Orders Header Table (Fully Upgraded with all 20 Master Order Headers)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_orders (
            po_number TEXT PRIMARY KEY,
            bu_id TEXT,
            division TEXT,
            status TEXT DEFAULT 'Open',
            supplier_name TEXT,
            brand_manufacturer TEXT,
            approval_type TEXT,
            consignee TEXT,
            supplier_pi_no TEXT,
            supplier_pi_date DATE,
            payment_terms TEXT,
            rec_signed_pi_date DATE,
            sent_signed_pi_date DATE,
            bu_po_date DATE,
            order_execution_date DATE,
            latest_shipment_date DATE,
            incoterm TEXT,
            country_of_origin TEXT,
            offshore_1_name TEXT,
            offshore_2_name TEXT,
            currency TEXT DEFAULT 'USD',
            total_po_value REAL,
            form_i_number TEXT,
            bank_name TEXT,
            port_of_loading TEXT,
            order_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- DB MIGRATION: Ensure existing tables receive new columns dynamically ---
    cursor.execute("PRAGMA table_info(master_orders)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    new_cols = {
        "division": "TEXT",
        "brand_manufacturer": "TEXT",
        "approval_type": "TEXT",
        "consignee": "TEXT",
        "supplier_pi_no": "TEXT",
        "supplier_pi_date": "DATE",
        "rec_signed_pi_date": "DATE",
        "sent_signed_pi_date": "DATE",
        "bu_po_date": "DATE",
        "order_execution_date": "DATE",
        "latest_shipment_date": "DATE",
        "offshore_1_name": "TEXT",
        "offshore_2_name": "TEXT",
    }
    for col_name, col_type in new_cols.items():
        if col_name not in existing_cols:
            cursor.execute(
                f"ALTER TABLE master_orders ADD COLUMN {col_name} {col_type}"
            )

    # 2. PO Line Items Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS po_line_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT,
            item_code TEXT,
            item_description TEXT,
            hs_code TEXT,
            quantity REAL,
            unit_price REAL,
            total_price REAL,
            ssmo_required INTEGER DEFAULT 0,
            FOREIGN KEY(po_number) REFERENCES master_orders(po_number)
        )
    """)

    # 3. Shipments Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            shipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bl_awb TEXT UNIQUE,
            po_number TEXT,
            bu_id TEXT,
            clear_at TEXT DEFAULT 'Pending',
            est_arrival_date DATE,
            act_arrival_date DATE,
            est_clearance_date DATE,
            act_clearance_date DATE,
            manual_override_est_date INTEGER DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (po_number) REFERENCES master_orders(po_number)
        )
    """)

    # 4. Process Tasks Engine Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS process_tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER,
            process_key TEXT,
            process_name TEXT,
            track TEXT,
            target_sla REAL,
            status TEXT DEFAULT 'Pending',
            data_json TEXT,
            completed_at DATE,
            FOREIGN KEY(shipment_id) REFERENCES shipments(shipment_id)
        )
    """)

    # Seed Sample Data if Database is Empty
    cursor.execute(
        "SELECT COUNT(*) FROM master_orders WHERE po_number = 'PO-2026-8812'"
    )
    if cursor.fetchone()[0] == 0:
        today = date.today()

        # Seed Master Order
        cursor.execute(
            """
            INSERT OR IGNORE INTO master_orders 
            (po_number, bu_id, division, status, supplier_name, brand_manufacturer, approval_type, consignee, 
             supplier_pi_no, supplier_pi_date, payment_terms, rec_signed_pi_date, sent_signed_pi_date, bu_po_date, 
             order_execution_date, latest_shipment_date, incoterm, country_of_origin, offshore_1_name, offshore_2_name,
             currency, total_po_value, form_i_number, bank_name, port_of_loading, order_date)
            VALUES 
            ('PO-2026-8812', 'BU-LOGISTICS', 'Heavy Equipment Div', 'In Execution', 'Global Industrial Supplies', 'CAT / Siemens', 'Standard', 'Sudan Operations LLC',
             'PI-88102', ?, 'L/C 90 Days', ?, ?, ?, ?, ?, 'CIF', 'Germany', 'Offshore Logistics Trading FZE', 'Global Maritime Ltd',
             'USD', 250000.0, 'FI-99201', 'Bank of Khartoum', 'Hamburg Port', ?)
        """,
            (
                (today - timedelta(days=20)).isoformat(),
                (today - timedelta(days=18)).isoformat(),
                (today - timedelta(days=17)).isoformat(),
                (today - timedelta(days=16)).isoformat(),
                (today - timedelta(days=15)).isoformat(),
                (today + timedelta(days=30)).isoformat(),
                (today - timedelta(days=15)).isoformat(),
            ),
        )

        # Seed PO Line Items
        cursor.execute("""
            INSERT OR IGNORE INTO po_line_items (po_number, item_code, item_description, hs_code, quantity, unit_price, total_price, ssmo_required)
            VALUES 
            ('PO-2026-8812', 'GEN-500KW', '500KW Heavy Duty Industrial Generator', '8502.13.00', 2, 100000.0, 200000.0, 1),
            ('PO-2026-8812', 'SPA-FILTER', 'Replacement Air Filter Assembly Set', '8421.23.00', 50, 1000.0, 50000.0, 0)
        """)

        # Seed Shipment
        cursor.execute(
            """
            INSERT OR IGNORE INTO shipments (bl_awb, po_number, bu_id, est_arrival_date, clear_at, notes)
            VALUES 
            ('BL-2026-PORT-101', 'PO-2026-8812', 'BU-LOGISTICS', ?, 'Port', 'Priority heavy equipment shipment')
        """,
            ((today + timedelta(days=2)).isoformat(),),
        )

        cursor.execute(
            "SELECT shipment_id FROM shipments WHERE bl_awb ="
            " 'BL-2026-PORT-101'"
        )
        shp1_id = cursor.fetchone()[0]
        seed_tasks_for_shipment(cursor, shp1_id)

    conn.commit()
    conn.close()


def seed_tasks_for_shipment(cursor, shipment_id):
    """Seeds standard clearance task definitions for a new shipment."""
    default_processes = [
        ("gen_info", "General Clearance Info", "Common", 0.25, "{}"),
        ("clear_at_select", "Clear at:", "Common", 0.25, "{}"),
        (
            "cost_estimate",
            "Clearance Cost Estimate",
            "Common",
            0.25,
            json.dumps({"value": 500000.0}),
        ),
        (
            "delivery_order",
            "Delivery Order",
            "Common",
            1.0,
            json.dumps({"do_fees": 150000.0}),
        ),
        (
            "customs_cert",
            "Customs Certificate Entry",
            "Common",
            0.5,
            json.dumps({"scuda_no": "SCUDA-99182"}),
        ),
        (
            "cont_move",
            "Containers Move Process",
            "Port",
            2.0,
            json.dumps({"bill_amount": 250000.0}),
        ),
        (
            "ssmo_file",
            "SSMO File Process",
            "Port",
            1.0,
            json.dumps({"bill_amount": 100000.0}),
        ),
        ("customs_exam", "Customs Examination (Form 48)", "Port", 1.0, "{}"),
        (
            "customs_lab",
            "Customs Lab",
            "Port",
            1.0,
            json.dumps({"lab_fees": 75000.0, "lab_required": "Yes"}),
        ),
        ("ssmo_exam", "SSMO Examination", "Port", 1.0, "{}"),
        (
            "customs_eval",
            "Customs Evaluation",
            "Port",
            1.0,
            json.dumps({"customs_value": 1250000.0}),
        ),
        (
            "spc_bill",
            "SPC Bill",
            "Port",
            1.0,
            json.dumps({"spc_bill_value": 300000.0}),
        ),
        ("truck_permit", "Truck Entry Permit", "Port", 1.0, "{}"),
        ("fz_deposit_req", "FZ Deposit Request", "Free Zone", 1.0, "{}"),
        (
            "fz_customs_insp",
            "Customs Inspection (FZ)",
            "Free Zone",
            1.0,
            "{}",
        ),
        (
            "fz_spc_police",
            "SPC Bill & Police Security",
            "Free Zone",
            1.0,
            json.dumps({"spc_bill_value": 350000.0}),
        ),
        ("fz_receive_cargo", "Receive Cargo at FZ", "Free Zone", 1.0, "{}"),
        (
            "final_clearance_complete",
            "Actual Clearance Completion",
            "Common",
            0.25,
            "{}",
        ),
    ]

    for key, name, track, sla, data_json in default_processes:
        cursor.execute(
            """
            INSERT OR IGNORE INTO process_tasks (shipment_id, process_key, process_name, track, target_sla, status, data_json)
            VALUES (?, ?, ?, ?, ?, 'Pending', ?)
        """,
            (shipment_id, key, name, track, sla, data_json),
        )


init_db()


# --- WORKFLOW ENGINE EVALUATOR ---
def evaluate_process_statuses(tasks_dict, clear_at_selection):
    status_map = {}

    def get_data(key):
        return json.loads(tasks_dict.get(key, {}).get("data_json", "{}"))

    def is_done(key):
        return tasks_dict.get(key, {}).get("status") == "Completed"

    status_map["gen_info"] = (
        "Completed" if is_done("gen_info") else "Active"
    )

    gen_data = get_data("gen_info")
    bl_copy_done = bool(gen_data.get("bl_copy_receipt_date"))
    orig_ship_done = bool(gen_data.get("orig_shipment_rec_date"))

    status_map["clear_at_select"] = (
        "Completed"
        if is_done("clear_at_select")
        else ("Active" if orig_ship_done else "Pending")
    )
    status_map["cost_estimate"] = (
        "Completed"
        if is_done("cost_estimate")
        else ("Active" if bl_copy_done else "Pending")
    )
    status_map["delivery_order"] = (
        "Completed"
        if is_done("delivery_order")
        else ("Active" if orig_ship_done else "Pending")
    )
    status_map["customs_cert"] = (
        "Completed"
        if is_done("customs_cert")
        else ("Active" if is_done("delivery_order") else "Pending")
    )

    if clear_at_selection == "Port":
        cert_done = is_done("customs_cert")
        status_map["cont_move"] = (
            "Completed"
            if is_done("cont_move")
            else ("Active" if cert_done else "Pending")
        )
        status_map["customs_lab"] = (
            "Completed"
            if is_done("customs_lab")
            else ("Active" if cert_done else "Pending")
        )

        cont_move_done = is_done("cont_move")
        status_map["ssmo_file"] = (
            "Completed"
            if is_done("ssmo_file")
            else ("Active" if cont_move_done else "Pending")
        )
        status_map["customs_exam"] = (
            "Completed"
            if is_done("customs_exam")
            else ("Active" if cont_move_done else "Pending")
        )

        status_map["ssmo_exam"] = (
            "Completed"
            if is_done("ssmo_exam")
            else ("Active" if is_done("ssmo_file") else "Pending")
        )

        lab_data = get_data("customs_lab")
        lab_not_req = lab_data.get("lab_required") == "No"
        lab_ready = is_done("customs_lab") or lab_not_req
        status_map["customs_eval"] = (
            "Completed"
            if is_done("customs_eval")
            else (
                "Active"
                if (is_done("customs_exam") and lab_ready)
                else "Pending"
            )
        )

        status_map["spc_bill"] = (
            "Completed"
            if is_done("spc_bill")
            else ("Active" if is_done("customs_eval") else "Pending")
        )
        status_map["truck_permit"] = (
            "Completed"
            if is_done("truck_permit")
            else ("Active" if is_done("spc_bill") else "Pending")
        )

        status_map["final_clearance_complete"] = (
            "Completed"
            if is_done("final_clearance_complete")
            else ("Active" if is_done("truck_permit") else "Pending")
        )

    elif clear_at_selection == "Free Zone":
        status_map["fz_deposit_req"] = (
            "Completed" if is_done("fz_deposit_req") else "Active"
        )

        fz_dep_done = is_done("fz_deposit_req")
        status_map["fz_customs_insp"] = (
            "Completed"
            if is_done("fz_customs_insp")
            else ("Active" if fz_dep_done else "Pending")
        )
        status_map["fz_spc_police"] = (
            "Completed"
            if is_done("fz_spc_police")
            else ("Active" if fz_dep_done else "Pending")
        )

        fz_cargo_ready = is_done("fz_customs_insp") and is_done("fz_spc_police")
        status_map["fz_receive_cargo"] = (
            "Completed"
            if is_done("fz_receive_cargo")
            else ("Active" if fz_cargo_ready else "Pending")
        )

        status_map["final_clearance_complete"] = (
            "Completed"
            if is_done("final_clearance_complete")
            else ("Active" if is_done("fz_receive_cargo") else "Pending")
        )

    return status_map


# --- NAVIGATION ---
st.sidebar.title("🚢 Supply Chain Hub")
menu = [
    "📦 Master Orders & Line Items",
    "🚢 Attach Shipment (BL/AWB)",
    "📋 Clearance Task Engine",
    "📊 Clearance & SLA Analytics",
    "⚙️ Target SLA Settings",
]
choice = st.sidebar.selectbox("Select Module", menu)


# ==============================================================================
# MODULE 1: MASTER ORDERS & LINE ITEMS (ALL 20 MASTER ORDER FIELDS INTEGRATED)
# ==============================================================================
if choice == "📦 Master Orders & Line Items":
    st.title("📦 Master Purchase Order & Line Item Management")

    tab1, tab2 = st.tabs(
        ["1️⃣ Create Master Order & Line Items", "2️⃣ Master Order Registry"]
    )

    # --- TAB 1: CREATE MASTER ORDER ---
    with tab1:
        st.subheader("📌 Main Master Order Specifications")

        # --- SECTION 1: HEADER IDENTIFICATION & ENTITIES ---
        st.markdown("##### 🏢 Order Identity & Business Entities")
        c1, c2, c3, c4 = st.columns(4)
        po_number = c1.text_input(
            "PO Number *", placeholder="e.g. PO-2026-9901"
        )
        bu_id = c2.selectbox(
            "BU (Business Unit) *",
            ["BU-LOGISTICS", "BU-RETAIL", "BU-ENERGY", "BU-MANUFACTURING"],
        )
        division = c3.selectbox(
            "Div (Division within BU)",
            [
                "Heavy Equipment Div",
                "Consumer Goods Div",
                "Industrial Div",
                "Spare Parts Div",
            ],
        )
        status = c4.selectbox(
            "Status (Today's Order Status)",
            ["Open", "Draft", "Approved", "PI Received", "In Execution", "Completed"],
        )

        c5, c6, c7, c8 = st.columns(4)
        supplier_name = c5.text_input(
            "Supplier Name *", placeholder="e.g. Global Industrial Supplies"
        )
        brand_manufacturer = c6.text_input(
            "Brand / Manufacturer", placeholder="e.g. Caterpillar / Siemens"
        )
        approval_type = c7.selectbox(
            "Approval Type", ["Standard", "Fast-Track", "Board Approved", "Emergency"]
        )
        consignee = c8.text_input(
            "Consignee Entity", placeholder="e.g. Sudan Operations LLC"
        )

        st.markdown("---")
        # --- SECTION 2: PROFORMA INVOICE (PI) & COMMERCIAL TERMS ---
        st.markdown("##### 📄 Supplier PI & Commercial Terms")
        c9, c10, c11, c12 = st.columns(4)
        supplier_pi_no = c9.text_input(
            "Supplier PI No", placeholder="e.g. PI-99201"
        )
        supplier_pi_date = c10.date_input(
            "Supplier PI Date", value=date.today()
        )
        payment_terms = c11.selectbox(
            "Supplier Payment Terms",
            ["L/C 90 Days", "L/C at Sight", "30% Advance / 70% LC", "CAD", "Open Account"],
        )
        incoterm = c12.selectbox(
            "Incoterm", ["CIF", "FOB", "CFR", "EXW", "DDP", "FCA"]
        )

        c13, c14, c15, c16 = st.columns(4)
        country_of_origin = c13.selectbox(
            "Origin (Country)",
            ["Germany", "China", "United States", "Turkey", "India", "UAE", "Saudi Arabia"],
        )
        offshore_1 = c14.selectbox(
            "Off Shore 1 Name",
            ["Offshore Logistics Trading FZE", "Global Trading Dubai", "Europe Sourcing GmbH", "None"],
        )
        offshore_2 = c15.text_input(
            "Off Shore 2 Name (Optional)", placeholder="Secondary Offshore entity..."
        )
        currency = c16.selectbox("Currency", ["USD", "EUR", "SDG", "AED"])

        c17, c18, c19, c20 = st.columns(4)
        po_val_raw = c17.text_input(
            "Total PO Value", value="100,000.00", help="Auto-formatted numeric input"
        )
        total_po_value = parse_amount(po_val_raw)
        form_i = c18.text_input("Form I / L/C Reference", placeholder="FI-99021")
        bank_name = c19.text_input("Bank Name", placeholder="Bank of Khartoum")
        port_of_loading = c20.text_input("Port of Loading", placeholder="Hamburg Port")

        st.markdown("---")
        # --- SECTION 3: KEY MILESTONE DATES ---
        st.markdown("##### 📅 Key Milestone Dates")
        d1, d2, d3, d4, d5 = st.columns(5)
        rec_signed_pi_date = d1.date_input("Received Signed PI Date", value=date.today())
        sent_signed_pi_date = d2.date_input("Sent Signed PI Date", value=date.today())
        bu_po_date = d3.date_input("BU PO Date", value=date.today())
        order_execution_date = d4.date_input("Order Execution Date", value=date.today())
        latest_shipment_date = d5.date_input("Latest Shipment Date", value=date.today() + timedelta(days=60))

        st.markdown("---")
        st.subheader("🛒 PO Line Items Entry")
        st.caption(
            "Add itemized line breakdown (HS Codes, Quantities, Unit Prices,"
            " SSMO flags)"
        )

        if "temp_line_items" not in st.session_state:
            st.session_state["temp_line_items"] = []

        with st.expander("➕ Add Line Item to PO", expanded=True):
            li_col1, li_col2, li_col3 = st.columns(3)
            item_code = li_col1.text_input(
                "Item Code / Part No.", placeholder="GEN-500"
            )
            item_desc = li_col2.text_input(
                "Item Description *", placeholder="500KW Generator Set"
            )
            hs_code = li_col3.text_input(
                "HS Code (Tariff)", placeholder="8502.13.00"
            )

            li_col4, li_col5, li_col6 = st.columns(3)
            qty = li_col4.number_input("Quantity", min_value=1.0, value=1.0)
            u_price_raw = li_col5.text_input("Unit Price", value="1,000.00")
            unit_price = parse_amount(u_price_raw)
            ssmo_req = li_col6.checkbox(
                "SSMO / Inspection Required?", value=True
            )

            line_total = qty * unit_price
            st.info(f"Calculated Line Total: **{format_amount(line_total)}**")

            if st.button("➕ Add Item to List"):
                if not item_desc.strip():
                    st.error("Item Description is required.")
                else:
                    st.session_state["temp_line_items"].append({
                        "item_code": item_code.strip(),
                        "item_description": item_desc.strip(),
                        "hs_code": hs_code.strip(),
                        "quantity": qty,
                        "unit_price": unit_price,
                        "total_price": line_total,
                        "ssmo_required": 1 if ssmo_req else 0,
                    })
                    st.success(f"Added '{item_desc}' to draft PO line items!")
                    st.rerun()

        if st.session_state["temp_line_items"]:
            st.markdown("##### Current Draft Line Items:")
            df_temp = pd.DataFrame(st.session_state["temp_line_items"])
            df_temp["formatted_unit_price"] = df_temp["unit_price"].apply(
                format_amount
            )
            df_temp["formatted_total"] = df_temp["total_price"].apply(
                format_amount
            )

            st.dataframe(
                df_temp[[
                    "item_code",
                    "item_description",
                    "hs_code",
                    "quantity",
                    "formatted_unit_price",
                    "formatted_total",
                    "ssmo_required",
                ]],
                use_container_width=True,
                hide_index=True,
            )

            line_item_sum = sum(
                item["total_price"]
                for item in st.session_state["temp_line_items"]
            )
            st.write(
                f"**Total Line Items Sum:** `{currency} {format_amount(line_item_sum)}`"
            )

            if st.button("🗑️ Clear Draft Line Items"):
                st.session_state["temp_line_items"] = []
                st.rerun()

        st.markdown("---")
        if st.button(
            "💾 Save Master Order with Full Metadata",
            use_container_width=True,
            type="primary",
        ):
            if not po_number.strip() or not supplier_name.strip():
                st.error("PO Number and Supplier Name are required.")
            else:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO master_orders 
                        (po_number, bu_id, division, status, supplier_name, brand_manufacturer, approval_type, consignee,
                         supplier_pi_no, supplier_pi_date, payment_terms, rec_signed_pi_date, sent_signed_pi_date, bu_po_date,
                         order_execution_date, latest_shipment_date, incoterm, country_of_origin, offshore_1_name, offshore_2_name,
                         currency, total_po_value, form_i_number, bank_name, port_of_loading, order_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            po_number.strip(),
                            bu_id,
                            division,
                            status,
                            supplier_name.strip(),
                            brand_manufacturer.strip(),
                            approval_type,
                            consignee.strip(),
                            supplier_pi_no.strip(),
                            supplier_pi_date.isoformat(),
                            payment_terms,
                            rec_signed_pi_date.isoformat(),
                            sent_signed_pi_date.isoformat(),
                            bu_po_date.isoformat(),
                            order_execution_date.isoformat(),
                            latest_shipment_date.isoformat(),
                            incoterm,
                            country_of_origin,
                            offshore_1,
                            offshore_2.strip(),
                            currency,
                            total_po_value,
                            form_i.strip(),
                            bank_name.strip(),
                            port_of_loading.strip(),
                            bu_po_date.isoformat(),
                        ),
                    )

                    for item in st.session_state["temp_line_items"]:
                        cursor.execute(
                            """
                            INSERT INTO po_line_items (po_number, item_code, item_description, hs_code, quantity, unit_price, total_price, ssmo_required)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                po_number.strip(),
                                item["item_code"],
                                item["item_description"],
                                item["hs_code"],
                                item["quantity"],
                                item["unit_price"],
                                item["total_price"],
                                item["ssmo_required"],
                            ),
                        )

                    conn.commit()
                    st.success(
                        f"Master Order **{po_number}** and"
                        f" {len(st.session_state['temp_line_items'])} Line Items"
                        " saved successfully!"
                    )
                    st.session_state["temp_line_items"] = []
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"PO Number '{po_number}' already exists.")
                finally:
                    conn.close()

    # --- TAB 2: MASTER ORDER REGISTRY ---
    with tab2:
        st.subheader("📋 Registered Master Orders Directory")
        conn = get_db_connection()
        mo_df = pd.read_sql_query(
            "SELECT po_number, bu_id, division, status, supplier_name, brand_manufacturer, consignee, supplier_pi_no, incoterm, country_of_origin, currency, total_po_value, latest_shipment_date FROM master_orders ORDER BY created_at DESC",
            conn,
        )

        if not mo_df.empty:
            mo_df["total_po_value"] = mo_df["total_po_value"].apply(
                format_amount
            )
            st.dataframe(mo_df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("🔎 Complete Header & Line Item Inspection")
            selected_inspect_po = st.selectbox(
                "Select Master Order to Inspect:", mo_df["po_number"].tolist()
            )

            # Display full Master Order Header Details in expandable view
            po_full_details = dict(
                conn.execute(
                    "SELECT * FROM master_orders WHERE po_number = ?",
                    (selected_inspect_po,),
                ).fetchone()
            )
            
            with st.expander("📌 Full Master Order Header Metadata", expanded=True):
                m_c1, m_c2, m_c3, m_c4 = st.columns(4)
                m_c1.write(f"**PO Number:** {po_full_details.get('po_number')}")
                m_c1.write(f"**BU:** {po_full_details.get('bu_id')}")
                m_c1.write(f"**Division:** {po_full_details.get('division')}")
                m_c1.write(f"**Status:** {po_full_details.get('status')}")

                m_c2.write(f"**Supplier:** {po_full_details.get('supplier_name')}")
                m_c2.write(f"**Brand/Manuf.:** {po_full_details.get('brand_manufacturer')}")
                m_c2.write(f"**Approval Type:** {po_full_details.get('approval_type')}")
                m_c2.write(f"**Consignee:** {po_full_details.get('consignee')}")

                m_c3.write(f"**Supplier PI No:** {po_full_details.get('supplier_pi_no')}")
                m_c3.write(f"**Supplier PI Date:** {po_full_details.get('supplier_pi_date')}")
                m_c3.write(f"**Payment Terms:** {po_full_details.get('payment_terms')}")
                m_c3.write(f"**Incoterm:** {po_full_details.get('incoterm')}")

                m_c4.write(f"**Origin:** {po_full_details.get('country_of_origin')}")
                m_c4.write(f"**Off Shore 1:** {po_full_details.get('offshore_1_name')}")
                m_c4.write(f"**Off Shore 2:** {po_full_details.get('offshore_2_name')}")
                m_c4.write(f"**Latest Shipment Date:** {po_full_details.get('latest_shipment_date')}")

            col_li, col_sh = st.columns(2)
            with col_li:
                st.markdown("**Itemized Line Breakdown:**")
                items_df = pd.read_sql_query(
                    "SELECT item_code, item_description, hs_code, quantity,"
                    " unit_price, total_price, ssmo_required FROM po_line_items"
                    " WHERE po_number = ?",
                    conn,
                    params=(selected_inspect_po,),
                )
                if not items_df.empty:
                    items_df["unit_price"] = items_df["unit_price"].apply(
                        format_amount
                    )
                    items_df["total_price"] = items_df["total_price"].apply(
                        format_amount
                    )
                    st.dataframe(
                        items_df, use_container_width=True, hide_index=True
                    )
                else:
                    st.info("No line items recorded for this PO.")

            with col_sh:
                st.markdown("**Linked Shipments (BL / AWB):**")
                shp_linked_df = pd.read_sql_query(
                    "SELECT bl_awb, clear_at, est_arrival_date,"
                    " est_clearance_date FROM shipments WHERE po_number = ?",
                    conn,
                    params=(selected_inspect_po,),
                )
                if not shp_linked_df.empty:
                    st.dataframe(
                        shp_linked_df,
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("No shipments linked to this PO yet.")

        conn.close()


# ==============================================================================
# MODULE 2: ATTACH SHIPMENT (BL / AWB)
# ==============================================================================
elif choice == "🚢 Attach Shipment (BL/AWB)":
    st.title("🚢 Attach Shipment to Master Purchase Order")

    conn = get_db_connection()
    existing_pos = pd.read_sql_query(
        "SELECT po_number, bu_id, supplier_name, currency, total_po_value FROM"
        " master_orders WHERE status != 'Completed'",
        conn,
    )

    if existing_pos.empty:
        st.info("No open Master Orders available. Please create a PO first.")
    else:
        selected_po = st.selectbox(
            "Select Master Order (PO) *",
            existing_pos["po_number"].tolist(),
            format_func=lambda x: f"{x} - {existing_pos[existing_pos['po_number'] == x]['supplier_name'].values[0]} ({existing_pos[existing_pos['po_number'] == x]['bu_id'].values[0]})",
        )

        col1, col2 = st.columns(2)
        bl_awb = col1.text_input(
            "BL / AWB Number *", placeholder="e.g. BL-2026-PORT-200"
        )
        clear_at = col2.selectbox(
            "Initial Clearance Route Track", ["Port", "Free Zone", "Pending"]
        )

        col3, col4 = st.columns(2)
        est_arrival = col3.date_input(
            "Estimated Arrival Date (ETA)", value=date.today()
        )
        notes = col4.text_area(
            "Shipment Cargo Description / Notes",
            placeholder="Containers specs, priority handling instructions...",
        )

        if st.button("🚀 Create Shipment & Seed Clearance Tasks"):
            if not bl_awb.strip():
                st.error("BL / AWB Number is required.")
            else:
                po_row = existing_pos[
                    existing_pos["po_number"] == selected_po
                ].iloc[0]
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO shipments (bl_awb, po_number, bu_id, clear_at, est_arrival_date, notes)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            bl_awb.strip(),
                            selected_po,
                            po_row["bu_id"],
                            clear_at,
                            est_arrival.isoformat(),
                            notes,
                        ),
                    )
                    shp_id = cursor.lastrowid

                    seed_tasks_for_shipment(cursor, shp_id)
                    conn.commit()
                    st.success(
                        f"Shipment **{bl_awb}** linked to PO **{selected_po}**"
                        " and initialized in Clearance Workflow Engine!"
                    )
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"Shipment with BL/AWB '{bl_awb}' already exists.")

    st.markdown("---")
    st.subheader("📌 Active Shipments Pipeline")
    shp_df = pd.read_sql_query(
        "SELECT shipment_id, bl_awb, po_number, bu_id, clear_at,"
        " est_arrival_date, est_clearance_date, created_at FROM shipments ORDER"
        " BY created_at DESC",
        conn,
    )
    conn.close()

    if not shp_df.empty:
        st.dataframe(shp_df, use_container_width=True, hide_index=True)


# ==============================================================================
# MODULE 3: CLEARANCE TASK ENGINE
# ==============================================================================
elif choice == "📋 Clearance Task Engine":
    st.title("📋 Clearance Task Workflow Engine")

    conn = get_db_connection()
    shipments = pd.read_sql_query(
        "SELECT shipment_id, bl_awb, po_number, bu_id, clear_at FROM shipments",
        conn,
    )

    if shipments.empty:
        st.warning("No shipments available. Attach a shipment first.")
        st.stop()

    selected_bl = st.selectbox(
        "Select Active Shipment / BL Number:", shipments["bl_awb"].tolist()
    )
    shipment_row = shipments[shipments["bl_awb"] == selected_bl].iloc[0]
    shipment_id = int(shipment_row["shipment_id"])

    shipment_data = dict(
        conn.execute(
            "SELECT * FROM shipments WHERE shipment_id = ?", (shipment_id,)
        ).fetchone()
    )
    tasks_rows = conn.execute(
        "SELECT * FROM process_tasks WHERE shipment_id = ?", (shipment_id,)
    ).fetchall()
    tasks_dict = {row["process_key"]: dict(row) for row in tasks_rows}

    clear_at = shipment_data.get("clear_at", "Port")
    evaluated_statuses = evaluate_process_statuses(tasks_dict, clear_at)

    active_track = clear_at if clear_at in ["Port", "Free Zone"] else "Port"
    track_tasks = [
        t
        for t in tasks_dict.values()
        if t["track"] in ["Common", active_track]
    ]
    total_sla_days = sum(t["target_sla"] for t in track_tasks)

    anchor_date_str = (
        shipment_data.get("act_arrival_date")
        or shipment_data.get("est_arrival_date")
        or date.today().isoformat()
    )
    anchor_date = date.fromisoformat(anchor_date_str)
    calculated_completion_est = anchor_date + timedelta(days=total_sla_days)

    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "PO / BU Reference", f"{shipment_row['po_number']} ({shipment_row['bu_id']})"
    )
    c2.metric("Selected Route Track", f"📍 {clear_at}")
    c3.metric("Cumulative Track SLA", f"{total_sla_days:.2f} Days")
    c4.metric(
        "Est. Completion Date",
        shipment_data.get("est_clearance_date")
        or calculated_completion_est.strftime("%Y-%m-%d"),
    )

    st.markdown("---")
    st.subheader("⚡ Active Clearance Processes Workflow")

    for key, task in tasks_dict.items():
        if task["track"] not in ["Common", clear_at]:
            continue

        status = evaluated_statuses.get(key, "Pending")
        task_data = json.loads(task.get("data_json", "{}"))

        if status == "Completed":
            badge = "🟢 COMPLETED"
        elif status == "Active":
            badge = "🟡 ACTIVE / IN-PROGRESS"
        else:
            badge = "🔒 LOCKED (Awaiting Prerequisite)"

        with st.expander(
            f"{task['process_name']}  |  SLA: {task['target_sla']} Days  | "
            f" Status: {badge}",
            expanded=(status == "Active"),
        ):
            st.caption(
                f"**Track:** {task['track']}  |  **Process Key:** `{key}`"
            )

            if status == "Locked":
                st.info(
                    "✋ Process locked. Complete preceding prerequisite steps to"
                    " activate."
                )
                continue

            updated_data = {}

            # 1. General Info Process
            if key == "gen_info":
                col1, col2 = st.columns(2)
                bl_rec = col1.date_input(
                    "1. BL Copy Receipt Date",
                    value=pd.to_datetime(
                        task_data.get("bl_copy_receipt_date")
                    ).date()
                    if task_data.get("bl_copy_receipt_date")
                    else None,
                    key=f"bl_rec_{shipment_id}",
                )
                orig_rec = col2.date_input(
                    "2. Original Shipment Set Received Date",
                    value=pd.to_datetime(
                        task_data.get("orig_shipment_rec_date")
                    ).date()
                    if task_data.get("orig_shipment_rec_date")
                    else None,
                    key=f"orig_rec_{shipment_id}",
                )

                lc_disabled = not bool(orig_rec)
                lc_no = st.text_input(
                    "3. L/C No. (Activates when Original Set Received)",
                    value=task_data.get("lc_no", ""),
                    disabled=lc_disabled,
                    key=f"lc_no_{shipment_id}",
                )

                col3, col4 = st.columns(2)
                est_arr = col3.date_input(
                    "4. Shipment Estimated Arrival Date",
                    value=pd.to_datetime(
                        shipment_data.get("est_arrival_date")
                    ).date()
                    if shipment_data.get("est_arrival_date")
                    else date.today(),
                    key=f"est_arr_{shipment_id}",
                )
                act_arr = col4.date_input(
                    "5. Shipment Actual Arrival Date",
                    value=pd.to_datetime(
                        shipment_data.get("act_arrival_date")
                    ).date()
                    if shipment_data.get("act_arrival_date")
                    else None,
                    key=f"act_arr_{shipment_id}",
                )

                st.markdown("---")
                st.markdown("**6. Clearance Completion Estimate Date:**")
                col_est1, col_est2 = st.columns(2)

                override_key = f"manual_override_cb_{shipment_id}"
                if override_key not in st.session_state:
                    st.session_state[override_key] = bool(
                        shipment_data.get("manual_override_est_date")
                    )

                with col_est1:
                    manual_override = st.checkbox(
                        "Manually Override Calculated Clearance Completion Estimate",
                        value=st.session_state[override_key],
                        key=override_key,
                    )

                with col_est2:
                    existing_est_date = shipment_data.get("est_clearance_date")
                    default_date = (
                        pd.to_datetime(existing_est_date).date()
                        if (existing_est_date and manual_override)
                        else calculated_completion_est
                    )
                    manual_est_clear_date = st.date_input(
                        "Select Manual Clearance Completion Estimate Date",
                        value=default_date,
                        disabled=not manual_override,
                        key=f"manual_date_input_{shipment_id}",
                    )

                est_clear_date = (
                    manual_est_clear_date
                    if manual_override
                    else calculated_completion_est
                )
                notes = st.text_area(
                    "7. General Notes",
                    value=shipment_data.get("notes", ""),
                    key=f"notes_{shipment_id}",
                )

                updated_data = {
                    "bl_copy_receipt_date": bl_rec.isoformat()
                    if bl_rec
                    else None,
                    "orig_shipment_rec_date": orig_rec.isoformat()
                    if orig_rec
                    else None,
                    "lc_no": lc_no,
                }

            # 2. Track Selection
            elif key == "clear_at_select":
                track_choice = st.selectbox(
                    "Select Clearance Destination Track:",
                    ["Port", "Free Zone"],
                    index=0 if clear_at == "Port" else 1,
                    key=f"track_choice_{shipment_id}",
                )
                updated_data = {"clear_at": track_choice}

            # 3. Cost Estimate
            elif key == "cost_estimate":
                c1, c2 = st.columns(2)
                est_d = c1.date_input(
                    "1. Estimate Date",
                    value=pd.to_datetime(task_data.get("est_date")).date()
                    if task_data.get("est_date")
                    else None,
                    key=f"est_d_{shipment_id}",
                )
                val_raw = c2.text_input(
                    "2. Estimated Value (SDG)",
                    value=format_amount(task_data.get("value", 500000.0)),
                    key=f"cost_val_{shipment_id}",
                )
                val = parse_amount(val_raw)

                c3, c4 = st.columns(2)
                not_bu = c3.date_input(
                    "3. Notify BU Date",
                    value=pd.to_datetime(
                        task_data.get("notify_bu_date")
                    ).date()
                    if task_data.get("notify_bu_date")
                    else None,
                    key=f"not_bu_{shipment_id}",
                )
                amt_rec_d = c4.date_input(
                    "4. Amount Received Date",
                    value=pd.to_datetime(
                        task_data.get("amount_received_date")
                    ).date()
                    if task_data.get("amount_received_date")
                    else None,
                    key=f"amt_rec_{shipment_id}",
                )

                updated_data = {
                    "est_date": est_d.isoformat() if est_d else None,
                    "value": val,
                    "notify_bu_date": not_bu.isoformat() if not_bu else None,
                    "amount_received_date": amt_rec_d.isoformat()
                    if amt_rec_d
                    else None,
                }

            # 4. Delivery Order
            elif key == "delivery_order":
                c1, c2 = st.columns(2)
                copy_do = c1.checkbox(
                    "1. Copy of DO Collected",
                    value=bool(task_data.get("copy_do")),
                    key=f"copy_do_{shipment_id}",
                )
                do_fees_raw = c2.text_input(
                    "2. DO Fees (SDG)",
                    value=format_amount(task_data.get("do_fees", 150000.0)),
                    key=f"do_fees_{shipment_id}",
                )
                do_fees = parse_amount(do_fees_raw)

                c3, c4 = st.columns(2)
                settle_d = c3.date_input(
                    "3. DO Fees Settled Date",
                    value=pd.to_datetime(task_data.get("settled_date")).date()
                    if task_data.get("settled_date")
                    else None,
                    key=f"do_settle_{shipment_id}",
                )
                rec_d = c4.date_input(
                    "4. DO Received Date",
                    value=pd.to_datetime(task_data.get("received_date")).date()
                    if task_data.get("received_date")
                    else None,
                    key=f"do_rec_{shipment_id}",
                )
                updated_data = {
                    "copy_do": copy_do,
                    "do_fees": do_fees,
                    "settled_date": settle_d.isoformat() if settle_d else None,
                    "received_date": rec_d.isoformat() if rec_d else None,
                }

            # 5. Customs Certificate
            elif key == "customs_cert":
                c1, c2 = st.columns(2)
                entry_d = c1.date_input(
                    "1. Entry Date",
                    value=pd.to_datetime(task_data.get("entry_date")).date()
                    if task_data.get("entry_date")
                    else None,
                    key=f"cert_entry_{shipment_id}",
                )
                scuda_no = c2.text_input(
                    "2. SCUDA Declaration No.",
                    value=task_data.get("scuda_no", "SCUDA-99182"),
                    key=f"scuda_{shipment_id}",
                )
                updated_data = {
                    "entry_date": entry_d.isoformat() if entry_d else None,
                    "scuda_no": scuda_no,
                }

            # Generic Step
            else:
                st.caption("Standard task status recording")

            st.markdown("---")
            c_save, c_mark = st.columns([2, 1])
            save_clicked = c_save.button(
                "💾 Save Inputs", key=f"btn_save_{key}_{shipment_id}"
            )
            complete_clicked = c_mark.button(
                "✅ Mark Complete", key=f"btn_comp_{key}_{shipment_id}"
            )

            if save_clicked or complete_clicked:
                new_status = "Completed" if complete_clicked else status
                now_str = (
                    date.today().isoformat()
                    if complete_clicked
                    else task.get("completed_at")
                )

                conn.execute(
                    """
                    UPDATE process_tasks 
                    SET data_json = ?, status = ?, completed_at = ?
                    WHERE task_id = ?
                """,
                    (
                        json.dumps(updated_data),
                        new_status,
                        now_str,
                        task["task_id"],
                    ),
                )

                if key == "gen_info":
                    conn.execute(
                        """
                        UPDATE shipments 
                        SET est_arrival_date = ?, act_arrival_date = ?, est_clearance_date = ?, 
                            manual_override_est_date = ?, notes = ?
                        WHERE shipment_id = ?
                    """,
                        (
                            est_arr.isoformat() if est_arr else None,
                            act_arr.isoformat() if act_arr else None,
                            est_clear_date.isoformat()
                            if est_clear_date
                            else None,
                            1 if manual_override else 0,
                            notes,
                            shipment_id,
                        ),
                    )
                elif key == "clear_at_select":
                    conn.execute(
                        "UPDATE shipments SET clear_at = ? WHERE shipment_id ="
                        " ?",
                        (updated_data["clear_at"], shipment_id),
                    )

                conn.commit()
                st.success(f"Updated '{task['process_name']}' successfully!")
                st.rerun()

    conn.close()


# ==============================================================================
# MODULE 4: ANALYTICS & TARGET SLA CONFIGURATION
# ==============================================================================
elif choice == "📊 Clearance & SLA Analytics":
    st.title("📊 Clearance SLA & Bottleneck Analytics")

    conn = get_db_connection()
    df_tasks = pd.read_sql_query(
        """
        SELECT t.task_id, s.bl_awb, s.po_number, s.clear_at, t.process_name, t.track, t.target_sla, t.status
        FROM process_tasks t
        JOIN shipments s ON t.shipment_id = s.shipment_id
    """,
        conn,
    )
    conn.close()

    if not df_tasks.empty:
        total_tasks = len(df_tasks)
        completed_tasks = len(df_tasks[df_tasks["status"] == "Completed"])
        active_tasks = len(df_tasks[df_tasks["status"] == "Active"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Steps", total_tasks)
        m2.metric("Completed Steps", completed_tasks)
        m3.metric("Active Steps", active_tasks)
        m4.metric(
            "Overall Progress", f"{(completed_tasks/total_tasks*100):.1f}%"
        )

        st.markdown("---")
        st.markdown("### ⏳ Target SLA Summary by Process Step")
        sla_summary = (
            df_tasks.groupby(["track", "process_name"])
            .agg(
                target_sla=("target_sla", "first"),
                completed_count=("status", lambda x: (x == "Completed").sum()),
                active_count=("status", lambda x: (x == "Active").sum()),
            )
            .reset_index()
        )

        st.dataframe(sla_summary, use_container_width=True, hide_index=True)

elif choice == "⚙️ Target SLA Settings":
    st.title("⚙️ Configure Process Target SLAs")

    conn = get_db_connection()
    distinct_tasks = pd.read_sql_query(
        "SELECT DISTINCT process_key, process_name, track, target_sla FROM"
        " process_tasks",
        conn,
    )

    if not distinct_tasks.empty:
        selected_proc = st.selectbox(
            "Select Process to Edit SLA:",
            distinct_tasks["process_name"].tolist(),
        )
        proc_row = distinct_tasks[
            distinct_tasks["process_name"] == selected_proc
        ].iloc[0]

        c1, c2 = st.columns(2)
        c1.text_input("Track Route", value=proc_row["track"], disabled=True)
        new_sla = c2.number_input(
            "Target SLA (Days)",
            value=float(proc_row["target_sla"]),
            step=0.25,
            min_value=0.1,
        )

        if st.button("💾 Save Updated SLA"):
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE process_tasks SET target_sla = ? WHERE process_name ="
                " ?",
                (new_sla, selected_proc),
            )
            conn.commit()
            st.success(
                f"Updated SLA for '{selected_proc}' to {new_sla} days!"
            )
            st.rerun()
    conn.close()
