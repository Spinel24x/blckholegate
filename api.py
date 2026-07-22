"""
REST API برای مدیریت MasterDNS
"""

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Optional, Dict
import time
import hashlib
import hmac
import json

class DNSRecordRequest(BaseModel):
    """مدل درخواست رکورد DNS"""
    domain: str
    record_type: str = "A"
    value: str
    ttl: int = 300

class WhitelistRequest(BaseModel):
    """مدل اضافه کردن دامنه به لیست سفید"""
    domain: str
    description: Optional[str] = None

class BlacklistRequest(BaseModel):
    """مدل اضافه کردن دامنه به لیست سیاه"""
    domain: str
    reason: Optional[str] = None

class VPNConfigRequest(BaseModel):
    """مدل تنظیمات VPN"""
    protocol: str = "wireguard"
    port: int = 51820
    dns_servers: List[str] = ["10.0.0.1"]
    mtu: int = 1420

def create_api(dns_server, config):
    """ایجاد اپلیکیشن FastAPI"""
    
    app = FastAPI(
        title="MasterDNS API",
        description="API for managing MasterDNS on Railway",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # API Key authentication
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
    
    async def verify_api_key(api_key: str = Depends(api_key_header)):
        if config.security_config.enable_auth:
            if not api_key or api_key != config.security_config.api_key:
                raise HTTPException(status_code=403, detail="Invalid API Key")
        return api_key
    
    @app.get("/")
    async def root():
        """صفحه اصلی"""
        return {
            "service": "MasterDNS",
            "version": "1.0.0",
            "status": "running",
            "railway_domain": config.railway_domain,
            "endpoints": {
                "dns": f"dns://{config.railway_domain}:{config.dns_port}",
                "api": f"https://{config.railway_domain}"
            }
        }
    
    @app.get("/health")
    async def health_check():
        """بررسی سلامت سرویس"""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "stats": dns_server.get_stats()
        }
    
    @app.get("/stats")
    async def get_stats():
        """دریافت آمار سرور"""
        return {
            "dns_stats": dns_server.get_stats(),
            "cache_size": len(dns_server.resolver.cache),
            "uptime": time.time() - app.state.start_time if hasattr(app.state, 'start_time') else 0
        }
    
    @app.post("/dns/resolve")
    async def resolve_domain(request: Request):
        """حل یک دامنه خاص"""
        data = await request.json()
        domain = data.get("domain")
        
        if not domain:
            raise HTTPException(status_code=400, detail="Domain is required")
        
        results = await dns_server.resolver.resolve(domain)
        
        return {
            "domain": domain,
            "results": results,
            "timestamp": time.time()
        }
    
    @app.get("/whitelist")
    async def get_whitelist():
        """دریافت لیست سفید"""
        return {
            "domains": list(dns_server.resolver.whitelist_domains),
            "count": len(dns_server.resolver.whitelist_domains)
        }
    
    @app.post("/whitelist/add")
    async def add_to_whitelist(request: WhitelistRequest):
        """اضافه کردن دامنه به لیست سفید"""
        dns_server.resolver.whitelist_domains.add(request.domain)
        return {
            "status": "success",
            "domain": request.domain,
            "message": f"Added {request.domain} to whitelist"
        }
    
    @app.delete("/whitelist/remove/{domain}")
    async def remove_from_whitelist(domain: str):
        """حذف دامنه از لیست سفید"""
        dns_server.resolver.whitelist_domains.discard(domain)
        return {
            "status": "success",
            "domain": domain,
            "message": f"Removed {domain} from whitelist"
        }
    
    @app.get("/blacklist")
    async def get_blacklist():
        """دریافت لیست سیاه"""
        return {
            "domains": list(dns_server.resolver.blacklist_domains),
            "count": len(dns_server.resolver.blacklist_domains)
        }
    
    @app.post("/blacklist/add")
    async def add_to_blacklist(request: BlacklistRequest):
        """اضافه کردن دامنه به لیست سیاه"""
        dns_server.resolver.blacklist_domains.add(request.domain)
        return {
            "status": "success",
            "domain": request.domain,
            "message": f"Added {request.domain} to blacklist"
        }
    
    @app.get("/vpn/config")
    async def get_vpn_config():
        """دریافت تنظیمات VPN"""
        return {
            "dns_server": config.get_connection_string(),
            "protocols": ["wireguard", "openvpn"],
            "security": {
                "dnssec": config.dns_config.enable_dnssec,
                "doh": config.dns_config.enable_doh
            }
        }
    
    @app.post("/vpn/generate-config")
    async def generate_vpn_config(request: VPNConfigRequest):
        """تولید کانفیگ VPN"""
        config_content = f"""
[Interface]
PrivateKey = <YOUR_PRIVATE_KEY>
Address = 10.0.0.2/24
DNS = {config.railway_domain}

[Peer]
PublicKey = <SERVER_PUBLIC_KEY>
Endpoint = {config.railway_domain}:{request.port}
AllowedIPs = 0.0.0.0/0
        """
        
        return {
            "protocol": request.protocol,
            "config": config_content,
            "connection_string": config.get_connection_string()
        }
    
    @app.get("/diagnostics")
    async def run_diagnostics():
        """اجرای تست‌های عیب‌یابی"""
        diagnostics = {
            "dns_resolution": await test_dns_resolution(config),
            "connectivity": await test_connectivity(),
            "cache_performance": test_cache_performance(dns_server),
            "system_resources": get_system_resources()
        }
        
        return diagnostics
    
    async def test_dns_resolution(config):
        """تست عملکرد DNS"""
        try:
            start = time.time()
            results = await dns_server.resolver.resolve("google.com")
            latency = (time.time() - start) * 1000
            
            return {
                "status": "success" if results else "failed",
                "latency_ms": round(latency, 2),
                "upstream_dns": config.dns_config.upstream_dns
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def test_connectivity():
        """تست اتصال شبکه"""
        import socket
        try:
            socket.gethostbyname("google.com")
            return {"status": "connected"}
        except:
            return {"status": "disconnected"}
    
    def test_cache_performance(dns_server):
        """تست عملکرد کش"""
        return {
            "cache_hits": dns_server.stats["cached_responses"],
            "cache_size": len(dns_server.resolver.cache),
            "hit_ratio": calculate_hit_ratio(dns_server.stats)
        }
    
    def calculate_hit_ratio(stats):
        """محاسبه نسبت hit کش"""
        total = stats["total_queries"]
        hits = stats["cached_responses"]
        return (hits / total * 100) if total > 0 else 0
    
    def get_system_resources():
        """دریافت منابع سیستم"""
        try:
            import psutil
            return {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent
            }
        except:
            return {"error": "psutil not available"}
    
    # تنظیم start_time برای محاسبه uptime
    @app.on_event("startup")
    async def startup_event():
        app.state.start_time = time.time()
    
    return app
