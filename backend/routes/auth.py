"""
Authentication routes
Basic user registration and login (simplified for demo)
In production, implement proper password hashing, JWT tokens, etc.
"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from passlib.context import CryptContext
import jwt

from config import settings
from models import UserRegisterRequest, UserLoginRequest, UserResponse, TokenResponse
from database import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash password"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, expires_delta: timedelta = None) -> str:
    """Create JWT token"""
    if expires_delta is None:
        expires_delta = timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    
    expire = datetime.utcnow() + expires_delta
    payload = {
        "user_id": user_id,
        "exp": expire,
    }
    
    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    
    return token


@router.post("/register", response_model=UserResponse)
async def register(request: UserRegisterRequest):
    """Register a new user"""
    
    try:
        # In production, connect to database and check for existing user
        # For demo, just create response
        
        user_id = f"patient_{request.email.split('@')[0]}"
        
        user = {
            "user_id": user_id,
            "email": request.email,
            "full_name": request.full_name,
            "created_at": datetime.now(),
            "password_hash": hash_password(request.password),
        }
        
        # Would save to database here
        logger.info(f"User registered: {user_id}")
        
        return UserResponse(
            user_id=user_id,
            email=request.email,
            full_name=request.full_name,
            created_at=datetime.now(),
        )
    
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLoginRequest):
    """Login user"""
    
    try:
        # In production, verify credentials against database
        # For demo, accept any email/password combination
        
        user_id = f"patient_{request.email.split('@')[0]}"
        
        # Generate token
        access_token = create_access_token(user_id)
        
        logger.info(f"User logged in: {user_id}")
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.JWT_EXPIRATION_HOURS * 3600,
        )
    
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.post("/logout")
async def logout():
    """Logout user (simplified - in production, invalidate token)"""
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_current_user(authorization: str = None):
    """Get current user (requires token)"""
    
    if not authorization:
        raise HTTPException(status_code=401, detail="No authorization header")
    
    try:
        # Extract token from "Bearer <token>"
        token = authorization.replace("Bearer ", "")
        
        # Verify token
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        
        user_id = payload.get("user_id")
        
        return UserResponse(
            user_id=user_id,
            email=f"{user_id}@example.com",
            full_name="Patient User",
            created_at=datetime.now(),
        )
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
