import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    dbname="freelance_bot",
    user="postgres",
    password="5757",
    host="localhost"
)
cursor = conn.cursor(cursor_factory=RealDictCursor)

def update_nickname(telegram_id, new_username):
    cursor.execute("UPDATE users SET username = %s WHERE telegram_id = %s", (new_username, telegram_id))
    conn.commit()

def update_bio(telegram_id, new_bio):
    cursor.execute("UPDATE profiles SET bio = %s WHERE telegram_id = %s", (new_bio, telegram_id))
    conn.commit()

def update_skills(telegram_id, new_skills):
    cursor.execute("UPDATE profiles SET skills = %s WHERE telegram_id = %s", (new_skills, telegram_id))
    conn.commit()

def add_user(telegram_id, username):
    print(f"Добавляю пользователя: {telegram_id}, {username}")
    cursor.execute("""
        INSERT INTO users (telegram_id, username, telegram_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (telegram_id) DO UPDATE
        SET username = EXCLUDED.username
    """, (telegram_id, username, username))
    conn.commit()

def create_future_order(customer_id: int, title: str, description: str, skills: str, payment: float, executor_id: int = None) -> int:
    """Создание заказа с возможностью указания исполнителя"""
    try:
        if executor_id:
            # Создаем заказ с указанным исполнителем (личный заказ)
            cursor.execute("""
                INSERT INTO future_orders 
                (customer_id, title, description, skills_required, payment_amount, executor_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending_executor')
                RETURNING id
            """, (customer_id, title, description, skills, payment, executor_id))
        else:
            # Создаем публичный заказ (без указания исполнителя)
            cursor.execute("""
                INSERT INTO future_orders 
                (customer_id, title, description, skills_required, payment_amount, status)
                VALUES (%s, %s, %s, %s, %s, 'available')
                RETURNING id
            """, (customer_id, title, description, skills, payment))
        
        order_id = cursor.fetchone()['id']
        conn.commit()
        return order_id
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при создании заказа: {e}")
        raise

# db.py
def get_user_profile(telegram_id):
    cursor.execute("SELECT username FROM users WHERE telegram_id = %s", (telegram_id,))
    return cursor.fetchone()  # Возвращает словарь, т.к. используется RealDictCursor

