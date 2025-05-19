import requests
import json
import re
import os
import configparser
import flask 
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import loguru
import chardet
import base64
import time
# ./.venv/scripts/activate.ps1
# pyinstaller -F bmrec.py
def mkdir(path):

    # 去除首位空格
    path = path.strip()
    # 去除尾部 \ 符号
    path = path.rstrip("\\")

    # 判断路径是否存在
    # 存在     True
    # 不存在   False
    isExists = os.path.exists(path)

    # 判断结果
    if not isExists:
        # 如果不存在则创建目录
        # 创建目录操作函数
        os.makedirs(path)

        print(path+' 创建成功')
        return True
    else:
        # 如果目录存在则不创建，并提示目录已存在
        print(path+' 目录已存在')
        return False


def new_thread(func):
    import threading
    from functools import wraps

    @wraps(func)
    def inner(*args, **kwargs):
        # print(f'函数的名字：{func.__name__}')
        # print(f'函数的位置参数：{args}')
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.start()

    return inner


@new_thread
def send_email(
    Subject,
    content,
    tomail,
    smtp_host,
    smtp_port,
    mail_user,
    mail_pass,
    sender_email,
    smtptype,
):  # 发送邮件-准备邮件内容
    # 设置登录及服务器信息
    # 设置email信息
    # 添加一个MIMEmultipart类，处理正文及附件
    message = MIMEMultipart()
    message["From"] = sender_email
    maillist = ""
    temp = []
    if type(tomail) == str:
        temp.append(tomail)
    else:
        temp = tomail
    for mail in temp:
        if maillist == "":
            maillist = maillist + mail
        else:
            maillist = maillist + "," + mail
    # print(maillist)
    message["To"] = maillist
    message["Cc"] = ""
    message["Bcc"] = ""

    # 设置html格式参数
    part1 = MIMEText(content, "html", "utf-8")
    # 添加一个附件
    message["Subject"] = Subject
    message.attach(part1)

    # message.attach(picture)
    return send_mail(message, smtp_host, smtp_port, mail_user, mail_pass, smtptype)


@new_thread
def send_mail(
    message, smtp_host, smtp_port, user=None, passwd=None, security=None
):  # 发送邮件
    """
    Sends a message to a smtp server
    """
    try:
        if security == "SSL":
            s = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            s = smtplib.SMTP(smtp_host, smtp_port)
        # s.set_debuglevel(10)
        s.ehlo()

        if security == "TLS":
            s.starttls()
            s.ehlo()

        if user:
            s.login(user, passwd)

        to_addr_list = []

        if message["To"]:
            to_addr_list.append(message["To"])
        if message["Cc"]:
            to_addr_list.append(message["Cc"])
        if message["Bcc"]:
            to_addr_list.append(message["Bcc"])

        to_addr_list = ",".join(to_addr_list).split(",")

        s.sendmail(message["From"], to_addr_list, message.as_string())
        s.close()
        # save_log("INFO", "邮件发送成功")
        loguru.logger.info("邮件发送成功")
        return True
    except Exception as e:
        # save_log("ERROR", "邮件发送失败"+str(e))
        loguru.logger.error("邮件发送失败" + str(e))
        return False


def prepare_conf_file(configpath):  # 准备配置文件
    if os.path.isfile(configpath) == True:
        pass
    else:
        config.add_section("config")
        config.set("config", "serv_port", r"5000")
        config.set("config", "servers", r"127.0.0.1")
        config.set("config", "names", r"INVT集成机柜")
        config.set("config", "users", r"admin")
        config.set("config", "passwords", r"123456")

        config.add_section("Email")
        config.set("Email", "smtp_host", r"smtp.qq.com")
        config.set("Email", "smtp_port", r"465")
        config.set("Email", "mail_user", r"cc@qq.com")
        config.set("Email", "mail_pass", r"cc")
        config.set("Email", "sender_email", r"cc@qq.com")
        config.set("Email", "email_receivers", r"cc@qq.com")
        config.set("Email", "smtptype", r"SSL")

        # write to file
        config.write(open(configpath, "w"))
        pass
    pass


