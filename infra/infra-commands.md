# Chit Infrastructure Commands

This document records the commands used to deploy and expose Chit on AWS EC2.

---

## 1. EC2 — Docker

### Install Docker

```bash
sudo dnf install -y docker
```

### Enable Docker

```bash
sudo systemctl enable --now docker
```

### Add ec2-user to Docker group

```bash
sudo usermod -aG docker ec2-user
```

After reconnecting:

```bash
docker --version
```

---

# 2. AWS ECR Login

Login to the Chit ECR repository:

```bash
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 316672688107.dkr.ecr.ap-south-1.amazonaws.com
```

---

# 3. Pull Chit Image

```bash
docker pull 316672688107.dkr.ecr.ap-south-1.amazonaws.com/chit:latest
```

---

# 4. Run Chit

The application listens on container port `8000`.

Example:

```bash
docker run -d \
  --name chit \
  -p 8000:8000 \
  --restart unless-stopped \
  316672688107.dkr.ecr.ap-south-1.amazonaws.com/chit:latest
```

---

# 5. Verify Container

```bash
docker ps
```

Check port mapping:

```bash
docker port chit
```

Inspect networking:

```bash
docker inspect chit --format '{{json .NetworkSettings.Ports}}'
```

Find container IP:

```bash
docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' chit
```

---

# 6. Test Chit Locally

From EC2:

```bash
curl http://localhost:8000/health
```

Test using the container IP:

```bash
curl http://172.17.0.2:8000/health
```

Test using the EC2 private IP:

```bash
curl http://172.31.25.207:8000/health
```

---

# 7. Verify Port 8000

Check whether the host is listening:

```bash
sudo ss -lntp | grep 8000
```

Expected:

```text
0.0.0.0:8000
[::]:8000
```

---

# 8. Test Public EC2 IP

Current Elastic IP:

```text
15.252.205.123
```

Temporary external test:

```bash
curl http://15.252.205.123:8000/health
```

This successfully proved public AWS → EC2 → Docker → Chit connectivity.

---

# 9. Install Caddy

The Amazon Linux 2023 ARM64 instance does not have a suitable Caddy COPR repository.

The attempted command was:

```bash
sudo dnf copr enable -y @caddy/caddy
```

It failed because:

```text
amazonlinux-2023-aarch64
```

was not available.

Therefore Caddy was installed using the official ARM64 binary.

Download:

```bash
curl -L "https://caddyserver.com/api/download?os=linux&arch=arm64" -o caddy
```

Make executable:

```bash
chmod +x caddy
```

Install:

```bash
sudo mv caddy /usr/local/bin/caddy
```

Verify:

```bash
caddy version
```

Current version used:

```text
v2.11.4
```

---

# 10. Create Caddy Configuration Directory

```bash
sudo mkdir -p /etc/caddy
```

---

# 11. Create Caddyfile

```bash
sudo nano /etc/caddy/Caddyfile
```

Configuration:

```caddyfile
api.chitt.online {
    reverse_proxy 127.0.0.1:8000
}
```

---

