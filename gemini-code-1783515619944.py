-- 1. Master Orders Table
CREATE TABLE IF NOT EXISTS master_orders (
    po_number TEXT PRIMARY KEY,
    supplier_name TEXT,
    bu_id TEXT,
    order_date DATE,
    total_po_value REAL,
    currency TEXT DEFAULT 'USD',
    status TEXT DEFAULT 'Open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Shipments Table (Linked via po_number)
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
);
