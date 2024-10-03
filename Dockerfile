# 使用官方 Python 镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 复制 Python 脚本到容器中
COPY ebis.py .

ENV TZ=Asia/Shanghai
ENV PIP_ROOT_USER_ACTION=ignore
ENV poll_interval=1800
ENV freshrss_auth_url=
ENV freshrss_list_subscription_url=
ENV freshrss_content_url_prefix=
ENV freshrss_filtered_label=
ENV sender_email=
ENV sender_auth_token=
ENV smtp_server=
ENV smtp_port=25
ENV receiver_email=
ENV ot_map_json={}

# 安装虚拟环境工具
RUN pip install --no-cache-dir virtualenv

# 创建虚拟环境
RUN virtualenv venv

# 激活虚拟环境并安装依赖
RUN . venv/bin/activate && pip install --no-cache-dir requests regex

# 设置容器启动命令
CMD ["venv/bin/python", "ebis.py"]