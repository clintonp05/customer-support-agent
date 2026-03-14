CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS customers (
    user_id VARCHAR(20) PRIMARY KEY,
    name_en VARCHAR(100) NOT NULL,
    name_ar VARCHAR(100),
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(20),
    city VARCHAR(50),
    tier VARCHAR(20) DEFAULT 'STANDARD',
    preferred_language VARCHAR(10) DEFAULT 'en',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(20) PRIMARY KEY,
    name_en VARCHAR(200) NOT NULL,
    name_ar VARCHAR(200),
    category VARCHAR(50) NOT NULL,
    subcategory VARCHAR(50),
    brand VARCHAR(100),
    price_aed DECIMAL(10,2) NOT NULL,
    warranty_months INTEGER DEFAULT 0,
    is_returnable BOOLEAN DEFAULT TRUE,
    return_window_days INTEGER DEFAULT 30,
    in_stock BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(25) PRIMARY KEY,
    user_id VARCHAR(20) NOT NULL REFERENCES customers(user_id),
    status VARCHAR(30) NOT NULL,
    total_aed DECIMAL(10,2) NOT NULL,
    item_count INTEGER NOT NULL,
    placed_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW(),
    shipping_address JSONB,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id VARCHAR(25) NOT NULL REFERENCES orders(order_id),
    product_id VARCHAR(20) NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price_aed DECIMAL(10,2) NOT NULL,
    total_price_aed DECIMAL(10,2) NOT NULL,
    item_status VARCHAR(30),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id VARCHAR(25) PRIMARY KEY,
    order_id VARCHAR(25) NOT NULL REFERENCES orders(order_id),
    user_id VARCHAR(20) NOT NULL REFERENCES customers(user_id),
    amount_aed DECIMAL(10,2) NOT NULL,
    method VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL,
    failure_reason VARCHAR(100),
    transaction_ref VARCHAR(50),
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id VARCHAR(25) PRIMARY KEY,
    order_id VARCHAR(25) NOT NULL REFERENCES orders(order_id),
    user_id VARCHAR(20) NOT NULL REFERENCES customers(user_id),
    carrier VARCHAR(50),
    tracking_number VARCHAR(50),
    status VARCHAR(30) NOT NULL,
    estimated_date DATE,
    delivered_at TIMESTAMP,
    delivery_address JSONB,
    delivery_notes TEXT,
    failed_attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS refunds (
    refund_id VARCHAR(25) PRIMARY KEY,
    order_id VARCHAR(25) NOT NULL REFERENCES orders(order_id),
    user_id VARCHAR(20) NOT NULL REFERENCES customers(user_id),
    payment_id VARCHAR(25) REFERENCES payments(payment_id),
    amount_aed DECIMAL(10,2) NOT NULL,
    reason VARCHAR(100),
    status VARCHAR(20) NOT NULL,
    rejection_reason VARCHAR(200),
    order_age_days INTEGER,
    refund_method VARCHAR(30),
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS warranties (
    warranty_id VARCHAR(25) PRIMARY KEY,
    order_id VARCHAR(25) NOT NULL REFERENCES orders(order_id),
    user_id VARCHAR(20) NOT NULL REFERENCES customers(user_id),
    product_id VARCHAR(20) NOT NULL REFERENCES products(product_id),
    warranty_type VARCHAR(30),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    claim_count INTEGER DEFAULT 0,
    last_claim_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_deliveries_order_id ON deliveries(order_id);
CREATE INDEX IF NOT EXISTS idx_refunds_order_id ON refunds(order_id);
