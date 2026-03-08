-- ============================================
-- ПОЛНОЕ ПЕРЕСОЗДАНИЕ ВСЕХ ТАБЛИЦ
-- ============================================

-- Удаляем исторические таблицы
DROP TABLE IF EXISTS dwh.DWH_DIM_CARDS_HIST CASCADE;
DROP TABLE IF EXISTS dwh.DWH_DIM_ACCOUNTS_HIST CASCADE;
DROP TABLE IF EXISTS dwh.DWH_DIM_CLIENTS_HIST CASCADE;
DROP TABLE IF EXISTS dwh.DWH_DIM_TERMINALS_HIST CASCADE;
DROP TABLE IF EXISTS dwh.DWH_FACT_TRANSACTIONS CASCADE;
DROP TABLE IF EXISTS dwh.DWH_FACT_PASSPORT_BLACKLIST CASCADE;
DROP TABLE IF EXISTS dwh.REP_FRAUD CASCADE;
DROP TABLE IF EXISTS dwh.META_LOAD_HISTORY CASCADE;
DROP TABLE IF EXISTS dwh.STG_TRANSACTIONS CASCADE;
DROP TABLE IF EXISTS dwh.STG_TERMINALS CASCADE;
DROP TABLE IF EXISTS dwh.STG_PASSPORT_BLACKLIST CASCADE;

-- ============================================
-- 1. Таблицы измерений SCD2
-- ============================================

-- Таблица для терминалов (SCD2)
CREATE TABLE dwh.DWH_DIM_TERMINALS_HIST (
    terminal_id VARCHAR(128),
    terminal_type VARCHAR(128),
    terminal_city VARCHAR(128),
    terminal_address VARCHAR(256),
    effective_from TIMESTAMP,
    effective_to TIMESTAMP,
    deleted_flg BOOLEAN DEFAULT FALSE
);

-- Таблица для карт (SCD2)
CREATE TABLE dwh.DWH_DIM_CARDS_HIST (
    card_num VARCHAR(128),
    account_num VARCHAR(128),
    effective_from TIMESTAMP,
    effective_to TIMESTAMP,
    deleted_flg BOOLEAN DEFAULT FALSE
);

-- Таблица для счетов (SCD2)
CREATE TABLE dwh.DWH_DIM_ACCOUNTS_HIST (
    account_num VARCHAR(128),
    valid_to DATE,
    client_id VARCHAR(128),
    effective_from TIMESTAMP,
    effective_to TIMESTAMP,
    deleted_flg BOOLEAN DEFAULT FALSE
);

-- Таблица для клиентов (SCD2)
CREATE TABLE dwh.DWH_DIM_CLIENTS_HIST (
    client_id VARCHAR(128),
    last_name VARCHAR(128),
    first_name VARCHAR(128),
    patronymic VARCHAR(128),
    date_of_birth DATE,
    passport_num VARCHAR(128),
    passport_valid_to DATE,
    phone VARCHAR(128),
    effective_from TIMESTAMP,
    effective_to TIMESTAMP,
    deleted_flg BOOLEAN DEFAULT FALSE
);

-- ============================================
-- 2. Staging таблицы
-- ============================================

CREATE TABLE dwh.STG_TRANSACTIONS (
    transaction_id VARCHAR(128),
    transaction_date TIMESTAMP,
    amount DECIMAL(15,2),
    card_num VARCHAR(128),
    oper_type VARCHAR(128),
    oper_result VARCHAR(128),
    terminal VARCHAR(128)
);

CREATE TABLE dwh.STG_TERMINALS (
    terminal_id VARCHAR(128),
    terminal_type VARCHAR(128),
    terminal_city VARCHAR(128),
    terminal_address VARCHAR(256)
);

CREATE TABLE dwh.STG_PASSPORT_BLACKLIST (
    entry_dt DATE,
    passport_num VARCHAR(128)
);

-- ============================================
-- 3. Фактовые таблицы
-- ============================================

CREATE TABLE dwh.DWH_FACT_TRANSACTIONS (
    transaction_id VARCHAR(128),
    transaction_date TIMESTAMP,
    amount DECIMAL(15,2),
    card_num VARCHAR(128),
    oper_type VARCHAR(128),
    oper_result VARCHAR(128),
    terminal_id VARCHAR(128)
);

CREATE TABLE dwh.DWH_FACT_PASSPORT_BLACKLIST (
    entry_dt DATE,
    passport_num VARCHAR(128)
);

-- ============================================
-- 4. Отчетная таблица
-- ============================================

CREATE TABLE dwh.REP_FRAUD (
    event_dt TIMESTAMP,
    passport VARCHAR(128),
    fio VARCHAR(256),
    phone VARCHAR(128),
    event_type VARCHAR(256),
    report_dt TIMESTAMP
);

-- ============================================
-- 5. Таблица метаданных
-- ============================================

CREATE TABLE dwh.META_LOAD_HISTORY (
    file_name VARCHAR(256),
    file_date DATE,
    load_dt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50),
    rows_loaded INTEGER,
    error_message TEXT
);

-- ============================================
-- 6. ЗАГРУЗКА ДАННЫХ ИЗ BANK
-- ============================================

-- Загружаем карты
INSERT INTO dwh.DWH_DIM_CARDS_HIST (
    card_num, 
    account_num, 
    effective_from, 
    effective_to, 
    deleted_flg
)
SELECT 
    card_num,
    account,
    '1900-01-01'::TIMESTAMP,
    NULL,
    FALSE
FROM dwh.cards;

-- Загружаем счета
INSERT INTO dwh.DWH_DIM_ACCOUNTS_HIST (
    account_num, 
    valid_to, 
    client_id, 
    effective_from, 
    effective_to, 
    deleted_flg
)
SELECT 
    account,
    valid_to,
    client,
    '1900-01-01'::TIMESTAMP,
    NULL,
    FALSE
FROM dwh.accounts;

-- Загружаем клиентов
INSERT INTO dwh.DWH_DIM_CLIENTS_HIST (
    client_id, 
    last_name, 
    first_name, 
    patronymic, 
    date_of_birth, 
    passport_num, 
    passport_valid_to, 
    phone, 
    effective_from, 
    effective_to, 
    deleted_flg
)
SELECT 
    client_id,
    last_name,
    first_name,
    patronymic,
    date_of_birth,
    passport_num,
    passport_valid_to,
    phone,
    '1900-01-01'::TIMESTAMP,
    NULL,
    FALSE
FROM dwh.clients;

-- ============================================
-- 7. ПРОВЕРКА
-- ============================================

SELECT 'DWH_DIM_CARDS_HIST' as table_name, COUNT(*) as count FROM dwh.DWH_DIM_CARDS_HIST
UNION ALL
SELECT 'DWH_DIM_ACCOUNTS_HIST', COUNT(*) FROM dwh.DWH_DIM_ACCOUNTS_HIST
UNION ALL
SELECT 'DWH_DIM_CLIENTS_HIST', COUNT(*) FROM dwh.DWH_DIM_CLIENTS_HIST;