def is_banned(user_id: int) -> bool:
    cursor.execute("SELECT 1 FROM banned_users WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    return result is not None

def ban_user(user_id: int):
    cursor.execute("INSERT INTO banned_users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
    conn.commit()

def unban_user(user_id: int):
    cursor.execute("DELETE FROM banned_users WHERE user_id = %s", (user_id,))
    conn.commit()

def get_executor_profile(user_id: int):
    """Безопасно получает профиль исполнителя"""
    try:
        # 1. Проверяем, является ли пользователь исполнителем
        cursor.execute("""
            SELECT username, is_executor 
            FROM users 
            WHERE telegram_id = %s
        """, (user_id,))
        user = cursor.fetchone()
        
        if not user or not user['is_executor']:
            return None
        
        # 2. Получаем существующий профиль
        cursor.execute("""
            SELECT bio, skills 
            FROM profiles 
            WHERE telegram_id = %s
        """, (user_id,))
        profile = cursor.fetchone()
        
        # 3. Если профиля нет - создаем пустой
        if not profile:
            cursor.execute("""
                INSERT INTO profiles (telegram_id, bio, skills)
                VALUES (%s, '', '')
                RETURNING bio, skills
            """, (user_id,))
            profile = cursor.fetchone()
            conn.commit()
        
        return (user['username'], profile['bio'], profile['skills'])
        
    except Exception as e:
        print(f"Ошибка при получении профиля: {e}")
        conn.rollback()
        return None
        
    except Exception as e:
        print(f"Ошибка при получении профиля исполнителя: {e}")
        return (user['username'], '', '') if user else None

def get_executor_profiles_paginated(limit=5, offset=0):
    cursor.execute("""
        SELECT u.telegram_id, u.username, u.rating, p.bio, p.skills
        FROM users u
        JOIN profiles p ON u.telegram_id = p.telegram_id
        WHERE u.is_executor = TRUE
        ORDER BY u.rating DESC
        LIMIT %s OFFSET %s
    """, (limit, offset))
    return cursor.fetchall()

def get_order(order_id: int):
    """Получает информацию о заказе по ID"""
    cursor.execute("""
        SELECT o.*, 
               cust.username as customer_username,
               exec.username as executor_username
        FROM orders o
        LEFT JOIN users cust ON o.customer_id = cust.telegram_id
        LEFT JOIN users exec ON o.executor_id = exec.telegram_id
        WHERE o.id = %s
    """, (order_id,))
    return cursor.fetchone()

def update_order_status(order_id: int, status: str):
    """Обновляет статус заказа"""
    cursor.execute("""
        UPDATE orders SET status = %s
        WHERE id = %s
    """, (status, order_id))
    conn.commit()

def get_order_chat_data(order_id: int):
    """Получает данные чата по ID заказа"""
    try:
        cursor.execute("""
            SELECT customer_id, executor_id, chat_id 
            FROM orders 
            WHERE id = %s
        """, (order_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Ошибка при получении данных чата: {e}")
        return None

def get_chat_participants(order_id: int):
    """Получает участников чата и chat_id"""
    try:
        cursor.execute("""
            SELECT customer_id, executor_id, chat_id
            FROM orders 
            WHERE id = %s
        """, (order_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Ошибка при получении участников чата: {e}")
        return None
    
def get_prechat_participants(chat_id: int) -> dict:
    """Получает участников чата"""
    cursor.execute(
        "SELECT customer_id, executor_id FROM chats WHERE id = %s",
        (chat_id,)
    )
    return cursor.fetchone()

def save_message_with_chat_data(order_id: int, sender_id: int, message_text: str):
    """Сохраняет сообщение и возвращает данные чата"""
    try:
        # Сохраняем сообщение
        cursor.execute("""
            INSERT INTO order_messages (order_id, sender_id, message_text)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (order_id, sender_id, message_text))
        
        message_id = cursor.fetchone()['id']
        
        # Получаем данные чата
        chat_data = get_order_chat_data(order_id)
        
        conn.commit()
        return {
            'message_id': message_id,
            'chat_data': chat_data
        }
    except Exception as e:
        print(f"Ошибка при сохранении сообщения: {e}")
        conn.rollback()
        return None
    
def get_future_order_details(order_id: int, user_id: int = None):
    """Получает информацию о будущем заказе с проверкой прав"""
    query = """
        SELECT id, customer_id, title, description, 
               skills_required, payment_amount, created_at, status
        FROM future_orders
        WHERE id = %s
    """
    params = (order_id,)
    
    cursor.execute(query, params)
    return cursor.fetchone()

def update_future_order(order_id: int, customer_id: int, title: str = None, description: str = None, 
                       skills: str = None, payment: float = None):
    """Обновляет данные будущего заказа"""
    updates = []
    params = []
    
    if title:
        updates.append("title = %s")
        params.append(title)
    if description:
        updates.append("description = %s")
        params.append(description)
    if skills:
        updates.append("skills_required = %s")
        params.append(skills)
    if payment:
        updates.append("payment_amount = %s")
        params.append(payment)
    
    if not updates:
        return False
    
    query = f"UPDATE future_orders SET {', '.join(updates)} WHERE id = %s AND customer_id = %s"
    params.extend([order_id, customer_id])
    
    cursor.execute(query, params)
    conn.commit()
    return cursor.rowcount > 0

def delete_future_order(order_id: int, customer_id: int) -> bool:
    """Удаляет будущий заказ и возвращает True при успехе"""
    try:
        cursor.execute("""
            DELETE FROM future_orders 
            WHERE id = %s AND customer_id = %s
        """, (order_id, customer_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Ошибка при удалении заказа: {e}")
        conn.rollback()
        return False

def get_available_orders_paginated(limit=5, offset=0):
    """Получает список доступных заказов с пагинацией (только публичные)"""
    cursor.execute("""
        SELECT id, title, description, skills_required, 
               payment_amount, created_at, customer_id
        FROM future_orders
        WHERE status = 'available'
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (limit, offset))
    return cursor.fetchall()

def create_order(customer_id: int, executor_id: int) -> int:
    """Создает новый заказ и возвращает его ID"""
    try:
        cursor.execute("""
            INSERT INTO orders (customer_id, executor_id, status)
            VALUES (%s, %s, 'active')
            RETURNING id
        """, (customer_id, executor_id))
        
        order_id = cursor.fetchone()['id']
        conn.commit()
        return order_id
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при создании заказа: {e}")
        raise

def get_chat_messages(chat_id: int, limit: int = 10) -> list:
    """Получает историю сообщений чата"""
    cursor.execute("""
        SELECT m.*, u.username as sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.telegram_id
        WHERE m.chat_id = %s
        ORDER BY m.created_at DESC
        LIMIT %s
    """, (chat_id, limit))
    return cursor.fetchall()

def create_confirmation_session(chat_id: int, customer_id: int, executor_id: int) -> int:
    """Создает сессию подтверждения заказа"""
    cursor.execute(
        """INSERT INTO order_confirmations 
        (chat_id, customer_id, executor_id) 
        VALUES (%s, %s, %s) RETURNING id""",
        (chat_id, customer_id, executor_id)
    )
    confirmation_id = cursor.fetchone()['id']
    conn.commit()
    return confirmation_id

def get_confirmation_status(confirmation_id: int) -> dict:
    """Получает статус подтверждения"""
    cursor.execute(
        "SELECT * FROM order_confirmations WHERE id = %s",
        (confirmation_id,)
    )
    return cursor.fetchone()

def update_confirmation(confirmation_id: int, is_customer: bool, confirmed: bool) -> bool:
    """Обновляет статус подтверждения"""
    field = 'customer_confirmed' if is_customer else 'executor_confirmed'
    cursor.execute(
        f"UPDATE order_confirmations SET {field} = %s WHERE id = %s RETURNING id",
        (confirmed, confirmation_id)
    )
    result = cursor.fetchone() is not None
    conn.commit()
    return result

def get_confirmation_status_by_chat(chat_id: int) -> dict:
    """Получает статус подтверждения по ID чата"""
    cursor.execute(
        "SELECT * FROM order_confirmations WHERE chat_id = %s",
        (chat_id,)
    )
    return cursor.fetchone()

def get_user_chats(user_id: int) -> list:
    """Получает все чаты пользователя с нужными полями"""
    cursor.execute("""
        SELECT 
            c.id,
            c.customer_id,
            c.executor_id,
            oc.id as confirmation_id,
            oc.customer_confirmed,
            oc.executor_confirmed,
            CASE 
                WHEN c.customer_id = %s THEN u2.username 
                ELSE u1.username 
            END as partner_username
        FROM chats c
        LEFT JOIN order_confirmations oc ON oc.chat_id = c.id
        JOIN users u1 ON c.customer_id = u1.telegram_id
        JOIN users u2 ON c.executor_id = u2.telegram_id
        WHERE c.customer_id = %s OR c.executor_id = %s
        ORDER BY c.created_at DESC
    """, (user_id, user_id, user_id))
    return cursor.fetchall()

def get_user_rating(user_id: int) -> float:
    cursor.execute("SELECT rating FROM users WHERE telegram_id = %s", (user_id,))
    return cursor.fetchone()

def get_user_reviews(user_id: int):
    """Получает 3 последних отзыва о пользователе"""
    cursor.execute("""
        SELECT comment FROM reviews 
        WHERE reviewed_id = %s AND comment IS NOT NULL
        ORDER BY created_at DESC 
        LIMIT 3
    """, (user_id,))  # Обратите внимание на запятую - создаем кортеж
    return cursor.fetchall()

def create_confirmation_request(order_id: int, action: str, initiator_id: int) -> int:
    """Создает запрос на подтверждение действия"""
    cursor.execute("""
        INSERT INTO confirmations (order_id, action, initiator_id, status)
        VALUES (%s, %s, %s, 'pending')
        RETURNING id
    """, (order_id, action, initiator_id))
    confirmation_id = cursor.fetchone()['id']
    conn.commit()
    return confirmation_id

def get_confirmation_request(confirmation_id: int):
    """Получает запрос на подтверждение"""
    cursor.execute("""
        SELECT * FROM confirmations WHERE id = %s
    """, (confirmation_id,))
    return cursor.fetchone()

def update_confirmation_request(confirmation_id: int, is_confirmed: bool) -> bool:
    """Обновляет статус подтверждения"""
    cursor.execute("""
        UPDATE confirmations 
        SET status = CASE WHEN %s THEN 'confirmed' ELSE 'rejected' END,
            updated_at = NOW()
        WHERE id = %s
        RETURNING id
    """, (is_confirmed, confirmation_id))
    result = cursor.fetchone()
    conn.commit()
    return result is not None

def delete_confirmation_request(confirmation_id: int) -> bool:
    """Удаляет запрос на подтверждение"""
    cursor.execute("""
        DELETE FROM confirmations 
        WHERE id = %s
        RETURNING id
    """, (confirmation_id,))
    result = cursor.fetchone()
    conn.commit()
    return result is not None

def respond_to_future_order(future_order_id: int, executor_id: int) -> int:
    """Создаёт новый заказ, даже если у пользователей уже есть активные заказы"""
    try:
        # 1. Получаем данные из future_orders
        cursor.execute("""
            SELECT customer_id, title, description, skills_required, payment_amount
            FROM future_orders
            WHERE id = %s AND status = 'available'
            FOR UPDATE
        """, (future_order_id,))
        
        future_order = cursor.fetchone()
        if not future_order:
            raise ValueError("Заказ не найден или уже занят")

        # 2. Создаём новый заказ (даже если уже есть активные)
        cursor.execute("""
            INSERT INTO orders (customer_id, executor_id, status, chat_id, title, description, skills_required, payment_amount)
            VALUES (%s, %s, 'active', %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            future_order['customer_id'],
            executor_id,
            future_order['customer_id'],  # chat_id = ID заказчика
            future_order['title'],
            future_order['description'],
            future_order['skills_required'],
            future_order['payment_amount']
        ))
        
        order_id = cursor.fetchone()["id"]
        
        # 3. Обновляем статус в future_orders
        cursor.execute("""
            UPDATE future_orders
            SET status = 'in_progress'
            WHERE id = %s
        """, (future_order_id,))
        
        conn.commit()
        return order_id
        
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при отклике на заказ: {e}")
        raise

def get_order_details(order_id: int, user_id: int = None):
    """Получает информацию о заказе с проверкой прав доступа"""
    query = """
        SELECT o.id, o.status, o.created_at, 
               u1.username as customer_name,
               u2.username as executor_name
        FROM orders o
        LEFT JOIN users u1 ON o.customer_id = u1.telegram_id
        LEFT JOIN users u2 ON o.executor_id = u2.telegram_id
        WHERE o.id = %s
    """
    params = (order_id,)
    
    if user_id:
        query += " AND (o.customer_id = %s OR o.executor_id = %s)"
        params += (user_id, user_id)
    
    cursor.execute(query, params)
    return cursor.fetchone()

def get_user_by_tg_id(tg_id: int) -> dict | None:
    cursor.execute("SELECT is_executor, is_customer FROM users WHERE telegram_id = %s", (tg_id,))
    row = cursor.fetchone()

    if row:
        return {"is_executor": row[0], "is_customer": row[1]}
    return None

def get_user_orders(user_id: int, limit: int = 5, offset: int = 0):
    """Получает все заказы пользователя (активные, ожидающие и предложенные)"""
    cursor.execute("""
        (
            -- Активные заказы (где пользователь исполнитель или заказчик)
            SELECT 
                o.id, 
                o.status,
                o.executor_id,
                o.customer_id, 
                o.title, 
                o.description,
                o.skills_required,
                o.payment_amount,
                o.created_at, 
                'order' as order_type,
                NULL as future_order_id
            FROM orders o
            WHERE o.customer_id = %s OR o.executor_id = %s
        )
        UNION ALL
        (
            -- Заказы, ожидающие подтверждения от этого исполнителя
            SELECT 
                fo.id, 
                fo.status,
                fo.executor_id,
                fo.customer_id, 
                fo.title, 
                fo.description,
                fo.skills_required,
                fo.payment_amount,
                fo.created_at, 
                'pending_executor' as order_type,
                fo.id as future_order_id
            FROM future_orders fo
            WHERE fo.executor_id = %s AND fo.status = 'waiting'
        )
        UNION ALL
        (
            -- Публичные заказы (для исполнителей)
            SELECT 
                fo.id, 
                fo.status,
                fo.executor_id,
                fo.customer_id, 
                fo.title,
                fo.description,
                fo.skills_required,
                fo.payment_amount,
                fo.created_at, 
                'available_order' as order_type,
                fo.id as future_order_id
            FROM future_orders fo
            WHERE fo.status = 'available' AND fo.customer_id = %s
        )
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (user_id, user_id, user_id, user_id, limit, offset))
    
    return [dict(row) for row in cursor.fetchall()]

def get_full_order_details(order_id: int):
    """Получает полные данные о заказе с именами пользователей"""
    cursor.execute("""
        SELECT 
            o.id,
            o.title,
            o.status,
            o.customer_id,
            o.executor_id,
            o.created_at,
            cu.username AS customer_username,
            ex.username AS executor_username
        FROM orders o
        LEFT JOIN users cu ON o.customer_id = cu.telegram_id
        LEFT JOIN users ex ON o.executor_id = ex.telegram_id
        WHERE o.id = %s
    """, (order_id,))
    return cursor.fetchone()

def check_profile_exists(telegram_id: int) -> bool:
    """Проверяет существование профиля"""
    cursor.execute("SELECT 1 FROM profiles WHERE telegram_id = %s", (telegram_id,))
    return cursor.fetchone() is not None

def create_empty_profile(telegram_id: int) -> bool:
    """Создает пустую анкету"""
    try:
        cursor.execute(
            "INSERT INTO profiles (telegram_id, bio, skills) VALUES (%s, '', '')",
            (telegram_id,)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при создании анкеты: {e}")
        return False

def get_order_messages(order_id: int, limit: int = 10, offset: int = 0):
    """Получает последние сообщения чата (новые внизу)"""
    try:
        cursor.execute("""
            SELECT 
                om.message_text,
                om.sent_at,
                u.username as sender_name,
                om.sender_id
            FROM order_messages om
            JOIN users u ON om.sender_id = u.telegram_id
            WHERE om.order_id = %s
            ORDER BY om.sent_at DESC
            LIMIT %s OFFSET %s
        """, (order_id, limit, offset))
        
        # Возвращаем сообщения в хронологическом порядке (новые внизу)
        messages = cursor.fetchall()
        return list(reversed(messages))  # Переворачиваем список
        
    except Exception as e:
        print(f"Ошибка при получении истории сообщений: {e}")
        return []
    
# Все функции должны быть синхронными, например:
def is_admin(telegram_id: int) -> bool:
    cursor.execute("SELECT 1 FROM admins WHERE telegram_id = %s", (telegram_id,))
    return cursor.fetchone() is not None

def get_active_reports():
    """Получает все активные жалобы (не удаленные)"""
    cursor.execute("""
        SELECT r.*, u.username as reporter_name
        FROM reports r
        JOIN users u ON r.reporter_id = u.telegram_id
        ORDER BY r.created_at DESC
    """)
    return cursor.fetchall()

def get_active_admins():
    """Получает список активных администраторов"""
    cursor.execute("""
        SELECT telegram_id, username 
        FROM admins
        ORDER BY added_at DESC
    """)
    return cursor.fetchall()

def get_report_details(report_id: int):
    """Получает полную информацию о жалобе"""
    cursor.execute("""
        SELECT r.*, u.username as reporter_name
        FROM reports r
        JOIN users u ON r.reporter_id = u.telegram_id
        WHERE r.id = %s
    """, (report_id,))
    return cursor.fetchone()

def add_admin_by_username(username: str) -> bool:
    """Добавляет администратора по username"""
    try:
        cursor.execute("""
            INSERT INTO admins (telegram_id, username)
            VALUES ((SELECT telegram_id FROM users WHERE username = %s), %s)
            ON CONFLICT (telegram_id) DO UPDATE
            SET username = EXCLUDED.username
            RETURNING telegram_id
        """, (username, username))
        conn.commit()
        return cursor.fetchone() is not None
    except Exception as e:
        print(f"Ошибка при добавлении администратора по username: {e}")
        conn.rollback()
        return False
    
def remove_admin(telegram_id: int) -> bool:
    """Удаляет администратора"""
    try:
        # Не позволяем удалить самого себя
        if is_super_admin(telegram_id):
            return False
            
        cursor.execute("""
            DELETE FROM admins
            WHERE telegram_id = %s
            RETURNING telegram_id
        """, (telegram_id,))
        conn.commit()
        return cursor.fetchone() is not None
    except Exception as e:
        print(f"Ошибка при удалении администратора: {e}")
        conn.rollback()
        return False

def add_admin_by_id(telegram_id: int) -> bool:
    """Добавляет администратора по ID"""
    try:
        cursor.execute("""
            INSERT INTO admins (telegram_id)
            VALUES (%s)
            ON CONFLICT (telegram_id) DO NOTHING
            RETURNING telegram_id
        """, (telegram_id,))
        conn.commit()
        return cursor.fetchone() is not None
    except Exception as e:
        print(f"Ошибка при добавлении администратора по ID: {e}")
        conn.rollback()
        return False

def is_super_admin(telegram_id: int) -> bool:
    """Проверяет, является ли пользователь супер-администратором"""
    # Можно добавить отдельное поле is_super_admin в таблицу admins
    # Пока просто проверяем по ID
    return telegram_id == 1007410403  # Ваш ID

def create_report(order_id: int, reporter_id: int, reason: str) -> int:
    """Создает новую жалобу и возвращает её ID"""
    try:
        cursor.execute("""
            INSERT INTO reports (order_id, reporter_id, reason)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (order_id, reporter_id, reason))
        report_id = cursor.fetchone()['id']
        conn.commit()
        return report_id
    except Exception as e:
        print(f"Ошибка при создании жалобы: {e}")
        conn.rollback()
        return None
    
def resolve_and_delete_report(report_id: int) -> bool:
    """Удаляет жалобу и возвращает True при успехе"""
    try:
        cursor.execute("""
            DELETE FROM reports 
            WHERE id = %s
            RETURNING id
        """, (report_id,))
        conn.commit()
        return cursor.fetchone() is not None
    except Exception as e:
        print(f"Ошибка при удалении жалобы: {e}")
        conn.rollback()
        return False

def save_message(chat_id: int, sender_id: int, message: str) -> int:
    """Сохраняет сообщение в чат"""
    cursor.execute(
        "INSERT INTO messages (chat_id, sender_id, message) VALUES (%s, %s, %s) RETURNING id",
        (chat_id, sender_id, message)
    )
    message_id = cursor.fetchone()['id']
    conn.commit()
    return message_id

def get_conversation(customer_id: int, executor_id: int):
    cursor.execute("""
        SELECT message, is_from_customer, sent_at
        FROM messages
        WHERE (customer_id = %s AND executor_id = %s)
        ORDER BY sent_at
    """, (customer_id, executor_id))
    return cursor.fetchall()

def search_executor_profiles(keyword, limit=5, offset=0):
    query = """
        SELECT u.username, u.rating, p.bio, p.skills
        FROM users u
        JOIN profiles p ON u.telegram_id = p.telegram_id
        WHERE u.is_executor = TRUE
          AND (LOWER(u.username) LIKE LOWER(%s) OR 
               LOWER(p.bio) LIKE LOWER(%s) OR 
               LOWER(p.skills) LIKE LOWER(%s))
        ORDER BY u.rating DESC
        LIMIT %s OFFSET %s
    """
    pattern = f"%{keyword}%"
    cursor.execute(query, (pattern, pattern, pattern, limit, offset))
    return cursor.fetchall()

def get_user_id(identifier):
    cursor.execute("SELECT telegram_id FROM users WHERE telegram_name = %s", (identifier[1:],))
    return cursor.fetchone()

def get_user_roles(user_id: int):
    """Корректное получение ролей с обработкой RealDictRow"""
    try:
        cursor.execute("""
            SELECT is_executor, is_customer
            FROM users 
            WHERE telegram_id = %s
        """, (user_id,))
        
        result = cursor.fetchone()
        
        if not result:
            print(f"Пользователь {user_id} не найден")
            return False, False
            
        # Правильное получение значений из RealDictRow
        is_executor = result['is_executor']
        is_customer = result['is_customer']
        
        print(f"Реальные значения из БД: executor={is_executor}, customer={is_customer}")
        return bool(is_executor), bool(is_customer)
        
    except Exception as e:
        print(f"Ошибка при получении ролей: {e}")
        return False, False 

def set_user_roles(telegram_id: int, is_customer: bool = None, is_executor: bool = None):
    """Обновляет роли пользователя с правильным управлением транзакциями"""
    try:
        # Начинаем новую транзакцию
        conn.rollback()  # Сначала сбрасываем возможные предыдущие ошибки
        
        cursor.execute("""
            INSERT INTO users (telegram_id, is_executor, is_customer)
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE
            SET is_executor = COALESCE(EXCLUDED.is_executor, users.is_executor),
                is_customer = COALESCE(EXCLUDED.is_customer, users.is_customer)
        """, (
            telegram_id,
            is_executor if is_executor is not None else False,
            is_customer if is_customer is not None else False
        ))
        
        conn.commit()
    except Exception as e:
        print(f"Ошибка при обновлении ролей: {e}")
        conn.rollback()
        raise

def get_user(telegram_id):
    cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
    return cursor.fetchone()
