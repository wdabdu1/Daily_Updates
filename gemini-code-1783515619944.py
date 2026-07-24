conn = sqlite3.connect("your_db_name.db", timeout=30.0)
conn.execute("PRAGMA journal_mode=WAL;")
import json
import sqlite3
from datetime import date, datetime, timedelta
import pandas as pd
import streamlit as st

# --- STREAMLIT PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Supply Chain, Offshore & Treasury Engine",
    page_icon="🚢",
    layout="wide",
)

# --- FX CONVERSION RATES TO USD ---
FX_RATES = {
    "USD": 1.0,
    "EUR": 1.08,
    "SDG": 0.00037,
    "AED": 0.272,
}

FORWARDER_LIST = [
    "DHS Logistics",
    "Kuehne+Nagel",
    "DB Schenker",
    "Maersk Line",
    "Bollore Africa",
    "Custom Forwarder",
]
BANK_LIST = [
    "Bank of Khartoum",
    "Omdurman National Bank",
    "Faisal Islamic Bank",
    "Standard Chartered FZE",
    "Emirates NBD",
    "Mashreq Bank",
]
DISPATCH_VIA_LIST = [
    "DHL Express",
    "FedEx",
    "Aramex",
    "Diplomatic Pouch",
    "Hand Delivery",
]
TENOR_LIST = [
    "Sight",
    "30 Days",
    "60 Days",
    "90 Days",
    "120 Days",
    "180 Days",
]
CURRENCY_LIST = ["USD", "EUR", "SDG", "AED"]


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


def get_index_safe(lst: list, value: str, default: int = 0) -> int:
    """Safely finds list index for selectboxes, falling back to default index."""
    if value in lst:
        return lst.index(value)
    return default


# --- DATABASE CONNECTION & INITIALIZATION ---
def get_db_connection():
    conn = sqlite3.connect("shipments.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Master Orders Header Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_orders (
            po_number TEXT PRIMARY KEY,
            bu_id TEXT,
            division TEXT,
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
            offshore_companies_json TEXT,
            offshore_po_no TEXT,
            offshore_po_date DATE,
            bu_est_shipping_cost REAL,
            mode_of_shipment TEXT,
            currency TEXT DEFAULT 'USD',
            total_po_value REAL DEFAULT 0.0,
            port_of_loading TEXT,
            order_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. PO Line Items Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS po_line_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT,
            category TEXT,
            model_product TEXT,
            type TEXT,
            ordered_qty REAL,
            unit_price REAL,
            total_value REAL,
            currency TEXT DEFAULT 'USD',
            item_code TEXT,
            item_description TEXT,
            hs_code TEXT,
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
            supplier_invoice_no TEXT,
            supplier_invoice_date DATE,
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

    # 4. Shipment Line Items Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipment_line_items (
            shipment_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER,
            po_item_id INTEGER,
            category TEXT,
            model_product TEXT,
            type TEXT,
            qty_shipped REAL,
            unit_price REAL,
            total_shipped_value REAL,
            offshore_pricing_json TEXT,
            FOREIGN KEY(shipment_id) REFERENCES shipments(shipment_id),
            FOREIGN KEY(po_item_id) REFERENCES po_line_items(item_id)
        )
    """)

    # 5. Grouped Actions / Key-Value Details per Shipment
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipment_group_data (
            shipment_id INTEGER,
            group_key TEXT,
            data_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (shipment_id, group_key),
            FOREIGN KEY(shipment_id) REFERENCES shipments(shipment_id)
        )
    """)

    # 6. Process Tasks Table
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

    # Seed Sample Data if Empty
    cursor.execute(
        "SELECT COUNT(*) FROM master_orders WHERE po_number = 'PO-2026-8812'"
    )
    if cursor.fetchone()[0] == 0:
        today = date.today()

        cursor.execute(
            """
            INSERT OR IGNORE INTO master_orders 
            (po_number, bu_id, division, supplier_name, brand_manufacturer, approval_type, consignee, 
             supplier_pi_no, supplier_pi_date, payment_terms, rec_signed_pi_date, sent_signed_pi_date, bu_po_date, 
             order_execution_date, latest_shipment_date, incoterm, country_of_origin, offshore_companies_json,
             offshore_po_no, offshore_po_date, bu_est_shipping_cost, mode_of_shipment, currency, total_po_value, port_of_loading, order_date)
            VALUES 
            ('PO-2026-8812', 'BU-LOGISTICS', 'Heavy Equipment Div', 'Global Industrial Supplies', 'CAT / Siemens', 'Standard', 'Sudan Operations LLC',
             'PI-88102', ?, 'L/C 90 Days', ?, ?, ?, ?, ?, 'CIF', 'Germany', ?,
             'OFF-PO-9912', ?, 12500.0, 'Sea', 'USD', 250000.0, 'Hamburg Port', ?)
        """,
            (
                (today - timedelta(days=20)).isoformat(),
                (today - timedelta(days=18)).isoformat(),
                (today - timedelta(days=17)).isoformat(),
                (today - timedelta(days=16)).isoformat(),
                (today - timedelta(days=15)).isoformat(),
                (today + timedelta(days=30)).isoformat(),
                json.dumps([
                    "Red Sea Trading FZE",
                    "Apex Global Offshore Ltd",
                ]),
                (today - timedelta(days=18)).isoformat(),
                (today - timedelta(days=15)).isoformat(),
            ),
        )

        cursor.execute("""
            INSERT OR IGNORE INTO po_line_items 
            (po_number, category, model_product, type, ordered_qty, unit_price, total_value, currency, item_code, item_description, hs_code, ssmo_required)
            VALUES 
            ('PO-2026-8812', 'Machinery', 'CAT 500KW Generator', 'Heavy Duty', 2, 100000.0, 200000.0, 'USD', 'GEN-500KW', '500KW Heavy Duty Industrial Generator', '8502.13.00', 1),
            ('PO-2026-8812', 'Spare Parts', 'Air Filter Set', 'OEM Replacement', 50, 1000.0, 50000.0, 'USD', 'SPA-FILTER', 'Replacement Air Filter Assembly Set', '8421.23.00', 0)
        """)

        cursor.execute(
            """
            INSERT OR IGNORE INTO shipments (bl_awb, po_number, bu_id, supplier_invoice_no, supplier_invoice_date, est_arrival_date, clear_at, notes)
            VALUES 
            ('BL-2026-PORT-101', 'PO-2026-8812', 'BU-LOGISTICS', 'INV-2026-001', ?, ?, 'Port', 'Priority heavy equipment shipment')
        """,
            (
                (today - timedelta(days=5)).isoformat(),
                (today + timedelta(days=2)).isoformat(),
            ),
        )

        cursor.execute(
            "SELECT shipment_id FROM shipments WHERE bl_awb ="
            " 'BL-2026-PORT-101'"
        )
        shp1_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT OR IGNORE INTO shipment_line_items (shipment_id, po_item_id, category, model_product, type, qty_shipped, unit_price, total_shipped_value, offshore_pricing_json)
            VALUES 
            (?, 1, 'Machinery', 'CAT 500KW Generator', 'Heavy Duty', 2, 100000.0, 200000.0, ?),
            (?, 2, 'Spare Parts', 'Air Filter Set', 'OEM Replacement', 50, 1000.0, 50000.0, ?)
        """,
            (
                shp1_id,
                json.dumps({"0": 110000.0, "1": 115000.0}),
                shp1_id,
                json.dumps({"0": 1150.0, "1": 1200.0}),
            ),
        )

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


def update_master_order_total(conn, po_number):
    """Recalculates total_po_value in master_orders based on line items."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(total_value) FROM po_line_items WHERE po_number = ?",
        (po_number,),
    )
    res = cursor.fetchone()[0]
    total_val = float(res) if res is not None else 0.0
    cursor.execute(
        "UPDATE master_orders SET total_po_value = ? WHERE po_number = ?",
        (total_val, po_number),
    )
    conn.commit()