def get_conf_from_file(config_path, config_section, conf_list):  # 读取配置文件
    conf_default = {
        'serv_port': '5000',
        'servers': '127.0.0.1',
        'names': 'INVT集成机柜',
        'users': 'users',
        'passwords': '123456',
        
        "send_wxmsg": "1",
        "send_email": "1",
        "send_serial": "0",
        "wxmsg_touser": "cra",
        "wxmsg_url_get": "http://pi.tzxy.cn/pi/app/wxadminsiteerr.asp",
        "wxmsg_url_post": "https://pi.tzxy.cn/PI/app/overlimwx.php",
        "wxmsg_method": "POST",
        "secret_seed": "cc",
        
        "smtp_host": "smtp.qq.com",
        "smtp_port": "465",
        "mail_user": "cc@qq.com",
        "mail_pass": "cc",
        "sender_email": "cc@qq.com",
        "smtptype": "SSL",
        "email_receivers": "cc@qq.com",

    }
    with open(config_path, "rb") as f:
        result = chardet.detect(f.read())
        encoding = result["encoding"]
    config.read(config_path, encoding=encoding)
    conf_item_settings = []
    for conf_item in conf_list:
        try:
            conf_item_setting = config[config_section][conf_item]

            # 获取 列表类型的配置项
            if conf_item == "piserver" or conf_item == "email_receivers":
                item_nodes = conf_item_setting.split(",")
                conf_item_setting = []
                for item_node in item_nodes:
                    conf_item_setting.append(item_node)
                # print(conf_item_setting)
        except Exception as e:
            conf_item_setting = conf_default[conf_item]

        print(str(conf_item) + ":" + str(conf_item_setting))
        conf_item_settings.append(conf_item_setting)
        pass
    if len(conf_list) > 1:
        return tuple(conf_item_settings)
    else:
        return conf_item_settings[0]


