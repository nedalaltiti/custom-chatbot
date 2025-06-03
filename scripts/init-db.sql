-- PostgreSQL initialization script for HR Teams Bot
-- This script is run when the PostgreSQL container starts for the first time

-- Create the database if it doesn't exist (though POSTGRES_DB will handle this)
-- CREATE DATABASE hrbot;

-- Create the hrbot user if it doesn't exist (though POSTGRES_USER will handle this)
-- CREATE USER hrbot WITH PASSWORD 'hrbot123';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE hrbot TO hrbot;

-- Connect to the hrbot database
\c hrbot;

-- Create necessary extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO hrbot;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO hrbot;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO hrbot;

-- Print success message
SELECT 'HR Teams Bot database initialized successfully!' AS status; 