"""
MasterDNS API با پشتیبانی DNS over HTTPS (DoH)
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import time
import logging
import base64
import dns.message
import dns.query
import dns.rdatatype
import dns.resolver

logger = logging.getLogger(__name__)

class DNSRequest(BaseModel):
    domain: str

class DomainRequest(BaseModel):
    domain: str
    description: str = ""

def create_api(dns_server, config):
    
    app = FastAPI(
        title="MasterDNS API + DoH",
        description="DNS Server Management API with DNS over HTTPS support",
        version="2.0.0"
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/")
    async def root():
        return {
            "service": "MasterDNS",
            "version": "2.0.0",
            "status": "running",
            "domain": config.railway_domain,
            "doh_endpoint": f"https://{config.railway_domain}/dns-query",
            "endpoints": {
                "health": f"https://{config.railway_domain}/health",
                "doh": f"https://{config.railway_domain}/dns-query",
                "docs": f"https://{config.railway_domain}/docs"
            },
            "timestamp": time.time()
        }
    
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "service": "MasterDNS",
            "doh": "enabled",
            "timestamp": time.time()
        }
    
    # ============================================
    # DNS over HTTPS (DoH) - GET Method
    # ============================================
    @app.get("/dns-query")
    async def doh_get(request: Request):
        """
        DNS over HTTPS - GET method
        استفاده در مرورگر و کلاینت‌های DoH
        Example: /dns-query?dns=AAABAAABAAAAAAAABmdvb2dsZQNjb20AAAEAAQ
        """
        dns_param = request.query_params.get("dns")
        
        if not dns_param:
            raise HTTPException(status_code=400, detail="Missing 'dns' parameter")
        
        return await process_doh_query(dns_param, dns_server)
    
    # ============================================
    # DNS over HTTPS (DoH) - POST Method
    # ============================================
    @app.post("/dns-query")
    async def doh_post(request: Request):
        """
        DNS over HTTPS - POST method
        استاندارد برای کلاینت‌های DNS
        Content-Type: application/dns-message
        """
        content_type = request.headers.get("content-type", "")
        
        if content_type == "application/dns-message":
            # Raw DNS message
            body = await request.body()
            return await process_doh_raw(body, dns_server)
        else:
            # JSON or form data
            data = await request.json()
            dns_param = data.get("dns")
            
            if not dns_param:
                raise HTTPException(status_code=400, detail="Missing 'dns' parameter")
            
            return await process_doh_query(dns_param, dns_server)
    
    # ============================================
    # Simple DNS Resolve (JSON API)
    # ============================================
    @app.post("/resolve")
    async def resolve_domain(request: DNSRequest):
        """حل دامنه با JSON"""
        if not request.domain:
            raise HTTPException(status_code=400, detail="Domain is required")
        
        try:
            results = await dns_server.resolver.resolve(request.domain)
            return {
                "domain": request.domain,
                "results": results,
                "timestamp": time.time()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ============================================
    # Test DoH Endpoint
    # ============================================
    @app.get("/doh-test")
    async def doh_test():
        """تست DoH با کوئری نمونه"""
        # یه کوئری ساده برای google.com
        query = dns.message.make_query("google.com", dns.rdatatype.A)
        query.id = 0
        wire = query.to_wire()
        encoded = base64.urlsafe_b64encode(wire).decode('utf-8').rstrip('=')
        
        return {
            "message": "برای تست DoH از این لینک استفاده کن:",
            "test_url": f"https://{config.railway_domain}/dns-query?dns={encoded}",
            "curl_command": f"curl '{config.railway_domain}/dns-query?dns={encoded}'",
            "curl_post": f"curl -X POST -H 'Content-Type: application/dns-message' --data-binary @query.bin {config.railway_domain}/dns-query",
            "dig_command": f"dig @{config.railway_domain} google.com +https"
        }
    
    # ============================================
    # Stats & Management
    # ============================================
    @app.get("/stats")
    async def get_stats():
        return {
            "dns_stats": dns_server.get_stats() if dns_server else {},
            "doh_enabled": True,
            "timestamp": time.time()
        }
    
    @app.get("/whitelist")
    async def get_whitelist():
        return {"domains": list(dns_server.resolver.whitelist_domains)}
    
    @app.post("/whitelist/add")
    async def add_whitelist(request: DomainRequest):
        dns_server.resolver.whitelist_domains.add(request.domain)
        return {"status": "success", "domain": request.domain}
    
    @app.get("/config")
    async def get_config():
        return {
            "domain": config.railway_domain,
            "api_port": config.api_port,
            "doh_endpoint": f"https://{config.railway_domain}/dns-query",
            "environment": config.environment
        }
    
    @app.on_event("startup")
    async def startup():
        app.state.start_time = time.time()
        logger.info("🚀 MasterDNS API + DoH started successfully")
    
    return app


# ============================================
# DoH Helper Functions
# ============================================

async def process_doh_query(dns_param: str, dns_server):
    """
    پردازش کوئری DNS over HTTPS (Base64 encoded)
    """
    try:
        # Decode Base64 URL-safe DNS query
        # اضافه کردن padding اگر لازم باشه
        padding = 4 - len(dns_param) % 4
        if padding != 4:
            dns_param += '=' * padding
        
        wire = base64.urlsafe_b64decode(dns_param)
        query = dns.message.from_wire(wire)
        
        # استخراج دامنه
        domain = str(query.question[0].name).rstrip('.')
        qtype = query.question[0].rdtype
        
        logger.info(f"DoH Query: {domain} (Type: {qtype})")
        
        # ساخت پاسخ
        response = dns.message.make_response(query)
        
        # تنظیم DNS resolver با upstream
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['8.8.8.8', '1.1.1.1']
        resolver.timeout = 3
        resolver.lifetime = 5
        
        try:
            # تلاش برای resolve
            answers = resolver.resolve(domain, qtype)
            
            # اضافه کردن پاسخ‌ها
            for answer in answers:
                response.answer.append(answer)
            
            # آپدیت آمار
            dns_server.stats["total_queries"] += 1
            
        except dns.resolver.NXDOMAIN:
            response.set_rcode(dns.rcode.NXDOMAIN)
            dns_server.stats["failed"] += 1
            
        except dns.resolver.NoAnswer:
            response.set_rcode(dns.rcode.NOERROR)
            dns_server.stats["failed"] += 1
            
        except Exception as e:
            logger.error(f"Upstream DNS error: {e}")
            response.set_rcode(dns.rcode.SERVFAIL)
            dns_server.stats["failed"] += 1
        
        # Encode response
        response_wire = response.to_wire()
        response_b64 = base64.urlsafe_b64encode(response_wire).decode('utf-8').rstrip('=')
        
        return Response(
            content=response_b64,
            media_type="application/dns-message"
        )
        
    except Exception as e:
        logger.error(f"DoH processing error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid DNS query: {str(e)}")


async def process_doh_raw(body: bytes, dns_server):
    """
    پردازش کوئری DNS over HTTPS (Raw DNS message)
    """
    try:
        query = dns.message.from_wire(body)
        domain = str(query.question[0].name).rstrip('.')
        qtype = query.question[0].rdtype
        
        logger.info(f"DoH Raw Query: {domain} (Type: {qtype})")
        
        response = dns.message.make_response(query)
        
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['8.8.8.8', '1.1.1.1']
        resolver.timeout = 3
        resolver.lifetime = 5
        
        try:
            answers = resolver.resolve(domain, qtype)
            for answer in answers:
                response.answer.append(answer)
            dns_server.stats["total_queries"] += 1
        except dns.resolver.NXDOMAIN:
            response.set_rcode(dns.rcode.NXDOMAIN)
        except Exception:
            response.set_rcode(dns.rcode.SERVFAIL)
        
        return Response(
            content=response.to_wire(),
            media_type="application/dns-message"
        )
        
    except Exception as e:
        logger.error(f"DoH raw processing error: {e}")
        raise HTTPException(status_code=400, detail="Invalid DNS message")
