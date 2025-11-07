from starlette.requests import Request
from starlette.responses import Response

def flash(request: Request, message: str, category: str = "info", title: str = None, icon: str = None):
    """
    Stores a message in the session to be displayed on the next request.
    Applies default title and Font Awesome icons based on category (success/danger).
    """
    if title is None:
        if category == "success":
            title = "Success"
        elif category == "danger":
            title = "Error"
        else:
            title = "Heads Up!" 

    if icon is None:
        if category == "success":
            icon = '<i class="fa-regular fa-circle-check"></i>' 
        elif category == "danger":
            icon = '<i class="fa-solid fa-circle-exclamation"></i>'
        else:
            icon = "💡" 

    request.session["flash_message"] = message
    request.session["flash_category"] = category
    request.session["flash_title"] = title
    request.session["flash_icon"] = icon

def get_flashed_messages(request: Request) -> dict:
    """
    Retrieves and clears (pops) the stored flash message from the session.
    """
    return {
        "message": request.session.pop("flash_message", None),
        "category": request.session.pop("flash_category", "info"),
        "title": request.session.pop("flash_title", "Heads Up!"),
        "icon": request.session.pop("flash_icon", "💡"),
    }
