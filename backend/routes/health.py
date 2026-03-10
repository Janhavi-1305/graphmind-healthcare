"""
Health check routes
Provides system health status and service connectivity checks
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends

from database import DatabaseManager
from models import HealthCheckResponse, ServiceStatus, HealthStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("", response_model=HealthCheckResponse)
async def health_check(db: DatabaseManager = Depends(lambda: __import__('main').db_manager)):
    """Check health of all services"""
    
    if db is None:
        return HealthCheckResponse(
            status=HealthStatus.UNHEALTHY,
            services={},
            uptime_seconds=0,
            version="1.0.0",
        )
    
    try:
        health_status = await db.health_check()
        
        # Convert health_status dict to ServiceStatus objects
        services = {}
        for service_name, status_str in health_status.items():
            if "error" in status_str:
                services[service_name] = ServiceStatus(
                    name=service_name,
                    status=HealthStatus.UNHEALTHY,
                    error=status_str,
                )
            else:
                services[service_name] = ServiceStatus(
                    name=service_name,
                    status=HealthStatus.HEALTHY,
                )
        
        # Overall status
        overall_status = HealthStatus.HEALTHY
        if any(s.status == HealthStatus.UNHEALTHY for s in services.values()):
            overall_status = HealthStatus.DEGRADED
        
        return HealthCheckResponse(
            status=overall_status,
            services=services,
            uptime_seconds=0,  # Can be calculated from process start time
            version="1.0.0",
        )
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthCheckResponse(
            status=HealthStatus.UNHEALTHY,
            services={
                "error": ServiceStatus(
                    name="health_check",
                    status=HealthStatus.UNHEALTHY,
                    error=str(e),
                )
            },
            uptime_seconds=0,
            version="1.0.0",
        )


@router.get("/ready")
async def readiness_check(db: DatabaseManager = Depends(lambda: __import__('main').db_manager)):
    """Check if service is ready to accept requests"""
    if db is None:
        return {"ready": False, "reason": "Database not initialized"}
    
    try:
        health_status = await db.health_check()
        all_connected = all("error" not in str(v) for v in health_status.values())
        return {
            "ready": all_connected,
            "services": health_status,
        }
    except Exception as e:
        return {"ready": False, "reason": str(e)}


@router.get("/ping")
async def ping():
    """Simple ping endpoint"""
    return {
        "pong": True,
        "timestamp": datetime.now().isoformat(),
    }
