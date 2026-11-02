from fastapi import FastAPI                                                                                                    
from app.core.config import settings                                                                                           
                                                                                                                                   
app = FastAPI(                                                                                                                 
    title=settings.SERVICE_NAME,                                                                                               
    version="0.1.0",                                                                                                           
    debug=settings.DEBUG,                                                                                                      
)

@app.get("/health")
async def health_check():
    return {
        "status": "UP",
        "service": settings.SERVICE_NAME,
        "environment": settings.ENVIRONMENT,
    } 