from kalib.hypertext import URL, Agent, HTTPException, HTTPResponse, Status

__all__ = (
    "URL",
    "Agent",
    "Catch",
    "Exception",
    "Status",
)

Catch = HTTPResponse.read
Exception = HTTPException
