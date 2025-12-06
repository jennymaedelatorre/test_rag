from fastapi import HTTPException, Request, status
from fastapi import Depends
from database.models import User, Course
from database.session import get_db
from sqlalchemy.orm import Session

# Role required to access the endpoint
REQUIRED_ROLE = "faculty" 

def check_user_role(
    request: Request, 
    db: Session = Depends(get_db), 
    required_role: str = REQUIRED_ROLE
):
    session = request.session
    current_role = session.get("role")      
    username = session.get("user")         

    # Check if user is authenticated
    if not username or not current_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="User not authenticated."
        )

    # Check if user has the required role
    if current_role.lower() != required_role.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Access denied. Restricted to {required_role}."
        )
    
    # Lookup the ID of the user in the database
    user = db.query(User.id).filter(User.username == username).first()

    # Defensive check: user should exist if login succeeded
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Internal session error: User ID lookup failed."
        )
        

    return user.id
