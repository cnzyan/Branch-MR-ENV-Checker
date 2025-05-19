import os
import time
import threading
import webbrowser
import json
import requests
import configparser
import chardet
import base64
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import tkinter as tk
from tkinter import ttk, messagebox,scrolledtext
from PIL import Image, ImageDraw
import pystray
import flask
from flask import send_from_directory
import queue
import logging
import sys
import platform
import hashlib
import traceback
import portalocker
import socket
# ./.venv/scripts/activate.ps1
# pyinstaller -F -w -i icon.ico --add-data "templates;templates" --add-data "static;static" --add-data "setup.ini;." --add-data "icon.ico;." bmrec_gui.py
# pyinstaller -F -w  --add-data "frontend_gui.htm;." bmrec_gui.py

# 常量配置
CONFIG_PATH = './setup.ini'
LOCK_FILE='./state_locker.tmp'
LOG_PATH = './logs'
NO_ALARM = '<img src=\\"\/public\/images\/redAlm.png\\"><label class=\\"redAlm\\">0<\/label><img src=\\"\/public\/images\/ylwAlm.png\\"><label class=\\"ylwAlm\\">0<\/label>'
FRONTEND_TEMPLATE = 'frontend_gui.htm'
VERSION = "5.0.0"
RELEASE_DATE = "2025-05-13"
SERV_PORT = 5000


# 全局状态
class AppState:
    def __init__(self):
        self.monitor_system = None
        self.tray_icon = None
        self.settings_window = None
        self.about_window=None
        self.data_ready = False
        self.result = ""
        self.current_settings = {}
        self.config = configparser.ConfigParser()
        self.gui_queue = queue.Queue()
        self.logger = self.setup_logger()
        self.root = None  # Tkinter根窗口
        self.flask_thread = None
        self.monitor_thread = None
        self.alarm_log=[]
        self.alarm_status={}

    @staticmethod
    def setup_logger():
        if not os.path.exists(LOG_PATH):
            os.makedirs(LOG_PATH)
        
        import logging.handlers
        logger = logging.getLogger('MonitorSystem')
        logger.setLevel(logging.INFO)
        
        # handler = logging.FileHandler(os.path.join(LOG_PATH, 'monitor.log'), encoding='utf-8')
        handler = logging.handlers.TimedRotatingFileHandler(os.path.join(LOG_PATH, 'monitor.log'), encoding='utf-8', when='W0', interval=1, backupCount=52)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        
        return logger

app_state = AppState()

# === GUI组件 ===
class ConsoleWindow:
    def __init__(self, master):
        self.top = tk.Toplevel(master)
        self.top.title("系统控制台")
        self.top.geometry("800x400")
        self.text_area = scrolledtext.ScrolledText(self.top, wrap=tk.WORD)
        self.text_area.pack(fill=tk.BOTH, expand=True)
        self.text_area.configure(state='disabled')
        self.top.protocol("WM_DELETE_WINDOW", self.hide)
    
    def append_log(self, message):
        self.text_area.configure(state='normal')
        self.text_area.insert(tk.END, message + "\n")
        self.text_area.configure(state='disabled')
        self.text_area.see(tk.END)
    
    def show(self):
        self.top.deiconify()
    
    def hide(self):
        self.top.withdraw()

