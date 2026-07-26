# --- 5. CLEARANCE BOTTLENECK & SLA ANALYTICS ---
elif choice == "Clearance Bottleneck & SLA Analytics":
    st.subheader("📊 Clearance Bottleneck & SLA Analytics")
    
    conn = get_db_connection()
    
    # Query all task instances across all shipments
    tasks_analytics_df = pd.read_sql_query("""
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
    """, conn)
    
    conn.close()

    if tasks_analytics_df.empty:
        st.info("No clearance task data available yet to perform SLA analytics.")
    else:
        # Calculate calculated metrics for each task
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

        tasks_analytics_df[["days_taken", "is_breached", "delay_days"]] = tasks_analytics_df.apply(compute_task_metrics, axis=1)

        # --- TOP LEVEL METRICS ---
        completed_tasks = tasks_analytics_df[tasks_analytics_df["status"] == "Completed"]
        in_progress_tasks = tasks_analytics_df[tasks_analytics_df["status"] == "In Progress"]
        total_breaches = tasks_analytics_df["is_breached"].sum()
        
        total_eval_tasks = len(completed_tasks) + len(in_progress_tasks)
        sla_compliance_rate = ((total_eval_tasks - total_breaches) / total_eval_tasks * 100) if total_eval_tasks > 0 else 100.0
        avg_completion_time = completed_tasks["days_taken"].mean() if not completed_tasks.empty else 0.0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Overall SLA Compliance Rate", f"{sla_compliance_rate:.1f}%")
        m2.metric("Active Clearance Tasks", len(in_progress_tasks))
        m3.metric("Total SLA Breaches", int(total_breaches), delta=f"-{total_breaches} Overdue" if total_breaches > 0 else "0", delta_color="inverse")
        m4.metric("Avg Step Duration", f"{avg_completion_time:.1f} Days")

        st.markdown("---")

        # --- DEPARTMENT BOTTLENECK ANALYSIS ---
        st.markdown("### 🏢 Bottleneck Analysis by Department")
        
        dept_summary = tasks_analytics_df.groupby("department").agg(
            total_tasks=("task_id", "count"),
            active_tasks=("status", lambda x: (x == "In Progress").sum()),
            completed_tasks=("status", lambda x: (x == "Completed").sum()),
            breach_count=("is_breached", "sum"),
            avg_days=("days_taken", "mean"),
            avg_sla=("sla_days", "mean")
        ).reset_index()

        dept_summary["Avg Delay (Days)"] = (dept_summary["avg_days"] - dept_summary["avg_sla"]).clip(lower=0)

        st.dataframe(
            dept_summary,
            column_config={
                "department": st.column_config.TextColumn("Department"),
                "total_tasks": st.column_config.NumberColumn("Total Tasks", format="%d"),
                "active_tasks": st.column_config.NumberColumn("In Progress", format="%d"),
                "completed_tasks": st.column_config.NumberColumn("Completed", format="%d"),
                "breach_count": st.column_config.NumberColumn("SLA Violations 🚨", format="%d"),
                "avg_days": st.column_config.NumberColumn("Avg Duration (Days)", format="%.1f"),
                "avg_sla": st.column_config.NumberColumn("Target SLA (Days)", format="%.1f"),
                "Avg Delay (Days)": st.column_config.NumberColumn("Avg Delay Overhead", format="%.1f days"),
            },
            use_container_width=True,
            hide_index=True
        )

        st.markdown("---")

        # --- STEP-BY-STEP BOTTLENECK RANKING ---
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("### ⏳ Slowest Clearance Steps")
            step_summary = tasks_analytics_df.groupby(["step_order", "task_name", "department"]).agg(
                avg_days=("days_taken", "mean"),
                target_sla=("sla_days", "first"),
                breaches=("is_breached", "sum")
            ).reset_index().sort_values(by="avg_days", ascending=False)

            step_summary.rename(columns={
                "step_order": "Step",
                "task_name": "Task Name",
                "department": "Department",
                "avg_days": "Avg Days Taken",
                "target_sla": "Target SLA",
                "breaches": "Breaches"
            }, inplace=True)

            st.dataframe(
                step_summary,
                column_config={
                    "Step": st.column_config.NumberColumn("Step", format="%d"),
                    "Avg Days Taken": st.column_config.NumberColumn("Avg Duration", format="%.1f d"),
                    "Target SLA": st.column_config.NumberColumn("Target SLA", format="%d d"),
                    "Breaches": st.column_config.NumberColumn("Breaches 🚨", format="%d"),
                },
                use_container_width=True,
                hide_index=True
            )

        with col_right:
            st.markdown("### 🚨 Active SLA Violations / Overdue Steps")
            overdue_df = tasks_analytics_df[(tasks_analytics_df["is_breached"] == True) & (tasks_analytics_df["status"] == "In Progress")].copy()

            if overdue_df.empty:
                st.success("🎉 No active SLA violations! All in-progress clearance tasks are on track.")
            else:
                overdue_view = overdue_df[["bl_awb", "po_number", "task_name", "department", "delay_days", "start_date"]].copy()
                overdue_view.columns = ["BL / AWB", "PO Number", "Stuck Task", "Department", "Days Overdue", "Started On"]
                
                st.dataframe(
                    overdue_view,
                    column_config={
                        "Days Overdue": st.column_config.NumberColumn("Days Overdue 🚨", format="%d days"),
                    },
                    use_container_width=True,
                    hide_index=True
                )
