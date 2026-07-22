"""
MasterDNS - Full DoH Server
پشتیبانی از تمام فرمت‌های DoH
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
import dns.name

logger = logging.getLogger(__name__)

class DNSRequest(BaseModel):
    domain: str
    type: str = "A"

class DomainRequest(BaseModel):
    domain: str
    description: str = ""

def create_api(dns_server, config):
    
    app = FastAPI(
        title="MasterDNS DoH Server",
        version="3.0.0"
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
            "service": "MasterDNS DoH",
            "version": "3.0.0",
            "status": "running",
            "doh_url": f"https://{config.railway_domain}/dns-query",
            "test": f"https://{config.railway_domain}/dns-query?name=google.com"
        }
    
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    # ============================================
    # ENDPOINT اصلی DoH - قبول همه متدها
    # ============================================
    @app.api_route("/dns-query", methods=["GET", "POST", "PUT", "PATCH"])
    async def doh_handler(request: Request):
        """
        Handler اصلی DoH
        قبول GET و POST
        پشتیبانی از:
        - Google JSON format
        - RFC 8484 wire format
        - Cloudflare style
        """
        
        # ============================================
        # GET Request
        # ============================================
        if request.method == "GET":
            params = request.query_params
            
            # 1. Google JSON style: ?name=domain.com&type=A
            if "name" in params:
                return await google_json_resolve(
                    name=params.get("name"),
                    type=params.get("type", "A"),
                    dns_server=dns_server
                )
            
            # 2. RFC 8484 wire format: ?dns=base64string
            if "dns" in params:
                return await rfc8484_wire_resolve(
                    dns_b64=params.get("dns"),
                    dns_server=dns_server
                )
            
            # 3. Cloudflare style: ?ct=application/dns-json&name=domain.com
            ct = params.get("ct", "")
            if "json" in ct and "name" in params:
                return await google_json_resolve(
                    name=params.get("name"),
                    type=params.get("type", "A"),
                    dns_server=dns_server
                )
            
            # هیچ پارامتری نبود
            return {
                "error": "Missing parameters",
                "usage": {
                    "json_format": f"{request.url.scheme}://{request.url.netloc}/dns-query?name=google.com&type=A",
                    "wire_format": f"{request.url.scheme}://{request.url.netloc}/dns-query?dns=BASE64",
                    "curl_example": f"curl '{request.url.scheme}://{request.url.netloc}/dns-query?name=google.com'"
                }
            }
        
        # ============================================
        # POST Request
        # ============================================
        elif request.method == "POST":
            content_type = request.headers.get("content-type", "")
            
            # 1. application/dns-message (RFC 8484 wire format)
            if "dns-message" in content_type:
                body = await request.body()
                return await rfc8484_raw_resolve(body, dns_server)
            
            # 2. application/json (Google JSON format)
            elif "json" in content_type:
                try:
                    data = await request.json()
                    name = data.get("name")
                    if name:
                        return await google_json_resolve(
                            name=name,
                            type=data.get("type", "A"),
                            dns_server=dns_server
                        )
                except:
                    pass
            
            # 3. application/x-www-form-urlencoded
            elif "form" in content_type:
                try:
                    form = await request.form()
                    name = form.get("name")
                    if name:
                        return await google_json_resolve(
                            name=name,
                            type=form.get("type", "A"),
                            dns_server=dns_server
                        )
                    dns_param = form.get("dns")
                    if dns_param:
                        return await rfc8484_wire_resolve(dns_param, dns_server)
                except:
                    pass
            
            # 4. Raw body as DNS wire format
            try:
                body = await request.body()
                if body and len(body) > 12:  # Minimum DNS query size
                    return await rfc8484_raw_resolve(body, dns_server)
            except:
                pass
            
            # 5. Try JSON body anyway
            try:
                data = await request.json()
                name = data.get("name")
                if name:
                    return await google_json_resolve(
                        name=name,
                        type=data.get("type", "A"),
                        dns_server=dns_server
                    )
            except:
                pass
            
            raise HTTPException(status_code=400, detail="Invalid POST request")
        
        # ============================================
        # Other methods - Try as GET
        # ============================================
        else:
            params = request.query_params
            if "name" in params:
                return await google_json_resolve(
                    name=params.get("name"),
                    type=params.get("type", "A"),
                    dns_server=dns_server
                )
            raise HTTPException(status_code=405, detail="Method not allowed")
    
    # ============================================
    # Endpoint ساده Google JSON
    # ============================================
    @app.get("/resolve")
    @app.post("/resolve")
    async def simple_resolve(
        request: Request,
        name: str = Query(default=None),
        type: str = Query(default="A")
    ):
        """Endpoint ساده برای Google JSON format"""
        if not name:
            # Try POST body
            try:
                data = await request.json()
                name = data.get("name")
                type = data.get("type", "A")
            except:
                pass
        
        if not name:
            raise HTTPException(status_code=400, detail="Missing 'name' parameter")
        
        return await google_json_resolve(name=name, type=type, dns_server=dns_server)
    
    # ============================================
    # Test page
    # ============================================
    @app.get("/test")
    async def test_page():
        return {
            "test_urls": {
                "json_format": "https://blckholegate-production.up.railway.app/dns-query?name=google.com&type=A",
                "wire_format": "https://blckholegate-production.up.railway.app/dns-query?dns=AAABAAABAAAAAAAABmdvb2dsZQNjb20AAAEAAQ",
                "simple": "https://blckholegate-production.up.railway.app/resolve?name=google.com"
            },
            "intra_settings": {
                "server_url": "https://blckholegate-production.up.railway.app/dns-query",
                "method": "GET"
            }
        }
    
    # ============================================
    # Stats
    # ============================================
    @app.get("/stats")
    async def stats():
        return {"queries": dns_server.stats.get("total_queries", 0)}
    
    @app.on_event("startup")
    async def startup():
        logger.info("🚀 MasterDNS DoH v3.0 ready")
    
    return app


# ============================================
# Google JSON Format Resolver
# ============================================
async def google_json_resolve(name: str, type: str, dns_server):
    """حل DNS به فرمت Google JSON"""
    try:
        domain = name.rstrip('.')
        
        qtype_map = {
            "A": dns.rdatatype.A,
            "AAAA": dns.rdatatype.AAAA,
            "CNAME": dns.rdatatype.CNAME,
            "MX": dns.rdatatype.MX,
            "TXT": dns.rdatatype.TXT,
            "NS": dns.rdatatype.NS,
            "SOA": dns.rdatatype.SOA,
        }
        qtype = qtype_map.get(type.upper(), dns.rdatatype.A)
        
        logger.info(f"Resolving: {domain} ({type})")
        
        # Use fresh resolver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['8.8.8.8', '1.1.1.1']
        resolver.timeout = 5
        resolver.lifetime = 10
        
        try:
            answers = resolver.resolve(domain, qtype)
            
            answer_data = []
            for rdata in answers:
                answer_data.append({
                    "name": f"{domain}.",
                    "type": qtype,
                    "TTL": answers.ttl,
                    "data": str(rdata)
                })
            
            dns_server.stats["total_queries"] = dns_server.stats.get("total_queries", 0) + 1
            
            return {
                "Status": 0,
                "TC": False,
                "RD": True,
                "RA": True,
                "AD": False,
                "CD": False,
                "Question": [{"name": f"{domain}.", "type": qtype}],
                "Answer": answer_data
            }
            
        except dns.resolver.NXDOMAIN:
            return {
                "Status": 3,
                "Question": [{"name": f"{domain}.", "type": qtype}]
            }
            
        except Exception as e:
            logger.error(f"DNS error: {e}")
            return {
                "Status": 2,
                "Question": [{"name": f"{domain}.", "type": qtype}],
                "Comment": f"DNS error: {str(e)}"
            }
            
    except Exception as e:
        logger.error(f"General error: {e}")
        return {
            "Status": 2,
            "Comment": f"Error: {str(e)}"
        }


# ============================================
# RFC 8484 Wire Format Resolver
# ============================================
async def rfc8484_wire_resolve(dns_b64: str, dns_server):
    """حل DNS از base64 wire format"""
    try:
        # Add padding
        padding = 4 - len(dns_b64) % 4
        if padding != 4:
            dns_b64 += '=' * padding
        
        wire = base64.urlsafe_b64decode(dns_b64)
        query = dns.message.from_wire(wire)
        domain = str(query.question[0].name).rstrip('.')
        qtype = query.question[0].rdtype
        
        return await resolve_wire_format(domain, qtype, query, dns_server)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid DNS query: {e}")


async def rfc8484_raw_resolve(body: bytes, dns_server):
    """حل DNS از raw wire format"""
    try:
        query = dns.message.from_wire(body)
        domain = str(query.question[0].name).rstrip('.')
        qtype = query.question[0].rdtype
        
        return await resolve_wire_format(domain, qtype, query, dns_server)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid DNS message: {e}")


async def resolve_wire_format(domain: str, qtype: int, query, dns_server):
    """حل و ساخت پاسخ wire format"""
    response = dns.message.make_response(query)
    
    resolver = dns.resolver.Resolver()
    resolver.nameservers = ['8.8.8.8', '1.1.1.1']
    resolver.timeout = 5
    resolver.lifetime = 10
    
    try:
        answers = resolver.resolve(domain, qtype)
        for answer in answers:
            response.answer.append(answer)
        dns_server.stats["total_queries"] = dns_server.stats.get("total_queries", 0) + 1
    except dns.resolver.NXDOMAIN:
        response.set_rcode(dns.rcode.NXDOMAIN)
    except Exception:
        response.set_rcode(dns.rcode.SERVFAIL)
    
    return Response(
        content=response.to_wire(),
        media_type="application/dns-message"
    )
