"""
Time utilities and audit logging
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class TimeUtils:
    """Utility functions for timestamp operations"""
    
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
        Calculate recency score using exponential decay.
        
        score = decay_rate^(days_ago)
        Example: 0.95^7 ≈ 0.70 (one week ago = 70% score)
        """
        if not timestamp_str:
            return 0.5
        
        days = TimeUtils.days_ago(timestamp_str)
        if days is None:
            return 0.5
        
        # Bound: keep minimum score of 0.1
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
