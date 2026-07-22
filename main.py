#!/usr/bin/env python3
"""
MasterDNS - DNS Server for VPN & White DNS Services
نسخه Railway Deployment
"""

import asyncio
import logging
import signal
import sys
import uvicorn
from pathlib import Path
from datetime import datetime

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/logs/masterdns.log')
    ]
)
logger = logging.getLogger(__name__)

# Import custom modules
from config import Config
from dns_server import DNSResolver, DNSServer
from api import create_api
from health_check import HealthChecker

class MasterDNS:
    """کلاس اصلی مدیریت MasterDNS"""
    
    def __init__(self):
        self.config = Config()
        self.dns_server = None
        self.api_server = None
        self.health_checker = None
        
        # دامنه‌های مجاز برای White DNS
        self.whitelist_domains = set()
        self.blacklist_domains = set()
        
        logger.info("MasterDNS initializing...")
    
    async def setup(self):
        """راه‌اندازی اولیه سرویس‌ها"""
        try:
            # بارگذاری تنظیمات
            self.config.load_config()
            
            # راه‌اندازی DNS Resolver
            self.dns_resolver = DNSResolver(self.config)
            
            # راه‌اندازی سرور DNS
            self.dns_server = DNSServer(
                resolver=self.dns_resolver,
                config=self.config
            )
            
            # راه‌اندازی API
            self.api = create_api(self.dns_server, self.config)
            
            # راه‌اندازی Health Checker
            self.health_checker = HealthChecker(self.config)
            
            # بارگذاری لیست‌های سفید و سیاه
            await self.load_domain_lists()
            
            logger.info("MasterDNS setup completed successfully")
            
        except Exception as e:
            logger.error(f"Setup failed: {e}")
            raise
    
    async def load_domain_lists(self):
        """بارگذاری لیست دامنه‌های مجاز و غیرمجاز"""
        whitelist_path = Path("/app/data/whitelist.txt")
        blacklist_path = Path("/app/data/blacklist.txt")
        
        if whitelist_path.exists():
            with open(whitelist_path, 'r') as f:
                self.whitelist_domains = set(line.strip() for line in f if line.strip())
        
        if blacklist_path.exists():
            with open(blacklist_path, 'r') as f:
                self.blacklist_domains = set(line.strip() for line in f if line.strip())
        
        logger.info(f"Loaded {len(self.whitelist_domains)} whitelist and {len(self.blacklist_domains)} blacklist domains")
    
    async def start(self):
        """شروع همه سرویس‌ها"""
        try:
            await self.setup()
            
            # شروع DNS Server
            dns_task = asyncio.create_task(self.dns_server.start())
            
            # شروع API Server
            api_config = uvicorn.Config(
                self.api,
                host="0.0.0.0",
                port=self.config.api_port,
                log_level=self.config.log_level.lower()
            )
            api_server = uvicorn.Server(api_config)
            api_task = asyncio.create_task(api_server.serve())
            
            # شروع Health Check
            health_task = asyncio.create_task(self.health_checker.start_monitoring())
            
            logger.info(f"MasterDNS started on DNS:{self.config.dns_port} API:{self.config.api_port}")
            
            # منتظر ماندن برای همه تسک‌ها
            await asyncio.gather(dns_task, api_task, health_task)
            
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            await self.shutdown()
        except Exception as e:
            logger.error(f"Error starting MasterDNS: {e}")
            await self.shutdown()
    
    async def shutdown(self):
        """خاموش کردن سرویس‌ها"""
        logger.info("Shutting down MasterDNS services...")
        
        if self.dns_server:
            await self.dns_server.stop()
        
        if self.health_checker:
            await self.health_checker.stop()
        
        logger.info("MasterDNS shutdown complete")

def handle_signal(signum, frame):
    """مدیریت سیگنال‌های سیستم"""
    logger.info(f"Received signal {signum}")
    sys.exit(0)

if __name__ == "__main__":
    # تنظیم signal handlers
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    # شروع MasterDNS
    master_dns = MasterDNS()
    
    try:
        asyncio.run(master_dns.start())
    except KeyboardInterrupt:
        logger.info("MasterDNS stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
