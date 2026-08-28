# 容器化部署:阿里云 ECS(多人共用)

> 目标:把表对比工具以 Docker 容器跑在阿里云 ECS 上,大家用浏览器访问,无需安装。
> 前置:一个阿里云账号、一台 ECS、一个域名(可选但推荐)。

## 一、整体架构

```
用户浏览器
   │ https://table-diff.example.com
   ▼
阿里云 ECS
 ├─ Nginx(80/443,HTTPS 证书,反向代理)   ← 只暴露这个
 │    └─ table-diff 容器(监听 8000,仅内网)
 │         └─ 数据卷 ./data(方案/对账记录/上传文件,定期备份)
```

## 二、准备

1. **ECS 选型**:2 核 2G 起(40G 系统盘),系统选 Ubuntu 22.04 或 Alibaba Cloud Linux 3;地域选离用户近的
2. **安全组**:只放行 **80、443**(如果先测试可不加域名,临时放行 8000,用完删掉);**不要**把 8000 直接对公网长期开放
3. **装 Docker**(ECS 上执行):
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo systemctl enable --now docker
   sudo curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   # 配置阿里云镜像加速(登录阿里云容器镜像服务控制台查看你的加速地址)
   sudo mkdir -p /etc/docker
   echo '{"registry-mirrors":["https://<你的加速地址>.mirror.aliyuncs.com"]}' | sudo tee /etc/docker/daemon.json
   sudo systemctl restart docker
   ```

## 三、部署

1. **上传项目**:
   ```bash
   # 方式 A(推荐):git 拉到服务器
   sudo apt install -y git
   git clone https://github.com/<你的用户名>/table-diff.git /opt/table-diff
   cd /opt/table-diff
   # 方式 B:本机打包上传 —— tar czf table-diff.tar.gz --exclude=.git --exclude=data table-diff,再 scp 到服务器解压
   ```

2. **配置访问口令(必填,安全防线)**:
   ```bash
   cd /opt/table-diff
   openssl rand -hex 16          # 生成口令,复制结果
   echo "TABLE_DIFF_TOKEN=<上一步的结果>" > .env
   chmod 600 .env                # 权限收紧,防止别人读到口令
   ```
   > 未设置口令时,`docker compose up` 会直接报错拒绝启动(防裸奔)。
   > 当前版本为"一套口令大家共用";需要"每人独立账号"是后续迭代方向。

3. **构建并启动**:
   ```bash
   sudo docker compose up -d --build
   sudo docker compose ps         # 看到 healthy/Up 即成功
   sudo docker compose logs -f    # 看日志
   ```

4. **验证**:浏览器访问 `http://<ECS公网IP>:8000`,输入口令即可使用。

## 四、Nginx + HTTPS(强烈推荐,正式使用前必做)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

`/etc/nginx/sites-available/table-diff`:
```nginx
server {
    listen 80;
    server_name table-diff.example.com;   # 换成你的域名(需先解析到 ECS 公网 IP)

    client_max_body_size 50m;             # 允许上传较大文件

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/table-diff /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# 申请免费证书(阿里云也有免费证书,控制台申请后填到 nginx 亦可)
sudo certbot --nginx -d table-diff.example.com
```
之后访问 `https://table-diff.example.com`,关闭安全组里临时开放的 8000。

## 五、数据备份(必须)

数据全在 `/opt/table-diff/data`(映射方案 + 对账记录 + 上传文件)。备份:

```bash
# 手动备份
tar czf /backup/table-diff-$(date +%F).tar.gz -C /opt/table-diff data
# 或 crontab 每日备份
0 3 * * * tar czf /backup/table-diff-$(date +\%F).tar.gz -C /opt/table-diff data && find /backup -name 'table-diff-*.tar.gz' -mtime +30 -delete
```

恢复:把备份解压回 `/opt/table-diff/data` 后 `docker compose restart`。

## 六、更新版本

```bash
cd /opt/table-diff
git pull                        # 拉新代码(或重新上传)
sudo docker compose up -d --build
```

## 七、运维速查

| 命令 | 作用 |
|---|---|
| `docker compose ps` | 看容器状态 |
| `docker compose logs -f table-diff` | 看实时日志 |
| `docker compose restart table-diff` | 重启 |
| `docker compose down` | 停止(数据保留在 ./data) |
| `docker compose down -v` | **危险**:连数据卷一起删 |

## 八、安全与合规提醒(务必读)

1. **数据在服务器上**:用户上传的账单/PMS 数据会存到你的服务器——这与"数据不出本机"的本地版卖点不同,要在使用说明里明确告知用户;涉及客人个人信息时注意《个人信息保护法》(建议用户上传前对账单做脱敏/去名处理)
2. **口令共享**:当前是"一套口令所有人共用",知道口令的人都能看到方案、上传文件、看到对账结果(run_id 不可猜,但不排除共享场景下互相看到);正式商用前建议做"用户注册/独立账号/数据隔离"
3. **HTTPS 必须**:口令通过 HTTP 明文传输会被窃取,上线前务必配好证书
4. **SQLite 并发上限**:适合几十人以内小规模共用;若用户量大了,考虑迁移 PostgreSQL(后续迭代)
5. **不要直接暴露 8000**:一律走 Nginx;安全组只开 80/443
6. 建议 ECS 开启**快照**(控制台手动/自动快照),出问题秒回滚
