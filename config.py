"""
تنظیمات MasterDNS
"""

import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class DNSConfig(BaseModel):
    """تنظیمات DNS"""
    upstream_dns: List[str] = ["8.8.8.8", "1.1.1.1"]
    cache_ttl: int = 300
    rate_limit: int = 100
    enable_dnssec: bool = True
    enable_doh: bool = True

class APIConfig(BaseModel):
    """تنظیمات API"""
    host: str = "0.0.0.0"
    port: int = 8000
    enable_auth: bool = False
    api_key: Optional[str] = None

class SecurityConfig(BaseModel):
    """تنظیمات امنیتی"""
    enable_firewall: bool = True
    block_malware: bool = True
    block_phishing: bool = True
    vpn_mode: bool = False
    encryption_key: Optional[str] = None

class Config:
    """کلاس اصلی مدیریت تنظیمات"""
    
    def __init__(self):
        # Railway environment variables
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.dns_port = int(os.getenv("DNS_PORT", "53"))
        self.api_port = int(os.getenv("API_PORT", "8000"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        
        # Railway domain
        self.railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
        self.railway_app_name = os.getenv("RAILWAY_SERVICE_NAME", "masterdns")
        
        # Database
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./masterdns.db")
        
        # DNS Configuration
        self.dns_config = DNSConfig(
            upstream_dns=os.getenv("UPSTREAM_DNS", "8.8.8.8,1.1.1.1").split(","),
            cache_ttl=int(os.getenv("CACHE_TTL", "300")),
            rate_limit=int(os.getenv("RATE_LIMIT", "100")),
            enable_dnssec=os.getenv("ENABLE_DNSSEC", "true").lower() == "true",
            enable_doh=os.getenv("ENABLE_DOH", "true").lower() == "true"
        )
        
        # Security Configuration
        self.security_config = SecurityConfig(
            enable_firewall=os.getenv("ENABLE_FIREWALL", "true").lower() == "true",
            block_malware=os.getenv("BLOCK_MALWARE", "true").lower() == "true",
            block_phishing=os.getenv("BLOCK_PHISHING", "true").lower() == "true",
            vpn_mode=os.getenv("VPN_MODE", "false").lower() == "true",
            encryption_key=os.getenv("ENCRYPTION_KEY")
        )
        
        # Paths
        self.data_dir = Path("/app/data")
        self.logs_dir = Path("/app/logs")
        
    def load_config(self):
        """بارگذاری و اعتبارسنجی تنظیمات"""
        # ایجاد دایرکتوری‌های مورد نیاز
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        return {
            "environment": self.environment,
            "dns_port": self.dns_port,
            "api_port": self.api_port,
            "railway_domain": self.railway_domain
        }
    
    def get_connection_string(self) -> str:
        """دریافت رشته اتصال DNS با پسوند Railway"""
        return f"dns://{self.railway_domain}:{self.dns_port}"
