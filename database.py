# -*- coding: utf-8 -*-
import sqlite3
import json
from datetime import datetime, timedelta
from contextlib import contextmanager

DATABASE = 'monitor.db'

@contextmanager
def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """初始化数据库表"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 监控项目表 - types 存储 JSON 数组，支持多种监控类型
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                types TEXT NOT NULL DEFAULT '["http"]',
                target TEXT NOT NULL,
                interval INTEGER DEFAULT 60,
                timeout INTEGER DEFAULT 30,
                method TEXT DEFAULT 'GET',
                headers TEXT DEFAULT '{}',
                body TEXT DEFAULT '',
                expected_status INTEGER DEFAULT 200,
                keyword TEXT DEFAULT '',
                port INTEGER DEFAULT 0,
                notify_channels TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 监控记录表 - 添加 check_type 字段区分不同类型的检查结果
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monitor_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_id INTEGER NOT NULL,
                check_type TEXT DEFAULT 'http',
                status INTEGER NOT NULL,
                response_time INTEGER DEFAULT 0,
                status_code INTEGER DEFAULT 0,
                message TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (monitor_id) REFERENCES monitors (id) ON DELETE CASCADE
            )
        ''')
        
        # 心跳推送表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_id INTEGER NOT NULL,
                status INTEGER DEFAULT 1,
                message TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (monitor_id) REFERENCES monitors (id) ON DELETE CASCADE
            )
        ''')
        
        # 通知渠道表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notify_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                config TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 事件日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_id INTEGER,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (monitor_id) REFERENCES monitors (id) ON DELETE SET NULL
            )
        ''')
        
        # 网站设置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                site_title TEXT DEFAULT '酷监控',
                site_icon TEXT DEFAULT '🚀',
                footer_author TEXT DEFAULT 'Xpccm',
                footer_icp TEXT DEFAULT '',
                footer_url TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 管理员表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_monitor ON monitor_logs(monitor_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_created ON monitor_logs(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_heartbeats_monitor ON heartbeats(monitor_id)')
        
        conn.commit()
        print("数据库初始化完成")

# 监控项目 CRUD
def create_monitor(data):
    """创建监控项目"""
    with get_db() as conn:
        cursor = conn.cursor()
        # types 是数组，存储为 JSON
        types = data.get('types', ['http'])
        if isinstance(types, str):
            types = [types]
        
        cursor.execute('''
            INSERT INTO monitors (name, types, target, interval, timeout, method, headers, body, 
                                  expected_status, keyword, port, notify_channels, tags, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'], json.dumps(types), data['target'],
            data.get('interval', 60), data.get('timeout', 30),
            data.get('method', 'GET'), json.dumps(data.get('headers', {})),
            data.get('body', ''), data.get('expected_status', 200),
            data.get('keyword', ''), data.get('port', 0),
            json.dumps(data.get('notify_channels', [])),
            json.dumps(data.get('tags', [])), data.get('enabled', 1)
        ))
        conn.commit()
        return cursor.lastrowid

def get_all_monitors():
    """获取所有监控项目"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM monitors ORDER BY created_at DESC')
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_monitor(monitor_id):
    """获取单个监控项目"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM monitors WHERE id = ?', (monitor_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_monitor(monitor_id, data):
    """更新监控项目"""
    with get_db() as conn:
        cursor = conn.cursor()
        fields = []
        values = []
        for key in ['name', 'target', 'interval', 'timeout', 'method', 
                    'expected_status', 'keyword', 'port', 'enabled']:
            if key in data:
                fields.append(f'{key} = ?')
                values.append(data[key])
        
        if 'types' in data:
            types = data['types']
            if isinstance(types, str):
                types = [types]
            fields.append('types = ?')
            values.append(json.dumps(types))
        if 'headers' in data:
            fields.append('headers = ?')
            values.append(json.dumps(data['headers']))
        if 'notify_channels' in data:
            fields.append('notify_channels = ?')
            values.append(json.dumps(data['notify_channels']))
        if 'tags' in data:
            fields.append('tags = ?')
            values.append(json.dumps(data['tags']))
        
        fields.append('updated_at = CURRENT_TIMESTAMP')
        values.append(monitor_id)
        
        cursor.execute(f'UPDATE monitors SET {", ".join(fields)} WHERE id = ?', values)
        conn.commit()
        return cursor.rowcount > 0

def delete_monitor(monitor_id):
    """删除监控项目"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM monitors WHERE id = ?', (monitor_id,))
        conn.commit()
        return cursor.rowcount > 0

