# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
import threading
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from database import (
    init_db, get_all_monitors, get_monitor, create_monitor, update_monitor, delete_monitor,
    add_log, get_logs, get_recent_logs, get_latest_status, get_latest_status_by_types,
    get_uptime_stats, get_avg_response_time, add_heartbeat, get_last_heartbeat, 
    create_notify_channel, get_all_notify_channels, delete_notify_channel, 
    add_event, get_recent_events, cleanup_old_data,
    get_settings, update_settings, get_admin, create_admin, verify_admin
)
import hashlib
import secrets
from monitor import MonitorChecker
from notify import send_notification

app = Flask(__name__, static_folder='static')
app.secret_key = secrets.token_hex(32)
CORS(app)

# 简单的token存储
admin_tokens = set()

def hash_password(password):
    """密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()

def check_auth():
    """检查认证"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    return token in admin_tokens

checker = MonitorChecker()
scheduler = BackgroundScheduler()

# 存储上次状态，用于检测状态变化 {monitor_id: {check_type: status}}
last_status = {}

TYPE_NAMES = {
    'http': 'HTTP',
    'keyword': '关键词',
    'ssl': 'SSL证书',
    'port': '端口',
    'push': '推送',
    'mysql': 'MySQL',
    'redis': 'Redis'
}

def check_monitor(monitor):
    """检查单个监控项目的所有类型"""
    global last_status
    
    if not monitor.get('enabled', 1):
        return
    
    monitor_id = monitor['id']
    
    # 获取监控类型列表
    types_str = monitor.get('types', '["http"]')
    try:
        types = json.loads(types_str) if isinstance(types_str, str) else types_str
    except:
        types = ['http']
    
    # 初始化状态记录
    if monitor_id not in last_status:
        last_status[monitor_id] = {}
    
    # 对每种类型执行检查
    for check_type in types:
        # 跳过推送类型（被动接收）
        if check_type == 'push':
            continue
            
        # 构建单类型检查用的 monitor 对象
        check_monitor_obj = {**monitor, 'type': check_type}
        result = checker.check(check_monitor_obj)
        
        # 记录日志
        add_log(monitor_id, check_type, result['status'], result['response_time'], 
                result['status_code'], result['message'])
        
        # 检查状态变化
        prev_status = last_status[monitor_id].get(check_type)
        current_status = result['status']
        
        if prev_status is not None and prev_status != current_status:
            type_name = TYPE_NAMES.get(check_type, check_type)
            if current_status == 0:
                event_type = 'down'
                event_msg = f"{monitor['name']} [{type_name}] 异常: {result['message']}"
            else:
                event_type = 'up'
                event_msg = f"{monitor['name']} [{type_name}] 恢复正常"
            
            add_event(monitor_id, event_type, event_msg)
            send_notification(monitor, current_status, f"[{type_name}] {result['message']}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {event_msg}")
        
        last_status[monitor_id][check_type] = current_status

def run_all_checks():
    """运行所有监控检查"""
    monitors = get_all_monitors()
    for monitor in monitors:
        try:
            check_monitor(monitor)
        except Exception as e:
            print(f"检查 {monitor['name']} 出错: {e}")

def schedule_monitor(monitor):
    """为单个监控项目安排定时任务"""
    job_id = f"monitor_{monitor['id']}"
    interval = monitor.get('interval', 60)
    
    # 移除旧任务
    try:
        scheduler.remove_job(job_id)
    except:
        pass
    
    # 获取监控类型
    types_str = monitor.get('types', '["http"]')
    try:
        types = json.loads(types_str) if isinstance(types_str, str) else types_str
    except:
        types = ['http']
    
    # 如果只有推送类型，不需要主动检查
    has_active_types = any(t != 'push' for t in types)
    
    if monitor.get('enabled', 1) and has_active_types:
        scheduler.add_job(
            check_monitor,
            'interval',
            seconds=interval,
            args=[monitor],
            id=job_id,
            replace_existing=True
        )

def init_scheduler():
    """初始化调度器"""
    monitors = get_all_monitors()
    for monitor in monitors:
        schedule_monitor(monitor)
    
    # 每天清理旧数据
    scheduler.add_job(cleanup_old_data, 'cron', hour=3, minute=0, args=[90])
    
    if not scheduler.running:
        scheduler.start()
    print(f"调度器已启动，监控 {len(monitors)} 个项目")

