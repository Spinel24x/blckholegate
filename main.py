#!/usr/bin/env python3
"""
MasterDNS - Railway Deployment
"""

import uvicorn
import logging
from config import Config
from dns_server import DNSResolver, DNSServer
from api import create_api

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
        
        config = Config()
        config.load_config()
        
        logger.info(f"Port: {config.api_port}")
        logger.info(f"Domain: {config.railway_domain}")
        
        resolver = DNSResolver(config)
        dns_server = DNSServer(resolver, config)
        api = create_api(dns_server, config)
        
        logger.info(f"✅ Starting on port {config.api_port}")
        
        uvicorn.run(api, host="0.0.0.0", port=config.api_port)
        
    except Exception as e:
        logger.error(f"❌ Failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
