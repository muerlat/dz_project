-- ============================================
-- СОЗДАНИЕ ТАБЛИЦ
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
