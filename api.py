"""
MasterDNS API با پشتیبانی DNS over HTTPS (DoH)
"""

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import time
import logging
import base64
import dns.message
import dns.rdatatype
import dns.resolver as dns_resolver_module  # اسم متفاوت برای جلوگیری از conflict

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
        version="2.1.1"
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
            "version": "2.1.1",
            "status": "running",
            "domain": config.railway_domain,
            "doh_endpoint": f"https://{config.railway_domain}/resolve?name=google.com&type=A"
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
        type: str = Query(default="A")
    ):
        """
        Google DNS-over-HTTPS JSON API compatible
        Example: /resolve?name=google.com&type=A
        """
        try:
            domain = name.rstrip('.')
            
            # تبدیل نوع رکورد
            qtype_map = {
                "A": dns.rdatatype.A,
                "AAAA": dns.rdatatype.AAAA,
                "CNAME": dns.rdatatype.CNAME,
                "MX": dns.rdatatype.MX,
                "TXT": dns.rdatatype.TXT,
                "NS": dns.rdatatype.NS,
            }
            qtype = qtype_map.get(type.upper(), dns.rdatatype.A)
            
            logger.info(f"DoH JSON: {domain} (Type: {type})")
            
            # استفاده از dns.resolver مستقیم
            import dns.resolver as dnsr
            resolver = dnsr.Resolver()
            resolver.nameservers = ['8.8.8.8', '1.1.1.1']
            resolver.timeout = 5
            resolver.lifetime = 10
            
            try:
                answers = resolver.resolve(domain, qtype)
                
                answer_list = []
                for rdata in answers:
                    answer_list.append({
                        "name": domain + ".",
                        "type": qtype,
                        "TTL": answers.ttl,
                        "data": str(rdata)
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
                
                # آپدیت آمار
                dns_server.stats["total_queries"] += 1
                
                return response
                
            except dns.resolver.NXDOMAIN:
                return {
                    "Status": 3,
                    "Question": [{"name": f"{domain}.", "type": qtype}]
                }
                
            except Exception as e:
                logger.error(f"DNS error for {domain}: {e}")
                return {
                    "Status": 2,
                    "Question": [{"name": f"{domain}.", "type": qtype}],
                    "Comment": f"Upstream error: {str(e)}"
                }
                
        except Exception as e:
            logger.error(f"General error: {e}")
            return {
                "Status": 2,
                "Comment": f"Error: {str(e)}"
            }
    
    # ============================================
    # DoH - Standard wire format
    # ============================================
    @app.get("/dns-query")
    async def doh_get(request: Request, dns: str = Query(default=None)):
        if not dns:
            # اگر name پارامتر داده شده، از JSON format استفاده کن
            name = request.query_params.get("name")
            if name:
                return await resolve_json(
                    name=name,
                    type=request.query_params.get("type", "A")
                )
            raise HTTPException(status_code=400, detail="Missing 'dns' or 'name' parameter")
        return await process_doh_query(dns, dns_server)
    
    @app.post("/dns-query")
    async def doh_post(request: Request):
        content_type = request.headers.get("content-type", "")
        
        if content_type == "application/dns-message":
            body = await request.body()
            return await process_doh_raw(body, dns_server)
        else:
            try:
                data = await request.json()
                if "name" in data:
                    return await resolve_json(
                        name=data["name"],
                        type=data.get("type", "A")
                    )
                dns_param = data.get("dns")
                if dns_param:
                    return await process_doh_query(dns_param, dns_server)
            except:
                pass
            raise HTTPException(status_code=400, detail="Invalid request")
    
    # ============================================
    # Test
    # ============================================
    @app.get("/doh-test")
    async def doh_test():
        domain = "google.com"
        test_url = f"https://blckholegate-production.up.railway.app/resolve?name={domain}&type=A"
        
        return {
            "message": "برای تست DoH این لینک رو باز کن:",
            "test_url": test_url,
            "curl_test": f"curl '{test_url}'",
            "intra_settings": {
                "url": "https://blckholegate-production.up.railway.app/resolve",
                "format": "Google JSON"
            }
        }
    
    # ============================================
    # Simple API
    # ============================================
    @app.post("/api/resolve")
    async def api_resolve(request: DNSRequest):
        if not request.domain:
            raise HTTPException(status_code=400, detail="Domain is required")
        try:
            results = await dns_server.resolver.resolve(request.domain)
            return {"domain": request.domain, "results": results}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
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
# Helper Functions
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
        
        response = dns.message.make_response(query)
        import dns.resolver as dnsr
        resolver = dnsr.Resolver()
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
        raise HTTPException(status_code=400, detail=str(e))


async def process_doh_raw(body: bytes, dns_server):
    """پردازش DoH raw message"""
    try:
        query = dns.message.from_wire(body)
        domain = str(query.question[0].name).rstrip('.')
        qtype = query.question[0].rdtype
        
        response = dns.message.make_response(query)
        import dns.resolver as dnsr
        resolver = dnsr.Resolver()
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
        raise HTTPException(status_code=400, detail=str(e))
