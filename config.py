"""
تنظیمات MasterDNS
"""

import os
from pathlib import Path

class Config:
    """مدیریت تنظیمات"""
    
    def __init__(self):
        # ⚠️ Railway از PORT استفاده می‌کنه نه API_PORT!
        self.api_port = int(os.getenv("PORT", "8080"))
        self.environment = os.getenv("ENVIRONMENT", "production")
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        
        # Railway domain
        self.railway_domain = os.getenv(
            "RAILWAY_PUBLIC_DOMAIN", 
            "localhost"
        )
        
        # Paths
        self.data_dir = Path("/app/data")
        self.logs_dir = Path("/app/logs")
    
    def load_config(self):
        """بارگذاری تنظیمات"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        return {
            "environment": self.environment,
            "api_port": self.api_port,
            "railway_domain": self.railway_domain
        }
