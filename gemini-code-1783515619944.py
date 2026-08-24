import hashlib
import os
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

# ---------------------------------------------------------
# PAGE CONFIG & MAERSK BRANDING INJECTION
# ---------------------------------------------------------
st.set_page_config(
    page_title="Corporate Treasury Portal",
    page_icon="🛳️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Maersk Theme CSS
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Roboto', sans-serif;
        background-color: #F4F6F8;
    }
    
    /* Top Header Styling */
    .stApp > header {
        background-color: #00243A !important;
    }
    
    /* Primary Buttons & Accents */
    .stButton>button {
        background-color: #42B0D5 !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border-radius: 2px !important;
        border: none !important;
        padding: 0.5rem 1rem !important;
    }
    
    .stButton>button:hover {
        background-color: #3197BB !important;
        color: #FFFFFF !important;
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #00243A !important;
        color: #FFFFFF !important;
    }
    
    [data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }
    
    /* Cards and Containers */
    div[data-testid="metric-container"] {
        background-color: #FFFFFF;
        border-left: 5px solid #42B0D5;
        padding: 15px;
        border-radius: 4px;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.05);
    }
    </style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL and hasattr(st, "secrets"):
  DATABASE_URL = st.secrets.get("DATABASE_URL")

if not DATABASE_URL:
  st.error("DATABASE_URL environment variable missing in Railway setup.")
  st.stop()

engine = create_engine(DATABASE_URL)


def hash_password(password):
  return hashlib.sha256(password.encode()).hexdigest()


def init_db():
  with engine.connect() as conn:
    conn.execute(
        text("""
            -- Create users table if it doesn't exist
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(64),
                role VARCHAR(20) DEFAULT 'Read/Write'
            );

            -- Directly patch missing columns if an old users table exists
            ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(64);
            ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'Read/Write';

            -- Ensure UNIQUE constraint exists on username
            DO $$ 
            BEGIN 
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'users_username_key'
                ) THEN 
                    ALTER TABLE users ADD CONSTRAINT users_username_key UNIQUE (username);
                END IF;
            END $$;

            CREATE TABLE IF NOT EXISTS bus (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS banks (
                id SERIAL PRIMARY KEY,
                short_name VARCHAR(50) UNIQUE NOT NULL,
                full_name VARCHAR(150) NOT NULL
            );
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
                is_auto_filled BOOLEAN DEFAULT FALSE
            );
            
            ALTER TABLE exchange_rates DROP CONSTRAINT IF EXISTS exchange_rates_rate_date_key;
            DO $$ 
            BEGIN 
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_rate_date_pair') THEN 
                    ALTER TABLE exchange_rates ADD CONSTRAINT uq_rate_date_pair UNIQUE (rate_date, currency_pair);
                END IF;
            END $$;

            CREATE TABLE IF NOT EXISTS bank_dues (
                id SERIAL PRIMARY KEY,
                account_id INT REFERENCES master_accounts(id) ON DELETE CASCADE,
                due_date DATE,
                facility_type VARCHAR(100),
                amount NUMERIC(15, 2),
                status VARCHAR(50) DEFAULT 'Active'
            );
            CREATE TABLE IF NOT EXISTS daily_cash_positions (
                id SERIAL PRIMARY KEY,
                position_date DATE,
                account_id INT REFERENCES master_accounts(id) ON DELETE CASCADE,
                cash_balance NUMERIC(15, 2),
                UNIQUE(position_date, account_id)
            );
            
            -- Seed Default Manager User (Forces password reset to admin123)
            INSERT INTO users (username, password_hash, role)
            VALUES ('admin', :default_pass, 'Manager')
            ON CONFLICT (username) DO UPDATE 
            SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role;
            
            INSERT INTO currencies (code) 
            VALUES ('USD'), ('EUR'), ('EGP'), ('GBP'), ('SAR'), ('AED'), ('SDG')
            ON CONFLICT DO NOTHING;
        """),
        {"default_pass": hash_password("admin123")},
    )
    conn.commit()


