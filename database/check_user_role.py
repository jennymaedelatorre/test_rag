from fastapi import HTTPException, Request, status
from fastapi import Depends
from database.models import User, Course
from database.session import get_db
from sqlalchemy.orm import Session
# Note: You don't need a DB session here if the role is stored in the session!

REQUIRED_ROLE = "faculty" 

def check_user_role(
    request: Request, 
    db: Session = Depends(get_db), # Need DB to get the ID
    required_role: str = REQUIRED_ROLE
):
    session = request.session
    current_role = session.get("role")
    username = session.get("user") # The unique username

    if not username or not current_role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated.")

    if current_role.lower() != required_role.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Access denied. Restricted to {required_role}.")
    
    # 🌟 NEW: Look up the numerical ID using the validated username
    user = db.query(User.id).filter(User.username == username).first()

    if not user:
        # Should not happen if login worked, but handle defensively
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal session error: User ID lookup failed.")
        
    # 🌟 Return the numerical ID (the true PK)
    return user.id