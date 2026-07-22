"""
DNS Server Core - پیاده‌سازی پروتکل DNS
"""

import asyncio
import socket
import struct
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import dns.message
import dns.query
import dns.rdatatype
import dns.resolver
from cachetools import TTLCache

logger = logging.getLogger(__name__)

@dataclass
class DNSQuery:
    """ساختار داده کوئری DNS"""
    id: int
    domain: str
    qtype: int
    client_ip: str
    timestamp: datetime

class DNSResolver:
    """حل کننده DNS با قابلیت کش و فیلترینگ"""
    
    def __init__(self, config):
        self.config = config
        self.cache = TTLCache(maxsize=10000, ttl=config.dns_config.cache_ttl)
        self.resolver = dns.resolver.Resolver()
        self.resolver.nameservers = config.dns_config.upstream_dns
        
        # Rate limiting
        self.request_counts = {}
        self.rate_limit = config.dns_config.rate_limit
        
    async def resolve(self, domain: str, qtype: int = dns.rdatatype.A) -> Optional[List[str]]:
        """
        حل کوئری DNS با قابلیت کش و فیلترینگ
        """
        cache_key = f"{domain}:{qtype}"
        
        # Check cache
        if cache_key in self.cache:
            logger.debug(f"Cache hit for {domain}")
            return self.cache[cache_key]
        
        try:
            # Resolve DNS
            answers = self.resolver.resolve(domain, qtype)
            results = [str(rdata) for rdata in answers]
            
            # Cache results
            self.cache[cache_key] = results
            
            return results
            
        except Exception as e:
            logger.error(f"DNS resolution failed for {domain}: {e}")
            return None
    
    async def check_domain_security(self, domain: str) -> bool:
        """بررسی امنیتی دامنه"""
        # بررسی در لیست سیاه
        blacklisted = [
            "malware.test",
            "phishing.test",
            "spam.test"
        ]
        
        if domain in blacklisted:
            logger.warning(f"Blocked malicious domain: {domain}")
            return False
            
        return True

class DNSServer:
    """سرور DNS اصلی"""
    
    def __init__(self, resolver: DNSResolver, config):
        self.resolver = resolver
        self.config = config
        self.server = None
        self.running = False
        
        # آمار سرور
        self.stats = {
            "total_queries": 0,
            "cached_responses": 0,
            "blocked_domains": 0,
            "errors": 0
        }
    
    async def start(self):
        """شروع سرور DNS"""
        try:
            # ایجاد سوکت‌های UDP و TCP
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            udp_socket.bind(('0.0.0.0', self.config.dns_port))
            tcp_socket.bind(('0.0.0.0', self.config.dns_port))
            
            self.running = True
            logger.info(f"DNS Server listening on port {self.config.dns_port}")
            
            # مدیریت همزمان UDP و TCP
            await asyncio.gather(
                self.handle_udp(udp_socket),
                self.handle_tcp(tcp_socket)
            )
            
        except Exception as e:
            logger.error(f"Failed to start DNS server: {e}")
            raise
    
    async def handle_udp(self, socket):
        """مدیریت درخواست‌های UDP"""
        while self.running:
            try:
                data, addr = await asyncio.get_event_loop().sock_recvfrom(socket, 512)
                asyncio.create_task(self.process_dns_query(data, addr, socket, 'udp'))
            except Exception as e:
                logger.error(f"UDP handler error: {e}")
    
    async def handle_tcp(self, socket):
        """مدیریت درخواست‌های TCP"""
        socket.listen(100)
        while self.running:
            try:
                client, addr = await asyncio.get_event_loop().sock_accept(socket)
                asyncio.create_task(self.handle_tcp_client(client, addr))
            except Exception as e:
                logger.error(f"TCP handler error: {e}")
    
    async def process_dns_query(self, data: bytes, addr: Tuple[str, int], 
                                socket, protocol: str):
        """پردازش کوئری DNS"""
        try:
            self.stats["total_queries"] += 1
            
            # Parse DNS query
            query = dns.message.from_wire(data)
            domain = str(query.question[0].name).rstrip('.')
            qtype = query.question[0].rdtype
            
            logger.info(f"DNS Query from {addr[0]}: {domain} (Type: {qtype})")
            
            # Security check
            if not await self.resolver.check_domain_security(domain):
                self.stats["blocked_domains"] += 1
                response = self.create_blocked_response(query)
            else:
                # Resolve domain
                results = await self.resolver.resolve(domain, qtype)
                
                if results:
                    response = self.create_response(query, results)
                else:
                    response = self.create_error_response(query)
                    self.stats["errors"] += 1
            
            # Send response
            if protocol == 'udp':
                await asyncio.get_event_loop().sock_sendto(
                    socket, response.to_wire(), addr
                )
            
        except Exception as e:
            logger.error(f"Query processing error: {e}")
            self.stats["errors"] += 1
    
    def create_response(self, query, results):
        """ایجاد پاسخ DNS"""
        response = dns.message.make_response(query)
        for result in results:
            response.answer.append(result)
        return response
    
    def create_blocked_response(self, query):
        """ایجاد پاسخ برای دامنه‌های مسدود شده"""
        response = dns.message.make_response(query)
        response.set_rcode(dns.rcode.NXDOMAIN)
        return response
    
    def create_error_response(self, query):
        """ایجاد پاسخ خطا"""
        response = dns.message.make_response(query)
        response.set_rcode(dns.rcode.SERVFAIL)
        return response
    
    async def stop(self):
        """توقف سرور DNS"""
        self.running = False
        logger.info("DNS Server stopped")
    
    def get_stats(self):
        """دریافت آمار سرور"""
        return self.stats