# Run database initialization
init_db()

# ---------------------------------------------------------
# AUTHENTICATION MODULE
# ---------------------------------------------------------
if "authenticated" not in st.session_state:
  st.session_state.authenticated = False
  st.session_state.user_role = None
  st.session_state.username = None


def login():
  st.title("🛳️ Treasury Portal Login")
  with st.form("login_form"):
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.form_submit_button("Sign In"):
      h = hash_password(p)
      user_df = pd.read_sql(
          text(
              "SELECT username, role FROM users WHERE username = :u AND"
              " password_hash = :h"
          ),
          engine,
          params={"u": u, "h": h},
      )
      if not user_df.empty:
        st.session_state.authenticated = True
        st.session_state.username = user_df.iloc[0]["username"]
        st.session_state.user_role = user_df.iloc[0]["role"]
        st.success("Login successful!")
        st.rerun()
      else:
        st.error("Invalid username or password.")


if not st.session_state.authenticated:
  login()
  st.stop()

# ---------------------------------------------------------
# HORIZONTAL TOP MENU & SIDEBAR SETTINGS
# ---------------------------------------------------------
st.markdown(
    f"**Logged in as:** `{st.session_state.username}`"
    f" ({st.session_state.user_role})"
)

# Horizontal Main Navigation Tabs
main_tab = st.radio(
    "",
    ["📊 Dashboard & Coverage", "💱 Daily EX Rates", "🏦 Bank Dues & Cash"],
    horizontal=True,
)

# Left Sidebar dedicated strictly to Settings (Managers only)
st.sidebar.title("⚙️ System Settings")

if st.session_state.user_role == "Manager":
  settings_menu = st.sidebar.radio(
      "Manage Configurations",
      [
          "Account Master",
          "Business Units (BU)",
          "Banks",
          "FX Currencies",
          "User Management",
      ],
  )
else:
  st.sidebar.info("🔒 Settings access is restricted to Manager users.")
  settings_menu = None

if st.sidebar.button("Logout"):
  st.session_state.authenticated = False
  st.session_state.user_role = None
  st.session_state.username = None
  st.rerun()

