import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH
from utils import get_week_start_str

class Database:
    def __init__(self):
        self.db_path = DB_PATH

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    is_admin BOOLEAN DEFAULT FALSE,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    schedule_text TEXT,
                    week_start DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_shifts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    hotel TEXT,
                    date TEXT,
                    time_start TEXT,
                    time_end TEXT,
                    status TEXT DEFAULT 'pending',
                    max_employees INTEGER DEFAULT 1,
                    confirmed_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            cursor = await db.execute("PRAGMA table_info(user_shifts)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'max_employees' not in column_names:
                try:
                    await db.execute('ALTER TABLE user_shifts ADD COLUMN max_employees INTEGER DEFAULT 1')
                except:
                    pass
            
            if 'confirmed_count' not in column_names:
                try:
                    await db.execute('ALTER TABLE user_shifts ADD COLUMN confirmed_count INTEGER DEFAULT 0')
                except:
                    pass

            await db.execute('''
                CREATE TABLE IF NOT EXISTS assigned_shifts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    day TEXT,
                    date TEXT,
                    hotel TEXT,
                    time_start TEXT,
                    time_end TEXT,
                    assigned_by INTEGER,
                    week_start TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            cursor = await db.execute("PRAGMA table_info(assigned_shifts)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'week_start' not in column_names:
                try:
                    await db.execute('ALTER TABLE assigned_shifts ADD COLUMN week_start TEXT')
                except:
                    pass

            await db.commit()

    async def clear_old_data(self):
        """Очистка данных старше 2 недель"""
        two_weeks_ago = datetime.now().date() - timedelta(days=14)
        week_start = two_weeks_ago.strftime("%Y-%m-%d")
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM user_schedules WHERE week_start < ?', (week_start,))
            await db.execute('DELETE FROM assigned_shifts WHERE week_start < ?', (week_start,))
            await db.execute('DELETE FROM user_shifts WHERE date < date("now", "-14 days")')
            await db.commit()

    async def is_admin(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            return row and row[0] == 1

    async def add_user(self, user_id, username=None, first_name=None, last_name=None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            await db.commit()

    async def get_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'username': row[1],
                    'first_name': row[2],
                    'last_name': row[3],
                    'is_admin': bool(row[4])
                }
            return None

    async def get_all_users(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT * FROM users')
            rows = await cursor.fetchall()
            return [
                {
                    'user_id': r[0],
                    'username': r[1],
                    'first_name': r[2],
                    'last_name': r[3],
                    'is_admin': bool(r[4])
                }
                for r in rows
            ]

    async def get_all_users_with_names(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT * FROM users ORDER BY first_name')
            rows = await cursor.fetchall()
            return [
                {
                    'user_id': r[0],
                    'username': r[1],
                    'first_name': r[2],
                    'last_name': r[3],
                    'full_name': f"{r[2]} {r[3] or ''}".strip(),
                }
                for r in rows
            ]

    async def get_all_users_with_schedules(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT u.user_id, u.username, u.first_name, u.last_name, s.schedule_text, s.created_at
                FROM users u
                LEFT JOIN user_schedules s ON u.user_id = s.user_id
                ORDER BY u.first_name
            ''')
            rows = await cursor.fetchall()
            
            result = []
            for r in rows:
                result.append({
                    'user_id': r[0],
                    'username': r[1],
                    'first_name': r[2],
                    'last_name': r[3],
                    'full_name': f"{r[2]} {r[3] or ''}".strip(),
                    'schedule_text': r[4] if r[4] else '',
                    'created_at': r[5]
                })
            return result

    async def update_user_name(self, user_id, first_name, last_name):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE users SET first_name = ?, last_name = ? WHERE user_id = ?',
                (first_name, last_name, user_id)
            )
            await db.commit()

    async def update_username(self, user_id, username):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE users SET username = ? WHERE user_id = ?',
                (username, user_id)
            )
            await db.commit()

    async def save_user_schedule(self, user_id, schedule_text, week_start=None):
        if week_start is None:
            week_start = get_week_start_str()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM user_schedules WHERE user_id = ? AND week_start = ?',
                (user_id, week_start)
            )
            await db.execute('''
                INSERT INTO user_schedules (user_id, schedule_text, week_start)
                VALUES (?, ?, ?)
            ''', (user_id, schedule_text, week_start))
            await db.commit()

    async def update_user_schedule(self, user_id, schedule_text, week_start=None):
        if week_start is None:
            week_start = get_week_start_str()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                DELETE FROM user_schedules 
                WHERE user_id = ? AND week_start = ?
            ''', (user_id, week_start))
            
            await db.execute('''
                INSERT INTO user_schedules (user_id, schedule_text, week_start)
                VALUES (?, ?, ?)
            ''', (user_id, schedule_text, week_start))
            await db.commit()

    async def get_user_schedule(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT schedule_text FROM user_schedules 
                WHERE user_id = ? 
                ORDER BY created_at DESC LIMIT 1
            ''', (user_id,))
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_all_schedules_with_users(self, week_start=None):
        if week_start is None:
            week_start = get_week_start_str()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT s.user_id, u.first_name, u.last_name, u.username, s.schedule_text, s.created_at
                FROM user_schedules s
                LEFT JOIN users u ON s.user_id = u.user_id
                WHERE s.week_start = ?
                ORDER BY u.first_name
            ''', (week_start,))
            rows = await cursor.fetchall()
            
            result = []
            for r in rows:
                first = r[1] or ''
                last = r[2] or ''
                full = f"{first} {last}".strip() or f"ID {r[0]}"
                result.append({
                    'user_id': r[0],
                    'first_name': first,
                    'last_name': last,
                    'username': r[3],
                    'full_name': full,
                    'schedule_text': r[4],
                    'created_at': r[5]
                })
            return result

    # ========== НАЗНАЧЕННЫЕ СМЕНЫ (ГОТОВЫЙ ГРАФИК) ==========
    
    async def assign_shift(self, user_id, day, date, hotel, time_start, time_end, assigned_by, week_start):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO assigned_shifts (user_id, day, date, hotel, time_start, time_end, assigned_by, week_start)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, day, date, hotel, time_start, time_end, assigned_by, week_start))
            await db.commit()
            cursor = await db.execute('SELECT last_insert_rowid()')
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_assigned_shifts_for_week(self, week_start):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM assigned_shifts WHERE week_start = ?
            ''', (week_start,))
            rows = await cursor.fetchall()
            return [
                {
                    'id': r[0],
                    'user_id': r[1],
                    'day': r[2],
                    'date': r[3],
                    'hotel': r[4],
                    'time_start': r[5],
                    'time_end': r[6],
                    'assigned_by': r[7],
                    'week_start': r[8],
                    'created_at': r[9]
                }
                for r in rows
            ]

    async def clear_assigned_shifts_for_week(self, week_start):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM assigned_shifts WHERE week_start = ?', (week_start,))
            await db.commit()

    async def get_assigned_users_for_day(self, day, date=None):
        week_start = get_week_start_str()
        assigned = await self.get_assigned_shifts_for_day(day, date, week_start)
        return [a['user_id'] for a in assigned]

    async def get_assigned_shifts_for_day(self, day, date=None, week_start=None):
        if week_start is None:
            week_start = get_week_start_str()
            
        async with aiosqlite.connect(self.db_path) as db:
            if date:
                cursor = await db.execute('''
                    SELECT * FROM assigned_shifts WHERE day = ? AND date = ? AND week_start = ?
                ''', (day, date, week_start))
            else:
                cursor = await db.execute('''
                    SELECT * FROM assigned_shifts WHERE day = ? AND week_start = ?
                ''', (day, week_start))
            rows = await cursor.fetchall()
            return [
                {
                    'id': r[0],
                    'user_id': r[1],
                    'day': r[2],
                    'date': r[3],
                    'hotel': r[4],
                    'time_start': r[5],
                    'time_end': r[6],
                    'assigned_by': r[7],
                    'week_start': r[8],
                    'created_at': r[9]
                }
                for r in rows
            ]

    async def get_all_assigned_shifts(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT * FROM assigned_shifts')
            rows = await cursor.fetchall()
            return [
                {
                    'id': r[0],
                    'user_id': r[1],
                    'day': r[2],
                    'date': r[3],
                    'hotel': r[4],
                    'time_start': r[5],
                    'time_end': r[6],
                    'assigned_by': r[7],
                    'week_start': r[8],
                    'created_at': r[9]
                }
                for r in rows
            ]

    # ========== РАБОТА С ЛИМИТОМ И СЧЕТЧИКОМ ==========
    
    async def get_shift_limit(self, shift_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT max_employees FROM user_shifts WHERE id = ?', (shift_id,))
            row = await cursor.fetchone()
            return row[0] if row else 1

    async def get_shift_confirmed_count(self, shift_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT confirmed_count FROM user_shifts WHERE id = ?', (shift_id,))
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def increment_shift_confirmed(self, shift_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE user_shifts 
                SET confirmed_count = COALESCE(confirmed_count, 0) + 1 
                WHERE id = ?
            ''', (shift_id,))
            await db.commit()

    async def close_shift(self, shift_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE user_shifts SET status = "closed" WHERE id = ?', (shift_id,))
            await db.commit()

    # ========== СТАРЫЕ МЕТОДЫ ==========

    async def add_shift_to_user(self, user_id, shift_data):
        max_employees = shift_data.get('max_employees', 1)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO user_shifts (user_id, hotel, date, time_start, time_end, status, max_employees, confirmed_count)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, 0)
            ''', (user_id, shift_data['hotel'], shift_data['date'], shift_data['time_start'], shift_data['time_end'], max_employees))
            await db.commit()
            cursor = await db.execute('SELECT last_insert_rowid()')
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_user_shifts(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM user_shifts WHERE user_id = ? ORDER BY date
            ''', (user_id,))
            rows = await cursor.fetchall()
            return [
                {
                    'id': r[0],
                    'user_id': r[1],
                    'hotel': r[2],
                    'date': r[3],
                    'time_start': r[4],
                    'time_end': r[5],
                    'status': r[6],
                    'max_employees': r[7] if len(r) > 7 else 1,
                    'confirmed_count': r[8] if len(r) > 8 else 0,
                    'created_at': r[9] if len(r) > 9 else None
                }
                for r in rows
            ]

    async def confirm_shift(self, shift_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE user_shifts SET status = 'confirmed' WHERE id = ?
            ''', (shift_id,))
            await db.commit()

    async def decline_shift(self, shift_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE user_shifts SET status = 'declined' WHERE id = ?
            ''', (shift_id,))
            await db.commit()

    async def get_shift_by_id(self, shift_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT * FROM user_shifts WHERE id = ?', (shift_id,))
            row = await cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'user_id': row[1],
                    'hotel': row[2],
                    'date': row[3],
                    'time_start': row[4],
                    'time_end': row[5],
                    'status': row[6],
                    'max_employees': row[7] if len(row) > 7 else 1,
                    'confirmed_count': row[8] if len(row) > 8 else 0,
                    'created_at': row[9] if len(row) > 9 else None
                }
            return None

    async def get_all_confirmed_shifts(self):
        week_start = get_week_start_str()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM user_shifts 
                WHERE date >= ? AND status = 'confirmed'
            ''', (week_start,))
            rows = await cursor.fetchall()
            return [
                {
                    'id': r[0],
                    'user_id': r[1],
                    'hotel': r[2],
                    'date': r[3],
                    'time_start': r[4],
                    'time_end': r[5],
                    'status': r[6]
                }
                for r in rows
            ]

    async def get_free_employees(self, day, time_start=None, time_end=None):
        schedules = await self.get_all_schedules_with_users()
        all_users = await self.get_all_users_with_names()
        
        if not schedules:
            return []
        
        all_days = [
            'Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela',
            'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье',
            'Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd'
        ]
        
        search_day_lower = day.lower()
        
        free_employees = []
        busy_employees = []
        
        for s in schedules:
            full_name = s['full_name']
            schedule_text = s['schedule_text']
            
            day_found = False
            is_free = False
            
            lines = schedule_text.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                for d in all_days:
                    if d.lower() in line.lower() and search_day_lower in line.lower():
                        day_found = True
                        
                        if ':' in line:
                            time_part = line.split(':', 1)[1].strip().lower()
                            
                            if any(word in time_part for word in ['wolne', 'nie mogę', 'выходной', 'не могу', 'off', 'free']):
                                is_free = True
                            else:
                                is_free = False
                        else:
                            is_free = True
                        break
                
                if day_found:
                    break
            
            if not day_found:
                is_free = True
            
            if is_free:
                if full_name not in free_employees and full_name not in busy_employees:
                    free_employees.append(full_name)
            else:
                if full_name not in busy_employees and full_name not in free_employees:
                    busy_employees.append(full_name)
        
        return free_employees
    
    async def update_shift_user(self, shift_id, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE user_shifts SET user_id = ? WHERE id = ?
            ''', (user_id, shift_id))
            await db.commit()

    async def clear_all_data(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM user_schedules')
            await db.execute('DELETE FROM user_shifts')
            await db.execute('DELETE FROM assigned_shifts')
            await db.commit()

    async def clear_data_for_week(self, week_start: str):
        """Удаляет графики и назначения ТОЛЬКО указанной недели. users не трогает."""
        start = datetime.strptime(week_start[:10], "%Y-%m-%d").date()
        dates_dot = [(start + timedelta(days=i)).strftime("%d.%m.%Y") for i in range(7)]
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                'DELETE FROM user_schedules WHERE week_start = ?', (week_start,)
            )
            n_sched = cur.rowcount
            cur = await db.execute(
                'DELETE FROM assigned_shifts WHERE week_start = ?', (week_start,)
            )
            n_assigned = cur.rowcount
            n_shifts = 0
            if dates_dot:
                q = ','.join('?' * len(dates_dot))
                cur = await db.execute(
                    f'DELETE FROM user_shifts WHERE date IN ({q})', dates_dot
                )
                n_shifts = cur.rowcount
            await db.commit()
        return {
            'schedules': n_sched or 0,
            'assigned': n_assigned or 0,
            'extra_shifts': n_shifts or 0,
        }

    async def get_assigned_days_for_user(self, user_id, week_start):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT DISTINCT day FROM assigned_shifts 
                WHERE user_id = ? AND week_start = ?
            ''', (user_id, week_start))
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

    async def get_assigned_shifts_for_user(self, user_id, week_start=None):
        """Смены, которые координатор выдал сотруднику на неделю"""
        if week_start is None:
            week_start = get_week_start_str()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id, user_id, day, date, hotel, time_start, time_end, assigned_by, week_start
                FROM assigned_shifts
                WHERE user_id = ? AND week_start = ?
                ORDER BY date, time_start
            ''', (user_id, week_start))
            rows = await cursor.fetchall()
            return [
                {
                    'id': r[0],
                    'user_id': r[1],
                    'day': r[2],
                    'date': r[3],
                    'hotel': r[4],
                    'time_start': r[5],
                    'time_end': r[6],
                    'assigned_by': r[7],
                    'week_start': r[8],
                }
                for r in rows
            ]

    async def is_user_assigned_on_date(self, user_id, date):
        week_start = get_week_start_str()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id FROM assigned_shifts 
                WHERE user_id = ? AND date = ? AND week_start = ?
            ''', (user_id, date, week_start))
            row = await cursor.fetchone()
            return row is not None

# get_week_start_str — из utils