import os
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

# ---------------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    st.error(
        "DATABASE_URL variable missing. Set it in your Railway dashboard."
    )
    st.stop()

engine = create_engine(DATABASE_URL)


def init_db():
    with engine.connect() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS currencies (
                code VARCHAR(10) PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS master_accounts (
                id SERIAL PRIMARY KEY,
                bu VARCHAR(100),
                department VARCHAR(100),
                bank_shortname VARCHAR(50),
                bank_name VARCHAR(150),
                account_number VARCHAR(100),
                account_name VARCHAR(150),
                currency VARCHAR(10)
            );
            CREATE TABLE IF NOT EXISTS exchange_rates (
                id SERIAL PRIMARY KEY,
                rate_date DATE,
                currency_pair VARCHAR(20),
                rate NUMERIC(15, 4),
                is_auto_filled BOOLEAN DEFAULT FALSE,
                UNIQUE(rate_date, currency_pair)
            );
            CREATE TABLE IF NOT EXISTS bank_dues (
                id SERIAL PRIMARY KEY,
                account_id INT REFERENCES master_accounts(id),
                due_date DATE,
                facility_type VARCHAR(100),
                amount NUMERIC(15, 2),
                status VARCHAR(50) DEFAULT 'Active'
            );
            CREATE TABLE IF NOT EXISTS daily_cash_positions (
                id SERIAL PRIMARY KEY,
                position_date DATE,
                account_id INT REFERENCES master_accounts(id),
                cash_balance NUMERIC(15, 2),
                UNIQUE(position_date, account_id)
            );
            
            -- Insert default currencies if table is empty
            INSERT INTO currencies (code) 
            VALUES ('USD'), ('EUR'), ('EGP'), ('GBP'), ('SAR'), ('AED')
            ON CONFLICT DO NOTHING;
        """)
        )
        conn.commit()


init_db()


def get_currencies():
    df = pd.read_sql(
        "SELECT code FROM currencies ORDER BY code ASC", engine
    )
    return df["code"].tolist() if not df.empty else ["USD"]


# ---------------------------------------------------------
# NAVIGATION & SIDEBAR
# ---------------------------------------------------------
st.sidebar.title("🏦 Treasury Portal")
menu = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard & Coverage",
        "Daily EX Rates",
        "Bank Dues & Cash",
        "Master Settings",
    ],
)

# ---------------------------------------------------------
# MASTER SETTINGS
# ---------------------------------------------------------
if menu == "Master Settings":
    st.title("⚙️ Master Settings & Entity Registration")

    # SECTION 1: CURRENCY MANAGEMENT
    st.subheader("1. Currency List Management")
    c_list = get_currencies()
    st.write(f"**Current Currencies:** {', '.join(c_list)}")

    with st.form("add_currency_form"):
        new_curr = st.text_input(
            "Add New Currency Code (e.g., KWD, QAR, JPY)"
        ).upper()
        if st.form_submit_button("Add Currency"):
            if new_curr:
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO currencies (code) VALUES (:c) ON CONFLICT DO NOTHING"
                        ),
                        {"c": new_curr.strip()},
                    )
                    conn.commit()
                st.success(f"Currency '{new_curr}' added successfully!")
                st.rerun()

    st.markdown("---")

    # SECTION 2: BANK ACCOUNT REGISTRATION
    st.subheader("2. Add Business Unit & Bank Account")
    available_currencies = get_currencies()

    with st.form("add_account"):
        c1, c2 = st.columns(2)
        bu = c1.text_input("Business Unit (BU)")
        dept = c2.text_input("Department")

        c3, c4 = st.columns(2)
        bank_short = c3.text_input("Bank Short Name (e.g., CIB, HSBC)")
        bank_name = c4.text_input("Full Bank Name")

        c5, c6, c7 = st.columns(3)
        acc_num = c5.text_input("Account Number")
        acc_name = c6.text_input("Account Name")
        currency = c7.selectbox("Currency", available_currencies)

        if st.form_submit_button("Save Account Master"):
            with engine.connect() as conn:
                conn.execute(
                    text("""
                    INSERT INTO master_accounts (bu, department, bank_shortname, bank_name, account_number, account_name, currency)
                    VALUES (:bu, :dept, :bs, :bn, :an, :ana, :curr)
                """),
                    {
                        "bu": bu,
                        "dept": dept,
                        "bs": bank_short,
                        "bn": bank_name,
                        "an": acc_num,
                        "ana": acc_name,
                        "curr": currency,
                    },
                )
                conn.commit()
            st.success("Account registered successfully!")

    st.markdown("---")
    st.subheader("Registered Accounts Registry")
    accounts_df = pd.read_sql("SELECT * FROM master_accounts", engine)
    st.dataframe(accounts_df, use_container_width=True)

# ---------------------------------------------------------
# DAILY EX RATES
# ---------------------------------------------------------
elif menu == "Daily EX Rates":
    st.title("💱 Foreign Exchange Rate Management")

    today = pd.to_datetime("today").date()

    # Get registered non-USD currencies for pair dropdown
    all_currencies = [c for c in get_currencies() if c != "USD"]

    st.subheader("Log Daily Rate")

    # Sequence: Date -> Rate -> Currency
    c1, c2, c3 = st.columns([1, 1.5, 1.5])
    rate_date = c1.date_input("Date", today)
    rate_val = c2.number_input(
        "Rate", value=0.0000, format="%.4f", step=0.0001
    )

    col_fix, col_drop = c3.columns([0.4, 1])
    col_fix.markdown("<br><b>USD /</b>", unsafe_allow_html=True)
    target_currency = col_drop.selectbox("Target Currency", all_currencies)

    full_pair = f"USD/{target_currency}"

    if st.button("Record Rate"):
        if rate_val <= 0:
            st.error("Please enter a rate value greater than 0.")
        else:
            with engine.connect() as conn:
                conn.execute(
                    text("""
                    INSERT INTO exchange_rates (rate_date, currency_pair, rate, is_auto_filled)
                    VALUES (:d, :p, :r, FALSE)
                    ON CONFLICT (rate_date, currency_pair) DO UPDATE SET rate = EXCLUDED.rate, is_auto_filled = FALSE
                """),
                    {"d": rate_date, "p": full_pair, "r": rate_val},
                )
                conn.commit()
            st.success(
                f"Recorded: {full_pair} = {rate_val:,.4f} for {rate_date}"
            )

    st.markdown("---")
    st.subheader("EX Rate Analytics & Trends")

    selected_pair = st.selectbox(
        "Select Currency Pair to View",
        [f"USD/{c}" for c in all_currencies],
    )

    rates_df = pd.read_sql(
        "SELECT * FROM exchange_rates WHERE currency_pair = :p ORDER BY rate_date ASC",
        engine,
        params={"p": selected_pair},
    )

    if not rates_df.empty:
        rates_df["rate_date"] = pd.to_datetime(rates_df["rate_date"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Average Rate", f"{rates_df['rate'].mean():,.4f}")
        m2.metric("Max Rate", f"{rates_df['rate'].max():,.4f}")
        m3.metric("Min Rate", f"{rates_df['rate'].min():,.4f}")
        m4.metric("Std Dev", f"{rates_df['rate'].std():,.4f}")

        fig = px.line(
            rates_df,
            x="rate_date",
            y="rate",
            title=f"{selected_pair} Rate Movement",
            markers=True,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"No exchange rate data recorded yet for {selected_pair}.")

# ---------------------------------------------------------
# BANK DUES & CASH
# ---------------------------------------------------------
elif menu == "Bank Dues & Cash":
    st.title("🏦 Bank Dues & Daily Cash Positions")

    acc_df = pd.read_sql(
        "SELECT id, bank_shortname, account_number, currency FROM master_accounts",
        engine,
    )
    acc_options = (
        {
            f"{r['bank_shortname']} - {r['account_number']} ({r['currency']})": r[
                "id"
            ]
            for _, r in acc_df.iterrows()
        }
        if not acc_df.empty
        else {}
    )

    t1, t2 = st.tabs(["Register Bank Due", "Log Cash Position"])

    with t1:
        if not acc_options:
            st.warning("Please configure accounts in Master Settings first.")
        else:
            with st.form("dues_form"):
                acc_choice = st.selectbox(
                    "Select Account", list(acc_options.keys())
                )
                due_date = st.date_input("Due Date")
                fac_type = st.text_input(
                    "Facility Type (e.g., LC, LTR, Overdraft)"
                )
                amount = st.number_input(
                    "Amount Due", min_value=0.0, format="%.2f"
                )

                if st.form_submit_button("Save Bank Due"):
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                            INSERT INTO bank_dues (account_id, due_date, facility_type, amount)
                            VALUES (:a, :d, :f, :amt)
                        """),
                            {
                                "a": acc_options[acc_choice],
                                "d": due_date,
                                "f": fac_type,
                                "amt": amount,
                            },
                        )
                        conn.commit()
                    st.success("Bank due registered successfully!")

    with t2:
        if acc_options:
            with st.form("cash_form"):
                pos_date = st.date_input("Position Date")
                acc_choice = st.selectbox(
                    "Select Account",
                    list(acc_options.keys()),
                    key="cash_acc",
                )
                cash_bal = st.number_input(
                    "Cash in Hand / Balance", min_value=0.0, format="%.2f"
                )

                if st.form_submit_button("Record Position"):
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                            INSERT INTO daily_cash_positions (position_date, account_id, cash_balance)
                            VALUES (:d, :a, :c)
                            ON CONFLICT (position_date, account_id) DO UPDATE SET cash_balance = EXCLUDED.cash_balance
                        """),
                            {
                                "d": pos_date,
                                "a": acc_options[acc_choice],
                                "c": cash_bal,
                            },
                        )
                        conn.commit()
                    st.success("Cash balance saved!")

# ---------------------------------------------------------
# DASHBOARD & COVERAGE
# ---------------------------------------------------------
else:
    st.title("📊 Treasury Coverage & Liquidity Dashboard")

    cash_df = pd.read_sql(
        "SELECT SUM(cash_balance) as total_cash FROM daily_cash_positions WHERE position_date = CURRENT_DATE",
        engine,
    )
    dues_df = pd.read_sql(
        "SELECT SUM(amount) as total_dues FROM bank_dues WHERE status = 'Active'",
        engine,
    )

    total_cash = (
        cash_df.iloc[0]["total_cash"]
        if not cash_df.empty and cash_df.iloc[0]["total_cash"]
        else 0.0
    )
    total_dues = (
        dues_df.iloc[0]["total_dues"]
        if not dues_df.empty and dues_df.iloc[0]["total_dues"]
        else 0.0
    )
    gap = total_cash - total_dues

    c1, c2, c3 = st.columns(3)
    c1.metric("Cash in Hand (Today)", f"${total_cash:,.2f}")
    c2.metric("Active Bank Dues", f"${total_dues:,.2f}")
    c3.metric("Net Coverage Gap", f"${gap:,.2f}", delta=f"{gap:,.2f}")

    if total_dues > total_cash:
        st.error(
            f"⚠️ Liquidity Alert: Bank Dues exceed available Cash in Hand by ${abs(gap):,.2f}!"
        )
    else:
        st.success("✅ Cash position is sufficient to cover active bank dues.")