# 监控日志
def add_log(monitor_id, check_type, status, response_time=0, status_code=0, message=''):
    """添加监控日志"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO monitor_logs (monitor_id, check_type, status, response_time, status_code, message)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (monitor_id, check_type, status, response_time, status_code, message))
        conn.commit()

def get_logs(monitor_id, limit=100, check_type=None):
    """获取监控日志"""
    with get_db() as conn:
        cursor = conn.cursor()
        if check_type:
            cursor.execute('''
                SELECT * FROM monitor_logs 
                WHERE monitor_id = ? AND check_type = ?
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (monitor_id, check_type, limit))
        else:
            cursor.execute('''
                SELECT * FROM monitor_logs 
                WHERE monitor_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (monitor_id, limit))
        return [dict(row) for row in cursor.fetchall()]

def get_recent_logs(monitor_id, hours=24, check_type=None):
    """获取最近N小时的日志"""
    with get_db() as conn:
        cursor = conn.cursor()
        since = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
        if check_type:
            cursor.execute('''
                SELECT * FROM monitor_logs 
                WHERE monitor_id = ? AND check_type = ? AND created_at >= ?
                ORDER BY created_at ASC
            ''', (monitor_id, check_type, since))
        else:
            cursor.execute('''
                SELECT * FROM monitor_logs 
                WHERE monitor_id = ? AND created_at >= ?
                ORDER BY created_at ASC
            ''', (monitor_id, since))
        return [dict(row) for row in cursor.fetchall()]

def get_latest_status(monitor_id, check_type=None):
    """获取最新状态"""
    with get_db() as conn:
        cursor = conn.cursor()
        if check_type:
            cursor.execute('''
                SELECT * FROM monitor_logs 
                WHERE monitor_id = ? AND check_type = ?
                ORDER BY created_at DESC 
                LIMIT 1
            ''', (monitor_id, check_type))
        else:
            cursor.execute('''
                SELECT * FROM monitor_logs 
                WHERE monitor_id = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            ''', (monitor_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_latest_status_by_types(monitor_id, check_types):
    """获取每种类型的最新状态"""
    results = {}
    for ct in check_types:
        results[ct] = get_latest_status(monitor_id, ct)
    return results

def get_uptime_stats(monitor_id, days=30, check_type=None):
    """获取可用率统计"""
    with get_db() as conn:
        cursor = conn.cursor()
        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        if check_type:
            cursor.execute('''
                SELECT COUNT(*) as total, SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as up_count
                FROM monitor_logs 
                WHERE monitor_id = ? AND check_type = ? AND created_at >= ?
            ''', (monitor_id, check_type, since))
        else:
            cursor.execute('''
                SELECT COUNT(*) as total, SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as up_count
                FROM monitor_logs 
                WHERE monitor_id = ? AND created_at >= ?
            ''', (monitor_id, since))
        row = cursor.fetchone()
        
        if row and row['total'] > 0:
            return round(row['up_count'] / row['total'] * 100, 2)
        return 100.0

def get_avg_response_time(monitor_id, hours=24):
    """获取平均响应时间"""
    with get_db() as conn:
        cursor = conn.cursor()
        since = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            SELECT AVG(response_time) as avg_time
            FROM monitor_logs 
            WHERE monitor_id = ? AND created_at >= ? AND status = 1
        ''', (monitor_id, since))
        row = cursor.fetchone()
        return round(row['avg_time'] or 0, 2)

# 心跳推送
def add_heartbeat(monitor_id, status=1, message=''):
    """添加心跳记录"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO heartbeats (monitor_id, status, message)
            VALUES (?, ?, ?)
        ''', (monitor_id, status, message))
        conn.commit()
        # 同时记录到日志
        add_log(monitor_id, 'push', status, 0, 0, message)

def get_last_heartbeat(monitor_id):
    """获取最后一次心跳"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM heartbeats 
            WHERE monitor_id = ? 
            ORDER BY created_at DESC 
            LIMIT 1
        ''', (monitor_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

# 通知渠道
def create_notify_channel(data):
    """创建通知渠道"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO notify_channels (name, type, config, enabled)
            VALUES (?, ?, ?, ?)
        ''', (data['name'], data['type'], json.dumps(data['config']), data.get('enabled', 1)))
        conn.commit()
        return cursor.lastrowid

def get_all_notify_channels():
    """获取所有通知渠道"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM notify_channels')
        return [dict(row) for row in cursor.fetchall()]

def delete_notify_channel(channel_id):
    """删除通知渠道"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM notify_channels WHERE id = ?', (channel_id,))
        conn.commit()

# 事件
def add_event(monitor_id, event_type, message):
    """添加事件"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events (monitor_id, event_type, message)
            VALUES (?, ?, ?)
        ''', (monitor_id, event_type, message))
        conn.commit()

def get_recent_events(limit=50):
    """获取最近事件"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT e.*, m.name as monitor_name 
            FROM events e 
            LEFT JOIN monitors m ON e.monitor_id = m.id
            ORDER BY e.created_at DESC 
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in cursor.fetchall()]

# 网站设置
def get_settings():
    """获取网站设置"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM settings WHERE id = 1')
        row = cursor.fetchone()
        if row:
            return dict(row)
        # 返回默认设置
        return {
            'site_title': '酷监控',
            'site_icon': '🚀',
            'footer_author': 'Xpccm',
            'footer_icp': '',
            'footer_url': ''
        }

def update_settings(data):
    """更新网站设置"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM settings WHERE id = 1')
        if cursor.fetchone():
            cursor.execute('''
                UPDATE settings SET 
                    site_title = ?, site_icon = ?, footer_author = ?, 
                    footer_icp = ?, footer_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            ''', (data.get('site_title', '酷监控'), data.get('site_icon', '🚀'),
                  data.get('footer_author', 'Xpccm'), data.get('footer_icp', ''),
                  data.get('footer_url', '')))
        else:
            cursor.execute('''
                INSERT INTO settings (id, site_title, site_icon, footer_author, footer_icp, footer_url)
                VALUES (1, ?, ?, ?, ?, ?)
            ''', (data.get('site_title', '酷监控'), data.get('site_icon', '🚀'),
                  data.get('footer_author', 'Xpccm'), data.get('footer_icp', ''),
                  data.get('footer_url', '')))
        conn.commit()
        return True

# 管理员
def get_admin():
    """获取管理员信息"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM admin WHERE id = 1')
        row = cursor.fetchone()
        return dict(row) if row else None

def create_admin(username, password_hash):
    """创建管理员"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM admin WHERE id = 1')
        if cursor.fetchone():
            cursor.execute('UPDATE admin SET username = ?, password = ? WHERE id = 1',
                          (username, password_hash))
        else:
            cursor.execute('INSERT INTO admin (id, username, password) VALUES (1, ?, ?)',
                          (username, password_hash))
        conn.commit()
        return True

def verify_admin(username, password_hash):
    """验证管理员"""
    admin = get_admin()
    if admin and admin['username'] == username and admin['password'] == password_hash:
        return True
    return False

# 清理旧数据
def cleanup_old_data(days=90):
    """清理旧数据"""
    with get_db() as conn:
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('DELETE FROM monitor_logs WHERE created_at < ?', (cutoff,))
        cursor.execute('DELETE FROM heartbeats WHERE created_at < ?', (cutoff,))
        cursor.execute('DELETE FROM events WHERE created_at < ?', (cutoff,))
        
        conn.commit()
        print(f"已清理 {days} 天前的旧数据")

if __name__ == '__main__':
    init_db()