# ============ 页面路由 ============

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/admin')
def admin_page():
    return send_from_directory('static', 'admin.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

# ============ 认证API ============

@app.route('/api/auth/setup', methods=['POST'])
def api_auth_setup():
    """初始化管理员账号（仅首次）"""
    admin = get_admin()
    if admin:
        return jsonify({'error': '管理员已存在'}), 400
    
    data = request.json
    username = data.get('username', 'admin')
    password = data.get('password', '')
    
    if len(password) < 6:
        return jsonify({'error': '密码至少6位'}), 400
    
    create_admin(username, hash_password(password))
    return jsonify({'success': True, 'message': '管理员创建成功'})

@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    """登录"""
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')
    
    admin = get_admin()
    if not admin:
        return jsonify({'error': '请先初始化管理员', 'need_setup': True}), 401
    
    if verify_admin(username, hash_password(password)):
        token = secrets.token_hex(32)
        admin_tokens.add(token)
        return jsonify({'success': True, 'token': token})
    
    return jsonify({'error': '用户名或密码错误'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    """登出"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    admin_tokens.discard(token)
    return jsonify({'success': True})

@app.route('/api/auth/check', methods=['GET'])
def api_auth_check():
    """检查登录状态"""
    admin = get_admin()
    if not admin:
        return jsonify({'authenticated': False, 'need_setup': True})
    return jsonify({'authenticated': check_auth()})

@app.route('/api/auth/password', methods=['PUT'])
def api_auth_password():
    """修改密码"""
    if not check_auth():
        return jsonify({'error': '未授权'}), 401
    
    data = request.json
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    admin = get_admin()
    if not verify_admin(admin['username'], hash_password(old_password)):
        return jsonify({'error': '原密码错误'}), 400
    
    if len(new_password) < 6:
        return jsonify({'error': '新密码至少6位'}), 400
    
    create_admin(admin['username'], hash_password(new_password))
    return jsonify({'success': True})

# ============ 网站设置API ============

@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    """获取网站设置"""
    settings = get_settings()
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'])
def api_update_settings():
    """更新网站设置"""
    if not check_auth():
        return jsonify({'error': '未授权'}), 401
    
    data = request.json
    update_settings(data)
    return jsonify({'success': True})

# ============ API路由 ============

@app.route('/api/monitors', methods=['GET'])
def api_get_monitors():
    """获取所有监控项目及其状态"""
    monitors = get_all_monitors()
    result = []
    
    for m in monitors:
        # 解析类型列表
        types_str = m.get('types', '["http"]')
        try:
            types = json.loads(types_str) if isinstance(types_str, str) else types_str
        except:
            types = ['http']
        
        # 获取每种类型的最新状态
        type_results = {}
        overall_status = 1  # 默认正常
        last_check_time = None
        
        for check_type in types:
            latest = get_latest_status(m['id'], check_type)
            uptime = get_uptime_stats(m['id'], 30, check_type)
            avg_time = get_avg_response_time(m['id'], 24)
            
            if latest:
                type_results[check_type] = {
                    'status': latest['status'],
                    'response_time': latest['response_time'],
                    'status_code': latest['status_code'],
                    'message': latest['message'],
                    'last_check': latest['created_at'],
                    'uptime': uptime
                }
                # 只要有一个类型失败，整体就是失败
                if latest['status'] == 0:
                    overall_status = 0
                if not last_check_time or latest['created_at'] > last_check_time:
                    last_check_time = latest['created_at']
            else:
                type_results[check_type] = {
                    'status': 0,
                    'response_time': 0,
                    'status_code': 0,
                    'message': '等待检查',
                    'last_check': None,
                    'uptime': 100
                }
        
        # 获取整体历史（所有类型混合）
        recent = get_recent_logs(m['id'], 24)
        history = []
        for log in recent[-24:]:
            history.append({
                'status': log['status'],
                'time': log['created_at'],
                'response_time': log['response_time'],
                'check_type': log.get('check_type', 'http')
            })
        
        # 计算整体可用率和响应时间
        overall_uptime = get_uptime_stats(m['id'], 30)
        overall_avg_time = get_avg_response_time(m['id'], 24)
        
        result.append({
            **m,
            'types': types,
            'type_results': type_results,
            'tags': json.loads(m.get('tags', '[]')),
            'notify_channels': json.loads(m.get('notify_channels', '[]')),
            'headers': json.loads(m.get('headers', '{}')),
            'current_status': overall_status,
            'last_check': last_check_time,
            'uptime': overall_uptime,
            'avg_response_time': overall_avg_time,
            'history': history
        })
    
    # 统计数据
    online = sum(1 for m in result if m['current_status'] == 1)
    offline = len(result) - online
    avg_uptime = sum(m['uptime'] for m in result) / len(result) if result else 100
    
    return jsonify({
        'monitors': result,
        'stats': {
            'total': len(result),
            'online': online,
            'offline': offline,
            'avg_uptime': round(avg_uptime, 2)
        },
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/monitors', methods=['POST'])
def api_create_monitor():
    """创建监控项目"""
    if not check_auth():
        return jsonify({'error': '未授权，请先登录后台'}), 401
    
    data = request.json
    
    # 支持 types (数组) 或 type (单个)
    if 'types' not in data and 'type' in data:
        data['types'] = [data['type']]
    
    required = ['name', 'types', 'target']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'缺少必填字段: {field}'}), 400
    
    monitor_id = create_monitor(data)
    monitor = get_monitor(monitor_id)
    
    # 添加到调度器
    schedule_monitor(monitor)
    
    # 立即执行一次检查
    threading.Thread(target=check_monitor, args=(monitor,)).start()
    
    types_str = ', '.join([TYPE_NAMES.get(t, t) for t in data['types']])
    add_event(monitor_id, 'create', f"创建监控项目: {data['name']} [{types_str}]")
    
    return jsonify({'success': True, 'id': monitor_id})

@app.route('/api/monitors/<int:monitor_id>', methods=['GET'])
def api_get_monitor(monitor_id):
    """获取单个监控项目详情"""
    monitor = get_monitor(monitor_id)
    if not monitor:
        return jsonify({'error': '监控项目不存在'}), 404
    
    # 解析类型
    types_str = monitor.get('types', '["http"]')
    try:
        types = json.loads(types_str) if isinstance(types_str, str) else types_str
    except:
        types = ['http']
    
    logs = get_logs(monitor_id, 100)
    uptime = get_uptime_stats(monitor_id, 30)
    avg_time = get_avg_response_time(monitor_id, 24)
    
    # 获取每种类型的状态
    type_results = get_latest_status_by_types(monitor_id, types)
    
    return jsonify({
        **monitor,
        'types': types,
        'type_results': type_results,
        'tags': json.loads(monitor.get('tags', '[]')),
        'notify_channels': json.loads(monitor.get('notify_channels', '[]')),
        'logs': logs,
        'uptime': uptime,
        'avg_response_time': avg_time
    })

@app.route('/api/monitors/<int:monitor_id>', methods=['PUT'])
def api_update_monitor(monitor_id):
    """更新监控项目"""
    if not check_auth():
        return jsonify({'error': '未授权'}), 401
    
    data = request.json
    
    if not update_monitor(monitor_id, data):
        return jsonify({'error': '更新失败'}), 400
    
    # 更新调度器
    monitor = get_monitor(monitor_id)
    schedule_monitor(monitor)
    
    return jsonify({'success': True})

@app.route('/api/monitors/<int:monitor_id>', methods=['DELETE'])
def api_delete_monitor(monitor_id):
    """删除监控项目"""
    if not check_auth():
        return jsonify({'error': '未授权'}), 401
    
    monitor = get_monitor(monitor_id)
    if not monitor:
        return jsonify({'error': '监控项目不存在'}), 404
    
    # 从调度器移除
    try:
        scheduler.remove_job(f"monitor_{monitor_id}")
    except:
        pass
    
    delete_monitor(monitor_id)
    add_event(None, 'delete', f"删除监控项目: {monitor['name']}")
    
    return jsonify({'success': True})

@app.route('/api/monitors/<int:monitor_id>/check', methods=['POST'])
def api_check_now(monitor_id):
    """立即检查所有类型"""
    monitor = get_monitor(monitor_id)
    if not monitor:
        return jsonify({'error': '监控项目不存在'}), 404
    
    # 解析类型
    types_str = monitor.get('types', '["http"]')
    try:
        types = json.loads(types_str) if isinstance(types_str, str) else types_str
    except:
        types = ['http']
    
    results = {}
    overall_status = 1
    
    for check_type in types:
        if check_type == 'push':
            continue
        
        check_monitor_obj = {**monitor, 'type': check_type}
        result = checker.check(check_monitor_obj)
        add_log(monitor_id, check_type, result['status'], result['response_time'], 
                result['status_code'], result['message'])
        
        results[check_type] = result
        if result['status'] == 0:
            overall_status = 0
    
    return jsonify({
        'overall_status': overall_status,
        'results': results
    })

@app.route('/api/monitors/<int:monitor_id>/logs', methods=['GET'])
def api_get_logs(monitor_id):
    """获取监控日志"""
    limit = request.args.get('limit', 100, type=int)
    logs = get_logs(monitor_id, limit)
    return jsonify({'logs': logs})

# ============ 心跳推送 ============

@app.route('/api/push/<token>', methods=['GET', 'POST'])
def api_push_heartbeat(token):
    """接收心跳推送"""
    # token 格式: monitor_id 或 自定义token
    monitors = get_all_monitors()
    monitor = None
    
    for m in monitors:
        # 解析 types 数组
        types_str = m.get('types', '["http"]')
        try:
            types = json.loads(types_str) if isinstance(types_str, str) else types_str
        except:
            types = ['http']
        
        # 检查是否包含 push 类型
        if 'push' in types and (str(m['id']) == token or m.get('target') == token):
            monitor = m
            break
    
    if not monitor:
        return jsonify({'error': '无效的推送token'}), 404
    
    status = 1
    message = 'OK'
    
    if request.method == 'POST' and request.json:
        status = request.json.get('status', 1)
        message = request.json.get('msg', request.json.get('message', 'OK'))
    elif request.args.get('status'):
        status = int(request.args.get('status', 1))
        message = request.args.get('msg', 'OK')
    
    add_heartbeat(monitor['id'], status, message)
    
    return jsonify({'ok': True})

# ============ 通知渠道 ============

@app.route('/api/notify-channels', methods=['GET'])
def api_get_channels():
    """获取所有通知渠道"""
    channels = get_all_notify_channels()
    result = []
    for c in channels:
        result.append({
            **c,
            'config': json.loads(c['config']) if isinstance(c['config'], str) else c['config']
        })
    return jsonify({'channels': result})

@app.route('/api/notify-channels', methods=['POST'])
def api_create_channel():
    """创建通知渠道"""
    if not check_auth():
        return jsonify({'error': '未授权'}), 401
    
    data = request.json
    channel_id = create_notify_channel(data)
    return jsonify({'success': True, 'id': channel_id})

@app.route('/api/notify-channels/<int:channel_id>', methods=['DELETE'])
def api_delete_channel(channel_id):
    """删除通知渠道"""
    if not check_auth():
        return jsonify({'error': '未授权'}), 401
    
    delete_notify_channel(channel_id)
    return jsonify({'success': True})

@app.route('/api/notify-channels/<int:channel_id>/test', methods=['POST'])
def api_test_channel(channel_id):
    """测试通知渠道"""
    channels = get_all_notify_channels()
    channel = next((c for c in channels if c['id'] == channel_id), None)
    
    if not channel:
        return jsonify({'error': '通知渠道不存在'}), 404
    
    from notify import notifier
    test_monitor = {'id': 0, 'name': '测试监控', 'type': 'http', 'target': 'https://example.com'}
    success = notifier.send(channel, test_monitor, 1, '这是一条测试通知')
    
    return jsonify({'success': success})

# ============ 事件日志 ============

@app.route('/api/events', methods=['GET'])
def api_get_events():
    """获取事件日志"""
    limit = request.args.get('limit', 50, type=int)
    events = get_recent_events(limit)
    return jsonify({'events': events})

# ============ 统计数据 ============

@app.route('/api/stats', methods=['GET'])
def api_get_stats():
    """获取统计数据"""
    monitors = get_all_monitors()
    
    total = len(monitors)
    online = 0
    uptimes = []
    response_times = []
    
    for m in monitors:
        latest = get_latest_status(m['id'])
        if latest and latest['status'] == 1:
            online += 1
        
        uptime = get_uptime_stats(m['id'], 30)
        uptimes.append(uptime)
        
        avg_time = get_avg_response_time(m['id'], 24)
        if avg_time > 0:
            response_times.append(avg_time)
    
    return jsonify({
        'total': total,
        'online': online,
        'offline': total - online,
        'avg_uptime': round(sum(uptimes) / len(uptimes), 2) if uptimes else 100,
        'avg_response_time': round(sum(response_times) / len(response_times), 2) if response_times else 0
    })

if __name__ == '__main__':
    print("正在初始化数据库...")
    init_db()
    
    print("正在启动调度器...")
    init_scheduler()
    
    print("执行首次检查...")
    threading.Thread(target=run_all_checks).start()
    
    print("\n" + "="*50)
    print("  网站监控系统已启动")
    print("  访问 http://localhost:5000 查看监控面板")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
