"""
Utility modules for GraphMind Healthcare system
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid

logger = logging.getLogger(__name__)


class TimeUtils:
    """Utility functions for timestamp and time-based operations"""
    
    @staticmethod
    def now_iso() -> str:
        """Get current timestamp as ISO string"""
        return datetime.now().isoformat()
    
    @staticmethod
    def parse_iso(timestamp_str: str) -> Optional[datetime]:
        """Parse ISO timestamp string"""
        try:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except Exception as e:
            logger.warning(f"Failed to parse timestamp: {e}")
            return None
    
    @staticmethod
    def days_ago(timestamp_str: str) -> Optional[int]:
        """Calculate days since timestamp"""
        try:
            timestamp = TimeUtils.parse_iso(timestamp_str)
            if timestamp:
                return (datetime.now(timestamp.tzinfo or datetime.now().tzinfo) - timestamp).days
            return None
        except Exception as e:
            logger.warning(f"Failed to calculate days_ago: {e}")
            return None
    
    @staticmethod
    def recency_score(timestamp_str: Optional[str], decay_rate: float = 0.95) -> float:
        """
        Calculate recency score (newer = higher).
        Uses exponential decay: score = decay_rate^(days_ago)
        """
        if not timestamp_str:
            return 0.5
        
        days = TimeUtils.days_ago(timestamp_str)
        if days is None:
            return 0.5
        
        score = max(0.1, decay_rate ** days)
        return score
    
    @staticmethod
    def is_recent(timestamp_str: str, days: int = 7) -> bool:
        """Check if timestamp is within N days"""
        try:
            timestamp = TimeUtils.parse_iso(timestamp_str)
            if timestamp:
                cutoff = datetime.now(timestamp.tzinfo or datetime.now().tzinfo) - timedelta(days=days)
                return timestamp >= cutoff
            return False
        except Exception as e:
            logger.warning(f"Failed to check recency: {e}")
            return False


class AuditLogger:
    """Audit logging for compliance and monitoring"""
    
    def __init__(self, db):
        self.db = db
    
    async def log_event(
        self,
        user_id: str,
        event_type: str,
        action: str,
        resource: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ):
        """Log an audit event"""
        try:
            collection = await self.db.get_mongo_collection("audit_logs")
            
            log_entry = {
                "log_id": str(uuid.uuid4()),
                "user_id": user_id,
                "event_type": event_type,
                "action": action,
                "resource": resource,
                "status": status,
                "details": details or {},
                "error": error,
                "duration_ms": duration_ms,
                "timestamp": datetime.now(),
            }
            
            await collection.insert_one(log_entry)
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
    
    async def get_user_audit_log(self, user_id: str, limit: int = 100) -> list:
        """Get audit log for a user"""
        try:
            collection = await self.db.get_mongo_collection("audit_logs")
            cursor = collection.find(
                {"user_id": user_id}
            ).sort("timestamp", -1).limit(limit)
            
            logs = await cursor.to_list(length=limit)
            return logs
        
        except Exception as e:
            logger.error(f"Failed to retrieve audit log: {e}")
            return []


class PerformanceMonitor:
    """Monitor and log performance metrics"""
    
    def __init__(self, db):
        self.db = db
    
    async def log_metric(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        total_time_ms: float,
        db_time_ms: float = 0.0,
        llm_time_ms: float = 0.0,
        retrieval_time_ms: Optional[float] = None,
    ):
        """Log performance metric"""
        try:
            collection = await self.db.get_mongo_collection("performance_metrics")
            
            metric = {
                "metric_id": str(uuid.uuid4()),
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "total_time_ms": total_time_ms,
                "db_time_ms": db_time_ms,
                "llm_time_ms": llm_time_ms,
                "retrieval_time_ms": retrieval_time_ms,
                "timestamp": datetime.now(),
            }
            
            await collection.insert_one(metric)
        
        except Exception as e:
            logger.error(f"Failed to log performance metric: {e}")
    
    async def get_performance_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance summary for last N hours"""
        try:
            from statistics import mean, median, quantiles
            
            collection = await self.db.get_mongo_collection("performance_metrics")
            
            cutoff = datetime.now() - timedelta(hours=hours)
            metrics = await collection.find(
                {"timestamp": {"$gte": cutoff}}
            ).to_list(length=None)
            
            if not metrics:
                return {
                    "total_requests": 0,
                    "avg_time_ms": 0,
                    "p50_time_ms": 0,
                    "p95_time_ms": 0,
                    "p99_time_ms": 0,
                    "slow_requests": 0,
                    "errors": 0,
                }
            
            times = [m["total_time_ms"] for m in metrics]
            errors = sum(1 for m in metrics if m["status_code"] >= 400)
            slow = sum(1 for m in metrics if m["total_time_ms"] > 1000)
            
            return {
                "total_requests": len(metrics),
                "avg_time_ms": mean(times),
                "p50_time_ms": median(times),
                "p95_time_ms": quantiles(times, n=20)[19] if len(times) > 20 else max(times),
                "p99_time_ms": max(times),
                "slow_requests": slow,
                "errors": errors,
            }
        
        except Exception as e:
            logger.error(f"Failed to get performance summary: {e}")
            return {}
