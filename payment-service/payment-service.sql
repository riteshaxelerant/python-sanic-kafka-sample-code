-- Create database 
CREATE DATABASE payment_service_db;

-- Create the payment_service_db schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS payment_service_db;

-- Switch to the payment_service_db schema
SET search_path TO payment_service_db;

-- set uuid autogenerate unique ID 
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create the orders table
CREATE TABLE IF NOT EXISTS payments (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    order_id UUID DEFAULT NULL,
    amount DECIMAL,
    status TEXT,
    payment_gateway_response TEXT,
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
CREATE TRIGGER update_payments_updated_at
BEFORE UPDATE ON payments
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();