# 12. Validate Caddy Configuration

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
```

Expected:

```text
Valid configuration
```

---

# 13. Create systemd Service

Create:

```bash
sudo nano /etc/systemd/system/caddy.service
```

Service used:

```ini
[Unit]
Description=Caddy Web Server
Documentation=https://caddyserver.com/docs/
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
User=root
Group=root
ExecStart=/usr/local/bin/caddy run --environ --config /etc/caddy/Caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile
TimeoutStopSec=5s
LimitNOFILE=1048576
LimitNPROC=512
PrivateTmp=true
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
```

### Important

The following settings were initially used but caused Caddy's certificate storage to fail:

```ini
ProtectSystem=full
ProtectHome=true
```

They were removed.

The error was:

```text
mkdir /root/.local: read-only file system
```

---

# 14. Register Caddy Service

```bash
sudo systemctl daemon-reload
```

Enable and start:

```bash
sudo systemctl enable --now caddy
```

---

# 15. Check Caddy

```bash
sudo systemctl status caddy --no-pager
```

Expected:

```text
Active: active (running)
```

---

# 16. Caddy Logs

```bash
sudo journalctl -u caddy -n 50 --no-pager
```

For more logs:

```bash
sudo journalctl -u caddy -n 100 --no-pager
```

---

# 17. DNS Verification

Domain:

```text
api.chitt.online
```

Verify through Google DNS:

```bash
nslookup api.chitt.online 8.8.8.8
```

Verify through Cloudflare DNS:

```bash
nslookup api.chitt.online 1.1.1.1
```

Expected:

```text
Address: 15.252.205.123
```

---

# 18. HTTPS Verification

From the client machine:

```bash
curl -v https://api.chitt.online/health
```

Simple test:

```bash
curl https://api.chitt.online/health
```

Swagger:

```text
https://api.chitt.online/docs
```

---

# 19. AWS Security Group

Temporary debugging rule:

```text
TCP 8000 → 0.0.0.0/0
```

This was deliberately used to prove external connectivity.

Once HTTPS through Caddy is confirmed, remove the public `8000` rule.

Final intended inbound rules:

```text
TCP 22   → administrator IP
TCP 80   → 0.0.0.0/0
TCP 443  → 0.0.0.0/0
```

Do NOT expose:

```text
TCP 8000 → 0.0.0.0/0
```

in the final setup.

---

# 20. Useful Docker Commands

List containers:

```bash
docker ps
```

All containers:

```bash
docker ps -a
```

Container logs:

```bash
docker logs chit
```

Follow logs:

```bash
docker logs -f chit
```

Restart:

```bash
docker restart chit
```

Stop:

```bash
docker stop chit
```

Remove:

```bash
docker rm chit
```

Pull latest image:

```bash
docker pull 316672688107.dkr.ecr.ap-south-1.amazonaws.com/chit:latest
```

---

# 21. Useful System Commands

Check architecture:

```bash
uname -m
```

Expected:

```text
aarch64
```

Check IP addresses:

```bash
ip addr
```

Check listening ports:

```bash
sudo ss -lntp
```

Check public IP:

```bash
curl -4 ifconfig.me
```

Current expected public IP:

```text
15.252.205.123
```

---

# 22. Current Public Endpoints

Health:

```text
https://api.chitt.online/health
```

Swagger:

```text
https://api.chitt.online/docs
```

OpenAPI:

```text
https://api.chitt.online/openapi.json
```

---

# 23. Final Architecture

```text
Internet
   │
   ▼
api.chitt.online
   │
   ▼
15.252.205.123
   │
   ▼
AWS EC2 ARM64
   │
   ▼
Caddy :443
   │
   ▼
127.0.0.1:8000
   │
   ▼
Chit Docker container
```

---

# 24. Important Addresses

```text
Domain:
chitt.online

API:
api.chitt.online

Elastic IP:
15.252.205.123

EC2 private IP:
172.31.25.207

ECR:
316672688107.dkr.ecr.ap-south-1.amazonaws.com/chit

Container port:
8000

HTTPS:
443

HTTP:
80
```

---

# 25. Deployment Notes

* Local container tooling: Podman / podman-compose.
* GitHub Actions uses Docker Buildx.
* Image target: `linux/arm64`.
* EC2 target architecture: ARM64.
* ECR repository is private.
* GitHub Actions authenticates to AWS using OIDC.
* EC2 authenticates to ECR using its IAM role.
* Caddy terminates HTTPS.
* Chit itself does not handle TLS.
* Chit remains behind the reverse proxy.
* Port `8000` was opened publicly only for initial connectivity testing.
* Public port `8000` should be removed after HTTPS verification.
* Current Chit health response indicates that the container is running but `checkpoints/latest.pt` has not yet been deployed.
