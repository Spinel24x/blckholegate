"""
MasterDNS - Pure RFC 8484 DoH Server
مخصوص Intra/Slipnet/Nebulo
"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
import time
import logging
import dns.message
import dns.resolver
import dns.rdatatype
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("doh")

def create_api(dns_server, config):
    
    app = FastAPI(title="MasterDNS DoH")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/")
    async def root():
        return {
            "service": "MasterDNS DoH",
            "endpoint": f"https://{config.railway_domain}/dns-query",
            "method": "POST",
            "content_type": "application/dns-message"
        }
    
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    # ============================================
    # RFC 8484 DoH - POST application/dns-message
    # ============================================
    @app.post("/dns-query")
    async def doh_post(request: Request):
        """
        Standard DNS-over-HTTPS (RFC 8484)
        Accepts: application/dns-message
        Returns: application/dns-message
        """
        content_type = request.headers.get("content-type", "")
        
        # Read body
        body = await request.body()
        
        if not body:
            logger.warning("Empty body")
            return Response(status_code=400)
        
        logger.info(f"DoH request: {len(body)} bytes, Content-Type: {content_type}")
        
        try:
            # Parse DNS query
            query = dns.message.from_wire(body)
            
            # Extract domain and type
            for question in query.question:
                domain = str(question.name).rstrip('.')
                qtype = question.rdtype
                
                logger.info(f"Query: {domain} (type={qtype})")
                
                # Resolve using upstream DNS
                resolver = dns.resolver.Resolver()
                resolver.nameservers = ['8.8.8.8', '1.1.1.1']
                resolver.timeout = 5
                resolver.lifetime = 10
                
                # Build response
                response = dns.message.make_response(query)
                
                try:
                    answers = resolver.resolve(domain, qtype)
                    for rrset in answers.response.answer:
                        response.answer.append(rrset)
                    
                    dns_server.stats["total_queries"] = dns_server.stats.get("total_queries", 0) + 1
                    logger.info(f"Resolved: {domain}")
                    
                except dns.resolver.NXDOMAIN:
                    response.set_rcode(dns.rcode.NXDOMAIN)
                    logger.info(f"NXDOMAIN: {domain}")
                    
                except Exception as e:
                    response.set_rcode(dns.rcode.SERVFAIL)
                    logger.error(f"Failed: {domain} - {e}")
                
                # Return DNS wire format response
                return Response(
                    content=response.to_wire(),
                    media_type="application/dns-message",
                    headers={
                        "Cache-Control": "max-age=300",
                        "Server": "MasterDNS"
                    }
                )
        
        except Exception as e:
            logger.error(f"Parse error: {e}")
            return Response(status_code=400)
    
    # ============================================
    # GET method for DoH (for testing)
    # ============================================
    @app.get("/dns-query")
    async def doh_get(request: Request):
        """
        GET method for DoH
        Accepts: ?dns=<base64url>
        """
        dns_param = request.query_params.get("dns")
        
        if dns_param:
            try:
                # Add padding
                padding = 4 - len(dns_param) % 4
                if padding != 4:
                    dns_param += '=' * padding
                
                body = base64.urlsafe_b64decode(dns_param)
                query = dns.message.from_wire(body)
                
                domain = str(query.question[0].name).rstrip('.')
                qtype = query.question[0].rdtype
                
                logger.info(f"GET Query: {domain}")
                
                resolver = dns.resolver.Resolver()
                resolver.nameservers = ['8.8.8.8', '1.1.1.1']
                resolver.timeout = 5
                
                response = dns.message.make_response(query)
                
                try:
                    answers = resolver.resolve(domain, qtype)
                    for rrset in answers.response.answer:
                        response.answer.append(rrset)
                    dns_server.stats["total_queries"] = dns_server.stats.get("total_queries", 0) + 1
                except:
                    response.set_rcode(dns.rcode.SERVFAIL)
                
                return Response(
                    content=response.to_wire(),
                    media_type="application/dns-message"
                )
                
            except Exception as e:
                logger.error(f"GET error: {e}")
                return Response(status_code=400)
        
        # No params - return help
        return {
            "usage": "POST application/dns-message to this endpoint",
            "get_usage": "?dns=<base64url_encoded_dns_query>"
        }
    
    # ============================================
    # Stats
    # ============================================
    @app.get("/stats")
    async def stats():
        return {
            "total_queries": dns_server.stats.get("total_queries", 0),
            "domain": config.railway_domain
        }
    
    return app
