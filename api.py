"""
REST API برای مدیریت MasterDNS
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time
import logging

logger = logging.getLogger(__name__)

class DNSRequest(BaseModel):
    domain: str

class DomainRequest(BaseModel):
    domain: str
    description: str = ""

def create_api(dns_server, config):
    
    app = FastAPI(
        title="MasterDNS API",
        description="DNS Server Management API for Railway",
        version="1.0.0"
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
            "version": "1.0.0",
            "status": "running",
            "domain": config.railway_domain,
            "api_port": config.api_port,
            "endpoints": {
                "health": f"https://{config.railway_domain}/health",
                "docs": f"https://{config.railway_domain}/docs",
                "stats": f"https://{config.railway_domain}/stats"
            },
            "timestamp": time.time()
        }
    
    @app.get("/health")
    async def health_check():
        """سلامت سرویس - برای Railway Healthcheck"""
        return {
            "status": "healthy",
            "timestamp": time.time()
        }
    
    @app.get("/stats")
    async def get_stats():
        """آمار سرور"""
        return {
            "dns_stats": dns_server.get_stats() if dns_server else {},
            "timestamp": time.time()
        }
    
    @app.post("/resolve")
    async def resolve_domain(request: DNSRequest):
        """حل یک دامنه"""
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
    
    @app.get("/whitelist")
    async def get_whitelist():
        """لیست سفید"""
        return {"domains": list(dns_server.resolver.whitelist_domains)}
    
    @app.post("/whitelist/add")
    async def add_whitelist(request: DomainRequest):
        """افزودن به لیست سفید"""
        dns_server.resolver.whitelist_domains.add(request.domain)
        return {"status": "success", "domain": request.domain}
    
    @app.get("/config")
    async def get_config():
        """تنظیمات فعلی"""
        return {
            "domain": config.railway_domain,
            "api_port": config.api_port,
            "environment": config.environment
        }
    
    @app.on_event("startup")
    async def startup():
        app.state.start_time = time.time()
        logger.info("API started successfully")
    
    return app
