"""
MasterDNS API با پشتیبانی DNS over HTTPS (DoH)
پشتیبانی از Google/Cloudflare DoH JSON format
"""

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
import time
import logging
import base64
import json
import dns.message
import dns.rdatatype
import dns.resolver
import dns.name
import dns.rdata
import socket
import struct

logger = logging.getLogger(__name__)

class DNSRequest(BaseModel):
    domain: str

class DomainRequest(BaseModel):
    domain: str
    description: str = ""

def create_api(dns_server, config):
    
    app = FastAPI(
        title="MasterDNS API + DoH",
        description="DNS Server with DoH support",
        version="2.1.0"
    )
    
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
            "version": "2.1.0",
            "status": "running",
            "domain": config.railway_domain,
            "doh_endpoint": f"https://{config.railway_domain}/dns-query",
            "doh_json": f"https://{config.railway_domain}/resolve?name=google.com&type=A"
        }
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "doh": "enabled"}
    
    # ============================================
    # DoH - Google JSON API Style (برای Intra/Slipnet)
    # ============================================
    @app.get("/resolve")
    async def resolve_json(
        name: str = Query(...),
        type: str = Query(default="A"),
        cd: str = Query(default="false"),
        do: str = Query(default="false")
    ):
        """
        Google DNS-over-HTTPS JSON API compatible
        Example: /resolve?name=google.com&type=A
        
        این فرمت با Intra و خیلی از کلاینت‌ها سازگاره
        """
        try:
            domain = name.rstrip('.')
            qtype = getattr(dns.rdatatype, type.upper(), dns.rdatatype.A)
            
            logger.info(f"Resolving: {domain} (Type: {type})")
            
            # Resolve
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ['8.8.8.8', '1.1.1.1']
            resolver.timeout = 5
            resolver.lifetime = 10
            
            try:
                answers = resolver.resolve(domain, qtype)
                
                # ساخت پاسخ به فرمت Google DoH JSON
                answer_list = []
                for answer in answers:
                    answer_list.append({
                        "name": str(answer.name).rstrip('.'),
                        "type": answer.rdtype,
                        "TTL": answer.ttl,
                        "data": str(answer)
                    })
                
                response = {
                    "Status": 0,
                    "TC": False,
                    "RD": True,
                    "RA": True,
                    "AD": False,
                    "CD": False,
                    "Question": [{
                        "name": f"{domain}.",
                        "type": qtype
                    }],
                    "Answer": answer_list
                }
                
                dns_server.stats["total_queries"] += 1
                return response
                
            except dns.resolver.NXDOMAIN:
                return {
                    "Status": 3,
                    "TC": False,
                    "RD": True,
                    "RA": True,
                    "AD": False,
                    "CD": False,
                    "Question": [{"name": f"{domain}.", "type": qtype}],
                    "Authority": []
                }
                
            except Exception as e:
                logger.error(f"Resolve error: {e}")
                return {
                    "Status": 2,
                    "TC": False,
                    "RD": True,
                    "RA": True,
                    "AD": False,
                    "CD": False,
                    "Question": [{"name": f"{domain}.", "type": qtype}],
                    "Comment": str(e)
                }
                
        except Exception as e:
            logger.error(f"JSON DoH error: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    # ============================================
    # DoH - Standard wire format (GET + POST)
    # ============================================
    @app.get("/dns-query")
    async def doh_get(request: Request, dns: str = Query(default=None)):
        """DNS over HTTPS - GET (RFC 8484)"""
        if not dns:
            raise HTTPException(status_code=400, detail="Missing 'dns' parameter")
        return await process_doh_query(dns, dns_server)
    
    @app.post("/dns-query")
    async def doh_post(request: Request):
        """DNS over HTTPS - POST (RFC 8484)"""
        content_type = request.headers.get("content-type", "")
        
        if content_type == "application/dns-message":
            body = await request.body()
            return await process_doh_raw(body, dns_server)
        else:
            data = await request.json()
            dns_param = data.get("dns")
            if not dns_param:
                raise HTTPException(status_code=400, detail="Missing 'dns'")
            return await process_doh_query(dns_param, dns_server)
    
    # ============================================
    # DoH - Cloudflare Style (DNS wire format in body)
    # ============================================
    @app.api_route("/dns-query", methods=["GET", "POST"])
    async def doh_rfc8484(request: Request):
        """
        Full RFC 8484 DoH endpoint
        Supports both GET and POST
        """
        if request.method == "GET":
            dns_param = request.query_params.get("dns")
            if dns_param:
                return await process_doh_query(dns_param, dns_server)
            
            # Fallback: try Google JSON format
            name = request.query_params.get("name")
            if name:
                return await resolve_json(name=name, type=request.query_params.get("type", "A"))
            
            raise HTTPException(status_code=400, detail="Missing query parameters")
        
        elif request.method == "POST":
            content_type = request.headers.get("content-type", "")
            
            if content_type == "application/dns-message":
                body = await request.body()
                return await process_doh_raw(body, dns_server)
            else:
                # Try JSON
                try:
                    data = await request.json()
                    if "name" in data:
                        return await resolve_json(
                            name=data["name"],
                            type=data.get("type", "A")
                        )
                except:
                    pass
                
                # Try form data
                form = await request.form()
                if "dns" in form:
                    return await process_doh_query(form["dns"], dns_server)
                
                raise HTTPException(status_code=400, detail="Invalid request")
    
    # ============================================
    # Simple resolve endpoint
    # ============================================
    @app.post("/api/resolve")
    async def api_resolve(request: DNSRequest):
        """حل دامنه با JSON POST"""
        if not request.domain:
            raise HTTPException(status_code=400, detail="Domain is required")
        try:
            results = await dns_server.resolver.resolve(request.domain)
            return {"domain": request.domain, "results": results}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ============================================
    # Test & Debug
    # ============================================
    @app.get("/doh-test")
    async def doh_test():
        """صفحه تست DoH"""
        domain = "google.com"
        
        # Test URL
        test_url = f"https://{config.railway_domain}/resolve?name={domain}&type=A"
        
        # DNS wire format test
        query = dns.message.make_query(domain, dns.rdatatype.A)
        query.id = 0
        wire_b64 = base64.urlsafe_b64encode(query.to_wire()).decode('utf-8').rstrip('=')
        doh_url = f"https://{config.railway_domain}/dns-query?dns={wire_b64}"
        
        return {
            "message": "DoH endpoints ready!",
            "test_urls": {
                "json_format": test_url,
                "wire_format": doh_url,
                "curl_test": f"curl '{test_url}'",
                "dig_test": f"dig @{config.railway_domain} {domain} +https"
            },
            "settings": {
                "doh_url": f"https://{config.railway_domain}/resolve",
                "doh_host": config.railway_domain,
                "doh_path": "/resolve",
                "doh_query_format": "google_json"
            }
        }
    
    # ============================================
    # Stats & Management
    # ============================================
    @app.get("/stats")
    async def get_stats():
        return {"dns_stats": dns_server.get_stats() if dns_server else {}}
    
    @app.get("/whitelist")
    async def get_whitelist():
        return {"domains": list(dns_server.resolver.whitelist_domains)}
    
    @app.post("/whitelist/add")
    async def add_whitelist(request: DomainRequest):
        dns_server.resolver.whitelist_domains.add(request.domain)
        return {"status": "success", "domain": request.domain}
    
    @app.on_event("startup")
    async def startup():
        app.state.start_time = time.time()
        logger.info("🚀 MasterDNS DoH started")
    
    return app


# ============================================
# DoH Processing Functions
# ============================================

async def process_doh_query(dns_param: str, dns_server):
    """پردازش DoH base64 query"""
    try:
        padding = 4 - len(dns_param) % 4
        if padding != 4:
            dns_param += '=' * padding
        
        wire = base64.urlsafe_b64decode(dns_param)
        query = dns.message.from_wire(wire)
        domain = str(query.question[0].name).rstrip('.')
        qtype = query.question[0].rdtype
        
        logger.info(f"DoH query: {domain}")
        
        response = dns.message.make_response(query)
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['8.8.8.8', '1.1.1.1']
        resolver.timeout = 5
        resolver.lifetime = 10
        
        try:
            answers = resolver.resolve(domain, qtype)
            for answer in answers:
                response.answer.append(answer)
            dns_server.stats["total_queries"] += 1
        except:
            response.set_rcode(dns.rcode.SERVFAIL)
        
        response_b64 = base64.urlsafe_b64encode(response.to_wire()).decode('utf-8').rstrip('=')
        
        return Response(content=response_b64, media_type="application/dns-message")
        
    except Exception as e:
        logger.error(f"DoH error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


async def process_doh_raw(body: bytes, dns_server):
    """پردازش DoH raw message"""
    try:
        query = dns.message.from_wire(body)
        domain = str(query.question[0].name).rstrip('.')
        qtype = query.question[0].rdtype
        
        response = dns.message.make_response(query)
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['8.8.8.8', '1.1.1.1']
        resolver.timeout = 5
        resolver.lifetime = 10
        
        try:
            answers = resolver.resolve(domain, qtype)
            for answer in answers:
                response.answer.append(answer)
            dns_server.stats["total_queries"] += 1
        except:
            response.set_rcode(dns.rcode.SERVFAIL)
        
        return Response(content=response.to_wire(), media_type="application/dns-message")
        
    except Exception as e:
        logger.error(f"DoH raw error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