# ---------------------------------------------------------
# SETTINGS PAGE CONTENT (Left Sidebar Navigation)
# ---------------------------------------------------------
if settings_menu:
  st.title(f"⚙️ Settings: {settings_menu}")

  if settings_menu == "User Management":
    st.subheader("Manage System Access")
    with st.form("add_user"):
      new_u = st.text_input("New Username")
      new_p = st.text_input("New Password", type="password")
      new_r = st.selectbox("Role", ["Read-Only", "Read/Write", "Manager"])
      if st.form_submit_button("Create User"):
        if new_u and new_p:
          with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (username, password_hash, role) VALUES"
                    " (:u, :p, :r) ON CONFLICT DO NOTHING"
                ),
                {"u": new_u, "p": hash_password(new_p), "r": new_r},
            )
            conn.commit()
          st.success(f"User {new_u} created!")
          st.rerun()

    st.markdown("---")
    users_df = pd.read_sql("SELECT id, username, role FROM users", engine)
    st.dataframe(users_df, use_container_width=True)

  elif settings_menu == "Business Units (BU)":
    st.subheader("Define Business Units")
    with st.form("add_bu"):
      bu_name = st.text_input("BU Name")
      if st.form_submit_button("Add BU"):
        if bu_name:
          with engine.connect() as conn:
            conn.execute(
                text("INSERT INTO bus (name) VALUES (:n) ON CONFLICT DO NOTHING"),
                {"n": bu_name},
            )
            conn.commit()
          st.success("BU added successfully!")
          st.rerun()
    bu_df = pd.read_sql("SELECT * FROM bus", engine)
    st.dataframe(bu_df, use_container_width=True)

  elif settings_menu == "Banks":
    st.subheader("Define Partner Banks")
    with st.form("add_bank"):
      bs = st.text_input("Bank Short Name (e.g. CIB)")
      bn = st.text_input("Full Bank Name")
      if st.form_submit_button("Add Bank"):
        if bs and bn:
          with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO banks (short_name, full_name) VALUES (:s, :f)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"s": bs, "f": bn},
            )
            conn.commit()
          st.success("Bank registered successfully!")
          st.rerun()
    banks_df = pd.read_sql("SELECT * FROM banks", engine)
    st.dataframe(banks_df, use_container_width=True)

  elif settings_menu == "FX Currencies":
    st.subheader("FX Currencies List")
    with st.form("add_curr"):
      code = st.text_input("Currency Code (e.g. CAD)").upper()
      if st.form_submit_button("Add Currency"):
        if code:
          with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO currencies (code) VALUES (:c) ON CONFLICT DO"
                    " NOTHING"
                ),
                {"c": code},
            )
            conn.commit()
          st.success("Currency added!")
          st.rerun()
    curr_df = pd.read_sql("SELECT * FROM currencies", engine)
    st.dataframe(curr_df, use_container_width=True)

  elif settings_menu == "Account Master":
    st.subheader("Register Master Accounts")
    bus = pd.read_sql("SELECT name FROM bus", engine)["name"].tolist()
    banks = pd.read_sql("SELECT short_name, full_name FROM banks", engine)
    currs = pd.read_sql("SELECT code FROM currencies", engine)["code"].tolist()

    with st.form("add_acc"):
      c1, c2 = st.columns(2)
      selected_bu = c1.selectbox(
          "Business Unit", bus if bus else ["Default BU"]
      )
      dept = c2.text_input("Department")

      c3, c4 = st.columns(2)
      bank_choice = c3.selectbox(
          "Bank",
          banks["short_name"].tolist()
          if not banks.empty
          else ["Default Bank"],
      )
      acc_num = c4.text_input("Account Number")

      c5, c6 = st.columns(2)
      acc_name = c5.text_input("Account Name")
      curr = c6.selectbox("Currency", currs if currs else ["USD"])

      if st.form_submit_button("Save Account"):
        fn = (
            banks[banks["short_name"] == bank_choice]["full_name"].values[0]
            if not banks.empty
            else bank_choice
        )
        with engine.connect() as conn:
          conn.execute(
              text("""
                        INSERT INTO master_accounts (bu, department, bank_shortname, bank_name, account_number, account_name, currency)
                        VALUES (:bu, :dept, :bs, :bn, :an, :ana, :curr)
                    """),
              {
                  "bu": selected_bu,
                  "dept": dept,
                  "bs": bank_choice,
                  "bn": fn,
                  "an": acc_num,
                  "ana": acc_name,
                  "curr": curr,
              },
          )
          conn.commit()
        st.success("Master account registered!")
        st.rerun()

  st.stop()  # Halt execution when viewing Settings so main dashboard doesn't overlap

# ---------------------------------------------------------
# MAIN HORIZONTAL MENU PAGES
# ---------------------------------------------------------
if "Dashboard" in main_tab:
  st.title("📊 Treasury Coverage & Liquidity Dashboard")
  cash_df = pd.read_sql(
      "SELECT SUM(cash_balance) as total_cash FROM daily_cash_positions WHERE"
      " position_date = CURRENT_DATE",
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
        f"⚠️ Liquidity Alert: Bank Dues exceed available Cash in Hand by"
        f" ${abs(gap):,.2f}!"
    )
  else:
    st.success("✅ Cash position is sufficient to cover active bank dues.")

