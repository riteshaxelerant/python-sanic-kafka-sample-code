-- Create database 
CREATE DATABASE order_service_db;



-- Create the order_service_db schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS order_service_db;

-- Switch to the order_service_db schema
SET search_path TO order_service_db;

-- select database using command \c order_service_db
-- Create the order_status_enum ENUM type
CREATE TYPE ORDER_STATUS AS ENUM (
    'Pending',
    'Paid',
    'Failed'
);

-- set uuid autogenerate unique ID 
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create the orders table
CREATE TABLE IF NOT EXISTS orders (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID DEFAULT NULL,
    total_price DECIMAL,
    status ORDER_STATUS DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

-- Create a trigger function to update the 'updated_at' timestamp on every update
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create a trigger to call the function when a row is updated
CREATE TRIGGER update_orders_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();

-- Create the order_items table
CREATE TABLE IF NOT EXISTS order_items (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    order_id UUID REFERENCES orders(id),
    product_id UUID DEFAULT NULL,
    quantity INTEGER,
    price DECIMAL
);
-- Create the registered_users table
CREATE TABLE IF NOT EXISTS order_service_db.registered_users
(
    id uuid NOT NULL DEFAULT order_service_db.uuid_generate_v4(),
    user_id uuid,        
    CONSTRAINT registered_users_pkey PRIMARY KEY (id)
);