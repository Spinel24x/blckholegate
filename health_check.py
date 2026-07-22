"""
سیستم بررسی سلامت MasterDNS
"""

import asyncio
import time
import socket
import logging
from typing import Dict, Any
import dns.resolver

logger = logging.getLogger(__name__)

class HealthChecker:
    """بررسی سلامت سرویس‌ها"""
    
    def __init__(self, config):
        self.config = config
        self.running = False
        self.health_status = {
            "dns_server": "unknown",
            "api_server": "unknown",
            "upstream_dns": "unknown",
            "network": "unknown"
        }
        self.last_check = 0
        self.check_interval = 30  # ثانیه
    
    async def start_monitoring(self):
        """شروع مانیتورینگ سلامت"""
        self.running = True
        
        while self.running:
            try:
                await self.perform_health_checks()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(5)
    
    async def perform_health_checks(self):
        """انجام تمام بررسی‌های سلامت"""
        checks = [
            self.check_dns_server(),
            self.check_api_server(),
            self.check_upstream_dns(),
            self.check_network_connectivity()
        ]
        
        results = await asyncio.gather(*checks, return_exceptions=True)
        
        self.health_status.update({
            "dns_server": results[0],
            "api_server": results[1],
            "upstream_dns": results[2],
            "network": results[3]
        })
        
        self.last_check = time.time()
        
        # لاگ وضعیت در صورت وجود مشکل
        for service, status in self.health_status.items():
            if status != "healthy":
                logger.warning(f"Service {service} is {status}")
    
    async def check_dns_server(self) -> str:
        """بررسی سلامت سرور DNS"""
        try:
            # تست resolution محلی
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ['127.0.0.1']
            resolver.port = self.config.dns_port
            
            answer = resolver.resolve('localhost', 'A', lifetime=2)
            
            return "healthy" if answer else "degraded"
        except Exception as e:
            logger.error(f"DNS server check failed: {e}")
            return "unhealthy"
    
    async def check_api_server(self) -> str:
        """بررسی سلامت API Server"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://localhost:{self.config.api_port}/health",
                    timeout=2.0
                )
                
            return "healthy" if response.status_code == 200 else "degraded"
        except Exception as e:
            logger.error(f"API server check failed: {e}")
            return "unhealthy"
    
    async def check_upstream_dns(self) -> str:
        """بررسی سلامت DNS های upstream"""
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = self.config.dns_config.upstream_dns
            
            answer = resolver.resolve('google.com', 'A', lifetime=3)
            
            return "healthy" if answer else "degraded"
        except Exception as e:
            logger.error(f"Upstream DNS check failed: {e}")
            return "unhealthy"
    
    async def check_network_connectivity(self) -> str:
        """بررسی اتصال شبکه"""
        try:
            # تست اتصال اینترنت
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return "healthy"
        except OSError:
            return "disconnected"
    
    async def stop(self):
        """توقف مانیتورینگ"""
        self.running = False
        logger.info("Health checker stopped")
    
    def get_health_report(self) -> Dict[str, Any]:
        """دریافت گزارش کامل سلامت"""
        return {
            "status": self.health_status,
            "last_check": self.last_check,
            "overall_health": self.calculate_overall_health(),
            "timestamp": time.time()
        }
    
    def calculate_overall_health(self) -> str:
        """محاسبه وضعیت کلی سلامت"""
        statuses = list(self.health_status.values())
        
        if all(s == "healthy" for s in statuses):
            return "healthy"
        elif "unhealthy" in statuses:
            return "unhealthy"
        else:
            return "degraded"