def save_group_data(shipment_id: int, group_key: str, data_dict: dict):
    """Saves grouped form inputs for a specific shipment."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO shipment_group_data (shipment_id, group_key, data_json)
        VALUES (?, ?, ?)
        ON CONFLICT(shipment_id, group_key) DO UPDATE SET
            data_json = excluded.data_json,
            updated_at = CURRENT_TIMESTAMP
    """,
        (shipment_id, group_key, json.dumps(data_dict)),
    )
    conn.commit()
    conn.close()


def load_group_data(shipment_id: int, group_key: str) -> dict:
    """Loads stored group form inputs for a shipment."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT data_json FROM shipment_group_data WHERE shipment_id = ? AND"
        " group_key = ?",
        (shipment_id, group_key),
    )
    row = cursor.fetchone()
    conn.close()
    if row and row["data_json"]:
        return json.loads(row["data_json"])
    return {}


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
    "📂 Shipment Grouped Details & Actions",
    "📈 Offshore Valuation & Profitability",
    "🏦 Treasury Operations",
    "📋 Clearance Task Engine",
    "📊 Clearance & SLA Analytics",
    "⚙️ Target SLA Settings",
]
choice = st.sidebar.selectbox("Select Module", menu)


# ==============================================================================
# MODULE 1: MASTER ORDERS & LINE ITEMS
# ==============================================================================
if choice == "📦 Master Orders & Line Items":
    st.title("📦 Master Purchase Order & Line Item Management")

    tab1, tab2 = st.tabs(
        ["1️⃣ Create / Manage PO & Line Items", "2️⃣ Master Order Registry"]
    )

    with tab1:
        st.subheader("1️⃣ Create Master Order Header")

        st.markdown("##### 🏢 Order Identity & Business Entities")
        c1, c2, c3 = st.columns(3)
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

        c4, c5, c6, c7 = st.columns(4)
        supplier_name = c4.text_input(
            "Supplier Name *", placeholder="e.g. Global Industrial Supplies"
        )
        brand_manufacturer = c5.text_input(
            "Brand / Manufacturer", placeholder="e.g. Caterpillar / Siemens"
        )
        approval_type = c6.selectbox(
            "Approval Type", ["Standard", "Fast-Track", "Board Approved", "Emergency"]
        )
        consignee = c7.text_input(
            "Consignee Entity", placeholder="e.g. Sudan Operations LLC"
        )

        st.markdown("---")
        st.markdown("##### 🏢 Offshore Companies (Dynamic Multiple Entities)")
        st.caption(
            "Provide Offshore Company 1, and optionally add Offshore 2, Offshore"
            " 3, etc."
        )

        if "offshore_companies_list" not in st.session_state:
            st.session_state["offshore_companies_list"] = [""]

        offshore_inputs = []
        offshore_cols = st.columns(
            max(1, len(st.session_state["offshore_companies_list"]))
        )
        for idx in range(len(st.session_state["offshore_companies_list"])):
            with offshore_cols[idx]:
                label = f"Offshore Company {idx+1}" + (
                    " (Primary)" if idx == 0 else " (Optional)"
                )
                val = st.text_input(
                    label,
                    value=st.session_state["offshore_companies_list"][idx],
                    key=f"offshore_input_{idx}",
                )
                offshore_inputs.append(val)

        col_add_co, col_rem_co = st.columns([1, 4])
        if col_add_co.button("➕ Add Another Offshore Company"):
            st.session_state["offshore_companies_list"].append("")
            st.rerun()

        st.markdown("---")
        st.markdown("##### 📄 Supplier PI, Offshore PO & Shipping Terms")
        c8, c9, c10, c11 = st.columns(4)
        supplier_pi_no = c8.text_input(
            "Supplier PI No", placeholder="e.g. PI-99201"
        )
        supplier_pi_date = c9.date_input(
            "Supplier PI Date", value=date.today()
        )
        payment_terms = c10.selectbox(
            "Supplier Payment Terms",
            ["L/C 90 Days", "L/C at Sight", "30% Advance / 70% LC", "CAD", "Open Account"],
        )
        incoterm = c11.selectbox(
            "Incoterm", ["CIF", "FOB", "CFR", "EXW", "DDP", "FCA"]
        )

        c12, c13, c14, c15 = st.columns(4)
        country_of_origin = c12.selectbox(
            "Origin (Country)",
            ["Germany", "China", "United States", "Turkey", "India", "UAE", "Saudi Arabia"],
        )
        offshore_po_no = c13.text_input(
            "Offshore PO No.", placeholder="e.g. OFF-PO-9910"
        )
        offshore_po_date = c14.date_input(
            "Offshore PO Date", value=date.today()
        )
        mode_of_shipment = c15.selectbox(
            "Mode of Shipment", ["Sea", "Air", "Courier"]
        )

        c16, c17, c18 = st.columns(3)
        bu_est_shipping_raw = c16.text_input(
            "BU Estimated Shipping Cost", value="10,000.00"
        )
        bu_est_shipping_cost = parse_amount(bu_est_shipping_raw)
        port_of_loading = c17.text_input(
            "Port of Loading", placeholder="e.g. Hamburg Port"
        )
        currency_master = c18.selectbox(
            "Master Currency", CURRENCY_LIST
        )

        st.markdown("---")
        st.markdown("##### 📅 Key Milestone Dates")
        d1, d2, d3, d4, d5 = st.columns(5)
        rec_signed_pi_date = d1.date_input("Received Signed PI Date", value=date.today())
        sent_signed_pi_date = d2.date_input("Sent Signed PI Date", value=date.today())
        bu_po_date = d3.date_input("BU PO Date", value=date.today())
        order_execution_date = d4.date_input("Order Execution Date", value=date.today())
        latest_shipment_date = d5.date_input("Latest Shipment Date", value=date.today() + timedelta(days=60))

        st.markdown("---")
        if st.button(
            "💾 Save Master Order Header",
            use_container_width=True,
            type="primary",
        ):
            if not po_number.strip() or not supplier_name.strip():
                st.error("PO Number and Supplier Name are required fields.")
            else:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cleaned_offshore_list = [
                        name.strip() for name in offshore_inputs if name.strip()
                    ]
                    offshore_json_str = json.dumps(cleaned_offshore_list)

                    cursor.execute(
                        """
                        INSERT INTO master_orders 
                        (po_number, bu_id, division, supplier_name, brand_manufacturer, approval_type, consignee,
                         supplier_pi_no, supplier_pi_date, payment_terms, rec_signed_pi_date, sent_signed_pi_date, bu_po_date,
                         order_execution_date, latest_shipment_date, incoterm, country_of_origin, offshore_companies_json,
                         offshore_po_no, offshore_po_date, bu_est_shipping_cost, mode_of_shipment, currency, total_po_value, port_of_loading, order_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?)
                    """,
                        (
                            po_number.strip(),
                            bu_id,
                            division,
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
                            offshore_json_str,
                            offshore_po_no.strip(),
                            offshore_po_date.isoformat(),
                            bu_est_shipping_cost,
                            mode_of_shipment,
                            currency_master,
                            port_of_loading.strip(),
                            bu_po_date.isoformat(),
                        ),
                    )
                    conn.commit()
                    st.session_state["active_po_for_items"] = po_number.strip()
                    st.success(
                        f"Master Order Header **{po_number.strip()}** saved"
                        " successfully!"
                    )
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"PO Number '{po_number.strip()}' already exists.")
                finally:
                    conn.close()

        st.markdown("---")
        st.subheader("2️⃣ PO Line Items Entry")

        conn = get_db_connection()
        all_master_pos = pd.read_sql_query(
            "SELECT po_number, supplier_name, bu_id, currency, total_po_value FROM master_orders ORDER BY created_at DESC",
            conn,
        )

        if all_master_pos.empty:
            st.warning(
                "🔒 **PO Line Items Entry is locked.** Please fill out and save a"
                " Master Order Header above."
            )
        else:
            po_list = all_master_pos["po_number"].tolist()
            default_index = 0
            if (
                "active_po_for_items" in st.session_state
                and st.session_state["active_po_for_items"] in po_list
            ):
                default_index = po_list.index(st.session_state["active_po_for_items"])

            selected_open_po = st.selectbox(
                "Select Open Master Order (PO) to Add or View Line Items *",
                po_list,
                index=default_index,
                format_func=lambda x: f"{x} — {all_master_pos[all_master_pos['po_number'] == x]['supplier_name'].values[0]} ({all_master_pos[all_master_pos['po_number'] == x]['bu_id'].values[0]})",
            )

            current_items_df = pd.read_sql_query(
                "SELECT item_id, category, model_product, type, ordered_qty, unit_price, total_value, currency, hs_code, ssmo_required FROM po_line_items WHERE po_number = ?",
                conn,
                params=(selected_open_po,),
            )

            po_meta = all_master_pos[all_master_pos["po_number"] == selected_open_po].iloc[0]
            
            st.markdown(f"##### Current Saved Line Items for `{selected_open_po}`:")
            if not current_items_df.empty:
                disp_df = current_items_df.copy()
                disp_df["unit_price"] = disp_df["unit_price"].apply(format_amount)
                disp_df["total_value"] = disp_df["total_value"].apply(format_amount)
                st.dataframe(disp_df, use_container_width=True, hide_index=True)
                st.info(
                    f"Current Master Order Total Value: **{po_meta['currency']} {format_amount(po_meta['total_po_value'])}**"
                )
            else:
                st.info("No line items added yet for this PO.")

            with st.expander("➕ Add New Line Item to Selected PO", expanded=True):
                li_c1, li_c2, li_c3 = st.columns(3)
                category = li_c1.selectbox(
                    "Category *",
                    ["Machinery", "Spare Parts", "Electronics", "Raw Materials", "Vehicles", "Chemicals"],
                )
                model_product = li_c2.text_input(
                    "Model / Product *", placeholder="e.g. CAT 500KW Generator"
                )
                item_type = li_c3.selectbox(
                    "Type *",
                    ["Heavy Duty", "Standard", "OEM Replacement", "Industrial", "Consumable"],
                )

                li_c4, li_c5, li_c6, li_c7 = st.columns(4)
                ordered_qty = li_c4.number_input(
                    "Ordered Qty *", min_value=1.0, value=1.0
                )
                u_price_raw = li_c5.text_input("Unit Price *", value="1,000.00")
                unit_price = parse_amount(u_price_raw)
                item_currency = li_c6.selectbox(
                    "Currency", CURRENCY_LIST, index=0
                )
                ssmo_req = li_c7.checkbox("SSMO Inspection Req.?", value=True)

                li_c8, li_c9 = st.columns(2)
                hs_code = li_c8.text_input("HS Code", placeholder="8502.13.00")
                item_code = li_c9.text_input(
                    "Item Code / Part No.", placeholder="GEN-500KW"
                )

                total_value = ordered_qty * unit_price
                st.caption(
                    f"Calculated Item Value: **{item_currency} {format_amount(total_value)}**"
                )

                if st.button("➕ Save Item to Master Order"):
                    if not model_product.strip():
                        st.error("Model / Product Name is required.")
                    else:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            INSERT INTO po_line_items 
                            (po_number, category, model_product, type, ordered_qty, unit_price, total_value, currency, item_code, item_description, hs_code, ssmo_required)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                selected_open_po,
                                category,
                                model_product.strip(),
                                item_type,
                                ordered_qty,
                                unit_price,
                                total_value,
                                item_currency,
                                item_code.strip(),
                                f"{model_product.strip()} ({item_type})",
                                hs_code.strip(),
                                1 if ssmo_req else 0,
                            ),
                        )
                        conn.commit()
                        update_master_order_total(conn, selected_open_po)
                        st.success(
                            f"Line item '{model_product.strip()}' successfully added!"
                        )
                        st.rerun()

        conn.close()

    with tab2:
        st.subheader("📋 Registered Master Orders Registry")
        conn = get_db_connection()
        mo_df = pd.read_sql_query(
            "SELECT po_number, bu_id, division, supplier_name, brand_manufacturer, consignee, supplier_pi_no, mode_of_shipment, incoterm, country_of_origin, currency, total_po_value, latest_shipment_date FROM master_orders ORDER BY created_at DESC",
            conn,
        )

        if not mo_df.empty:
            mo_df["total_po_value"] = mo_df["total_po_value"].apply(
                format_amount
            )
            st.dataframe(mo_df, use_container_width=True, hide_index=True)
        conn.close()


# ==============================================================================
# MODULE 2: ATTACH SHIPMENT (BL/AWB)
# ==============================================================================
elif choice == "🚢 Attach Shipment (BL/AWB)":
    st.title("🚢 Attach Shipment & Invoice Details to Master Order")

    conn = get_db_connection()
    existing_pos = pd.read_sql_query(
        "SELECT po_number, bu_id, supplier_name, currency, total_po_value FROM master_orders",
        conn,
    )

    if existing_pos.empty:
        st.info("No Master Orders available. Please create a PO first.")
    else:
        selected_po = st.selectbox(
            "Select Master Order (PO) *",
            existing_pos["po_number"].tolist(),
            format_func=lambda x: f"{x} - {existing_pos[existing_pos['po_number'] == x]['supplier_name'].values[0]} ({existing_pos[existing_pos['po_number'] == x]['bu_id'].values[0]})",
        )

        st.markdown("##### 📦 Shipment Header & Supplier Invoice Details")
        col1, col2, col3 = st.columns(3)
        bl_awb = col1.text_input(
            "BL / AWB Number *", placeholder="e.g. BL-2026-PORT-200"
        )
        supplier_invoice_no = col2.text_input(
            "Supplier Invoice No. *", placeholder="e.g. INV-2026-9901"
        )
        supplier_invoice_date = col3.date_input(
            "Supplier Invoice Date", value=date.today()
        )

        col4, col5 = st.columns(2)
        est_arrival = col4.date_input(
            "Estimated Arrival Date (ETA)", value=date.today()
        )
        notes = col5.text_area(
            "Shipment Notes", placeholder="Cargo details, container numbers..."
        )

        st.markdown("---")
        st.markdown("##### 🛒 Shipment Item Level Breakdown")
        po_items_df = pd.read_sql_query(
            "SELECT item_id, category, model_product, type, ordered_qty, unit_price FROM po_line_items WHERE po_number = ?",
            conn,
            params=(selected_po,),
        )

        if "shipment_items_temp" not in st.session_state:
            st.session_state["shipment_items_temp"] = []

        if not po_items_df.empty:
            item_options = po_items_df["model_product"].tolist()
            selected_model = st.selectbox(
                "Select Model/Product from PO Line Items:", item_options
            )

            po_item_row = po_items_df[
                po_items_df["model_product"] == selected_model
            ].iloc[0]

            sh_c1, sh_c2, sh_c3 = st.columns(3)
            sh_c1.text_input(
                "Category", value=po_item_row["category"], disabled=True
            )
            sh_c2.text_input(
                "Model / Product",
                value=po_item_row["model_product"],
                disabled=True,
            )
            sh_c3.text_input("Type", value=po_item_row["type"], disabled=True)

            sh_c4, sh_c5, sh_c6 = st.columns(3)
            qty_shipped = sh_c4.number_input(
                "QTY Shipped *",
                min_value=0.1,
                value=float(po_item_row["ordered_qty"]),
            )
            u_price_sh_raw = sh_c5.text_input(
                "UNIT PRICE *", value=format_amount(po_item_row["unit_price"])
            )
            unit_price_sh = parse_amount(u_price_sh_raw)

            total_shipped_val = qty_shipped * unit_price_sh
            sh_c6.markdown(
                f"**Total Shipped Value:**\n###"
                f" {format_amount(total_shipped_val)}"
            )

            if st.button("➕ Add Item to Shipment"):
                st.session_state["shipment_items_temp"].append({
                    "po_item_id": int(po_item_row["item_id"]),
                    "category": po_item_row["category"],
                    "model_product": po_item_row["model_product"],
                    "type": po_item_row["type"],
                    "qty_shipped": qty_shipped,
                    "unit_price": unit_price_sh,
                    "total_shipped_value": total_shipped_val,
                })
                st.success(
                    f"Added '{po_item_row['model_product']}' to shipment items!"
                )
                st.rerun()

            if st.session_state["shipment_items_temp"]:
                st.markdown("##### Shipment Items Summary:")
                sh_summary_df = pd.DataFrame(
                    st.session_state["shipment_items_temp"]
                )
                sh_summary_df["formatted_unit_price"] = sh_summary_df[
                    "unit_price"
                ].apply(format_amount)
                sh_summary_df["formatted_total"] = sh_summary_df[
                    "total_shipped_value"
                ].apply(format_amount)
                st.dataframe(
                    sh_summary_df[[
                        "category",
                        "model_product",
                        "type",
                        "qty_shipped",
                        "formatted_unit_price",
                        "formatted_total",
                    ]],
                    use_container_width=True,
                    hide_index=True,
                )

        else:
            st.warning("Selected Master Order has no line items defined.")

        st.markdown("---")
        if st.button(
            "🚀 Create Shipment & Initialize Workflow Tasks", type="primary"
        ):
            if not bl_awb.strip() or not supplier_invoice_no.strip():
                st.error("BL / AWB Number and Supplier Invoice No. are required.")
            else:
                po_row = existing_pos[
                    existing_pos["po_number"] == selected_po
                ].iloc[0]
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO shipments (bl_awb, po_number, bu_id, supplier_invoice_no, supplier_invoice_date, clear_at, est_arrival_date, notes)
                        VALUES (?, ?, ?, ?, ?, 'Port', ?, ?)
                    """,
                        (
                            bl_awb.strip(),
                            selected_po,
                            po_row["bu_id"],
                            supplier_invoice_no.strip(),
                            supplier_invoice_date.isoformat(),
                            est_arrival.isoformat(),
                            notes,
                        ),
                    )
                    shp_id = cursor.lastrowid

                    for sh_item in st.session_state["shipment_items_temp"]:
                        cursor.execute(
                            """
                            INSERT INTO shipment_line_items (shipment_id, po_item_id, category, model_product, type, qty_shipped, unit_price, total_shipped_value)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                shp_id,
                                sh_item["po_item_id"],
                                sh_item["category"],
                                sh_item["model_product"],
                                sh_item["type"],
                                sh_item["qty_shipped"],
                                sh_item["unit_price"],
                                sh_item["total_shipped_value"],
                            ),
                        )

                    seed_tasks_for_shipment(cursor, shp_id)
                    conn.commit()
                    st.success(
                        f"Shipment **{bl_awb}** successfully attached to"
                        f" **{selected_po}**!"
                    )
                    st.session_state["shipment_items_temp"] = []
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"Shipment with BL/AWB '{bl_awb}' already exists.")

    conn.close()


# ==============================================================================
# MODULE 3: SHIPMENT GROUPED DETAILS & ACTIONS (13 WORKFLOW GROUPS)
# ==============================================================================
elif choice == "📂 Shipment Grouped Details & Actions":
    st.title("📂 Shipment Level Grouped Actions & Entry")

    conn = get_db_connection()
    shipments_df = pd.read_sql_query(
        "SELECT s.shipment_id, s.bl_awb, s.po_number, m.offshore_companies_json, m.bu_est_shipping_cost FROM shipments s JOIN master_orders m ON s.po_number = m.po_number",
        conn,
    )
    conn.close()

    if shipments_df.empty:
        st.warning("No active shipments available. Attach a shipment first.")
    else:
        selected_bl = st.selectbox(
            "Select BL/AWB Shipment *", shipments_df["bl_awb"].tolist()
        )
        shp_row = shipments_df[shipments_df["bl_awb"] == selected_bl].iloc[0]
        shipment_id = int(shp_row["shipment_id"])
        bu_est_shipping = float(shp_row["bu_est_shipping_cost"] or 0.0)

        # Parse linked offshore companies from Master Order
        raw_offshores = shp_row["offshore_companies_json"]
        offshore_list = (
            json.loads(raw_offshores)
            if raw_offshores
            else ["Primary Offshore"]
        )
        if not offshore_list:
            offshore_list = ["Primary Offshore"]

        st.info(
            f"Linked PO: **{shp_row['po_number']}** | Configured Offshore"
            f" Entities: **{', '.join(offshore_list)}**"
        )

        def group_save_button(group_key, data_dict):
            if st.button(
                f"💾 Save {group_key.replace('_', ' ').title()} Group Data",
                key=f"save_btn_{group_key}_{shipment_id}",
            ):
                save_group_data(shipment_id, group_key, data_dict)
                st.success(
                    f"Saved {group_key.replace('_', ' ').title()} information!"
                )
                st.rerun()

        # ----------------------------------------------------------------------
        # 1. Forwarder Group
        # ----------------------------------------------------------------------
        with st.expander("🚚 1. Forwarder Group", expanded=False):
            g_data = load_group_data(shipment_id, "forwarder")
            c1, c2, c3 = st.columns(3)
            fwd_name = c1.selectbox(
                "Forwarder Name",
                FORWARDER_LIST,
                index=get_index_safe(FORWARDER_LIST, g_data.get("fwd_name")),
                key=f"fwd_name_{shipment_id}",
            )
            act_ship_cost = c2.number_input(
                "Actual Shipping Cost",
                value=float(g_data.get("act_ship_cost", 0.0)),
                key=f"act_ship_cost_{shipment_id}",
            )
            act_ship_cost_usd = c3.number_input(
                "Actual Shipping Cost $",
                value=float(g_data.get("act_ship_cost_usd", 0.0)),
                key=f"act_ship_cost_usd_{shipment_id}",
            )

            c4, c5 = st.columns(2)
            amt_saved = bu_est_shipping - act_ship_cost_usd
            c4.metric(
                "Amount Saved in Shipping Cost ($)", f"${amt_saved:,.2f}"
            )
            marine_ins = c5.selectbox(
                "Marine Insurance",
                ["Yes", "No"],
                index=0 if g_data.get("marine_ins") == "Yes" else 1,
                key=f"marine_ins_{shipment_id}",
            )

            group_save_button("forwarder", {
                "fwd_name": fwd_name,
                "act_ship_cost": act_ship_cost,
                "act_ship_cost_usd": act_ship_cost_usd,
                "amt_saved": amt_saved,
                "marine_ins": marine_ins,
            })

        # ----------------------------------------------------------------------
        # 2. ACD Group
        # ----------------------------------------------------------------------
        with st.expander("📌 2. ACD (Advance Cargo Declaration)", expanded=False):
            g_data = load_group_data(shipment_id, "acd")
            c1, c2, c3, c4 = st.columns(4)
            acd_date = c1.date_input(
                "ACD Process Date",
                value=pd.to_datetime(g_data.get("acd_date")).date()
                if g_data.get("acd_date")
                else date.today(),
                key=f"acd_date_{shipment_id}",
            )
            acd_cost_usd = c2.number_input(
                "ACD COST $",
                value=float(g_data.get("acd_cost_usd", 0.0)),
                key=f"acd_cost_usd_{shipment_id}",
            )
            acd_settled_date = c3.date_input(
                "ACD Cost Settled Date",
                value=pd.to_datetime(g_data.get("acd_settled_date")).date()
                if g_data.get("acd_settled_date")
                else date.today(),
                key=f"acd_settled_date_{shipment_id}",
            )
            acd_number = c4.text_input(
                "ACD Number",
                value=g_data.get("acd_number", ""),
                key=f"acd_number_{shipment_id}",
            )

            group_save_button("acd", {
                "acd_date": acd_date.isoformat(),
                "acd_cost_usd": acd_cost_usd,
                "acd_settled_date": acd_settled_date.isoformat(),
                "acd_number": acd_number,
            })

        # ----------------------------------------------------------------------
        # 3. Draft Documents
        # ----------------------------------------------------------------------
        with st.expander("📄 3. Draft Documents", expanded=False):
            g_data = load_group_data(shipment_id, "draft_docs")
            c1, c2, c3 = st.columns(3)
            draft_recv = c1.date_input(
                "DRAFT DOC RECV DATE",
                value=pd.to_datetime(g_data.get("draft_recv")).date()
                if g_data.get("draft_recv")
                else date.today(),
                key=f"draft_recv_{shipment_id}",
            )
            final_draft_recv = c2.date_input(
                "FINAL DRAFT DOC. Received Date",
                value=pd.to_datetime(g_data.get("final_draft_recv")).date()
                if g_data.get("final_draft_recv")
                else date.today(),
                key=f"final_draft_recv_{shipment_id}",
            )
            final_confirmed = c3.date_input(
                "Final Draft Confirmed Date",
                value=pd.to_datetime(g_data.get("final_confirmed")).date()
                if g_data.get("final_confirmed")
                else date.today(),
                key=f"final_confirmed_{shipment_id}",
            )

            group_save_button("draft_docs", {
                "draft_recv": draft_recv.isoformat(),
                "final_draft_recv": final_draft_recv.isoformat(),
                "final_confirmed": final_confirmed.isoformat(),
            })

        # ----------------------------------------------------------------------
        # 4. SSMO Group
        # ----------------------------------------------------------------------
        with st.expander("🔬 4. SSMO (Standards Inspection)", expanded=False):
            g_data = load_group_data(shipment_id, "ssmo")
            c1, c2, c3, c4 = st.columns(4)
            ssmo_app_date = c1.date_input(
                "Certificate Application Date",
                value=pd.to_datetime(g_data.get("ssmo_app_date")).date()
                if g_data.get("ssmo_app_date")
                else date.today(),
                key=f"ssmo_app_date_{shipment_id}",
            )
            ssmo_cost = c2.number_input(
                "SSMO COST",
                value=float(g_data.get("ssmo_cost", 0.0)),
                key=f"ssmo_cost_{shipment_id}",
            )
            ssmo_settled_date = c3.date_input(
                "SSMO Cost Settled Date",
                value=pd.to_datetime(g_data.get("ssmo_settled_date")).date()
                if g_data.get("ssmo_settled_date")
                else date.today(),
                key=f"ssmo_settled_date_{shipment_id}",
            )
            ssmo_ref_no = c4.text_input(
                "Ref. Number",
                value=g_data.get("ssmo_ref_no", ""),
                key=f"ssmo_ref_no_{shipment_id}",
            )

            group_save_button("ssmo", {
                "ssmo_app_date": ssmo_app_date.isoformat(),
                "ssmo_cost": ssmo_cost,
                "ssmo_settled_date": ssmo_settled_date.isoformat(),
                "ssmo_ref_no": ssmo_ref_no,
            })

        # ----------------------------------------------------------------------
        # 5. MOT Group
        # ----------------------------------------------------------------------
        with st.expander("🏛️ 5. MOT (Ministry of Trade)", expanded=False):
            g_data = load_group_data(shipment_id, "mot")
            c1, c2, c3, c4 = st.columns(4)
            mot_proc_date = c1.date_input(
                "MOT Process Date",
                value=pd.to_datetime(g_data.get("mot_proc_date")).date()
                if g_data.get("mot_proc_date")
                else date.today(),
                key=f"mot_proc_date_{shipment_id}",
            )
            mot_cost = c2.number_input(
                "MOT COST",
                value=float(g_data.get("mot_cost", 0.0)),
                key=f"mot_cost_{shipment_id}",
            )
            mot_settled_date = c3.date_input(
                "MOT Cost Settled Date",
                value=pd.to_datetime(g_data.get("mot_settled_date")).date()
                if g_data.get("mot_settled_date")
                else date.today(),
                key=f"mot_settled_date_{shipment_id}",
            )
            mot_ref_no = c4.text_input(
                "Ref. Number",
                value=g_data.get("mot_ref_no", ""),
                key=f"mot_ref_no_{shipment_id}",
            )

            c5, c6 = st.columns(2)
            offshore_mot_pi_no = c5.text_input(
                "Off Shore MOT APPROVED P.I. NO",
                value=g_data.get("offshore_mot_pi_no", ""),
                key=f"offshore_mot_pi_no_{shipment_id}",
            )
            offshore_mot_pi_date = c6.date_input(
                "Off Shore MOT APPROVED P.I. DATE",
                value=pd.to_datetime(g_data.get("offshore_mot_pi_date")).date()
                if g_data.get("offshore_mot_pi_date")
                else date.today(),
                key=f"offshore_mot_pi_date_{shipment_id}",
            )

            group_save_button("mot", {
                "mot_proc_date": mot_proc_date.isoformat(),
                "mot_cost": mot_cost,
                "mot_settled_date": mot_settled_date.isoformat(),
                "mot_ref_no": mot_ref_no,
                "offshore_mot_pi_no": offshore_mot_pi_no,
                "offshore_mot_pi_date": offshore_mot_pi_date.isoformat(),
            })

        # ----------------------------------------------------------------------
        # 6. Supplier Full Set
        # ----------------------------------------------------------------------
        with st.expander("📦 6. Supplier Full Set Documents", expanded=False):
            g_data = load_group_data(shipment_id, "supplier_full_set")
            c1, c2, c3, c4 = st.columns(4)
            dispatch_date = c1.date_input(
                "Dispatch Date",
                value=pd.to_datetime(g_data.get("dispatch_date")).date()
                if g_data.get("dispatch_date")
                else date.today(),
                key=f"dispatch_date_{shipment_id}",
            )
            dispatched_via = c2.selectbox(
                "Dispatched Via",
                DISPATCH_VIA_LIST,
                index=get_index_safe(DISPATCH_VIA_LIST, g_data.get("dispatched_via")),
                key=f"dispatched_via_{shipment_id}",
            )
            tracking_number = c3.text_input(
                "Tracking Number",
                value=g_data.get("tracking_number", ""),
                key=f"tracking_number_{shipment_id}",
            )
            received_date = c4.date_input(
                "Received Date",
                value=pd.to_datetime(g_data.get("received_date")).date()
                if g_data.get("received_date")
                else date.today(),
                key=f"received_date_{shipment_id}",
            )

            group_save_button("supplier_full_set", {
                "dispatch_date": dispatch_date.isoformat(),
                "dispatched_via": dispatched_via,
                "tracking_number": tracking_number,
                "received_date": received_date.isoformat(),
            })

        # ----------------------------------------------------------------------
        # 7. Offshore -> Sender Bank
        # ----------------------------------------------------------------------
        with st.expander("🏦 7. Offshore ➔ Sender Bank", expanded=False):
            g_data = load_group_data(shipment_id, "offshore_sender_bank")
            c1, c2, c3 = st.columns(3)
            doc_dispatch_date = c1.date_input(
                "Doc. Dispatch Date",
                value=pd.to_datetime(g_data.get("doc_dispatch_date")).date()
                if g_data.get("doc_dispatch_date")
                else date.today(),
                key=f"doc_dispatch_date_{shipment_id}",
            )
            off_disp_via = c2.selectbox(
                "Dispatched Via",
                DISPATCH_VIA_LIST,
                index=get_index_safe(DISPATCH_VIA_LIST, g_data.get("off_disp_via")),
                key=f"off_disp_via_{shipment_id}",
            )
            off_track_no = c3.text_input(
                "Tracking Number",
                value=g_data.get("off_track_no", ""),
                key=f"off_track_no_{shipment_id}",
            )

            group_save_button("offshore_sender_bank", {
                "doc_dispatch_date": doc_dispatch_date.isoformat(),
                "off_disp_via": off_disp_via,
                "off_track_no": off_track_no,
            })

        # ----------------------------------------------------------------------
        # 8. Sender Bank --> Receiver Bank
        # ----------------------------------------------------------------------
        with st.expander("🏦 8. Sender Bank ➔ Receiver Bank", expanded=False):
            g_data = load_group_data(shipment_id, "sender_to_receiver_bank")
            c1, c2, c3 = st.columns(3)
            bank_dispatch_date = c1.date_input(
                "Dispatch Date",
                value=pd.to_datetime(g_data.get("bank_dispatch_date")).date()
                if g_data.get("bank_dispatch_date")
                else date.today(),
                key=f"bank_dispatch_date_{shipment_id}",
            )
            bank_disp_via = c2.selectbox(
                "Dispatched Via",
                DISPATCH_VIA_LIST,
                index=get_index_safe(DISPATCH_VIA_LIST, g_data.get("bank_disp_via")),
                key=f"bank_disp_via_{shipment_id}",
            )
            bank_track_no = c3.text_input(
                "Tracking Number",
                value=g_data.get("bank_track_no", ""),
                key=f"bank_track_no_{shipment_id}",
            )

            group_save_button("sender_to_receiver_bank", {
                "bank_dispatch_date": bank_dispatch_date.isoformat(),
                "bank_disp_via": bank_disp_via,
                "bank_track_no": bank_track_no,
            })

        # ----------------------------------------------------------------------
        # 9. Supplier Invoice
        # ----------------------------------------------------------------------
        with st.expander("🧾 9. Supplier Invoice Details", expanded=False):
            g_data = load_group_data(shipment_id, "supplier_invoice")
            c1, c2, c3 = st.columns(3)
            inv_date = c1.date_input(
                "Invoice Date",
                value=pd.to_datetime(g_data.get("inv_date")).date()
                if g_data.get("inv_date")
                else date.today(),
                key=f"inv_date_{shipment_id}",
            )
            due_date = c2.date_input(
                "DUE DATE",
                value=pd.to_datetime(g_data.get("due_date")).date()
                if g_data.get("due_date")
                else date.today(),
                key=f"due_date_{shipment_id}",
            )
            due_amt = c3.number_input(
                "DUE AMOUNT",
                value=float(g_data.get("due_amt", 0.0)),
                key=f"due_amt_{shipment_id}",
            )

            c4, c5, c6 = st.columns(3)
            curr_1 = c4.selectbox(
                "Currency 1",
                CURRENCY_LIST,
                index=get_index_safe(CURRENCY_LIST, g_data.get("curr_1")),
                key=f"inv_curr1_{shipment_id}",
            )
            val_1 = c5.number_input(
                "Value 1",
                value=float(g_data.get("val_1", 0.0)),
                key=f"val_1_{shipment_id}",
            )
            date_1 = c6.date_input(
                "Date 1",
                value=pd.to_datetime(g_data.get("date_1")).date()
                if g_data.get("date_1")
                else date.today(),
                key=f"date_1_{shipment_id}",
            )

            c7, c8, c9 = st.columns(3)
            curr_2 = c7.selectbox(
                "Currency 2",
                CURRENCY_LIST,
                index=get_index_safe(CURRENCY_LIST, g_data.get("curr_2")),
                key=f"inv_curr2_{shipment_id}",
            )
            val_2 = c8.number_input(
                "Value 2",
                value=float(g_data.get("val_2", 0.0)),
                key=f"val_2_{shipment_id}",
            )
            date_2 = c9.date_input(
                "Date 2",
                value=pd.to_datetime(g_data.get("date_2")).date()
                if g_data.get("date_2")
                else date.today(),
                key=f"date_2_{shipment_id}",
            )

            supp_remarks = st.text_area(
                "Supplier REMARKS",
                value=g_data.get("supp_remarks", ""),
                key=f"supp_remarks_{shipment_id}",
            )

            group_save_button("supplier_invoice", {
                "inv_date": inv_date.isoformat(),
                "due_date": due_date.isoformat(),
                "due_amt": due_amt,
                "curr_1": curr_1,
                "val_1": val_1,
                "date_1": date_1.isoformat(),
                "curr_2": curr_2,
                "val_2": val_2,
                "date_2": date_2.isoformat(),
                "supp_remarks": supp_remarks,
            })

        # ----------------------------------------------------------------------
        # 10. OFFSHORE-1 RELATED (Dynamic Company Name)
        # ----------------------------------------------------------------------
        off1_name = offshore_list[0]
        with st.expander(f"🌐 10. {off1_name} Related", expanded=False):
            g_data = load_group_data(shipment_id, "offshore_1_related")
            c1, c2, c3, c4 = st.columns(4)
            c1.text_input(
                "Off Shore Name",
                value=off1_name,
                disabled=True,
                key=f"off1_name_{shipment_id}",
            )
            pr_no = c2.text_input(
                "ORION PR NO",
                value=g_data.get("pr_no", ""),
                key=f"pr_no_{shipment_id}",
            )
            orion_po_no = c3.text_input(
                "ORION PO NO",
                value=g_data.get("orion_po_no", ""),
                key=f"orion_po_no_{shipment_id}",
            )
            orion_sa = c4.text_input(
                "ORION SA",
                value=g_data.get("orion_sa", ""),
                key=f"orion_sa_{shipment_id}",
            )

            c5, c6, c7, c8 = st.columns(4)
            orion_grn = c5.text_input(
                "ORION GRN",
                value=g_data.get("orion_grn", ""),
                key=f"orion_grn_{shipment_id}",
            )
            orion_bill_reg = c6.text_input(
                "ORION BILL REG",
                value=g_data.get("orion_bill_reg", ""),
                key=f"orion_bill_reg_{shipment_id}",
            )
            orion_inv_no = c7.text_input(
                "ORION INVOICE No.",
                value=g_data.get("orion_inv_no", ""),
                key=f"orion_inv_no_{shipment_id}",
            )
            inv_no = c8.text_input(
                "Invoice No.",
                value=g_data.get("inv_no", ""),
                key=f"inv_no_{shipment_id}",
            )

            c9, c10, c11 = st.columns(3)
            off_curr = c9.selectbox(
                "Currency",
                CURRENCY_LIST,
                index=get_index_safe(CURRENCY_LIST, g_data.get("off_curr")),
                key=f"off1_curr_{shipment_id}",
            )
            unit_price_tp = c10.number_input(
                "Unit Price (at TP Screen)",
                value=float(g_data.get("unit_price_tp", 0.0)),
                key=f"unit_price_tp_{shipment_id}",
            )
            tot_val = c11.number_input(
                "Total Value",
                value=float(g_data.get("tot_val", 0.0)),
                key=f"tot_val_{shipment_id}",
            )

            inv_val_usd = tot_val * FX_RATES.get(off_curr, 1.0)
            st.metric("Invoice Value ($ Calculated)", f"${inv_val_usd:,.2f}")

            group_save_button("offshore_1_related", {
                "offshore_name": off1_name,
                "pr_no": pr_no,
                "orion_po_no": orion_po_no,
                "orion_sa": orion_sa,
                "orion_grn": orion_grn,
                "orion_bill_reg": orion_bill_reg,
                "orion_inv_no": orion_inv_no,
                "inv_no": inv_no,
                "off_curr": off_curr,
                "unit_price_tp": unit_price_tp,
                "tot_val": tot_val,
                "inv_val_usd": inv_val_usd,
            })

        # ----------------------------------------------------------------------
        # 11. OFFSHORE-2 RELATED (if applicable)
        # ----------------------------------------------------------------------
        if len(offshore_list) >= 2:
            off2_name = offshore_list[1]
            with st.expander(f"🌐 11. {off2_name} Related", expanded=False):
                g_data = load_group_data(shipment_id, "offshore_2_related")
                c1, c2, c3 = st.columns(3)
                c1.text_input(
                    "Off Shore Name",
                    value=off2_name,
                    disabled=True,
                    key=f"off2_name_{shipment_id}",
                )
                insp_no = c2.text_input(
                    "INSPECTION NO.",
                    value=g_data.get("insp_no", ""),
                    key=f"insp_no_{shipment_id}",
                )
                grn_no = c3.text_input(
                    "GRN NO.",
                    value=g_data.get("grn_no", ""),
                    key=f"grn_no_{shipment_id}",
                )

                c4, c5 = st.columns(2)
                orion_inv_no2 = c4.text_input(
                    "ORION INVOICE No.",
                    value=g_data.get("orion_inv_no2", ""),
                    key=f"orion_inv2_{shipment_id}",
                )
                erp_remarks = c5.text_input(
                    "ERP REMARKS",
                    value=g_data.get("erp_remarks", ""),
                    key=f"erp_remarks_{shipment_id}",
                )

                group_save_button("offshore_2_related", {
                    "offshore_name": off2_name,
                    "insp_no": insp_no,
                    "grn_no": grn_no,
                    "orion_inv_no2": orion_inv_no2,
                    "erp_remarks": erp_remarks,
                })

        # ----------------------------------------------------------------------
        # 12. OFFSHORE-3 RELATED (if applicable)
        # ----------------------------------------------------------------------
        if len(offshore_list) >= 3:
            off3_name = offshore_list[2]
            with st.expander(f"🌐 12. {off3_name} Related", expanded=False):
                g_data = load_group_data(shipment_id, "offshore_3_related")
                c1, c2, c3 = st.columns(3)
                c1.text_input(
                    "Off Shore Name",
                    value=off3_name,
                    disabled=True,
                    key=f"off3_name_{shipment_id}",
                )
                insp_no3 = c2.text_input(
                    "INSPECTION NO.",
                    value=g_data.get("insp_no3", ""),
                    key=f"insp3_{shipment_id}",
                )
                grn_no3 = c3.text_input(
                    "GRN NO.",
                    value=g_data.get("grn_no3", ""),
                    key=f"grn3_{shipment_id}",
                )

                c4, c5 = st.columns(2)
                orion_inv_no3 = c4.text_input(
                    "ORION INVOICE No.",
                    value=g_data.get("orion_inv_no3", ""),
                    key=f"orion_inv3_{shipment_id}",
                )
                erp_remarks3 = c5.text_input(
                    "ERP REMARKS",
                    value=g_data.get("erp_remarks3", ""),
                    key=f"erp3_{shipment_id}",
                )

                group_save_button("offshore_3_related", {
                    "offshore_name": off3_name,
                    "insp_no3": insp_no3,
                    "grn_no3": grn_no3,
                    "orion_inv_no3": orion_inv_no3,
                    "erp_remarks3": erp_remarks3,
                })

        # ----------------------------------------------------------------------
        # 13. Treasury Group
        # ----------------------------------------------------------------------
        with st.expander("🏛️ 13. Treasury Group", expanded=False):
            g_data = load_group_data(shipment_id, "treasury")
            c1, c2, c3 = st.columns(3)
            nec_good = c1.selectbox(
                "Necessary Good Type",
                ["Yes", "No"],
                index=0 if g_data.get("nec_good") == "Yes" else 1,
                key=f"tr_nec_good_{shipment_id}",
            )
            sender_bank = c2.selectbox(
                "Sender Bank",
                BANK_LIST,
                index=get_index_safe(BANK_LIST, g_data.get("sender_bank"), 0),
                key=f"tr_sender_bank_{shipment_id}",
            )
            rec_bank = c3.selectbox(
                "Receiving Bank",
                BANK_LIST,
                index=get_index_safe(BANK_LIST, g_data.get("rec_bank"), 1),
                key=f"tr_rec_bank_{shipment_id}",
            )

            c4, c5, c6 = st.columns(3)
            coll_ref = c4.text_input(
                "Collection Ref. No",
                value=g_data.get("coll_ref", ""),
                key=f"coll_ref_{shipment_id}",
            )
            coll_val = c5.number_input(
                "Collection Value",
                value=float(g_data.get("coll_val", 0.0)),
                key=f"coll_val_{shipment_id}",
            )
            coll_curr = c6.selectbox(
                "Collection Currency",
                CURRENCY_LIST,
                index=get_index_safe(CURRENCY_LIST, g_data.get("coll_curr")),
                key=f"tr_curr_{shipment_id}",
            )

            c7, c8, c9 = st.columns(3)
            tenor = c7.selectbox(
                "Tenor",
                TENOR_LIST,
                index=get_index_safe(TENOR_LIST, g_data.get("tenor")),
                key=f"tenor_{shipment_id}",
            )
            tr_due_date = c8.date_input(
                "DUE DATE",
                value=pd.to_datetime(g_data.get("tr_due_date")).date()
                if g_data.get("tr_due_date")
                else date.today(),
                key=f"tr_due_date_{shipment_id}",
            )
            amt_settled = c9.number_input(
                "Amount Settled",
                value=float(g_data.get("amt_settled", 0.0)),
                key=f"amt_settled_{shipment_id}",
            )

            rem_dues = coll_val - amt_settled
            c10, c11, c12 = st.columns(3)
            c10.metric("Remaining Dues", f"{rem_dues:,.2f} {coll_curr}")
            im_no = c11.text_input(
                "IM Form No.",
                value=g_data.get("im_no", ""),
                key=f"im_no_{shipment_id}",
            )
            im_date = c12.date_input(
                "IM Form Date",
                value=pd.to_datetime(g_data.get("im_date")).date()
                if g_data.get("im_date")
                else date.today(),
                key=f"im_date_{shipment_id}",
            )

            s_bank_chg = coll_val * 0.005
            r_bank_chg = coll_val * 0.0025
            st.caption(
                f"Calculated Bank Charges — Sender: **${s_bank_chg:,.2f}** |"
                f" Receiver: **${r_bank_chg:,.2f}**"
            )

            group_save_button("treasury", {
                "nec_good": nec_good,
                "sender_bank": sender_bank,
                "rec_bank": rec_bank,
                "coll_ref": coll_ref,
                "coll_val": coll_val,
                "coll_curr": coll_curr,
                "tenor": tenor,
                "tr_due_date": tr_due_date.isoformat(),
                "amt_settled": amt_settled,
                "rem_dues": rem_dues,
                "im_no": im_no,
                "im_date": im_date.isoformat(),
                "s_bank_chg": s_bank_chg,
                "r_bank_chg": r_bank_chg,
            })


# ==============================================================================
# MODULE 4: OFFSHORE VALUATION & PROFITABILITY BREAKDOWN
# ==============================================================================
elif choice == "📈 Offshore Valuation & Profitability":
    st.title("📈 Offshore Item Pricing & Multi-Tier Profitability Engine")

    conn = get_db_connection()
    shipments_df = pd.read_sql_query(
        "SELECT s.shipment_id, s.bl_awb, s.po_number, m.offshore_companies_json FROM shipments s JOIN master_orders m ON s.po_number = m.po_number",
        conn,
    )

    if shipments_df.empty:
        st.warning("No shipments available for valuation.")
    else:
        selected_bl = st.selectbox(
            "Select BL/AWB to Inspect Items & Multi-Tier Offshore Valuation *",
            shipments_df["bl_awb"].tolist(),
        )

        shp_row = shipments_df[shipments_df["bl_awb"] == selected_bl].iloc[0]
        shipment_id = int(shp_row["shipment_id"])

        raw_offshores = shp_row["offshore_companies_json"]
        offshore_list = (
            json.loads(raw_offshores)
            if raw_offshores
            else ["Primary Offshore"]
        )
        if not offshore_list:
            offshore_list = ["Primary Offshore"]

        items_df = pd.read_sql_query(
            "SELECT shipment_item_id, category, model_product, type, qty_shipped, unit_price, total_shipped_value, offshore_pricing_json FROM shipment_line_items WHERE shipment_id = ?",
            conn,
            params=(shipment_id,),
        )

        if items_df.empty:
            st.info("No items found for this shipment.")
        else:
            st.markdown("##### 🛒 Item Pricing & Profitability Table")
            st.caption(
                "Enter Offshore Unit Prices ($) for each configured offshore"
                " company to calculate totals and tiered profit percentages."
            )

            updated_rows = []
            for idx, row in items_df.iterrows():
                st.markdown(
                    f"**Item #{idx+1}: {row['model_product']}**"
                    f" ({row['category']} - {row['type']})"
                )

                qty = float(row["qty_shipped"])
                supp_unit_price = float(row["unit_price"])
                supp_total = qty * supp_unit_price

                supp_unit_usd = supp_unit_price * FX_RATES["USD"]
                supp_total_usd = supp_total * FX_RATES["USD"]

                raw_pricing_json = row["offshore_pricing_json"]
                existing_prices = (
                    json.loads(raw_pricing_json) if raw_pricing_json else {}
                )

                col_meta1, col_meta2, col_meta3 = st.columns(3)
                col_meta1.metric("Qty Shipped", f"{qty:,.0f}")
                col_meta2.metric("Supplier Price ($)", f"${supp_unit_usd:,.2f}")
                col_meta3.metric("Supplier Total ($)", f"${supp_total_usd:,.2f}")

                offshore_prices = {}
                cols = st.columns(len(offshore_list))

                prev_price = supp_unit_usd
                for off_idx, off_name in enumerate(offshore_list):
                    with cols[off_idx]:
                        default_val = float(
                            existing_prices.get(
                                str(off_idx), supp_unit_usd * 1.10
                            )
                        )
                        u_price_off = st.number_input(
                            f"{off_name} Unit Price ($)",
                            value=default_val,
                            key=f"off_price_{row['shipment_item_id']}_{off_idx}_{shipment_id}",
                        )
                        tot_off = qty * u_price_off

                        profit_pct = (
                            ((u_price_off - prev_price) / prev_price * 100)
                            if prev_price > 0
                            else 0.0
                        )
                        st.write(f"**Total $:** ${tot_off:,.2f}")
                        st.write(f"**Profit %:** {profit_pct:+.2f}%")

                        offshore_prices[str(off_idx)] = u_price_off
                        prev_price = u_price_off

                updated_rows.append((
                    json.dumps(offshore_prices),
                    row["shipment_item_id"],
                ))
                st.markdown("---")

            if st.button(
                "💾 Save All Offshore Pricing & Valuation", type="primary"
            ):
                cursor = conn.cursor()
                for prices_json, shp_item_id in updated_rows:
                    cursor.execute(
                        "UPDATE shipment_line_items SET offshore_pricing_json"
                        " = ? WHERE shipment_item_id = ?",
                        (prices_json, shp_item_id),
                    )
                conn.commit()
                st.success("Updated offshore pricing & profitability metrics!")
                st.rerun()

    conn.close()


# ==============================================================================
# MODULE 5: TREASURY OPERATIONS
# ==============================================================================
elif choice == "🏦 Treasury Operations":
    st.title("🏦 Standalone Treasury Operations Module")

    conn = get_db_connection()
    shipments_df = pd.read_sql_query(
        "SELECT s.shipment_id, s.bl_awb, s.po_number, m.supplier_name FROM shipments s JOIN master_orders m ON s.po_number = m.po_number",
        conn,
    )

    if shipments_df.empty:
        st.warning("No active shipments found.")
    else:
        selected_bl = st.selectbox(
            "Select Active Shipment / BL Number for Treasury Operations:",
            shipments_df["bl_awb"].tolist(),
        )

        shp_row = shipments_df[shipments_df["bl_awb"] == selected_bl].iloc[0]
        shipment_id = int(shp_row["shipment_id"])

        g_data = load_group_data(shipment_id, "treasury")

        st.subheader(
            f"🏦 Treasury Details for Shipment `{selected_bl}` ({shp_row['supplier_name']})"
        )

        c1, c2, c3 = st.columns(3)
        nec_good = c1.selectbox(
            "Necessary Good Type *",
            ["Yes", "No"],
            index=0 if g_data.get("nec_good") == "Yes" else 1,
            key=f"standalone_nec_good_{shipment_id}",
        )
        sender_bank = c2.selectbox(
            "Sender Bank *",
            BANK_LIST,
            index=get_index_safe(BANK_LIST, g_data.get("sender_bank"), 0),
            key=f"standalone_sender_bank_{shipment_id}",
        )
        rec_bank = c3.selectbox(
            "Receiving Bank *",
            BANK_LIST,
            index=get_index_safe(BANK_LIST, g_data.get("rec_bank"), 1),
            key=f"standalone_rec_bank_{shipment_id}",
        )

        c4, c5, c6 = st.columns(3)
        coll_ref = c4.text_input(
            "Collection Ref. No",
            value=g_data.get("coll_ref", "COL-2026-8801"),
            key=f"standalone_coll_ref_{shipment_id}",
        )
        coll_val = c5.number_input(
            "Collection Value",
            value=float(g_data.get("coll_val", 250000.0)),
            key=f"standalone_coll_val_{shipment_id}",
        )
        coll_curr = c6.selectbox(
            "Collection Currency",
            CURRENCY_LIST,
            index=get_index_safe(CURRENCY_LIST, g_data.get("coll_curr")),
            key=f"standalone_coll_curr_{shipment_id}",
        )

        c7, c8, c9 = st.columns(3)
        tenor = c7.selectbox(
            "Tenor",
            TENOR_LIST,
            index=get_index_safe(TENOR_LIST, g_data.get("tenor"), 3),
            key=f"standalone_tenor_{shipment_id}",
        )
        tr_due_date = c8.date_input(
            "DUE DATE",
            value=pd.to_datetime(g_data.get("tr_due_date")).date()
            if g_data.get("tr_due_date")
            else date.today() + timedelta(days=90),
            key=f"standalone_tr_due_date_{shipment_id}",
        )
        amt_settled = c9.number_input(
            "Amount Settled",
            value=float(g_data.get("amt_settled", 50000.0)),
            key=f"standalone_amt_settled_{shipment_id}",
        )

        rem_dues = coll_val - amt_settled
        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Collection Value", f"{coll_val:,.2f} {coll_curr}")
        m2.metric("Amount Settled", f"{amt_settled:,.2f} {coll_curr}")
        m3.metric("Remaining Dues (Calculated)", f"{rem_dues:,.2f} {coll_curr}")

        st.markdown("---")
        c10, c11 = st.columns(2)
        im_no = c10.text_input(
            "IM Form No.",
            value=g_data.get("im_no", "IM-2026-9912"),
            key=f"standalone_im_no_{shipment_id}",
        )
        im_date = c11.date_input(
            "IM Form Date",
            value=pd.to_datetime(g_data.get("im_date")).date()
            if g_data.get("im_date")
            else date.today(),
            key=f"standalone_im_date_{shipment_id}",
        )

        s_bank_chg = coll_val * 0.005
        r_bank_chg = coll_val * 0.0025
        st.info(
            f"Estimated Sender Bank Charges: **${s_bank_chg:,.2f}** | Estimated"
            f" Receiver Bank Charges: **${r_bank_chg:,.2f}**"
        )

        if st.button("💾 Save Treasury Record", type="primary"):
            save_group_data(shipment_id, "treasury", {
                "nec_good": nec_good,
                "sender_bank": sender_bank,
                "rec_bank": rec_bank,
                "coll_ref": coll_ref,
                "coll_val": coll_val,
                "coll_curr": coll_curr,
                "tenor": tenor,
                "tr_due_date": tr_due_date.isoformat(),
                "amt_settled": amt_settled,
                "rem_dues": rem_dues,
                "im_no": im_no,
                "im_date": im_date.isoformat(),
                "s_bank_chg": s_bank_chg,
                "r_bank_chg": r_bank_chg,
            })
            st.success("Treasury record saved successfully!")
            st.rerun()

    conn.close()


# ==============================================================================
# MODULE 6: CLEARANCE TASK ENGINE
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

                col3, col4 = st.columns(2)
                est_arr = col3.date_input(
                    "3. Shipment Estimated Arrival Date",
                    value=pd.to_datetime(
                        shipment_data.get("est_arrival_date")
                    ).date()
                    if shipment_data.get("est_arrival_date")
                    else date.today(),
                    key=f"est_arr_{shipment_id}",
                )
                act_arr = col4.date_input(
                    "4. Shipment Actual Arrival Date",
                    value=pd.to_datetime(
                        shipment_data.get("act_arrival_date")
                    ).date()
                    if shipment_data.get("act_arrival_date")
                    else None,
                    key=f"act_arr_{shipment_id}",
                )

                st.markdown("---")
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
                    "5. General Notes",
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
                }

            elif key == "clear_at_select":
                track_choice = st.selectbox(
                    "Select Clearance Destination Track:",
                    ["Port", "Free Zone"],
                    index=0 if clear_at == "Port" else 1,
                    key=f"track_choice_{shipment_id}",
                )
                updated_data = {"clear_at": track_choice}

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
# MODULE 7 & 8: ANALYTICS & TARGET SLA CONFIGURATION
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
