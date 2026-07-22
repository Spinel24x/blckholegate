"""
MasterDNS - Optimized for Intra/Slipnet/Nebulo
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import time
import logging
import base64
import dns.message
import dns.rdatatype

logger = logging.getLogger(__name__)

def create_api(dns_server, config):
    
    app = FastAPI(title="MasterDNS DoH", version="4.0.0")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # ============================================
    # Main DoH endpoint - همه چی رو قبول می‌کنه
    # ============================================
    @app.api_route("/dns-query", methods=["GET", "POST", "HEAD", "OPTIONS"])
    async def doh_main(request: Request):
        """
        DoH endpoint اصلی
        اگه پارامتر name باشه → Google JSON
        اگه پارامتر dns باشه → Wire format
        اگه POST با body باشه → Wire format raw
        در غیر این صورت → صفحه راهنما
        """
        
        # CORS preflight
        if request.method == "OPTIONS":
            return Response(status_code=200)
        
        # GET request
        if request.method == "GET":
            params = request.query_params
            
            # Google JSON format
            if "name" in params:
                return google_dns(
                    params.get("name", "google.com"),
                    params.get("type", "A"),
                    dns_server
                )
            
            # Wire format base64
            if "dns" in params:
                return wire_dns_b64(params.get("dns"), dns_server)
            
            # اگر هیچ پارامتری نبود، یه تست برگردون
            # این برای کلاینت‌هایی که اول تست می‌کنن
            return google_dns("google.com", "A", dns_server)
        
        # POST request
        if request.method == "POST":
            content_type = request.headers.get("content-type", "")
            
            # Wire format (application/dns-message)
            if "dns-message" in content_type:
                body = await request.body()
                if body:
                    return wire_dns_raw(body, dns_server)
            
            # Try JSON body
            try:
                body = await request.json()
                if body:
                    if "name" in body:
                        return google_dns(
                            body.get("name", "google.com"),
                            body.get("type", "A"),
                            dns_server
                        )
                    if "dns" in body:
                        return wire_dns_b64(body["dns"], dns_server)
            except:
                pass
            
            # Try form data
            try:
                form = await request.form()
                if "name" in form:
                    return google_dns(
                        form.get("name", "google.com"),
                        form.get("type", "A"),
                        dns_server
                    )
            except:
                pass
            
            # Try raw body as DNS wire format
            try:
                body = await request.body()
                if body and len(body) >= 12:
                    return wire_dns_raw(body, dns_server)
            except:
                pass
            
            # Fallback - return test response
            # بعضی کلاینت‌ها POST خالی می‌فرستن برای تست
            return google_dns("google.com", "A", dns_server)
        
        # Fallback for any other method
        return google_dns("google.com", "A", dns_server)
    
    # ============================================
    # Simple resolve (Google JSON format)
    # ============================================
    @app.api_route("/resolve", methods=["GET", "POST"])
    async def simple_resolve(request: Request):
        """Google JSON API compatible"""
        
        name = None
        rtype = "A"
        
        if request.method == "GET":
            name = request.query_params.get("name")
            rtype = request.query_params.get("type", "A")
        else:
            try:
                data = await request.json()
                name = data.get("name")
                rtype = data.get("type", "A")
            except:
                try:
                    form = await request.form()
                    name = form.get("name")
                    rtype = form.get("type", "A")
                except:
                    pass
        
        if not name:
            name = "google.com"
        
        return google_dns(name, rtype, dns_server)
    
    # ============================================
    # Health check
    # ============================================
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    @app.get("/")
    async def root():
        return {
            "service": "MasterDNS DoH",
            "doh_url": f"https://{config.railway_domain}/dns-query",
            "status": "running"
        }
    
    @app.get("/stats")
    async def stats():
        return {"queries": dns_server.stats.get("total_queries", 0)}
    
    return app


# ============================================
# Google JSON DNS Resolver
# ============================================
def google_dns(name: str, rtype: str, dns_server):
    """Resolve DNS and return Google JSON format"""
    try:
        domain = name.rstrip('.')
        
        qtype_map = {
            "A": dns.rdatatype.A,
            "AAAA": dns.rdatatype.AAAA,
            "CNAME": dns.rdatatype.CNAME,
            "MX": dns.rdatatype.MX,
            "TXT": dns.rdatatype.TXT,
            "NS": dns.rdatatype.NS,
        }
        qtype = qtype_map.get(rtype.upper(), dns.rdatatype.A)
        
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['8.8.8.8', '1.1.1.1']
        resolver.timeout = 5
        resolver.lifetime = 10
        
        answers = resolver.resolve(domain, qtype)
        
        answer_list = []
        for rdata in answers:
            answer_list.append({
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
            "Answer": answer_list
        }
        
    except dns.resolver.NXDOMAIN:
        return {"Status": 3, "Question": [{"name": f"{domain}.", "type": qtype}]}
    except Exception as e:
        return {"Status": 2, "Question": [{"name": f"{domain}.", "type": qtype}], "Comment": str(e)}


# ============================================
# Wire Format DNS Resolver
# ============================================
def wire_dns_b64(dns_b64: str, dns_server):
    """Resolve from base64 wire format"""
    try:
        padding = 4 - len(dns_b64) % 4
        if padding != 4:
            dns_b64 += '=' * padding
        
        wire = base64.urlsafe_b64decode(dns_b64)
        return process_wire(wire, dns_server)
    except:
        raise HTTPException(status_code=400, detail="Invalid base64")


def wire_dns_raw(body: bytes, dns_server):
    """Resolve from raw wire format"""
    try:
        return process_wire(body, dns_server)
    except:
        raise HTTPException(status_code=400, detail="Invalid DNS message")


def process_wire(wire: bytes, dns_server):
    """Process DNS wire format"""
    query = dns.message.from_wire(wire)
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
        dns_server.stats["total_queries"] = dns_server.stats.get("total_queries", 0) + 1
    except:
        response.set_rcode(dns.rcode.SERVFAIL)
    
    return Response(content=response.to_wire(), media_type="application/dns-message")
