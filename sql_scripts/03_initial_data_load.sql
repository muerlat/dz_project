-- ============================================
-- ЗАПОЛНЕНИЕ ТАБЛИЦ НАЧАЛЬНЫМИ ДАННЫМИ
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

-- Проверка загрузки данных
-- ============================================

SELECT 'DWH_DIM_CARDS_HIST' as table_name, COUNT(*) as count FROM dwh.DWH_DIM_CARDS_HIST
UNION ALL
SELECT 'DWH_DIM_ACCOUNTS_HIST', COUNT(*) FROM dwh.DWH_DIM_ACCOUNTS_HIST
UNION ALL
SELECT 'DWH_DIM_CLIENTS_HIST', COUNT(*) FROM dwh.DWH_DIM_CLIENTS_HIST;
