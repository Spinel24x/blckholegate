#!/usr/bin/env python3
"""
MasterDNS - نسخه Railway
شروع ساده با فقط API
"""

import uvicorn
import logging
import time
from config import Config
from dns_server import DNSResolver, DNSServer
from api import create_api

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("=" * 50)
        logger.info("Starting MasterDNS on Railway...")
        logger.info("=" * 50)
        
        # بارگذاری تنظیمات
        config = Config()
        config.load_config()
        
        logger.info(f"Environment: {config.environment}")
        logger.info(f"API Port: {config.api_port}")
        logger.info(f"Railway Domain: {config.railway_domain}")
        
        # راه‌اندازی resolver و dns server
        resolver = DNSResolver(config)
        dns_server = DNSServer(resolver, config)
        
        # ایجاد API
        api = create_api(dns_server, config)
        
        logger.info(f"✅ API ready at port {config.api_port}")
        logger.info(f"📡 Health check: http://0.0.0.0:{config.api_port}/health")
        logger.info(f"📚 API Docs: http://0.0.0.0:{config.api_port}/docs")
        
        # شروع سرور
        uvicorn.run(
            api,
            host="0.0.0.0",
            port=config.api_port,
            log_level=config.log_level.lower()
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to start: {e}")
        raise
