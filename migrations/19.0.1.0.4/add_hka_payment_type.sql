-- Add hka_payment_type column to account_payment_method_line table
-- This migration ensures the field exists for Odoo 19 compatibility

ALTER TABLE account_payment_method_line 
ADD COLUMN IF NOT EXISTS hka_payment_type VARCHAR(2);

-- Set default values for existing records that don't have hka_payment_type set
UPDATE account_payment_method_line 
SET hka_payment_type = '99' 
WHERE hka_payment_type IS NULL;
