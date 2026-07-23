import sqlite3
from datetime import date
import pandas as pd
import streamlit as st


# --- HELPER FUNCTIONS ---
def parse_amount(val) -> float:
    if not val:
        return 0.0
    cleaned = (
        str(val).replace(",", "").replace("$", "").replace("SDG", "").strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def format_amount(val) -> str:
    return f"{parse_amount(val):,.2f}"


def get_db_connection():
    conn = sqlite3.connect("shipments.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# --- MODULE: MASTER ORDERS & SHIPMENT CREATION ---
def render_order_and_shipment_creation():
    st.title("📦 Master Order & Shipment Creation")

    tab1, tab2 = st.tabs(
        ["1️⃣ Create Master Order (PO)", "2️⃣ Create Shipment (BL / AWB)"]
    )

    # ==========================================
    # TAB 1: MASTER ORDER CREATION
    # ==========================================
    with tab1:
        st.subheader("📝 New Master Purchase Order")

        col1, col2 = st.columns(2)
        po_number = col1.text_input(
            "PO Number *", placeholder="e.g. PO-2026-9901"
        )
        supplier_name = col2.text_input(
            "Supplier Name", placeholder="e.g. Global Tech Ltd"
        )

        col3, col4, col5 = st.columns(3)
        bu_id = col3.selectbox(
            "Business Unit (BU)",
            ["BU-LOGISTICS", "BU-RETAIL", "BU-ENERGY", "BU-MANUFACTURING"],
        )
        order_date = col4.date_input("Order Date", value=date.today())
        currency = col5.selectbox("Currency", ["USD", "EUR", "SDG", "AED"])

        po_val_raw = st.text_input(
            "Total PO Value",
            value="100,000.00",
            help="Formatted automatically with comma separators",
        )
        po_value = parse_amount(po_val_raw)

        if st.button("💾 Save Master Order", use_container_width=True):
            if not po_number.strip():
                st.error("PO Number is required.")
            else:
                conn = get_db_connection()
                try:
                    conn.execute(
                        """
                        INSERT INTO master_orders (po_number, supplier_name, bu_id, order_date, total_po_value, currency)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            po_number.strip(),
                            supplier_name.strip(),
                            bu_id,
                            order_date.isoformat(),
                            po_value,
                            currency,
                        ),
                    )
                    conn.commit()
                    st.success(
                        f"Master Order **{po_number}** created successfully!"
                    )
                except sqlite3.IntegrityError:
                    st.error(f"PO Number '{po_number}' already exists.")
                finally:
                    conn.close()

    # ==========================================
    # TAB 2: SHIPMENT CREATION
    # ==========================================
    with tab2:
        st.subheader("🚢 Attach Shipment to Master Order")

        conn = get_db_connection()
        existing_pos = pd.read_sql_query(
            "SELECT po_number, bu_id, supplier_name FROM master_orders WHERE"
            " status = 'Open'",
            conn,
        )
        conn.close()

        if existing_pos.empty:
            st.info(
                "No open Master Orders available. Please create a Master Order"
                " first."
            )
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
                "Initial Clearance Route Track",
                ["Pending", "Port", "Free Zone"],
            )

            col3, col4 = st.columns(2)
            est_arrival = col3.date_input(
                "Estimated Arrival Date (ETA)", value=date.today()
            )
            notes = col4.text_area(
                "Shipment Notes / Cargo Description",
                placeholder="Container specs, fragility, priority...",
            )

            if st.button("🚀 Create Shipment", use_container_width=True):
                if not bl_awb.strip():
                    st.error("BL / AWB Number is required.")
                else:
                    conn = get_db_connection()
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

                        # Automatically seed default task pipeline for this new shipment
                        from clearance_engine import seed_tasks_for_shipment

                        seed_tasks_for_shipment(cursor, shp_id)

                        conn.commit()
                        st.success(
                            f"Shipment **{bl_awb}** linked to PO"
                            f" **{selected_po}** and initialized in the"
                            " clearance workflow!"
                        )
                    except sqlite3.IntegrityError:
                        st.error(
                            f"Shipment with BL/AWB '{bl_awb}' already exists."
                        )
                    finally:
                        conn.close()
