import sqlite3
from datetime import date, timedelta
import pandas as pd
import streamlit as st

# Set Streamlit Page Configuration
st.set_page_config(
    page_title="Supply Chain & Clearance Control Tower",
    page_icon="📦",
    layout="wide",
)


# --- 1. DATABASE CONNECTION & INITIALIZATION ---
def get_db_connection():
    conn = sqlite3.connect("shipments.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes tables and populates sample data if empty."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT,
            bu_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            shipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            bl_awb TEXT,
            shipment_ref TEXT,
            origin TEXT,
            destination TEXT,
            fob_value REAL,
            freight_cost REAL,
            insurance_cost REAL,
            FOREIGN KEY(order_id) REFERENCES master_orders(order_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipment_tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER,
            step_order INTEGER,
            task_name TEXT,
            department TEXT,
            status TEXT,
            sla_days INTEGER,
            start_date DATE,
            completion_date DATE,
            ref_number TEXT,
            FOREIGN KEY(shipment_id) REFERENCES shipments(shipment_id)
        )
    """)

    # Seed data if database is empty
    cursor.execute("SELECT COUNT(*) FROM master_orders")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO master_orders (po_number, bu_id) VALUES ('PO-2026-001',"
            " 'BU-LOGISTICS')"
        )
        cursor.execute(
            "INSERT INTO master_orders (po_number, bu_id) VALUES ('PO-2026-002',"
            " 'BU-RETAIL')"
        )

        cursor.execute(
            "INSERT INTO shipments (order_id, bl_awb, shipment_ref, origin,"
            " destination, fob_value, freight_cost, insurance_cost) VALUES (1,"
            " 'BL-123456789', 'SHP-2026-001', 'Shanghai, CN', 'Port Sudan, SD',"
            " 45000.0, 3200.0, 450.0)"
        )
        cursor.execute(
            "INSERT INTO shipments (order_id, bl_awb, shipment_ref, origin,"
            " destination, fob_value, freight_cost, insurance_cost) VALUES (2,"
            " 'AWB-987654321', 'SHP-2026-002', 'Dubai, AE', 'Khartoum, SD',"
            " 28000.0, 1800.0, 280.0)"
        )

        today = date.today()

        tasks_shp1 = [
            (
                1,
                1,
                "Document Verification",
                "Compliance",
                "Completed",
                2,
                today - timedelta(days=10),
                today - timedelta(days=8),
                "REF-101",
            ),
            (
                1,
                2,
                "Customs Declaration",
                "Customs",
                "Completed",
                3,
                today - timedelta(days=8),
                today - timedelta(days=3),
                "REF-102",
            ),
            (
                1,
                3,
                "Port Duty Payment",
                "Operations",
                "In Progress",
                1,
                today - timedelta(days=3),
                None,
                "REF-103",
            ),
            (
                1,
                4,
                "Physical Inspection",
                "Regulatory",
                "Pending",
                2,
                None,
                None,
                "REF-104",
            ),
        ]

        tasks_shp2 = [
            (
                2,
                1,
                "Document Verification",
                "Compliance",
                "Completed",
                2,
                today - timedelta(days=5),
                today - timedelta(days=4),
                "REF-201",
            ),
            (
                2,
                2,
                "Customs Declaration",
                "Customs",
                "In Progress",
                3,
                today - timedelta(days=1),
                None,
                "REF-202",
            ),
            (
                2,
                3,
                "Port Duty Payment",
                "Operations",
                "Pending",
                1,
                None,
                None,
                "REF-203",
            ),
        ]

        cursor.executemany(
            """
            INSERT INTO shipment_tasks (shipment_id, step_order, task_name, department, status, sla_days, start_date, completion_date, ref_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            tasks_shp1 + tasks_shp2,
        )

    conn.commit()
    conn.close()


init_db()


# --- 2. NAVIGATION SIDEBAR ---
st.sidebar.title("🚢 Control Tower Navigation")
menu = [
    "Dashboard Overview",
    "Landed Cost Calculator",
    "Clearance Bottleneck & SLA Analytics",
]
choice = st.sidebar.selectbox("Select Module", menu)


# --- 3. MODULE: DASHBOARD OVERVIEW ---
if choice == "Dashboard Overview":
    st.title("📌 Dashboard Overview")
    st.write(
        "Welcome to your integrated Logistics, Landed Cost, and Clearance"
        " Control Tower."
    )

    conn = get_db_connection()
    shipments_df = pd.read_sql_query(
        """
        SELECT s.shipment_ref, s.bl_awb, mo.po_number, mo.bu_id, s.origin, s.destination, s.fob_value
        FROM shipments s
        JOIN master_orders mo ON s.order_id = mo.order_id
    """,
        conn,
    )
    conn.close()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Active Shipments", len(shipments_df))
    col2.metric(
        "Total Portfolio FOB Value", f"${shipments_df['fob_value'].sum():,.2f}"
    )
    col3.metric("Active Operating BUs", shipments_df["bu_id"].nunique())

    st.markdown("---")
    st.markdown("### 📦 Active Shipments Summary")
    st.dataframe(shipments_df, use_container_width=True, hide_index=True)


# --- 4. MODULE: LANDED COST CALCULATOR ---
elif choice == "Landed Cost Calculator":
    st.title("💰 Landed Cost Calculator")
    st.write(
        "Calculate complete landed cost breakdowns per shipment including CIF"
        " value, duties, taxes, and port handling charges."
    )

    conn = get_db_connection()
    shipments_df = pd.read_sql_query(
        "SELECT shipment_id, shipment_ref, bl_awb, fob_value, freight_cost,"
        " insurance_cost FROM shipments",
        conn,
    )
    conn.close()

    selected_ref = st.selectbox(
        "Select Shipment to Calculate",
        options=shipments_df["shipment_ref"].tolist(),
    )
    shipment_data = shipments_df[
        shipments_df["shipment_ref"] == selected_ref
    ].iloc[0]

    st.markdown("#### 1. Base Commercial Values")
    c1, c2, c3, c4 = st.columns(4)
    fob = c1.number_input(
        "FOB Value ($)",
        value=float(shipment_data["fob_value"]),
        step=500.0,
    )
    freight = c2.number_input(
        "Freight Cost ($)",
        value=float(shipment_data["freight_cost"]),
        step=100.0,
    )
    insurance = c3.number_input(
        "Insurance Cost ($)",
        value=float(shipment_data["insurance_cost"]),
        step=50.0,
    )
    quantity = c4.number_input(
        "Shipment Units / Quantity", value=1000, step=50
    )

    cif_value = fob + freight + insurance
    st.info(f"**Calculated CIF Value:** ${cif_value:,.2f}")

    st.markdown("#### 2. Duty, Tax & Clearing Overhead Inputs")
    col_a, col_b, col_c, col_d = st.columns(4)
    duty_rate = (
        col_a.number_input("Customs Duty Rate (%)", value=10.0, step=0.5) / 100.0
    )
    vat_rate = col_b.number_input("VAT Rate (%)", value=15.0, step=0.5) / 100.0
    port_fees = col_c.number_input("Port & Demurrage Fees ($)", value=750.0)
    misc_fees = col_d.number_input("Clearance & Agency Fees ($)", value=450.0)

    # Landed Cost Calculation logic
    duty_amount = cif_value * duty_rate
    taxable_vat_base = cif_value + duty_amount
    vat_amount = taxable_vat_base * vat_rate
    total_landed_cost = (
        cif_value + duty_amount + vat_amount + port_fees + misc_fees
    )
    unit_landed_cost = (
        total_landed_cost / quantity if quantity > 0 else total_landed_cost
    )

    st.markdown("---")
    st.markdown("### 📊 Landed Cost Breakdown")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Landed Cost", f"${total_landed_cost:,.2f}")
    m2.metric("Unit Landed Cost", f"${unit_landed_cost:,.2f} / unit")
    m3.metric("Customs Duties & VAT", f"${duty_amount + vat_amount:,.2f}")
    m4.metric(
        "Landed Cost Multiplier", f"{(total_landed_cost / fob):.2f}x FOB"
    )

    cost_data = {
        "Cost Component": [
            "FOB Goods Value",
            "Freight",
            "Insurance",
            "Customs Duty",
            "VAT",
            "Port & Handling Fees",
            "Clearance & Agency Fees",
            "TOTAL LANDED COST",
        ],
        "Amount ($)": [
            fob,
            freight,
            insurance,
            duty_amount,
            vat_amount,
            port_fees,
            misc_fees,
            total_landed_cost,
        ],
        "% of Total": [
            (fob / total_landed_cost) * 100,
            (freight / total_landed_cost) * 100,
            (insurance / total_landed_cost) * 100,
            (duty_amount / total_landed_cost) * 100,
            (vat_amount / total_landed_cost) * 100,
            (port_fees / total_landed_cost) * 100,
            (misc_fees / total_landed_cost) * 100,
            100.0,
        ],
    }

    cost_df = pd.DataFrame(cost_data)
    st.dataframe(
        cost_df,
        column_config={
            "Amount ($)": st.column_config.NumberColumn(format="$%.2f"),
            "% of Total": st.column_config.NumberColumn(format="%.1f%%"),
        },
        use_container_width=True,
        hide_index=True,
    )


# --- 5. MODULE: CLEARANCE BOTTLENECK & SLA ANALYTICS ---
elif choice == "Clearance Bottleneck & SLA Analytics":
    st.title("📊 Clearance Bottleneck & SLA Analytics")

    conn = get_db_connection()

    tasks_analytics_df = pd.read_sql_query(
        """
        SELECT 
            st.task_id,
            st.shipment_id,
            s.bl_awb,
            s.shipment_ref,
            mo.po_number,
            mo.bu_id,
            st.step_order,
            st.task_name,
            st.department,
            st.status,
            st.sla_days,
            st.start_date,
            st.completion_date,
            st.ref_number
        FROM shipment_tasks st
        JOIN shipments s ON st.shipment_id = s.shipment_id
        JOIN master_orders mo ON s.order_id = mo.order_id
        ORDER BY st.shipment_id DESC, st.step_order ASC
    """,
        conn,
    )

    conn.close()

    if tasks_analytics_df.empty:
        st.info("No clearance task data available yet to perform SLA analytics.")
    else:
        # Date parsing
        tasks_analytics_df["start_date"] = pd.to_datetime(
            tasks_analytics_df["start_date"]
        ).dt.date
        tasks_analytics_df["completion_date"] = pd.to_datetime(
            tasks_analytics_df["completion_date"]
        ).dt.date

        today = date.today()

        def compute_task_metrics(row):
            status = row["status"]
            sla = int(row["sla_days"]) if pd.notna(row["sla_days"]) else 2
            st_date = row["start_date"]
            comp_date = row["completion_date"]

            days_taken = None
            is_breached = False
            delay_days = 0

            if status == "Completed" and pd.notna(st_date) and pd.notna(comp_date):
                days_taken = max(0, (comp_date - st_date).days)
                if days_taken > sla:
                    is_breached = True
                    delay_days = days_taken - sla
            elif status == "In Progress" and pd.notna(st_date):
                days_taken = max(0, (today - st_date).days)
                if days_taken > sla:
                    is_breached = True
                    delay_days = days_taken - sla

            return pd.Series([days_taken, is_breached, delay_days])

        tasks_analytics_df[["days_taken", "is_breached", "delay_days"]] = (
            tasks_analytics_df.apply(compute_task_metrics, axis=1)
        )

        # Top level KPIs
        completed_tasks = tasks_analytics_df[
            tasks_analytics_df["status"] == "Completed"
        ]
        in_progress_tasks = tasks_analytics_df[
            tasks_analytics_df["status"] == "In Progress"
        ]
        total_breaches = tasks_analytics_df["is_breached"].sum()

        total_eval_tasks = len(completed_tasks) + len(in_progress_tasks)
        sla_compliance_rate = (
            ((total_eval_tasks - total_breaches) / total_eval_tasks * 100)
            if total_eval_tasks > 0
            else 100.0
        )
        avg_completion_time = (
            completed_tasks["days_taken"].mean()
            if not completed_tasks.empty
            else 0.0
        )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Overall SLA Compliance Rate", f"{sla_compliance_rate:.1f}%")
        m2.metric("Active Clearance Tasks", len(in_progress_tasks))
        m3.metric(
            "Total SLA Breaches",
            int(total_breaches),
            delta=f"-{total_breaches} Overdue" if total_breaches > 0 else "0",
            delta_color="inverse",
        )
        m4.metric("Avg Step Duration", f"{avg_completion_time:.1f} Days")

        st.markdown("---")
        st.markdown("### 🏢 Bottleneck Analysis by Department")

        dept_summary = (
            tasks_analytics_df.groupby("department")
            .agg(
                total_tasks=("task_id", "count"),
                active_tasks=("status", lambda x: (x == "In Progress").sum()),
                completed_tasks=("status", lambda x: (x == "Completed").sum()),
                breach_count=("is_breached", "sum"),
                avg_days=("days_taken", "mean"),
                avg_sla=("sla_days", "mean"),
            )
            .reset_index()
        )

        dept_summary["Avg Delay (Days)"] = (
            dept_summary["avg_days"] - dept_summary["avg_sla"]
        ).clip(lower=0)

        st.dataframe(
            dept_summary,
            column_config={
                "department": st.column_config.TextColumn("Department"),
                "total_tasks": st.column_config.NumberColumn(
                    "Total Tasks", format="%d"
                ),
                "active_tasks": st.column_config.NumberColumn(
                    "In Progress", format="%d"
                ),
                "completed_tasks": st.column_config.NumberColumn(
                    "Completed", format="%d"
                ),
                "breach_count": st.column_config.NumberColumn(
                    "SLA Violations 🚨", format="%d"
                ),
                "avg_days": st.column_config.NumberColumn(
                    "Avg Duration (Days)", format="%.1f"
                ),
                "avg_sla": st.column_config.NumberColumn(
                    "Target SLA (Days)", format="%.1f"
                ),
                "Avg Delay (Days)": st.column_config.NumberColumn(
                    "Avg Delay Overhead", format="%.1f days"
                ),
            },
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("### ⏳ Slowest Clearance Steps")
            step_summary = (
                tasks_analytics_df.groupby(
                    ["step_order", "task_name", "department"]
                )
                .agg(
                    avg_days=("days_taken", "mean"),
                    target_sla=("sla_days", "first"),
                    breaches=("is_breached", "sum"),
                )
                .reset_index()
                .sort_values(by="avg_days", ascending=False)
            )

            step_summary.rename(
                columns={
                    "step_order": "Step",
                    "task_name": "Task Name",
                    "department": "Department",
                    "avg_days": "Avg Days Taken",
                    "target_sla": "Target SLA",
                    "breaches": "Breaches",
                },
                inplace=True,
            )

            st.dataframe(
                step_summary,
                column_config={
                    "Step": st.column_config.NumberColumn("Step", format="%d"),
                    "Avg Days Taken": st.column_config.NumberColumn(
                        "Avg Duration", format="%.1f d"
                    ),
                    "Target SLA": st.column_config.NumberColumn(
                        "Target SLA", format="%d d"
                    ),
                    "Breaches": st.column_config.NumberColumn(
                        "Breaches 🚨", format="%d"
                    ),
                },
                use_container_width=True,
                hide_index=True,
            )

        with col_right:
            st.markdown("### 🚨 Active SLA Violations / Overdue Steps")
            overdue_df = tasks_analytics_df[
                (tasks_analytics_df["is_breached"] == True)
                & (tasks_analytics_df["status"] == "In Progress")
            ].copy()

            if overdue_df.empty:
                st.success(
                    "🎉 No active SLA violations! All in-progress clearance"
                    " tasks are on track."
                )
            else:
                overdue_view = overdue_df[
                    [
                        "bl_awb",
                        "po_number",
                        "task_name",
                        "department",
                        "delay_days",
                        "start_date",
                    ]
                ].copy()
                overdue_view.columns = [
                    "BL / AWB",
                    "PO Number",
                    "Stuck Task",
                    "Department",
                    "Days Overdue",
                    "Started On",
                ]

                st.dataframe(
                    overdue_view,
                    column_config={
                        "Days Overdue": st.column_config.NumberColumn(
                            "Days Overdue 🚨", format="%d days"
                        ),
                    },
                    use_container_width=True,
                    hide_index=True,
                )
