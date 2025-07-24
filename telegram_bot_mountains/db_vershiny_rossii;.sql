CREATE TABLE news (
    id SERIAL PRIMARY KEY,
    telegram_url TEXT NOT NULL UNIQUE, -- <<< ЭТОТ 'UNIQUE' КРАЙНЕ ВАЖЕН!
    news_type TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);