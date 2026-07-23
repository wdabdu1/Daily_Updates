import json
import sqlite3
from datetime import date, datetime, timedelta
import pandas as pd
import streamlit as st

# --- STREAMLIT PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Clearance Workflow & Task Engine",
    page_icon="🚢",
    layout="wide",
)


# --- 1. DATABASE CONNECTION & INITIALIZATION ---
def get_db_connection():
    conn = sqlite3.connect("shipments.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes tables for master shipments and process workflows."""
    conn = get_db_connection()
    cursor = conn.cursor()

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

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

    cursor.execute(
        "SELECT COUNT(*) FROM process_tasks WHERE process_key ="
        " 'final_clearance_complete'"
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute("DELETE FROM process_tasks")
        cursor.execute("DELETE FROM shipments")

        today = date.today()

        # Seed Shipment 1 (Port)
        cursor.execute(
            """
            INSERT INTO shipments (bl_awb, po_number, bu_id, est_arrival_date, act_arrival_date, clear_at, notes)
            VALUES ('BL-2026-PORT-01', 'PO-8812', 'BU-LOGISTICS', ?, ?, 'Port', 'Priority machinery cargo')
        """,
            (
                (today - timedelta(days=5)).isoformat(),
                (today - timedelta(days=4)).isoformat(),
            ),
        )
        shp1_id = cursor.lastrowid

        # Seed Shipment 2 (Free Zone)
        cursor.execute(
            """
            INSERT INTO shipments (bl_awb, po_number, bu_id, est_arrival_date, clear_at, notes)
            VALUES ('BL-2026-FZ-02', 'PO-9043', 'BU-RETAIL', ?, 'Free Zone', 'FZ Storage deposit shipment')
        """,
            ((today + timedelta(days=2)).isoformat(),),
        )
        shp2_id = cursor.lastrowid

        seed_tasks_for_shipment(cursor, shp1_id)
        seed_tasks_for_shipment(cursor, shp2_id)

    conn.commit()
    conn.close()


def seed_tasks_for_shipment(cursor, shipment_id):
    """Populates standard process definitions."""
    default_processes = [
        # Common Processes
        ("gen_info", "General Clearance Info", "Common", 0.25),
        ("clear_at_select", "Clear at:", "Common", 0.25),
        ("cost_estimate", "Clearance Cost Estimate", "Common", 0.25),
        ("delivery_order", "Delivery Order", "Common", 1.0),
        ("customs_cert", "Customs Certificate Entry", "Common", 0.5),
        # Track 1: Port
        ("cont_move", "Containers Move Process", "Port", 2.0),
        ("ssmo_file", "SSMO File Process", "Port", 1.0),
        ("customs_exam", "Customs Examination (Form 48)", "Port", 1.0),
        ("customs_lab", "Customs Lab", "Port", 1.0),
        ("ssmo_exam", "SSMO Examination", "Port", 1.0),
        ("customs_eval", "Customs Evaluation", "Port", 1.0),
        ("spc_bill", "SPC Bill", "Port", 1.0),
        ("truck_permit", "Truck Entry Permit", "Port", 1.0),
        # Track 2: Free Zone
        ("fz_deposit_req", "FZ Deposit Request", "Free Zone", 1.0),
        ("fz_customs_insp", "Customs Inspection (FZ)", "Free Zone", 1.0),
        ("fz_spc_police", "SPC Bill & Police Security", "Free Zone", 1.0),
        ("fz_receive_cargo", "Receive Cargo at FZ", "Free Zone", 1.0),
        # Final Step
        (
            "final_clearance_complete",
            "Actual Clearance Completion",
            "Common",
            0.25,
        ),
    ]

    for key, name, track, sla in default_processes:
        cursor.execute(
            """
            INSERT INTO process_tasks (shipment_id, process_key, process_name, track, target_sla, status, data_json)
            VALUES (?, ?, ?, ?, ?, 'Pending', '{}')
        """,
            (shipment_id, key, name, track, sla),
        )


init_db()


# --- 2. WORKFLOW ENGINE & DEPENDENCY LOGIC ---
def evaluate_process_statuses(tasks_dict, clear_at_selection):
    """Evaluates task activations dynamically based on workflow progress."""
    status_map = {}

    def get_data(key):
        return json.loads(tasks_dict.get(key, {}).get("data_json", "{}"))

    def is_done(key):
        return tasks_dict.get(key, {}).get("status") == "Completed"

    # 1. General Clearance Info: Always Active
    status_map["gen_info"] = (
        "Completed" if is_done("gen_info") else "Active"
    )

    gen_data = get_data("gen_info")
    bl_copy_done = bool(gen_data.get("bl_copy_receipt_date"))
    orig_ship_done = bool(gen_data.get("orig_shipment_rec_date"))

    # 2. Clear at: Active when "Original Shipment Set Received Date" completed
    status_map["clear_at_select"] = (
        "Completed"
        if is_done("clear_at_select")
        else ("Active" if orig_ship_done else "Pending")
    )

    # 3. Clearance Cost Estimate: Active when "BL Copy Receipt Date" completed
    status_map["cost_estimate"] = (
        "Completed"
        if is_done("cost_estimate")
        else ("Active" if bl_copy_done else "Pending")
    )

    # 4. Delivery Order: Active when "Original Shipment Set Received Date" completed
    status_map["delivery_order"] = (
        "Completed"
        if is_done("delivery_order")
        else ("Active" if orig_ship_done else "Pending")
    )

    # 5. Customs Certificate Entry: Active when "Delivery Order" completed
    status_map["customs_cert"] = (
        "Completed"
        if is_done("customs_cert")
        else ("Active" if is_done("delivery_order") else "Pending")
    )

    # --- TRACK 1: PORT CLEARANCE ---
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

    # --- TRACK 2: FREE ZONE ---
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


# --- 3. NAVIGATION SIDEBAR ---
st.sidebar.title("🚢 Clearance Task Control")
menu = [
    "📋 Clearance Task Engine",
    "📊 Clearance & SLA Analytics",
    "⚙️ Target SLA Settings",
]
choice = st.sidebar.selectbox("Select Module", menu)


# --- 4. MODULE 1: CLEARANCE TASK ENGINE ---
if choice == "📋 Clearance Task Engine":
    st.title("📋 Clearance Task Workflow Engine")

    conn = get_db_connection()
    shipments = pd.read_sql_query(
        "SELECT shipment_id, bl_awb, po_number, bu_id, clear_at FROM shipments",
        conn,
    )

    if shipments.empty:
        st.warning("No shipments available.")
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
            badge = "🔒 LOCKED (Awaiting Dependency)"

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
                    "✋ This process is currently locked. Complete the preceding"
                    " prerequisite process step to activate."
                )
                continue

            with st.form(key=f"form_{key}"):
                updated_data = {}

                # 1. General Clearance Info
                if key == "gen_info":
                    col1, col2 = st.columns(2)
                    bl_rec = col1.date_input(
                        "1. BL Copy Receipt Date",
                        value=pd.to_datetime(
                            task_data.get("bl_copy_receipt_date")
                        ).date()
                        if task_data.get("bl_copy_receipt_date")
                        else None,
                    )
                    orig_rec = col2.date_input(
                        "2. Original Shipment Set Received Date",
                        value=pd.to_datetime(
                            task_data.get("orig_shipment_rec_date")
                        ).date()
                        if task_data.get("orig_shipment_rec_date")
                        else None,
                    )

                    lc_disabled = not bool(orig_rec)
                    lc_no = st.text_input(
                        "3. L/C No. (Activates when Original Set Received)",
                        value=task_data.get("lc_no", ""),
                        disabled=lc_disabled,
                    )

                    col3, col4 = st.columns(2)
                    est_arr = col3.date_input(
                        "4. Shipment Estimated Arrival Date",
                        value=pd.to_datetime(
                            shipment_data.get("est_arrival_date")
                        ).date()
                        if shipment_data.get("est_arrival_date")
                        else date.today(),
                    )
                    act_arr = col4.date_input(
                        "5. Shipment Actual Arrival Date",
                        value=pd.to_datetime(
                            shipment_data.get("act_arrival_date")
                        ).date()
                        if shipment_data.get("act_arrival_date")
                        else None,
                    )

                    st.markdown("---")
                    st.markdown("**6. Clearance Completion Estimate Date:**")
                    col_est1, col_est2 = st.columns(2)
                    
                    with col_est1:
                        manual_override = st.checkbox(
                            "Manually Override Calculated Clearance Completion Estimate",
                            value=bool(shipment_data.get("manual_override_est_date")),
                        )

                    if manual_override:
                        with col_est2:
                            est_clear_date = st.date_input(
                                "Select Manual Clearance Completion Estimate Date",
                                value=pd.to_datetime(
                                    shipment_data.get("est_clearance_date")
                                ).date()
                                if shipment_data.get("est_clearance_date")
                                else calculated_completion_est,
                            )
                    else:
                        est_clear_date = calculated_completion_est
                        with col_est2:
                            st.info(f"Calculated Target Date: **{calculated_completion_est}**")

                    notes = st.text_area(
                        "7. General Notes",
                        value=shipment_data.get("notes", ""),
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

                # 2. Select Track / Clear at:
                elif key == "clear_at_select":
                    track_choice = st.selectbox(
                        "Select Clearance Destination Track:",
                        ["Port", "Free Zone"],
                        index=0 if clear_at == "Port" else 1,
                    )
                    updated_data = {"clear_at": track_choice}

                # 3. Clearance Cost Estimate
                elif key == "cost_estimate":
                    c1, c2 = st.columns(2)
                    est_d = c1.date_input(
                        "1. Estimate Date",
                        value=pd.to_datetime(task_data.get("est_date")).date()
                        if task_data.get("est_date")
                        else None,
                    )
                    val = c2.number_input(
                        "2. Estimated Value (SDG)",
                        value=float(task_data.get("value", 0.0)),
                        format="%.2f",
                    )

                    c3, c4 = st.columns(2)
                    not_bu = c3.date_input(
                        "3. Notify BU Date",
                        value=pd.to_datetime(
                            task_data.get("notify_bu_date")
                        ).date()
                        if task_data.get("notify_bu_date")
                        else None,
                    )
                    amt_rec_d = c4.date_input(
                        "4. Amount Received Date",
                        value=pd.to_datetime(
                            task_data.get("amount_received_date")
                        ).date()
                        if task_data.get("amount_received_date")
                        else None,
                    )

                    updated_data = {
                        "est_date": est_d.isoformat() if est_d else None,
                        "value": val,
                        "notify_bu_date": not_bu.isoformat()
                        if not_bu
                        else None,
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
                    )
                    do_fees = c2.number_input(
                        "2. DO Fees (SDG)",
                        value=float(task_data.get("do_fees", 0.0)),
                        format="%.2f",
                    )

                    c3, c4 = st.columns(2)
                    settle_d = c3.date_input(
                        "3. DO Fees Settled Date",
                        value=pd.to_datetime(
                            task_data.get("settled_date")
                        ).date()
                        if task_data.get("settled_date")
                        else None,
                    )
                    rec_d = c4.date_input(
                        "4. DO Received Date",
                        value=pd.to_datetime(
                            task_data.get("received_date")
                        ).date()
                        if task_data.get("received_date")
                        else None,
                    )
                    updated_data = {
                        "copy_do": copy_do,
                        "do_fees": do_fees,
                        "settled_date": settle_d.isoformat()
                        if settle_d
                        else None,
                        "received_date": rec_d.isoformat() if rec_d else None,
                    }

                # 5. Customs Certificate Entry
                elif key == "customs_cert":
                    c1, c2 = st.columns(2)
                    entry_d = c1.date_input(
                        "1. Entry Date",
                        value=pd.to_datetime(task_data.get("entry_date")).date()
                        if task_data.get("entry_date")
                        else None,
                    )
                    scuda_no = c2.text_input(
                        "2. SCUDA Declaration No.",
                        value=task_data.get("scuda_no", ""),
                    )
                    updated_data = {
                        "entry_date": entry_d.isoformat() if entry_d else None,
                        "scuda_no": scuda_no,
                    }

                # 6. Containers Move Process
                elif key == "cont_move":
                    c1, c2, c3 = st.columns(3)
                    req_d = c1.date_input(
                        "1. Move Request Date",
                        value=pd.to_datetime(
                            task_data.get("request_date")
                        ).date()
                        if task_data.get("request_date")
                        else None,
                    )
                    bill = c2.number_input(
                        "2. Bill Amount (SDG)",
                        value=float(task_data.get("bill_amount", 0.0)),
                        format="%.2f",
                    )
                    set_d = c3.date_input(
                        "3. Bill Settlement Date",
                        value=pd.to_datetime(
                            task_data.get("settlement_date")
                        ).date()
                        if task_data.get("settlement_date")
                        else None,
                    )
                    updated_data = {
                        "request_date": req_d.isoformat() if req_d else None,
                        "bill_amount": bill,
                        "settlement_date": set_d.isoformat() if set_d else None,
                    }

                # 7. SSMO File Process
                elif key == "ssmo_file":
                    c1, c2, c3 = st.columns(3)
                    req_d = c1.date_input(
                        "1. Move Request Date",
                        value=pd.to_datetime(
                            task_data.get("request_date")
                        ).date()
                        if task_data.get("request_date")
                        else None,
                    )
                    bill = c2.number_input(
                        "2. Bill Amount (SDG)",
                        value=float(task_data.get("bill_amount", 0.0)),
                        format="%.2f",
                    )
                    set_d = c3.date_input(
                        "3. Bill Settlement Date",
                        value=pd.to_datetime(
                            task_data.get("settlement_date")
                        ).date()
                        if task_data.get("settlement_date")
                        else None,
                    )
                    updated_data = {
                        "request_date": req_d.isoformat() if req_d else None,
                        "bill_amount": bill,
                        "settlement_date": set_d.isoformat() if set_d else None,
                    }

                # 8. Customs Examination (Form 48)
                elif key == "customs_exam":
                    c1, c2 = st.columns(2)
                    st_d = c1.date_input(
                        "1. Examination Start Date",
                        value=pd.to_datetime(task_data.get("start_date")).date()
                        if task_data.get("start_date")
                        else None,
                    )
                    comp_d = c2.date_input(
                        "2. Examination Completed Date",
                        value=pd.to_datetime(
                            task_data.get("completion_date")
                        ).date()
                        if task_data.get("completion_date")
                        else None,
                    )
                    updated_data = {
                        "start_date": st_d.isoformat() if st_d else None,
                        "completion_date": comp_d.isoformat()
                        if comp_d
                        else None,
                    }

                # 9. Customs Lab
                elif key == "customs_lab":
                    lab_req = st.radio(
                        "1. Customs Lab Required?",
                        ["No", "Yes"],
                        index=1
                        if task_data.get("lab_required") == "Yes"
                        else 0,
                    )
                    is_lab_yes = lab_req == "Yes"

                    c1, c2, c3 = st.columns(3)
                    lab_fees = c1.number_input(
                        "2. Customs Lab Fees (SDG)",
                        value=float(task_data.get("lab_fees", 0.0)),
                        disabled=not is_lab_yes,
                        format="%.2f",
                    )
                    pay_d = c2.date_input(
                        "3. Fees Payment Date",
                        value=pd.to_datetime(
                            task_data.get("payment_date")
                        ).date()
                        if task_data.get("payment_date")
                        else None,
                        disabled=not is_lab_yes,
                    )
                    res_d = c3.date_input(
                        "4. Lab Result Issuance Date",
                        value=pd.to_datetime(
                            task_data.get("result_date")
                        ).date()
                        if task_data.get("result_date")
                        else None,
                        disabled=not is_lab_yes,
                    )
                    updated_data = {
                        "lab_required": lab_req,
                        "lab_fees": lab_fees,
                        "payment_date": pay_d.isoformat() if pay_d else None,
                        "result_date": res_d.isoformat() if res_d else None,
                    }

                # 10. SSMO Examination
                elif key == "ssmo_exam":
                    c1, c2 = st.columns(2)
                    st_d = c1.date_input(
                        "1. Examination Start Date",
                        value=pd.to_datetime(task_data.get("start_date")).date()
                        if task_data.get("start_date")
                        else None,
                    )
                    iss_d = c2.date_input(
                        "2. SSMO Certificate Issuance Date",
                        value=pd.to_datetime(
                            task_data.get("issuance_date")
                        ).date()
                        if task_data.get("issuance_date")
                        else None,
                    )
                    updated_data = {
                        "start_date": st_d.isoformat() if st_d else None,
                        "issuance_date": iss_d.isoformat() if iss_d else None,
                    }

                # 11. Customs Evaluation
                elif key == "customs_eval":
                    c1, c2 = st.columns(2)
                    eval_d = c1.date_input(
                        "1. Evaluation Date",
                        value=pd.to_datetime(task_data.get("eval_date")).date()
                        if task_data.get("eval_date")
                        else None,
                    )
                    cust_val = c2.number_input(
                        "2. Customs Value (SDG)",
                        value=float(task_data.get("customs_value", 0.0)),
                        format="%.2f",
                    )

                    c3, c4 = st.columns(2)
                    settle_d = c3.date_input(
                        "3. Settlement Date",
                        value=pd.to_datetime(
                            task_data.get("settlement_date")
                        ).date()
                        if task_data.get("settlement_date")
                        else None,
                    )
                    exit_d = c4.date_input(
                        "4. Release & Exit Pass Date",
                        value=pd.to_datetime(
                            task_data.get("exit_pass_date")
                        ).date()
                        if task_data.get("exit_pass_date")
                        else None,
                    )

                    updated_data = {
                        "eval_date": eval_d.isoformat() if eval_d else None,
                        "customs_value": cust_val,
                        "settlement_date": settle_d.isoformat()
                        if settle_d
                        else None,
                        "exit_pass_date": exit_d.isoformat()
                        if exit_d
                        else None,
                    }

                # 12. SPC Bill
                elif key == "spc_bill":
                    c1, c2, c3 = st.columns(3)
                    req_d = c1.date_input(
                        "1. Request Date",
                        value=pd.to_datetime(
                            task_data.get("request_date")
                        ).date()
                        if task_data.get("request_date")
                        else None,
                    )
                    spc_val = c2.number_input(
                        "2. SPC Bill Value (SDG)",
                        value=float(task_data.get("spc_bill_value", 0.0)),
                        format="%.2f",
                    )
                    set_d = c3.date_input(
                        "3. SPC Bill Settlement Date",
                        value=pd.to_datetime(
                            task_data.get("settlement_date")
                        ).date()
                        if task_data.get("settlement_date")
                        else None,
                    )
                    updated_data = {
                        "request_date": req_d.isoformat() if req_d else None,
                        "spc_bill_value": spc_val,
                        "settlement_date": set_d.isoformat() if set_d else None,
                    }

                # 13. Truck Entry Permit
                elif key == "truck_permit":
                    c1, c2 = st.columns(2)
                    perm_d = c1.date_input(
                        "1. Truck Entry Permit Date",
                        value=pd.to_datetime(
                            task_data.get("permit_date")
                        ).date()
                        if task_data.get("permit_date")
                        else None,
                    )
                    ret_d = c2.date_input(
                        "2. Return Containers Date",
                        value=pd.to_datetime(
                            task_data.get("return_containers_date")
                        ).date()
                        if task_data.get("return_containers_date")
                        else None,
                    )
                    updated_data = {
                        "permit_date": perm_d.isoformat() if perm_d else None,
                        "return_containers_date": ret_d.isoformat()
                        if ret_d
                        else None,
                    }

                # 14. Actual Clearance Completion (Final Step)
                elif key == "final_clearance_complete":
                    act_clear_d = st.date_input(
                        "1. Actual Clearance Completion Date",
                        value=pd.to_datetime(
                            task_data.get("act_clearance_date")
                        ).date()
                        if task_data.get("act_clearance_date")
                        else date.today(),
                    )
                    final_notes = st.text_area(
                        "2. Final Clearance & Handover Notes",
                        value=task_data.get("final_notes", ""),
                    )
                    updated_data = {
                        "act_clearance_date": act_clear_d.isoformat()
                        if act_clear_d
                        else None,
                        "final_notes": final_notes,
                    }

                # Track 2 - FZ Specific Form Tasks
                elif key == "fz_deposit_req":
                    c1, c2 = st.columns(2)
                    dep_d = c1.date_input(
                        "1. Deposit Request Date",
                        value=pd.to_datetime(
                            task_data.get("deposit_request_date")
                        ).date()
                        if task_data.get("deposit_request_date")
                        else None,
                    )
                    app_d = c2.date_input(
                        "2. Request Approval Date",
                        value=pd.to_datetime(
                            task_data.get("approval_date")
                        ).date()
                        if task_data.get("approval_date")
                        else None,
                    )
                    updated_data = {
                        "deposit_request_date": dep_d.isoformat()
                        if dep_d
                        else None,
                        "approval_date": app_d.isoformat() if app_d else None,
                    }

                elif key == "fz_customs_insp":
                    insp_d = st.date_input(
                        "1. Inspection Date",
                        value=pd.to_datetime(
                            task_data.get("inspection_date")
                        ).date()
                        if task_data.get("inspection_date")
                        else None,
                    )
                    updated_data = {
                        "inspection_date": insp_d.isoformat()
                        if insp_d
                        else None
                    }

                elif key == "fz_spc_police":
                    c1, c2 = st.columns(2)
                    req_d = c1.date_input(
                        "1. Request Date",
                        value=pd.to_datetime(
                            task_data.get("request_date")
                        ).date()
                        if task_data.get("request_date")
                        else None,
                    )
                    spc_val = c2.number_input(
                        "2. SPC Bill Value (SDG)",
                        value=float(task_data.get("spc_bill_value", 0.0)),
                        format="%.2f",
                    )
                    c3, c4 = st.columns(2)
                    set_d = c3.date_input(
                        "3. SPC Bill Settlement Date",
                        value=pd.to_datetime(
                            task_data.get("settlement_date")
                        ).date()
                        if task_data.get("settlement_date")
                        else None,
                    )
                    pol_d = c4.date_input(
                        "4. Police Security Appointed Date",
                        value=pd.to_datetime(
                            task_data.get("police_appointed_date")
                        ).date()
                        if task_data.get("police_appointed_date")
                        else None,
                    )
                    updated_data = {
                        "request_date": req_d.isoformat() if req_d else None,
                        "spc_bill_value": spc_val,
                        "settlement_date": set_d.isoformat() if set_d else None,
                        "police_appointed_date": pol_d.isoformat()
                        if pol_d
                        else None,
                    }

                elif key == "fz_receive_cargo":
                    c1, c2 = st.columns(2)
                    rec_d = c1.date_input(
                        "1. Containers Received Date",
                        value=pd.to_datetime(
                            task_data.get("containers_received_date")
                        ).date()
                        if task_data.get("containers_received_date")
                        else None,
                    )
                    ret_d = c2.date_input(
                        "2. Containers Returned Date",
                        value=pd.to_datetime(
                            task_data.get("containers_returned_date")
                        ).date()
                        if task_data.get("containers_returned_date")
                        else None,
                    )
                    updated_data = {
                        "containers_received_date": rec_d.isoformat()
                        if rec_d
                        else None,
                        "containers_returned_date": ret_d.isoformat()
                        if ret_d
                        else None,
                    }

                # Generic Fallback Renderer
                else:
                    d1 = st.date_input(
                        "Request / Start Date",
                        value=pd.to_datetime(task_data.get("start_date")).date()
                        if task_data.get("start_date")
                        else None,
                    )
                    d2 = st.date_input(
                        "Completion / Result Date",
                        value=pd.to_datetime(
                            task_data.get("completion_date")
                        ).date()
                        if task_data.get("completion_date")
                        else None,
                    )
                    val = st.number_input(
                        "Amount (SDG)",
                        value=float(task_data.get("amount", 0.0)),
                        format="%.2f",
                    )
                    updated_data = {
                        "start_date": d1.isoformat() if d1 else None,
                        "completion_date": d2.isoformat() if d2 else None,
                        "amount": val,
                    }

                st.markdown("---")
                c_submit, c_mark = st.columns([2, 1])
                submitted = c_submit.form_submit_button("💾 Save Step Inputs")
                mark_complete = c_mark.form_submit_button(
                    "✅ Mark Task as Complete"
                )

                if submitted or mark_complete:
                    new_status = "Completed" if mark_complete else status
                    now_str = (
                        date.today().isoformat()
                        if mark_complete
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
                            "UPDATE shipments SET clear_at = ? WHERE"
                            " shipment_id = ?",
                            (updated_data["clear_at"], shipment_id),
                        )
                    elif key == "final_clearance_complete" and mark_complete:
                        conn.execute(
                            "UPDATE shipments SET act_clearance_date = ?"
                            " WHERE shipment_id = ?",
                            (updated_data["act_clearance_date"], shipment_id),
                        )

                    conn.commit()
                    st.success(
                        f"Updated '{task['process_name']}' successfully!"
                    )
                    st.rerun()

    conn.close()


# --- 5. MODULE 2: BOTTLENECK & SLA ANALYTICS ---
elif choice == "📊 Clearance & SLA Analytics":
    st.title("📊 Clearance SLA & Bottleneck Analytics")

    conn = get_db_connection()
    df_tasks = pd.read_sql_query(
        """
        SELECT t.task_id, s.bl_awb, s.po_number, s.clear_at, t.process_name, t.track, t.target_sla, t.status, t.completed_at
        FROM process_tasks t
        JOIN shipments s ON t.shipment_id = s.shipment_id
    """,
        conn,
    )
    conn.close()

    if df_tasks.empty:
        st.info("No task data available.")
        st.stop()

    total_tasks = len(df_tasks)
    completed_tasks = len(df_tasks[df_tasks["status"] == "Completed"])
    active_tasks = len(df_tasks[df_tasks["status"] == "Active"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Workflow Steps", total_tasks)
    m2.metric("Completed Steps", completed_tasks)
    m3.metric("Active / In-Progress Steps", active_tasks)
    m4.metric(
        "Overall Workflow Progress",
        f"{(completed_tasks/total_tasks*100):.1f}%",
    )

    st.markdown("---")
    st.markdown("### ⏳ Target SLA Breakdown by Process")

    sla_summary = (
        df_tasks.groupby(["track", "process_name"])
        .agg(
            target_sla=("target_sla", "first"),
            completed_count=("status", lambda x: (x == "Completed").sum()),
            active_count=("status", lambda x: (x == "Active").sum()),
        )
        .reset_index()
    )

    st.dataframe(
        sla_summary,
        column_config={
            "track": st.column_config.TextColumn("Track Route"),
            "process_name": st.column_config.TextColumn("Process Name"),
            "target_sla": st.column_config.NumberColumn(
                "Target SLA (Days)", format="%.2f d"
            ),
            "completed_count": st.column_config.NumberColumn(
                "Completed Shipments", format="%d"
            ),
            "active_count": st.column_config.NumberColumn(
                "Active Shipments", format="%d"
            ),
        },
        use_container_width=True,
        hide_index=True,
    )


# --- 6. MODULE 3: TARGET SLA CONFIGURATION ---
elif choice == "⚙️ Target SLA Settings":
    st.title("⚙️ Configure Process SLA Targets")
    st.write(
        "Adjust target SLA durations (in days) for standard processes."
        " Calculations across active workflows will update dynamically."
    )

    conn = get_db_connection()
    distinct_tasks = pd.read_sql_query(
        "SELECT DISTINCT process_key, process_name, track, target_sla FROM"
        " process_tasks",
        conn,
    )

    if not distinct_tasks.empty:
        selected_proc = st.selectbox(
            "Select Process to Edit Target SLA:",
            distinct_tasks["process_name"].tolist(),
        )
        proc_row = distinct_tasks[
            distinct_tasks["process_name"] == selected_proc
        ].iloc[0]

        c1, c2 = st.columns(2)
        c1.text_input("Track Route", value=proc_row["track"], disabled=True)
        new_sla_val = c2.number_input(
            "Target SLA (Days)",
            value=float(proc_row["target_sla"]),
            step=0.25,
            min_value=0.1,
        )

        if st.button("💾 Save SLA Target"):
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE process_tasks SET target_sla = ? WHERE process_name ="
                " ?",
                (new_sla_val, selected_proc),
            )
            conn.commit()
            conn.close()
            st.success(
                f"Successfully updated SLA target for '{selected_proc}' to"
                f" {new_sla_val} days!"
            )
            st.rerun()
    conn.close()
