# MasterDNS on Railway 🚂

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

## 🌐 DNS Server for VPN & White DNS Services

A powerful DNS server designed to work with MasterDNS VPN and White DNS applications, optimized for Railway deployment.

### ✨ Features

- 🚀 **Fast DNS Resolution** with built-in caching
- 🛡️ **Security** - Malware & phishing protection
- 🔒 **VPN Support** - Optimized for WireGuard & OpenVPN
- 📊 **Real-time Monitoring** & statistics
- 🎯 **White/Black Lists** for domain filtering
- 🌍 **Anycast Ready** - Geo-distributed DNS
- 📡 **REST API** for management
- 🐳 **Docker Support** - Easy deployment

### 🚀 Quick Deploy on Railway

1. Click the "Deploy on Railway" button
2. Configure environment variables (optional)
3. Your DNS server will be ready in minutes!

### 📋 Endpoints

#### DNS Service
- **DNS Port**: `53` (UDP/TCP)
- **Connection**: `dns://your-app.railway.app:53`

#### API Service
- **Base URL**: `https://your-app.railway.app`
- **Docs**: `https://your-app.railway.app/docs`

### 🔧 Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DNS_PORT` | `53` | DNS server port |
| `API_PORT` | `8000` | API server port |
| `UPSTREAM_DNS` | `8.8.8.8,1.1.1.1` | Upstream DNS servers |
| `CACHE_TTL` | `300` | Cache TTL in seconds |
| `RATE_LIMIT` | `100` | Rate limit per client |
| `ENABLE_DNSSEC` | `true` | Enable DNSSEC validation |
| `ENABLE_DOH` | `true` | Enable DNS over HTTPS |

### 📡 API Examples

```bash
# Health Check
curl https://your-app.railway.app/health

# Resolve Domain
curl -X POST https://your-app.railway.app/dns/resolve \
  -H "Content-Type: application/json" \
  -d '{"domain": "google.com"}'

# Get VPN Config
curl https://your-app.railway.app/vpn/config

# Add to Whitelist
curl -X POST https://your-app.railway.app/whitelist/add \
  -H "Content-Type: application/json" \
  -d '{"domain": "trusted-site.com"}'
