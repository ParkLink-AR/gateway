from fastapi import Request
from fastapi.responses import JSONResponse


def problem_response(request: Request, status_code: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "type": "about:blank",
            "title": title,
            "status": status_code,
            "detail": detail,
            "instance": str(request.url.path),
        },
        media_type="application/problem+json",
    )
