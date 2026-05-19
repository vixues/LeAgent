CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    amount NUMERIC(12,2),
    category VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
INSERT INTO expenses (amount, category) VALUES (100.00, 'travel'), (50.00, 'meals');
