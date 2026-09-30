# GoDaddy DNS Setup

## Domain

**Domain:** `chitt.online`
**Registrar:** GoDaddy

DNS is managed directly through GoDaddy.

Route 53 is **not used**.

---

## DNS Records

### API

The Chit API is exposed through the subdomain:

```text
api.chitt.online
```

GoDaddy DNS record:

| Type | Host  | Value            | TTL        |
| ---- | ----- | ---------------- | ---------- |
| A    | `api` | `15.252.205.123` | 30 minutes |

The IP `15.252.205.123` is the Elastic IP attached to the Chit EC2 instance.

---

## Existing GoDaddy Records

The existing GoDaddy records were left unchanged:

| Type  | Host             | Value                                  |
| ----- | ---------------- | -------------------------------------- |
| A     | `@`              | `Parked`                               |
| NS    | `@`              | `ns35.domaincontrol.com.`              |
| NS    | `@`              | `ns36.domaincontrol.com.`              |
| CNAME | `www`            | `chitt.online.`                        |
| CNAME | `_domainconnect` | `_domainconnect.gd.domaincontrol.com.` |
| SOA   | `@`              | `ns35.domaincontrol.com.`              |
| TXT   | `_dmarc`         | GoDaddy DMARC record                   |

Only the `api` A record was added for the Chit API.

---

## DNS Verification

Verify using Google DNS:

```bash
nslookup api.chitt.online 8.8.8.8
```

Expected:

```text
Name:    api.chitt.online
Address: 15.252.205.123
```

Verify using Cloudflare DNS:

```bash
nslookup api.chitt.online 1.1.1.1
```

Expected:

```text
Name:    api.chitt.online
Address: 15.252.205.123
```

---

## HTTPS

Caddy runs on the EC2 instance and automatically manages the HTTPS certificate.

Traffic flow:

```text
Internet
    |
    v
api.chitt.online
    |
    v
15.252.205.123
    |
    v
EC2 :443
    |
    v
Caddy
    |
    v
127.0.0.1:8000
    |
    v
Chit container
```

Working API endpoints:

```text
https://api.chitt.online/health
https://api.chitt.online/docs
https://api.chitt.online/openapi.json
```

---

## Future Domain Usage

The intended domain structure is:

```text
chitt.online
    -> Future Chit website / UI

api.chitt.online
    -> Chit API
```

The root domain does not currently need to point to the EC2 instance.

---

## Elastic IP

Current Elastic IP:

```text
15.252.205.123
```

This IP is associated with the Chit EC2 instance.

Do **not** release the Elastic IP while the following DNS record points to it:

```text
api.chitt.online -> 15.252.205.123
```

If the Elastic IP ever changes, update the GoDaddy `api` A record accordingly.

The previously seen public IP:

```text
13.203.45.235
```

was the old automatically assigned public IPv4 address and is no longer the active address.

---

## Route 53

Route 53 was considered but not used.

Creating a Route 53 hosted zone resulted in:

```text
Route 53 encountered an unknown error...
Free Tier accounts are not supported for this service.
```

Therefore DNS remains with GoDaddy.

---

## GoDaddy Domain Protection

GoDaddy offered:

```text
Full Domain Protection
₹49.92/month
```

This is **not required** for the Chit DNS/API setup.

It is a GoDaddy account/domain-security feature and is separate from:

* DNS configuration
* EC2
* Elastic IP
* Caddy
* HTTPS
* Chit API

---

## Important Cleanup

Once HTTPS through Caddy is confirmed working, EC2 Security Group should expose only:

```text
22   SSH       -> administrator access
80   HTTP      -> 0.0.0.0/0
443  HTTPS     -> 0.0.0.0/0
```

The temporary public rule:

```text
8000 TCP -> 0.0.0.0/0
```

should be removed.

Port `8000` is intended to be an internal Chit application port behind Caddy.

---

## Current Status

| Component           | Status           |
| ------------------- | ---------------- |
| `chitt.online`      | Registered       |
| GoDaddy DNS         | Active           |
| `api.chitt.online`  | Configured       |
| DNS resolution      | Working          |
| Elastic IP          | `15.252.205.123` |
| HTTPS               | Working          |
| Caddy               | Running          |
| Chit API            | Running          |
| Swagger docs        | Working          |
| Route 53            | Not used         |
| Root domain website | Future           |