def get_server(server,server_name_last,user_last,password_last):

    result = ""
    url_login = "http://"+server+"/views/login.php"
    url_alarm = "http://"+server+"/action/curAlm_act.php"
    url_data = "http://"+server+"/action/sys_view_act.php"
    url_ac = "http://"+server+"/action/ac_sts_act.php"
    data_ac = {"curId": 0}
    url_power = "http://"+server+"/action/meter_sts_act.php"
    data_power = {"curId": 0, "mode": "sts"}

    url_ups = "http://"+server+"/action/ups_sts_act.php"
    data_ups = {"curId": 0}
    url_temp = "http://"+server+"/action/humiture_views_act.php"
    data_temp = ""
    url_leak = "http://"+server+"/action/leak_views_act.php"
    data_leak = ""
    index = servers_dict.index(server)
    try:
        server_name = server_names_dict[index]
    except:
        server_name=server_name_last
    server_name_last=server_name
    try:
        user = users_dict[index]
    except:
        user=user_last
    user_last=user
    try:
        password = passwords_dict[index]
    except:
        password=password_last
    password_last=password

    result = result+f'{{"addr":"{server_name}","url":"http://{server}",'
    r_session = requests.Session()
    # r = r_session.get(url=url_login,  verify=False).text
    # print(r)
    data = {"usern": user, "psw": password}
    # print(data)
    try:
        r = r_session.post(url=url_login, data=data, timeout=10,verify=False)
        print(server_name,r.status_code)
        rstatus=r.status_code
    except:
        print(server_name,"离线")
        rstatus=404
    if rstatus==200:
        result = result+'"online":"true",'
        r=r.text

        r_session.cookies.set("curlangC", "cn")
        # print(r)
        # alarm
        r = r_session.post(url=url_alarm, verify=False).text

        if no_alarm in r:
            pass
        else:
            dataj = json.loads(r)
            content = str(dataj['allAlm'])
            m_subject = '动环报警-'+server_name
            m_tomail = email_receivers
            m_content = base64.b64decode(content).decode()

            loguru.logger.info(m_subject)
            try:
                send_email(
                    m_subject,
                    m_content,
                    m_tomail,
                    smtp_host,
                    smtp_port,
                    mail_user,
                    mail_pass,
                    sender_email,
                    smtptype,
                )
                loguru.logger.info('Send email success'+m_subject)
                return 'Send email success'
            except Exception as e:
                loguru.logger.error('Send email failed'+m_subject)
                return 'Send email failed'
        result = result+'"alarm":'+r+","

        # data
        r = r_session.post(url=url_data, verify=False).text
        result = result+'"data":'+r+","
        # ac
        try:
            r = r_session.post(url=url_ac, data=data_ac, verify=False).text
            # print(r)
            dataj = json.loads(r)
            state_ac = dataj["data"]
            # print(state_ac)

            state_ac_in_temp = state_ac["inletTmp"]
            state_ac_in_hum = state_ac["inletHum"]
            state_ac_out_temp = state_ac["outletTmp"]
            state_ac = str(state_ac).replace("\"", "$")
            state_ac = (state_ac).replace("'", "\"")
            state_ac = (state_ac).replace("$", "'")
            state_ac = (state_ac).replace("True", "\"True\"")
            state_ac = (state_ac).replace("False", "\"False\"")
        except:
            state_ac='""'
        result = result+'"ac":'+state_ac+','
        # power
        try:
            r = r_session.post(url=url_power, data=data_power, verify=False).text
            # print(r)
            dataj = json.loads(r)
            state_power = dataj["param"]
            # print(state_power)
            state_power_status = state_power['intAlm']
            state_power_kwh = state_power['kwh']
            state_power_kw = state_power['kw']
            state_power_pf = state_power['pf']
            state_power_volt = state_power['volt_Ph']
            state_power_curr = state_power['curr_Ph']
            state_power_freq = state_power['allFreq']
            state_power = str(state_power).replace("\"", "$")
            state_power = (state_power).replace("'", "\"")
            state_power = (state_power).replace("$", "'")
            state_power = (state_power).replace("True", "\"True\"")
            state_power = (state_power).replace("False", "\"False\"")
        except:
            state_power='""'
        result = result+'"power":'+(state_power)+','
        # ups
        try:
            r = r_session.post(url=url_ups, data=data_ups, verify=False).text
            # print(r)
            dataj = json.loads(r)
            state_ups = dataj["data"]
            state_ups = str(state_ups).replace("\"", "$")
            state_ups = (state_ups).replace("'", "\"")
            state_ups = (state_ups).replace("$", "'")
            state_ups = (state_ups).replace("True", "\"True\"")
            state_ups = (state_ups).replace("False", "\"False\"")
        except:
            state_ups='""'
        result = result+'"ups":'+(state_ups)+','
        # print(state_ups)
        # temp
        try:
            r = r_session.post(url=url_temp, data=data_temp, verify=False).text
            # print(r)
            dataj = json.loads(r)
            state_th = str(dataj["hotData"])
            if state_th == "[]":
                state_th = str(dataj["coldData"])
            # print(state_th)
            state_temp = re.findall('\d*\.?\d*℃', state_th)[0]

            state_humi = re.findall('\d*\.?\d*%RH', state_th)[0]
            print(state_temp, state_humi)
        except:
            state_temp='"--"'
            state_humi='"--"'
        result = result+'"temp":"'+(state_temp)+'","humi":"'+state_humi+'",'
        # leak
        try:
            r = r_session.post(url=url_leak, data=data_leak, verify=False).text
            # print(r)

            dataj = json.loads(r)
            state_leak = str(dataj["lkDtlData"][0])
            state_leak = state_leak.split(
                "</label> </div>")[0].split("</label> <label>")[1]
            print(state_leak)
        except:
            state_leak='"--"'
        result = result+'"leak":"'+(state_leak)+'"'
    else:
        result = result+'"online":"false"'
    result = result+'}'
    return result,server_name_last,user_last,password_last


