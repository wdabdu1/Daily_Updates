import hashlib
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# Database setup (Replace with your database URL variable/string)
DATABASE_URL = st.secrets.get("DATABASE_URL", "postgresql://...")
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

            -- Directly patch missing columns if an old table exists
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
            
            -- Seed Default Manager User
            INSERT INTO users (username, password_hash, role)
            VALUES ('admin', :default_pass, 'Manager')
            ON CONFLICT (username) DO NOTHING;
            
            INSERT INTO currencies (code) 
            VALUES ('USD'), ('EUR'), ('EGP'), ('GBP'), ('SAR'), ('AED'), ('SDG')
            ON CONFLICT DO NOTHING;
        """),
        {"default_pass": hash_password("admin123")},
    )
    conn.commit()


# Initialize database schema before executing login check
init_db()


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


if __name__ == "__main__":
  if not st.session_state.get("authenticated", False):
    login()
  else:
    st.write(f"Welcome, {st.session_state.username}!")
