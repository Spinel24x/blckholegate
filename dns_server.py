"""
DNS Server Core - نسخه Railway
"""

import logging
from typing import List, Optional
import dns.resolver
from cachetools import TTLCache

logger = logging.getLogger(__name__)

class DNSResolver:
    """حل کننده DNS"""
    
    def __init__(self, config):
        self.config = config
        self.cache = TTLCache(maxsize=10000, ttl=300)  # مستقیماً 300 ثانیه
        self.whitelist_domains = set()
        self.blacklist_domains = set()
        
        # تنظیم resolver
        self.resolver = dns.resolver.Resolver()
        self.resolver.nameservers = ['8.8.8.8', '1.1.1.1']
        self.resolver.timeout = 3
        self.resolver.lifetime = 5
        
    async def resolve(self, domain: str) -> Optional[List[str]]:
        """حل دامنه"""
        if domain in self.cache:
            logger.debug(f"Cache hit: {domain}")
            return self.cache[domain]
        
        try:
            domain = domain.rstrip('.')
            answers = self.resolver.resolve(domain, 'A')
            results = [str(rdata) for rdata in answers]
            self.cache[domain] = results
            logger.info(f"Resolved: {domain} -> {results}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to resolve {domain}: {e}")
            return None

class DNSServer:
    """مدیریت سرور DNS"""
    
    def __init__(self, resolver: DNSResolver, config):
        self.resolver = resolver
        self.config = config
        self.stats = {
            "total_queries": 0,
            "cached": 0,
            "failed": 0
        }
    
    def get_stats(self):
        """دریافت آمار"""
        return {
            **self.stats,
            "cache_size": len(self.resolver.cache),
            "whitelist_count": len(self.resolver.whitelist_domains),
            "blacklist_count": len(self.resolver.blacklist_domains)
        }
    
    async def start(self):
        """شروع سرور"""
        logger.info("DNS Server ready (API mode only)")
    
    async def stop(self):
        """توقف سرور"""
        logger.info("DNS Server stopped")
