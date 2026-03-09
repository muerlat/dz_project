def detect_fraud(conn, report_dt, target_date):
    """Выявляет мошеннические операции по 4 правилам"""
    try:
        print(f"\nПоиск мошеннических операций за {target_date}")
        
        cur = conn.cursor()
        
        # Очищаем отчет за эту дату
        cur.execute("DELETE FROM dwh.REP_FRAUD WHERE DATE(event_dt) = %s", (target_date,))
        
        # Правило 1: Просроченный или заблокированный паспорт
        cur.execute("""
            INSERT INTO dwh.REP_FRAUD (event_dt, passport, fio, phone, event_type, report_dt)
            SELECT DISTINCT
                f.transaction_date,
                cl.passport_num,
                cl.last_name || ' ' || cl.first_name || ' ' || COALESCE(cl.patronymic, '') AS fio,
                cl.phone,
                'Просроченный или заблокированный паспорт',
                %s
            FROM dwh.DWH_FACT_TRANSACTIONS f
            LEFT JOIN dwh.DWH_DIM_CARDS_HIST c 
                ON f.card_num = c.card_num 
                AND f.transaction_date >= c.effective_from 
                AND (c.effective_to IS NULL OR f.transaction_date < c.effective_to)
            LEFT JOIN dwh.DWH_DIM_ACCOUNTS_HIST a 
                ON c.account_num = a.account_num 
                AND f.transaction_date >= a.effective_from 
                AND (a.effective_to IS NULL OR f.transaction_date < a.effective_to)
            LEFT JOIN dwh.DWH_DIM_CLIENTS_HIST cl 
                ON a.client_id = cl.client_id 
                AND f.transaction_date >= cl.effective_from 
                AND (cl.effective_to IS NULL OR f.transaction_date < cl.effective_to)
            WHERE DATE(f.transaction_date) = %s
            AND (
                cl.passport_num IN (
                    SELECT passport_num FROM dwh.DWH_FACT_PASSPORT_BLACKLIST
                )
                OR (cl.passport_valid_to IS NOT NULL AND cl.passport_valid_to < DATE(f.transaction_date))
            );
        """, (report_dt, target_date))
        
        rule1_count = cur.rowcount
        
        # Правило 2: Недействующий договор
        cur.execute("""
            INSERT INTO dwh.REP_FRAUD (event_dt, passport, fio, phone, event_type, report_dt)
            SELECT DISTINCT
                f.transaction_date,
                cl.passport_num,
                cl.last_name || ' ' || cl.first_name || ' ' || COALESCE(cl.patronymic, '') AS fio,
                cl.phone,
                'Недействующий договор',
                %s
            FROM dwh.DWH_FACT_TRANSACTIONS f
            LEFT JOIN dwh.DWH_DIM_CARDS_HIST c 
                ON f.card_num = c.card_num 
                AND f.transaction_date >= c.effective_from 
                AND (c.effective_to IS NULL OR f.transaction_date < c.effective_to)
            LEFT JOIN dwh.DWH_DIM_ACCOUNTS_HIST a 
                ON c.account_num = a.account_num 
                AND f.transaction_date >= a.effective_from 
                AND (a.effective_to IS NULL OR f.transaction_date < a.effective_to)
            LEFT JOIN dwh.DWH_DIM_CLIENTS_HIST cl 
                ON a.client_id = cl.client_id 
                AND f.transaction_date >= cl.effective_from 
                AND (cl.effective_to IS NULL OR f.transaction_date < cl.effective_to)
            WHERE DATE(f.transaction_date) = %s
            AND a.valid_to < DATE(f.transaction_date);
        """, (report_dt, target_date))
        
        rule2_count = cur.rowcount
        
        # Правило 3: Операции в разных городах за 1 час
        cur.execute("""
            INSERT INTO dwh.REP_FRAUD (event_dt, passport, fio, phone, event_type, report_dt)
            WITH client_transactions AS (
                SELECT 
                    f.transaction_id,
                    f.transaction_date,
                    cl.passport_num,
                    cl.last_name || ' ' || cl.first_name || ' ' || COALESCE(cl.patronymic, '') AS fio,
                    cl.phone,
                    t.terminal_city
                FROM dwh.DWH_FACT_TRANSACTIONS f
                LEFT JOIN dwh.DWH_DIM_CARDS_HIST c 
                    ON f.card_num = c.card_num 
                    AND f.transaction_date >= c.effective_from 
                    AND (c.effective_to IS NULL OR f.transaction_date < c.effective_to)
                LEFT JOIN dwh.DWH_DIM_ACCOUNTS_HIST a 
                    ON c.account_num = a.account_num 
                    AND f.transaction_date >= a.effective_from 
                    AND (a.effective_to IS NULL OR f.transaction_date < a.effective_to)
                LEFT JOIN dwh.DWH_DIM_CLIENTS_HIST cl 
                    ON a.client_id = cl.client_id 
                    AND f.transaction_date >= cl.effective_from 
                    AND (cl.effective_to IS NULL OR f.transaction_date < cl.effective_to)
                LEFT JOIN dwh.DWH_DIM_TERMINALS_HIST t 
                    ON f.terminal_id = t.terminal_id 
                    AND f.transaction_date >= t.effective_from 
                    AND (t.effective_to IS NULL OR f.transaction_date < t.effective_to)
                WHERE DATE(f.transaction_date) = %s
            ),
            diff_cities AS (
                SELECT 
                    v2.transaction_date as event_dt,
                    v1.passport_num,
                    v1.fio,
                    v1.phone
                FROM client_transactions v1
                JOIN client_transactions v2 
                    ON v1.passport_num = v2.passport_num
                    AND v1.transaction_id != v2.transaction_id
                    AND v1.terminal_city != v2.terminal_city
                    AND ABS(EXTRACT(EPOCH FROM (v2.transaction_date - v1.transaction_date))) < 3600
                WHERE v1.terminal_city IS NOT NULL 
                    AND v2.terminal_city IS NOT NULL
                    AND v1.passport_num IS NOT NULL
            )
            SELECT DISTINCT event_dt, passport_num, fio, phone, 
                   'Операции в разных городах за 1 час',
                   %s
            FROM diff_cities;
        """, (target_date, report_dt))
        
        rule3_count = cur.rowcount
        
        # Правило 4: Подбор суммы
        cur.execute("""
            INSERT INTO dwh.REP_FRAUD (event_dt, passport, fio, phone, event_type, report_dt)
            WITH ranked_transactions AS (
                SELECT 
                    f.transaction_date,
                    f.amount,
                    f.oper_result,
                    f.card_num,
                    cl.passport_num,
                    cl.last_name || ' ' || cl.first_name || ' ' || COALESCE(cl.patronymic, '') AS fio,
                    cl.phone,
                    LAG(f.amount) OVER (PARTITION BY f.card_num ORDER BY f.transaction_date) as prev_amount,
                    LAG(f.oper_result) OVER (PARTITION BY f.card_num ORDER BY f.transaction_date) as prev_result,
                    LAG(f.transaction_date) OVER (PARTITION BY f.card_num ORDER BY f.transaction_date) as prev_date,
                    COUNT(*) OVER (PARTITION BY f.card_num ORDER BY f.transaction_date 
                                   RANGE BETWEEN INTERVAL '20 minutes' PRECEDING AND CURRENT ROW) as attempts_20min
                FROM dwh.DWH_FACT_TRANSACTIONS f
                LEFT JOIN dwh.DWH_DIM_CARDS_HIST c 
                    ON f.card_num = c.card_num 
                    AND f.transaction_date >= c.effective_from 
                    AND (c.effective_to IS NULL OR f.transaction_date < c.effective_to)
                LEFT JOIN dwh.DWH_DIM_ACCOUNTS_HIST a 
                    ON c.account_num = a.account_num 
                    AND f.transaction_date >= a.effective_from 
                    AND (a.effective_to IS NULL OR f.transaction_date < a.effective_to)
                LEFT JOIN dwh.DWH_DIM_CLIENTS_HIST cl 
                    ON a.client_id = cl.client_id 
                    AND f.transaction_date >= cl.effective_from 
                    AND (cl.effective_to IS NULL OR f.transaction_date < cl.effective_to)
                WHERE DATE(f.transaction_date) = %s
            ),
            fraud_pattern AS (
                SELECT 
                    transaction_date,
                    passport_num,
                    fio,
                    phone
                FROM ranked_transactions
                WHERE oper_result = 'SUCCESS'
                    AND attempts_20min > 3
                    AND prev_result = 'REJECT'
                    AND amount < prev_amount
                    AND EXTRACT(EPOCH FROM (transaction_date - prev_date)) < 1200
                    AND passport_num IS NOT NULL
            )
            SELECT DISTINCT transaction_date, passport_num, fio, phone,
                   'Подбор суммы (успешная после 3+ отклоненных за 20 мин)',
                   %s
            FROM fraud_pattern;
        """, (target_date, report_dt))
        
        rule4_count = cur.rowcount
        
        conn.commit()
        
        print(f"\n  Результаты отчета за {target_date}:")
        print(f"    Правило 1 (просроченный паспорт): {rule1_count}")
        print(f"    Правило 2 (недействующий договор): {rule2_count}")
        print(f"    Правило 3 (разные города): {rule3_count}")
        print(f"    Правило 4 (подбор суммы): {rule4_count}")
        print(f"    ВСЕГО: {rule1_count + rule2_count + rule3_count + rule4_count}")
        
        cur.close()
        return True
        
    except Exception as e:
        print(f"  Ошибка при поиске мошенничеств: {e}")
        conn.rollback()
        return False