class AboutWindow:
    def __init__(self, master):
        self.top = tk.Toplevel(master) if master else tk.Tk()
        self.top.protocol("WM_DELETE_WINDOW", self.on_close)
        self.top.title("关于")
        self.top.geometry("300x260")

        
        # 居中窗口
        self.center_window()
        info = f"""
        环境监控系统
        
        版本: {VERSION}
        作者: CrazYan /w DeepSeek
        发布日期: {RELEASE_DATE}
        
        Python版本: {platform.python_version()}
        操作系统: {platform.system()} {platform.release()}
        """
        ttk.Label(self.top, text=info, justify=tk.LEFT).pack(padx=20, pady=20)
        ttk.Button(self.top, text="确定", command=self.on_close).pack(pady=5)
        # 防止重复打开
        self.top.grab_set()
        
    def center_window(self):
        self.top.update_idletasks()
        width = self.top.winfo_width()
        height = self.top.winfo_height()
        x = (self.top.winfo_screenwidth() // 2) - (width // 2)
        y = (self.top.winfo_screenheight() // 2) - (height // 2)
        self.top.geometry(f'+{x}+{y}')
        
    def on_close(self):
        self.top.grab_release()
        self.top.destroy()
        app_state.about_window = None
class MonitorSystem:
    def __init__(self):
        self.serv_port=SERV_PORT
        self.servers = []
        self.server_names = []
        self.users = []
        self.passwords = []
        self.email_settings = {}
        self.load_config()

    def load_config(self):
        if not os.path.isfile(CONFIG_PATH):
            self.create_default_config()

        with open(CONFIG_PATH, "rb") as f:
            encoding = chardet.detect(f.read())["encoding"]
        
        app_state.config.read(CONFIG_PATH, encoding=encoding)
        
        # 服务器设置
        self.serv_port = app_state.config.get("Config", "serv_port", fallback="5000"),
        self.servers = app_state.config.get("Config", "servers", fallback="127.0.0.1").split(",")
        self.server_names = app_state.config.get("Config", "names", fallback="INVT集成机柜").split(",")
        self.users = app_state.config.get("Config", "users", fallback="admin").split(",")
        self.passwords = app_state.config.get("Config", "passwords", fallback="123456").split(",")
        
        # 邮件设置
        self.email_settings = {
            "smtp_host": app_state.config.get("Email", "smtp_host", fallback="smtp.qq.com"),
            "smtp_port": app_state.config.get("Email", "smtp_port", fallback="465"),
            "mail_user": app_state.config.get("Email", "mail_user", fallback="cc@qq.com"),
            "mail_pass": app_state.config.get("Email", "mail_pass", fallback="cc"),
            "sender_email": app_state.config.get("Email", "sender_email", fallback="cc@qq.com"),
            "email_receivers": app_state.config.get("Email", "email_receivers", fallback="cc@qq.com").split(","),
            "smtptype": app_state.config.get("Email", "smtptype", fallback="SSL")
        }
        
        app_state.current_settings = {
            "serv_port": ",".join(self.serv_port),
            "servers": ",".join(self.servers),
            "names": ",".join(self.server_names),
            "users": ",".join(self.users),
            "passwords": ",".join(self.passwords),
            **self.email_settings,
            "email_receivers": ",".join(self.email_settings["email_receivers"])
        }

    def create_default_config(self):
        app_state.config["Config"] = {
            "serv_port": "5000",
            "servers": "127.0.0.1",
            "names": "INVT集成机柜",
            "users": "admin",
            "passwords": "123456"
        }

        app_state.config["Email"] = {
            "smtp_host": "smtp.qq.com",
            "smtp_port": "465",
            "mail_user": "cc@qq.com",
            "mail_pass": "cc",
            "sender_email": "cc@qq.com",
            "email_receivers": "cc@qq.com",
            "smtptype": "SSL"
        }

        with open(CONFIG_PATH, "w",encoding="utf-8") as configfile:
            app_state.config.write(configfile)

    def save_config(self, new_settings):
        app_state.current_settings = new_settings
        
        app_state.config["Config"] = {
            "serv_port": new_settings["serv_port"],
            "servers": new_settings["servers"],
            "names": new_settings["names"],
            "users": new_settings["users"],
            "passwords": new_settings["passwords"]
        }

        app_state.config["Email"] = {
            "smtp_host": new_settings["smtp_host"],
            "smtp_port": new_settings["smtp_port"],
            "mail_user": new_settings["mail_user"],
            "mail_pass": new_settings["mail_pass"],
            "sender_email": new_settings["sender_email"],
            "email_receivers": new_settings["email_receivers"],
            "smtptype": new_settings["smtptype"]
        }

        with open(CONFIG_PATH, "w",encoding="utf-8") as configfile:
            app_state.config.write(configfile)
        
        self.load_config()

    def get_server_data(self, server, server_name_last="", user_last="", password_last=""):
            
        result = ""
        try:
            index = self.servers.index(server)
            server_name = self.server_names[index]
            user = self.users[index]
            password = self.passwords[index]
        except (ValueError, IndexError):
            server_name = server_name_last or server
            user = user_last or "admin"
            password = password_last or "123456"
        # 发送账号密码
        send_passport=False
        if send_passport:
            result = f'{{"addr":"{server_name}","url":"http://{server}/views/login.php","user":"{user}","password":"{password}",'
        else:
            result = f'{{"addr":"{server_name}","url":"http://{server}/",'
        try:
            # 新建一个alarm
            alm_log_new=None
            with requests.Session() as r_session:
                # 登录
                login_url = f"http://{server}/views/login.php"
                r = r_session.post(login_url, data={"usern": user, "psw": password}, timeout=10, verify=False)
                
                if r.status_code == 200:
                    result += '"online":"true",'
                    r_session.cookies.set("curlangC", "cn")
                    
                    # 获取报警信息
                    alarm_url = f"http://{server}/action/curAlm_act.php"
                    r = r_session.post(alarm_url,data={"alm_sts":"1"}, verify=False).text
                    
                    if NO_ALARM not in r:
                        app_state.alarm_status[server]=1
                        dataj = json.loads(r)
                        content = str(dataj['allAlm'])
                        app_state.logger.info(dataj)
                        if content=="":
                            pass
                        else:
                            content = str(dataj['allAlm']['all'])
                        app_state.logger.info(content)
                        alm_log_new=server_name+str(hashlib.md5(content.encode("utf-8")).hexdigest())+str(time.strftime("%Y-%m-%d %H",time.localtime()))
                        # time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())
                        # datetime.datetime.now().strftime("%Y-%m-%d %H")
                        if alm_log_new in app_state.alarm_log:
                            pass
                        else:
                            app_state.logger.info(alm_log_new)
                            m_subject = f'动环报警-{server_name}'
                            m_content = content
                            
                            app_state.alarm_log.append(alm_log_new)
                            
                            self.send_email(
                                m_subject, m_content,
                                self.email_settings["email_receivers"],
                                self.email_settings["smtp_host"],
                                self.email_settings["smtp_port"],
                                self.email_settings["mail_user"],
                                self.email_settings["mail_pass"],
                                self.email_settings["sender_email"],
                                self.email_settings["smtptype"]
                            )
                    else:
                        try:
                            if(app_state.alarm_status[server]==1):
                                app_state.alarm_status[server]=0
                                m_subject = f'动环报警-{server_name}'
                                m_content = '报警解除'
                                alm_log_new=server_name+':'+m_content+str(time.strftime("%Y-%m-%d %H",time.localtime()))
                                app_state.alarm_log.append(alm_log_new)
                                
                                m_content = '报警解除'+ str(time.strftime("%Y-%m-%d %H:%M:%S",time.localtime()))
                                
                                self.send_email(
                                    m_subject, m_content,
                                    self.email_settings["email_receivers"],
                                    self.email_settings["smtp_host"],
                                    self.email_settings["smtp_port"],
                                    self.email_settings["mail_user"],
                                    self.email_settings["mail_pass"],
                                    self.email_settings["sender_email"],
                                    self.email_settings["smtptype"]
                                )  
                        except:
                            app_state.alarm_status[server]=0
                        pass
                    result += '"alarm":' + r + ","
                    
                    # 获取系统数据
                    data_url = f"http://{server}/action/sys_view_act.php"
                    r = r_session.post(data_url, verify=False).text
                    result += '"data":' + r + ","
                    
                    # 获取AC数据
                    ac_url = f"http://{server}/action/ac_sts_act.php"
                    r = r_session.post(ac_url, data={"curId": 0}, verify=False).text
                    result += '"ac":' + self._format_json(r) + ','
                    
                    # 获取电源数据
                    power_url = f"http://{server}/action/meter_sts_act.php"
                    r = r_session.post(power_url, data={"curId": 0, "mode": "sts"}, verify=False).text
                    result += '"power":' + self._format_json(r) + ','
                    
                    # 获取UPS数据
                    ups_url = f"http://{server}/action/ups_sts_act.php"
                    r = r_session.post(ups_url, data={"curId": 0}, verify=False).text
                    result += '"ups":' + self._format_json(r) + ','
                    
                    # 获取温湿度
                    temp_url = f"http://{server}/action/humiture_views_act.php"
                    r = r_session.post(temp_url, verify=False).text
                    temp, humi = self._parse_temp_humi(r)
                    result += f'"temp":"{temp}","humi":"{humi}",'
                    
                    # 获取漏水检测
                    leak_url = f"http://{server}/action/leak_views_act.php"
                    r = r_session.post(leak_url, verify=False).text
                    leak = self._parse_leak(r)
                    result += f'"leak":"{leak}"'
                else:
                    app_state.alarm_status[server]=1
                    alm_log_new=server_name+'-设备连接异常-'+str(time.strftime("%Y-%m-%d %H",time.localtime()))
                    if alm_log_new in app_state.alarm_log:
                        pass
                    else:
                        app_state.logger.info(alm_log_new)
                        m_subject = f'动环报警-{server_name}'
                        m_content = alm_log_new
                        
                        app_state.alarm_log.append(alm_log_new)
                        
                        self.send_email(
                            m_subject, m_content,
                            self.email_settings["email_receivers"],
                            self.email_settings["smtp_host"],
                            self.email_settings["smtp_port"],
                            self.email_settings["mail_user"],
                            self.email_settings["mail_pass"],
                            self.email_settings["sender_email"],
                            self.email_settings["smtptype"]
                        )
                    result += '"online":"false"'
        except Exception as e:
            app_state.logger.error(f"获取服务器数据出错: {str(e)}")
            app_state.alarm_status[server]=1
            alm_log_new=server_name+'-设备离线-'+str(time.strftime("%Y-%m-%d %H",time.localtime()))

            if alm_log_new in app_state.alarm_log:
                pass
            else:

                app_state.logger.info(alm_log_new)
                m_subject = f'动环报警-{server_name}'
                m_content = f"{server_name}设备离线，请检查网络连接或设备状态。" + \
                    str(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
                app_state.alarm_log.append(alm_log_new)
                
                self.send_email(
                    m_subject, m_content,
                    self.email_settings["email_receivers"],
                    self.email_settings["smtp_host"],
                    self.email_settings["smtp_port"],
                    self.email_settings["mail_user"],
                    self.email_settings["mail_pass"],
                    self.email_settings["sender_email"],
                    self.email_settings["smtptype"]
                )
            result += '"online":"false"'

        result += '}'
        return result, server_name, user, password

    def _format_json(self, json_str):
        try:
            data = json.loads(json_str)
            return json.dumps(data, ensure_ascii=False)
        except:
            return '""'

    def _parse_temp_humi(self, data):
        try:
            dataj = json.loads(data)
            state_th = str(dataj["hotData"]) if str(dataj["hotData"]) != "[]" else str(dataj["coldData"])
            temp = re.findall(r'\d*\.?\d*℃', state_th)[0]
            humi = re.findall(r'\d*\.?\d*%RH', state_th)[0]
            return temp, humi
        except:
            return "--", "--"

    def _parse_leak(self, data):
        try:
            dataj = json.loads(data)
            state_leak = str(dataj["lkDtlData"][0])
            return state_leak.split("</label> </div>")[0].split("</label> <label>")[1]
        except:
            return "--"

    def send_email(self, subject, content, to_mail, smtp_host, smtp_port, mail_user, mail_pass, sender_email, smtp_type):
        try:
            message = MIMEMultipart()
            message["From"] = sender_email
            message["To"] = ",".join(to_mail) if isinstance(to_mail, list) else to_mail
            message["Subject"] = subject
            message.attach(MIMEText(content, "html", "utf-8"))

            if smtp_type == "SSL":
                with smtplib.SMTP_SSL(smtp_host, int(smtp_port)) as s:
                    s.login(mail_user, mail_pass)
                    s.send_message(message)
            else:
                with smtplib.SMTP(smtp_host, int(smtp_port)) as s:
                    if smtp_type == "TLS":
                        s.starttls()
                    s.login(mail_user, mail_pass)
                    s.send_message(message)
            
            app_state.logger.info("邮件发送成功")
        except Exception as e:
            app_state.logger.error(f"邮件发送失败: {str(e)}")

class SettingsWindow:
    def __init__(self, master=None):
        self.top = tk.Toplevel(master) if master else tk.Tk()
        self.top.title("监控系统设置")
        self.top.geometry("650x550")
        self.top.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 防止重复打开
        self.top.grab_set()
        
        self.create_widgets()
        self.load_settings()
        
        # 居中窗口
        self.center_window()

    def center_window(self):
        self.top.update_idletasks()
        width = self.top.winfo_width()
        height = self.top.winfo_height()
        x = (self.top.winfo_screenwidth() // 2) - (width // 2)
        y = (self.top.winfo_screenheight() // 2) - (height // 2)
        self.top.geometry(f'+{x}+{y}')

    def create_widgets(self):
        main_frame = ttk.Frame(self.top)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill='both', expand=True)
        
        # 服务器设置标签页
        server_frame = ttk.Frame(notebook)
        notebook.add(server_frame, text="服务器设置")
        
        ttk.Label(server_frame, text="WEB服务端口:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.servport_entry = ttk.Entry(server_frame, width=60)
        self.servport_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(server_frame, text="监控地址(多个用逗号分隔):").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.servers_entry = ttk.Entry(server_frame, width=60)
        self.servers_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(server_frame, text="监控名称(多个用逗号分隔):").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.names_entry = ttk.Entry(server_frame, width=60)
        self.names_entry.grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Label(server_frame, text="监控用户名(多个用逗号分隔):").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        self.users_entry = ttk.Entry(server_frame, width=60)
        self.users_entry.grid(row=3, column=1, padx=5, pady=5)
        
        ttk.Label(server_frame, text="监控密码(多个用逗号分隔):").grid(row=4, column=0, padx=5, pady=5, sticky='e')
        self.passwords_entry = ttk.Entry(server_frame, width=60) #, show="*"
        self.passwords_entry.grid(row=4, column=1, padx=5, pady=5)
        
        # 邮件设置标签页
        email_frame = ttk.Frame(notebook)
        notebook.add(email_frame, text="邮件设置")
        
        ttk.Label(email_frame, text="SMTP服务器:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.smtp_host_entry = ttk.Entry(email_frame, width=60)
        self.smtp_host_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(email_frame, text="SMTP端口:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.smtp_port_entry = ttk.Entry(email_frame, width=60)
        self.smtp_port_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(email_frame, text="邮箱账号:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.mail_user_entry = ttk.Entry(email_frame, width=60)
        self.mail_user_entry.grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Label(email_frame, text="邮箱密码:").grid(row=3, column=0, padx=5, pady=5, sticky='e')
        self.mail_pass_entry = ttk.Entry(email_frame, width=60, show="*")
        self.mail_pass_entry.grid(row=3, column=1, padx=5, pady=5)
        
        ttk.Label(email_frame, text="发件人邮箱:").grid(row=4, column=0, padx=5, pady=5, sticky='e')
        self.sender_email_entry = ttk.Entry(email_frame, width=60)
        self.sender_email_entry.grid(row=4, column=1, padx=5, pady=5)
        
        ttk.Label(email_frame, text="收件人邮箱(多个用逗号分隔):").grid(row=5, column=0, padx=5, pady=5, sticky='e')
        self.email_receivers_entry = ttk.Entry(email_frame, width=60)
        self.email_receivers_entry.grid(row=5, column=1, padx=5, pady=5)
        
        ttk.Label(email_frame, text="SMTP类型:").grid(row=6, column=0, padx=5, pady=5, sticky='e')
        self.smtptype_combobox = ttk.Combobox(email_frame, values=["SSL", "TLS", "None"], width=57)
        self.smtptype_combobox.grid(row=6, column=1, padx=5, pady=5)
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(button_frame, text="保存", command=self.save_settings).pack(side='right', padx=5)
        ttk.Button(button_frame, text="取消", command=self.on_close).pack(side='right', padx=5)

    def load_settings(self):
        self.servport_entry.insert(0, app_state.current_settings["serv_port"])
        self.servers_entry.insert(0, app_state.current_settings["servers"])
        self.names_entry.insert(0, app_state.current_settings["names"])
        self.users_entry.insert(0, app_state.current_settings["users"])
        self.passwords_entry.insert(0, app_state.current_settings["passwords"])
        self.smtp_host_entry.insert(0, app_state.current_settings["smtp_host"])
        self.smtp_port_entry.insert(0, app_state.current_settings["smtp_port"])
        self.mail_user_entry.insert(0, app_state.current_settings["mail_user"])
        self.mail_pass_entry.insert(0, app_state.current_settings["mail_pass"])
        self.sender_email_entry.insert(0, app_state.current_settings["sender_email"])
        self.email_receivers_entry.insert(0, app_state.current_settings["email_receivers"])
        self.smtptype_combobox.set(app_state.current_settings["smtptype"])

    def save_settings(self):
        new_settings = {
            "serv_port":self.servport_entry.get(),
            "servers": self.servers_entry.get(),
            "names": self.names_entry.get(),
            "users": self.users_entry.get(),
            "passwords": self.passwords_entry.get(),
            "smtp_host": self.smtp_host_entry.get(),
            "smtp_port": self.smtp_port_entry.get(),
            "mail_user": self.mail_user_entry.get(),
            "mail_pass": self.mail_pass_entry.get(),
            "sender_email": self.sender_email_entry.get(),
            "email_receivers": self.email_receivers_entry.get(),
            "smtptype": self.smtptype_combobox.get()
        }
        
        try:
            app_state.monitor_system.save_config(new_settings)
            messagebox.showinfo("成功", "设置已保存")
            self.on_close()
        except Exception as e:
            messagebox.showerror("错误", f"保存设置时出错: {str(e)}")

    def on_close(self):
        self.top.grab_release()
        self.top.destroy()
        app_state.settings_window = None
# === 路径处理 ===
def get_base_path():
    """获取资源基础路径"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_template_path():
    """获取前端模板路径"""
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
    external_path = os.path.join(exe_dir, FRONTEND_TEMPLATE)
    return external_path if os.path.exists(external_path) else os.path.join(get_base_path(), FRONTEND_TEMPLATE)

def create_flask_app():
    app = flask.Flask(__name__)
    
    @app.route('/')
    def serve_frontend():
        template_path = get_template_path()
        if os.path.exists(template_path):
            return send_from_directory(os.path.dirname(template_path), 
                                      os.path.basename(template_path))
        return "Frontend template not found", 404
    
    @app.route('/dev_list', methods=['GET'])
    def http_resp():
        callback = flask.request.args.get('callback')
        if not callback:
            return "Error: No callback function provided.", 400

        while not app_state.data_ready:
            time.sleep(0.1)
            
        response = f"{callback}({app_state.result})"
        return response, 200, {'Content-Type': 'application/javascript; charset=utf-8'}
    
    return app

def run_flask():
    app = create_flask_app()
    # 检查端口占用状态
    app_port=app_state.config.get("Config", "serv_port", fallback=SERV_PORT)
    app_port_init=app_port
    port_available=False
    while port_available==False:
        port_available=check_port_available(app_port)
        if port_available==False:
            if app_port==app_port_init and app_port!=SERV_PORT:
                app_port=SERV_PORT
            else:
                app_port+=1
    app.run(host='0.0.0.0', port=app_port, debug=True, use_reloader=False)

def monitor_worker():
    while True:
        try:
            result_new = '{"num":"' + str(len(app_state.monitor_system.servers)) + '","servers":['
            
            server_name_last, user_last, password_last = "", "", ""
            for i, server in enumerate(app_state.monitor_system.servers):
                if i > 0:
                    result_new += ','
                
                result_get, server_name_last, user_last, password_last = app_state.monitor_system.get_server_data(
                    server, server_name_last, user_last, password_last)
                result_new += result_get
            
            result_new += "]}"
            app_state.result = result_new
            app_state.data_ready = True
        except Exception as e:
            e1=traceback.extract_tb(e.__traceback__)[1]
            app_state.logger.error(f"监控工作线程出错: {e1}:{str(e)}")
        
        time.sleep(60)

def on_show_web(icon, item):
    webbrowser.open("http://localhost:"+app_state.config.get("Config", "serv_port", fallback="5000"))

def on_show_about(icon, item):    
    def show_about():
        if app_state.about_window is None or not app_state.about_window.top.winfo_exists():
            app_state.about_window = AboutWindow(app_state.root)
        else:
            app_state.about_window.top.lift()
    app_state.gui_queue.put(show_about)
        
def on_show_settings(icon, item):
    def create_window():
        if app_state.settings_window is None or not app_state.settings_window.top.winfo_exists():
            app_state.settings_window = SettingsWindow(app_state.root)
        else:
            app_state.settings_window.top.lift()
    
    app_state.gui_queue.put(create_window)

def on_quit(icon, item):
    def shutdown():
        if app_state.settings_window and app_state.settings_window.top.winfo_exists():
            app_state.settings_window.top.destroy()
        if app_state.root:
            app_state.root.quit()
        portalocker.unlock(locker_file)
        locker_file.close()
        os._exit(0)
    
    app_state.gui_queue.put(shutdown)

def create_tray_icon():
    # 创建图标图像
    image = Image.new('RGB', (64, 64), color='white')
    draw = ImageDraw.Draw(image)
    draw.rectangle([(10, 10), (54, 54)], fill='blue')
    draw.text((20, 20), "MS", fill="white")
    
    # 创建系统托盘图标
    icon = pystray.Icon(
        "monitor_system",
        image,
        "环境监控系统",
        menu=pystray.Menu(
            pystray.MenuItem("打开监控页面", on_show_web),
            pystray.MenuItem("设置", on_show_settings),
            pystray.MenuItem("关于", on_show_about),
            pystray.MenuItem("退出", on_quit)
        )
    )
    
    return icon

def process_gui_events():
    while True:
        try:
            task = app_state.gui_queue.get_nowait()
            if callable(task):
                task()
        except queue.Empty:
            break
    app_state.root.after(100, process_gui_events)

def main():
    # 初始化Tkinter根窗口
    app_state.root = tk.Tk()
    app_state.root.withdraw()
    
    # 初始化监控系统
    app_state.monitor_system = MonitorSystem()
    
    # 启动监控线程
    app_state.monitor_thread = threading.Thread(target=monitor_worker, daemon=True)
    app_state.monitor_thread.start()
    
    # 启动Flask服务器线程
    app_state.flask_thread = threading.Thread(target=run_flask, daemon=True)
    app_state.flask_thread.start()
    
    # 创建系统托盘图标
    app_state.tray_icon = create_tray_icon()
    
    # 启动GUI事件处理循环
    app_state.root.after(100, process_gui_events)
    
    # 运行系统托盘图标
    def run_tray():
        try:
            app_state.tray_icon.run()
        except Exception as e:
            app_state.logger.error(f"系统托盘运行错误: {str(e)}")
            sys.exit(1)
    
    threading.Thread(target=run_tray, daemon=True).start()
    # 延时启动浏览器界面
    def start_browser():
        while 1==1:
            try:
                r=requests.get("http://localhost:"+app_state.config.get("Config", "serv_port", fallback="5000")+"/dev_list?callback=1233")
                if r.status_code==200:
                    break
                else:
                    time.sleep(1)
            except:
                time.sleep(1)
        on_show_web("","")
        pass
    threading.Thread(target=start_browser, daemon=True).start()
    # 运行Tkinter主循环
    try:
        app_state.root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        if app_state.tray_icon:
            app_state.tray_icon.stop()
def check_port_available(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = False
    port=int(port)
    try:
        sock.bind(('127.0.0.1', port))
        result = True
    except socket.error:
        result = False
    finally:
        sock.close()
    return result
if __name__ == "__main__":

    locker_file=None #锁文件
    run_2nd=False #重复执行检测标志
    try:
        locker_file= open(LOCK_FILE,'a')
        portalocker.lock(locker_file, portalocker.LOCK_EX | portalocker.LOCK_NB)
        run_2nd=False
        main()
    except:
        app_state.logger.error("重复运行监控系统")
        run_2nd=True
    finally:
        if run_2nd==False:
            portalocker.unlock(locker_file)
        locker_file.close()
        os._exit(0)