@new_thread
def get_result():
    global result, data_ready,server_name_last,user_last,password_last
    while 1 == 1:
        try:
            result_new = '{"num":"'+str(num_of_servers)+'","servers":['
            i = 0
            server_name_last,user_last,password_last='','',''
            for server in servers_dict:
                if i > 0:
                    result_new = result_new+','
                i += 1
                result_get,server_name_last,user_last,password_last=get_server(server,server_name_last,user_last,password_last)
                result_new = result_new+result_get
            result_new = result_new+"]}"

            result = result_new
            data_ready = 1
        except:
            pass
        time.sleep(60)
@new_thread
def get_newsettings():
    global serv_port, servers, server_names, users, passwords,smtp_host, smtp_port, mail_user, mail_pass, sender_email, smtptype, email_receivers,servers_dict,server_names_dict,users_dict,passwords_dict,num_of_servers
    while 1==1:
        serv_port1, servers, server_names, users, passwords = get_conf_from_file(
            configpath, "Config", [
                "serv_port", "servers", "names", "users", "passwords"
            ]
        )
        serv_port = int(serv_port1)

        smtp_host, smtp_port, mail_user, mail_pass, sender_email, smtptype, email_receivers = get_conf_from_file(
            configpath, "Email", [
                "smtp_host", "smtp_port", "mail_user", "mail_pass", "sender_email", "smtptype", "email_receivers"
            ]
        )

        servers_dict = servers.split(",")
        server_names_dict = server_names.split(",")
        users_dict = users.split(",")
        passwords_dict = passwords.split(",")

        # print(servers_dict,server_names_dict,users_dict,passwords_dict)
        num_of_servers = len(servers_dict)
        time.sleep(60)

app = flask.Flask(__name__, template_folder='./templates', static_folder='./static')


@app.route('/dev_list', methods=['GET'])
def http_resp():
    callback = flask.request.args.get('callback')

    if not callback:
        return "Error: No callback function provided.", 400

    while data_ready == 0:
        time.sleep(2)
    response = f"{callback}({result})"

    return response, 200, {'Content-Type': 'application/javascript; charset=utf-8'}


if __name__ == "__main__":
    no_alarm = '<img src=\\"\/public\/images\/redAlm.png\\"><label class=\\"redAlm\\">0<\/label><img src=\\"\/public\/images\/ylwAlm.png\\"><label class=\\"ylwAlm\\">0<\/label>'
    log_path = './logs'
    if not os.path.isdir(log_path):
        # 创建文件夹
        os.mkdir(log_path)
    sheduler = loguru.logger.add(
        log_path+"\\bmrec.log", rotation="1 day", retention="7 days", level="INFO", encoding="utf-8"
    )
    config = configparser.ConfigParser()  # 类实例化

    # 定义文件路径
    configpath = r'.\setup.ini'
    prepare_conf_file(configpath)
    serv_port, servers, server_names, users, passwords = get_conf_from_file(
        configpath, "Config", [
            "serv_port", "servers", "names", "users", "passwords"
        ]
    )
    serv_port = int(serv_port)

    smtp_host, smtp_port, mail_user, mail_pass, sender_email, smtptype, email_receivers = get_conf_from_file(
        configpath, "Email", [
            "smtp_host", "smtp_port", "mail_user", "mail_pass", "sender_email", "smtptype", "email_receivers"
        ]
    )

    servers_dict = servers.split(",")
    server_names_dict = server_names.split(",")
    users_dict = users.split(",")
    passwords_dict = passwords.split(",")

    # print(servers_dict,server_names_dict,users_dict,passwords_dict)
    num_of_servers = len(servers_dict)

    result = ""
    data_ready = 0

    get_result()
    get_newsettings()
    app.run(host='0.0.0.0', port=serv_port, debug=True)
