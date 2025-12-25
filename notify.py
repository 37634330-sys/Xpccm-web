# -*- coding: utf-8 -*-
import requests
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

class Notifier:
    """通知发送器"""
    
    def __init__(self):
        self.handlers = {
            'email': self.send_email,
            'webhook': self.send_webhook,
            'wechat': self.send_wechat,
            'telegram': self.send_telegram,
            'bark': self.send_bark,
            'pushplus': self.send_pushplus,
            'serverchan': self.send_serverchan,
        }
    
    def send(self, channel, monitor, status, message):
        """发送通知"""
        channel_type = channel['type']
        handler = self.handlers.get(channel_type)
        
        if not handler:
            print(f"未知的通知类型: {channel_type}")
            return False
        
        try:
            config = json.loads(channel['config']) if isinstance(channel['config'], str) else channel['config']
            return handler(config, monitor, status, message)
        except Exception as e:
            print(f"发送通知失败 [{channel_type}]: {e}")
            return False
    
    def format_message(self, monitor, status, message):
        """格式化通知消息"""
        status_text = '✅ 恢复正常' if status else '❌ 故障告警'
        time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 兼容 types 数组和旧的 type 字段
        monitor_type = monitor.get('type', '')
        if not monitor_type:
            types = monitor.get('types', ['http'])
            if isinstance(types, str):
                try:
                    types = json.loads(types)
                except:
                    types = ['http']
            monitor_type = ', '.join(t.upper() for t in types)
        else:
            monitor_type = monitor_type.upper()
        
        return {
            'title': f"[{status_text}] {monitor['name']}",
            'content': f"""
监控项目: {monitor['name']}
监控类型: {monitor_type}
监控地址: {monitor['target']}
当前状态: {status_text}
详细信息: {message}
检测时间: {time_str}
""".strip()
        }
    
    def send_email(self, config, monitor, status, message):
        """发送邮件通知"""
        msg_data = self.format_message(monitor, status, message)
        
        try:
            msg = MIMEMultipart()
            msg['From'] = config['from_email']
            msg['To'] = config['to_email']
            msg['Subject'] = msg_data['title']
            
            body = msg_data['content'].replace('\n', '<br>')
            msg.attach(MIMEText(f"<html><body>{body}</body></html>", 'html', 'utf-8'))
            
            if config.get('use_ssl', True):
                server = smtplib.SMTP_SSL(config['smtp_host'], config.get('smtp_port', 465))
            else:
                server = smtplib.SMTP(config['smtp_host'], config.get('smtp_port', 587))
                server.starttls()
            
            server.login(config['smtp_user'], config['smtp_pass'])
            server.send_message(msg)
            server.quit()
            
            print(f"邮件通知已发送: {config['to_email']}")
            return True
        except Exception as e:
            print(f"邮件发送失败: {e}")
            return False
    
    def send_webhook(self, config, monitor, status, message):
        """发送Webhook通知"""
        msg_data = self.format_message(monitor, status, message)
        url = config['url']
        
        payload = {
            'title': msg_data['title'],
            'content': msg_data['content'],
            'monitor': {
                'id': monitor['id'],
                'name': monitor['name'],
                'type': monitor['type'],
                'target': monitor['target']
            },
            'status': status,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            print(f"Webhook通知已发送: {response.status_code}")
            return response.status_code < 400
        except Exception as e:
            print(f"Webhook发送失败: {e}")
            return False
    
    def send_wechat(self, config, monitor, status, message):
        """发送企业微信通知"""
        msg_data = self.format_message(monitor, status, message)
        webhook_url = config['webhook_url']
        
        payload = {
            'msgtype': 'markdown',
            'markdown': {
                'content': f"### {msg_data['title']}\n\n{msg_data['content']}"
            }
        }
        
        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            print(f"企业微信通知已发送: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"企业微信发送失败: {e}")
            return False
    
    def send_telegram(self, config, monitor, status, message):
        """发送Telegram通知"""
        msg_data = self.format_message(monitor, status, message)
        bot_token = config['bot_token']
        chat_id = config['chat_id']
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': f"*{msg_data['title']}*\n\n{msg_data['content']}",
            'parse_mode': 'Markdown'
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            print(f"Telegram通知已发送: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram发送失败: {e}")
            return False
    
    def send_bark(self, config, monitor, status, message):
        """发送Bark通知 (iOS)"""
        msg_data = self.format_message(monitor, status, message)
        server = config.get('server', 'https://api.day.app')
        key = config['key']
        
        url = f"{server}/{key}/{msg_data['title']}/{message}"
        
        try:
            response = requests.get(url, timeout=10)
            print(f"Bark通知已发送: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"Bark发送失败: {e}")
            return False
    
    def send_pushplus(self, config, monitor, status, message):
        """发送PushPlus通知"""
        msg_data = self.format_message(monitor, status, message)
        token = config['token']
        
        url = "http://www.pushplus.plus/send"
        payload = {
            'token': token,
            'title': msg_data['title'],
            'content': msg_data['content'],
            'template': 'txt'
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            print(f"PushPlus通知已发送: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"PushPlus发送失败: {e}")
            return False
    
    def send_serverchan(self, config, monitor, status, message):
        """发送Server酱通知"""
        msg_data = self.format_message(monitor, status, message)
        sendkey = config['sendkey']
        
        url = f"https://sctapi.ftqq.com/{sendkey}.send"
        payload = {
            'title': msg_data['title'],
            'desp': msg_data['content']
        }
        
        try:
            response = requests.post(url, data=payload, timeout=10)
            print(f"Server酱通知已发送: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"Server酱发送失败: {e}")
            return False


# 全局通知器实例
notifier = Notifier()

def send_notification(monitor, status, message):
    """发送通知到所有配置的渠道"""
    from database import get_all_notify_channels
    
    try:
        notify_channel_ids = json.loads(monitor.get('notify_channels', '[]'))
    except:
        notify_channel_ids = []
    
    if not notify_channel_ids:
        return
    
    channels = get_all_notify_channels()
    
    for channel in channels:
        if channel['id'] in notify_channel_ids and channel['enabled']:
            notifier.send(channel, monitor, status, message)

