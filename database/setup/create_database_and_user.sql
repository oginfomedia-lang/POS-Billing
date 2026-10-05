-- Creates the pos_app login, the live database (pos_db) and the test database (pos_test).
--
-- Run once as the PostgreSQL superuser, passing the app password:
--   "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -v app_password=YOUR_PASSWORD -f database/setup/create_database_and_user.sql
--
-- Use the same password in DATABASE_URL / TEST_DATABASE_URL in backend/.env.

CREATE ROLE pos_app WITH LOGIN PASSWORD :'app_password';

CREATE DATABASE pos_db   OWNER pos_app ENCODING 'UTF8' TEMPLATE template0;
CREATE DATABASE pos_test OWNER pos_app ENCODING 'UTF8' TEMPLATE template0;