elif "Daily EX Rates" in main_tab:
  st.title("💱 Foreign Exchange Rate Management")
  all_currs = pd.read_sql("SELECT code FROM currencies", engine)["code"].tolist()

  if st.session_state.user_role in ["Read/Write", "Manager"]:
    st.subheader("Log Daily Rate")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.5])
    r_date = c1.date_input("Date")
    from_c = c2.selectbox(
        "From",
        all_currs,
        index=all_currs.index("AED") if "AED" in all_currs else 0,
    )
    to_opts = [c for c in all_currs if c != from_c]
    to_c = c3.selectbox(
        "To",
        to_opts,
        index=to_opts.index("SDG") if "SDG" in to_opts else 0,
    )
    r_val = c4.number_input("Rate", value=0.0000, format="%.4f", step=0.0001)
    pair = f"{from_c}/{to_c}"

    if st.button("Record Rate"):
      if r_val > 0:
        with engine.connect() as conn:
          conn.execute(
              text("""
                        INSERT INTO exchange_rates (rate_date, currency_pair, rate)
                        VALUES (:d, :p, :r)
                        ON CONFLICT (rate_date, currency_pair) DO UPDATE SET rate = EXCLUDED.rate
                    """),
              {"d": r_date, "p": pair, "r": r_val},
          )
          conn.commit()
        st.success("Rate saved!")
        st.rerun()

  st.markdown("---")
  st.subheader("Rate Trends")
  pairs = pd.read_sql(
      "SELECT DISTINCT currency_pair FROM exchange_rates", engine
  )
  if not pairs.empty:
    sel_pair = st.selectbox("Select Pair", pairs["currency_pair"].tolist())
    rates_df = pd.read_sql(
        text(
            "SELECT * FROM exchange_rates WHERE currency_pair = :p ORDER BY"
            " rate_date ASC"
        ),
        engine,
        params={"p": sel_pair},
    )
    if not rates_df.empty:
      fig = px.line(
          rates_df, x="rate_date", y="rate", title=f"{sel_pair} Movement"
      )
      st.plotly_chart(fig, use_container_width=True)

elif "Bank Dues & Cash" in main_tab:
  st.title("🏦 Bank Dues & Daily Cash Positions")
  acc_df = pd.read_sql(
      "SELECT id, bank_shortname, account_number, currency FROM"
      " master_accounts",
      engine,
  )
  acc_opts = (
      {
          f"{r['bank_shortname']} - {r['account_number']} ({r['currency']})": (
              r["id"]
          )
          for _, r in acc_df.iterrows()
      }
      if not acc_df.empty
      else {}
  )

  if st.session_state.user_role in ["Read/Write", "Manager"]:
    t1, t2 = st.tabs(["Register Bank Due", "Log Cash Position"])
    with t1:
      if acc_opts:
        with st.form("due_f"):
          choice = st.selectbox("Account", list(acc_opts.keys()))
          d_date = st.date_input("Due Date")
          fac = st.text_input("Facility Type")
          amt = st.number_input("Amount", min_value=0.0)
          if st.form_submit_button("Save Due"):
            with engine.connect() as conn:
              conn.execute(
                  text(
                      "INSERT INTO bank_dues (account_id, due_date,"
                      " facility_type, amount) VALUES (:a, :d, :f, :amt)"
                  ),
                  {
                      "a": acc_opts[choice],
                      "d": d_date,
                      "f": fac,
                      "amt": amt,
                  },
              )
              conn.commit()
            st.success("Bank due saved!")
    with t2:
      if acc_opts:
        with st.form("cash_f"):
          p_date = st.date_input("Position Date")
          choice = st.selectbox("Account", list(acc_opts.keys()), key="cash_a")
          bal = st.number_input("Cash Balance", min_value=0.0)
          if st.form_submit_button("Record Cash"):
            with engine.connect() as conn:
              conn.execute(
                  text("""
                                INSERT INTO daily_cash_positions (position_date, account_id, cash_balance)
                                VALUES (:d, :a, :c)
                                ON CONFLICT (position_date, account_id) DO UPDATE SET cash_balance = EXCLUDED.cash_balance
                            """),
                  {"d": p_date, "a": acc_opts[choice], "c": bal},
              )
              conn.commit()
            st.success("Cash position recorded!")
  else:
    st.info("🔒 Read-Only mode active. Entry forms are disabled.")
