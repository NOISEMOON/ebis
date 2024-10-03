import copy
import random
import requests
import json
from time import sleep
import smtplib
import re
import logging
import sys
import os

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# 配置日志记录
logging.basicConfig(
    stream=sys.stdout,  # 将日志输出到标准输出
    level=logging.INFO,  # 设置日志级别
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # 日志格式
)
logger = logging.getLogger("ebis")
poll_interval = int(os.getenv("poll_interval", "600"))
google_base_url = "https://translate.googleapis.com/translate_a/single"
freshrss_auth_url = os.getenv("freshrss_auth_url")
freshrss_list_subscription_url = os.getenv("freshrss_list_subscription_url")
freshrss_content_url_prefix = os.getenv("freshrss_content_url_prefix")
freshrss_filtered_label = os.getenv("freshrss_filtered_label")
sender_email = os.getenv("sender_email")
sender_auth_token = os.getenv("sender_auth_token")
smtp_server = os.getenv("smtp_server")
smtp_port = int(os.getenv("smtp_port", "25"))
receiver_email = os.getenv("receiver_email")
default_ot = int(os.getenv("default_ot", int(datetime.now().timestamp())))
logger.info(f"default_ot: {default_ot}")
ot_map_json = os.getenv("ot_map_json", "{}")
logger.info(ot_map_json)
ot_map = json.loads(ot_map_json)
new_ot_map = copy.deepcopy(ot_map)


class EmailSender:
    def __init__(self, smtp_server, smtp_port, login, password):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.login = login
        self.password = password
        self.server = None

    def connect(self):
        try:
            # 建立与SMTP服务器的连接
            self.server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            self.server.starttls()  # 启用TLS加密
            self.server.login(self.login, self.password)
            logger.info("Connected to SMTP server.")
        except Exception as e:
            logger.exception("Failed to connect to the SMTP server")

    def send_email(self, sender_email, receiver_email, subject, body):
        logger.info("start to send email...")
        # 创建MIME消息对象
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            # 发送邮件
            self.server.sendmail(sender_email, receiver_email, msg.as_string())
            logger.info(f"Email sent to {receiver_email} successfully!")
            return True
        except Exception as e:
            logger.exception(f"Failed to send email to {receiver_email}")
            return False

    def disconnect(self):
        # 关闭与SMTP服务器的连接
        if self.server:
            self.server.quit()
            logger.info("Disconnected from SMTP server.")


def translate(text):
    logger.info(f"translate: {text}")
    translated_text = ""
    query_params = {
        "client": "gtx",
        "sl": "auto",  # 源语言设置为自动检测
        "tl": "zh",  # 目标语言设置为中文
        "dt": "t",
        "q": text,
    }

    try:
        response = requests.get(google_base_url, params=query_params, timeout=3)
        response.raise_for_status()  # 如果响应码不为200，则引发HTTPError

        json_response = response.json()
        if json_response and len(json_response) > 0 and len(json_response[0]) > 0:
            translated_text = json_response[0][0][0]
        else:
            raise Exception("Google Translate API returned an empty translation.")

    except Exception as e:
        logger.exception("Error in translation")

    return translated_text


def rss_auth():
    response = requests.get(freshrss_auth_url)
    match = re.search(r"SID=([^\n]+)", response.text)
    if match:
        sid_value = match.group(1)
        logger.info(sid_value)
        return sid_value
    else:
        logger.error("SID not found")
        return "null"


def rss_list_sub(auth_token):
    en_sub = []
    headers = {"Authorization": f"GoogleLogin auth={auth_token}"}
    response = requests.get(freshrss_list_subscription_url, headers=headers)
    if response.status_code == 200:
        try:
            data = json.loads(response.text)
            items = data["subscriptions"]
            for item in items:
                for category in item["categories"]:
                    if (
                        freshrss_filtered_label
                        and category["label"] != freshrss_filtered_label
                    ):
                        continue
                    en_sub.append(item)
            return en_sub
        except Exception as e:
            logger.exception(f"response.text: {response.text}")
    else:
        logger.error(f"status error: {response.status_code}")


def rss_fetch_feed(feed_id, feed_title, auth_token):
    ot = ot_map.get(feed_id) or default_ot
    logger.info(f"rss_fetch_feed feed_id: {feed_id} feed_title: {feed_title} ot: {ot}")

    freshrss_content_url_suffix = f"{feed_id}?ot={ot}"
    freshrss_content_url = freshrss_content_url_prefix + freshrss_content_url_suffix
    headers = {"Authorization": f"GoogleLogin auth={auth_token}"}
    response = requests.get(freshrss_content_url, headers=headers)

    content = f"<h1>{feed_title}</h1>\n"

    if response.status_code == 200:
        data = json.loads(response.text)
        items = data.get("items", [])
        if items:
            crawl_time_msec = items[0].get("crawlTimeMsec")
            if crawl_time_msec:
                # 记录下一次请求开始的时间点
                crawl_time_sec = int(int(crawl_time_msec) / 1000)
                new_ot_map[feed_id] = crawl_time_sec + 1
            for item in items:
                title = item.get("title")
                if title:
                    cn_title = translate(title)
                    href = item.get("canonical", [{}])[0].get("href")
                    content += f"<li>{cn_title} <a href={href}>{title}</a></li>"
                    sleep(random.randint(1, 10))
        else:
            return None
    else:
        logger.error(f"Failed to fetch feed: {response.status_code}")
    return content


def build_mail_body(auth_token):
    subs = rss_list_sub(auth_token)
    body = ""
    for sub in subs:
        feed_id = sub["id"]
        feed_title = sub["title"]
        feed_content = rss_fetch_feed(feed_id, feed_title, auth_token)
        if feed_content:
            body += feed_content
            body += "\n"
        else:
            logger.info(f"No updates from {feed_id} {feed_title}")
    return body


if __name__ == "__main__":
    logger.info("Start loop...")
    try:
        auth_token = rss_auth()
        email_sender = EmailSender(
            smtp_server, smtp_port, sender_email, sender_auth_token
        )

        while True:
            try:
                body = build_mail_body(auth_token)
                if body:
                    subject = "RSS " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    email_sender.connect()
                    is_sent = email_sender.send_email(
                        sender_email, receiver_email, subject, body
                    )
                    if is_sent:
                        logger.info(f"Update ot_map: {ot_map}")
                        logger.info(f"Update new_ot_map: {new_ot_map}")
                        ot_map = copy.deepcopy(new_ot_map)
                else:
                    logger.info("No updates. Don't send email")
            except Exception as e:
                logger.exception("build_mail_body error")
            sleep(poll_interval)
    except Exception as e:
        logger.exception("Exit with error")
        exit
