# -*- coding: utf-8 -*-
import requests
import socket
import ssl
from datetime import datetime
from urllib.parse import urlparse
import json

class MonitorChecker:
    """监控检查器"""
    
    def __init__(self, timeout=30):
        self.timeout = timeout
    
    def check(self, monitor):
        """根据监控类型执行检查"""
        monitor_type = monitor['type']
        
        checkers = {
            'http': self.check_http,
            'https': self.check_http,
            'keyword': self.check_keyword,
            'port': self.check_port,
            'tcp': self.check_port,
            'ping': self.check_ping,
            'ssl': self.check_ssl_cert,
            'push': self.check_push,
            'mysql': self.check_mysql,
            'redis': self.check_redis,
        }
        
        checker = checkers.get(monitor_type, self.check_http)
        try:
            return checker(monitor)
        except Exception as e:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': str(e)
            }
    
    def check_http(self, monitor):
        """HTTP/HTTPS 检查"""
        url = monitor['target']
        method = monitor.get('method', 'GET')
        timeout = monitor.get('timeout', self.timeout)
        expected_status = monitor.get('expected_status', 200)
        
        try:
            headers_str = monitor.get('headers', '{}')
            headers = json.loads(headers_str) if isinstance(headers_str, str) else headers_str
        except:
            headers = {}
        
        headers.setdefault('User-Agent', 'SiteMonitor/1.0')
        
        try:
            start_time = datetime.now()
            
            if method.upper() == 'POST':
                body = monitor.get('body', '')
                response = requests.post(url, data=body, headers=headers, 
                                        timeout=timeout, allow_redirects=True, verify=True)
            elif method.upper() == 'HEAD':
                response = requests.head(url, headers=headers, 
                                        timeout=timeout, allow_redirects=True, verify=True)
            else:
                response = requests.get(url, headers=headers, 
                                       timeout=timeout, allow_redirects=True, verify=True)
            
            response_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # 检查状态码
            status = 1 if response.status_code == expected_status or response.status_code < 400 else 0
            
            return {
                'status': status,
                'response_time': response_time,
                'status_code': response.status_code,
                'message': 'OK' if status else f'状态码 {response.status_code}'
            }
            
        except requests.exceptions.Timeout:
            return {
                'status': 0,
                'response_time': timeout * 1000,
                'status_code': 0,
                'message': '请求超时'
            }
        except requests.exceptions.SSLError as e:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': f'SSL证书错误: {str(e)[:100]}'
            }
        except requests.exceptions.ConnectionError:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': '连接失败'
            }
        except Exception as e:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': str(e)[:200]
            }
    
    def check_keyword(self, monitor):
        """关键词检查"""
        result = self.check_http(monitor)
        
        if result['status'] == 1 and monitor.get('keyword'):
            keyword = monitor['keyword']
            url = monitor['target']
            
            try:
                response = requests.get(url, timeout=monitor.get('timeout', self.timeout))
                if keyword in response.text:
                    result['message'] = f'包含关键词: {keyword}'
                else:
                    result['status'] = 0
                    result['message'] = f'未找到关键词: {keyword}'
            except:
                pass
        
        return result
    
    def check_port(self, monitor):
        """TCP端口检查"""
        target = monitor['target']
        port = monitor.get('port', 80)
        timeout = monitor.get('timeout', self.timeout)
        
        # 解析目标
        if ':' in target and not target.startswith('['):
            parts = target.rsplit(':', 1)
            host = parts[0]
            port = int(parts[1])
        else:
            host = target
        
        try:
            start_time = datetime.now()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            response_time = int((datetime.now() - start_time).total_seconds() * 1000)
            sock.close()
            
            if result == 0:
                return {
                    'status': 1,
                    'response_time': response_time,
                    'status_code': 0,
                    'message': f'端口 {port} 开放'
                }
            else:
                return {
                    'status': 0,
                    'response_time': 0,
                    'status_code': 0,
                    'message': f'端口 {port} 未开放'
                }
        except socket.timeout:
            return {
                'status': 0,
                'response_time': timeout * 1000,
                'status_code': 0,
                'message': '连接超时'
            }
        except Exception as e:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': str(e)
            }
    
    def check_ping(self, monitor):
        """Ping检查（通过TCP模拟）"""
        monitor_copy = dict(monitor)
        monitor_copy['port'] = 80
        return self.check_port(monitor_copy)
    
    def check_ssl_cert(self, monitor):
        """SSL证书检查"""
        target = monitor['target']
        
        # 提取域名
        if target.startswith('http'):
            parsed = urlparse(target)
            hostname = parsed.hostname
        else:
            hostname = target.split(':')[0]
        
        port = 443
        
        try:
            start_time = datetime.now()
            context = ssl.create_default_context()
            
            with socket.create_connection((hostname, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
            
            response_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # 解析证书过期时间
            expire_date_str = cert['notAfter']
            expire_date = datetime.strptime(expire_date_str, '%b %d %H:%M:%S %Y %Z')
            days_left = (expire_date - datetime.now()).days
            
            if days_left <= 0:
                return {
                    'status': 0,
                    'response_time': response_time,
                    'status_code': days_left,
                    'message': '证书已过期'
                }
            elif days_left <= 7:
                return {
                    'status': 0,
                    'response_time': response_time,
                    'status_code': days_left,
                    'message': f'证书将在 {days_left} 天后过期'
                }
            elif days_left <= 30:
                return {
                    'status': 1,
                    'response_time': response_time,
                    'status_code': days_left,
                    'message': f'证书剩余 {days_left} 天（即将过期）'
                }
            else:
                return {
                    'status': 1,
                    'response_time': response_time,
                    'status_code': days_left,
                    'message': f'证书有效，剩余 {days_left} 天'
                }
                
        except ssl.SSLError as e:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': f'SSL错误: {str(e)[:100]}'
            }
        except Exception as e:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': str(e)[:200]
            }
    
    def check_push(self, monitor):
        """推送检查 - 通过心跳判断"""
        from database import get_last_heartbeat
        from datetime import timedelta
        
        last_beat = get_last_heartbeat(monitor['id'])
        
        if not last_beat:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': '从未收到心跳'
            }
        
        # 检查心跳是否超时（默认间隔的2倍）
        interval = monitor.get('interval', 60)
        beat_time = datetime.strptime(last_beat['created_at'], '%Y-%m-%d %H:%M:%S')
        timeout_threshold = datetime.now() - timedelta(seconds=interval * 2)
        
        if beat_time < timeout_threshold:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': f'心跳超时，上次: {last_beat["created_at"]}'
            }
        else:
            return {
                'status': last_beat['status'],
                'response_time': 0,
                'status_code': 0,
                'message': last_beat.get('message', 'OK')
            }
    
    def check_mysql(self, monitor):
        """MySQL数据库检查"""
        try:
            import pymysql
        except ImportError:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': '缺少 pymysql 模块'
            }
        
        target = monitor['target']
        timeout = monitor.get('timeout', self.timeout)
        
        # 解析连接字符串: host:port 或 user:pass@host:port/db
        try:
            if '@' in target:
                auth, rest = target.split('@', 1)
                user, password = auth.split(':', 1)
                if '/' in rest:
                    host_port, db = rest.rsplit('/', 1)
                else:
                    host_port = rest
                    db = ''
            else:
                user, password = 'root', ''
                host_port = target
                db = ''
            
            if ':' in host_port:
                host, port = host_port.rsplit(':', 1)
                port = int(port)
            else:
                host = host_port
                port = 3306
            
            start_time = datetime.now()
            conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=db if db else None, connect_timeout=timeout
            )
            conn.ping()
            response_time = int((datetime.now() - start_time).total_seconds() * 1000)
            conn.close()
            
            return {
                'status': 1,
                'response_time': response_time,
                'status_code': 0,
                'message': 'MySQL 连接正常'
            }
        except Exception as e:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': f'MySQL 连接失败: {str(e)[:100]}'
            }
    
    def check_redis(self, monitor):
        """Redis数据库检查"""
        try:
            import redis as redis_client
        except ImportError:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': '缺少 redis 模块'
            }
        
        target = monitor['target']
        timeout = monitor.get('timeout', self.timeout)
        
        try:
            # 解析 redis://host:port 或 host:port
            if target.startswith('redis://'):
                target = target[8:]
            
            if ':' in target:
                host, port = target.rsplit(':', 1)
                port = int(port)
            else:
                host = target
                port = 6379
            
            start_time = datetime.now()
            r = redis_client.Redis(host=host, port=port, socket_timeout=timeout)
            r.ping()
            response_time = int((datetime.now() - start_time).total_seconds() * 1000)
            r.close()
            
            return {
                'status': 1,
                'response_time': response_time,
                'status_code': 0,
                'message': 'Redis 连接正常'
            }
        except Exception as e:
            return {
                'status': 0,
                'response_time': 0,
                'status_code': 0,
                'message': f'Redis 连接失败: {str(e)[:100]}'
            }

