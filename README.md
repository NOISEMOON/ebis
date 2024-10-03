# ebis
定时从 FreshRSS 拉取最新文章列表的标题，翻译成中文，并发送邮件到指定邮箱

```
docker build -t ebis .
docker run -d --env-file env.list ebis
docker save -o ebis.tar ebis
```