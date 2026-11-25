import os
import sys
import time
import logging
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from prometheus_fastapi_instrumentator import Instrumentator

# Logging configuration
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backend-service")

# Environment & Database Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres_secure_pass@postgres:5432/taskdb"
)
POD_NAME = os.getenv("HOSTNAME", "local-pod")
NODE_NAME = os.getenv("NODE_NAME", "local-node")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
APP_VERSION = os.getenv("APP_VERSION", "v1.0.0")

# Database Setup with retry logic
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"connect_timeout": 5}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TaskModel(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))


# Pydantic Schemas
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, example="Deploy ArgoCD application")
    description: Optional[str] = Field(None, max_length=500, example="Setup GitOps sync")


class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    completed: bool

    class Config:
        from_attributes = True


class SystemInfo(BaseModel):
    status: str
    version: str
    environment: str
    pod_name: str
    node_name: str
    database_connected: bool
    uptime_seconds: float


# Chaos State (in-memory for fault simulation)
chaos_state = {
    "error_spike_remaining": 0,
    "memory_leak_chunks": [],
}

start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database schema with connection retry...")
    max_retries = 15
    for attempt in range(1, max_retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database schema initialized successfully.")
            break
        except Exception as exc:
            logger.warning(f"Database schema init attempt {attempt}/{max_retries} failed: {exc}. Retrying in 2s...")
            time.sleep(2)
    yield
    logger.info("Shutting down backend service...")


app = FastAPI(
    title="Cloud & AIOps Demo Backend",
    version=APP_VERSION,
    description="Production-grade 3-tier microservice API with observability & chaos hooks",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus Metrics Instrumentation
instrumentator = Instrumentator().instrument(app)


@app.on_event("startup")
async def _startup():
    instrumentator.expose(app, endpoint="/metrics")


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Health & Readiness Probes
@app.get("/healthz", tags=["Health"])
def liveness():
    """Kubernetes Liveness Probe"""
    return {"status": "alive"}


@app.get("/readyz", tags=["Health"])
def readiness(db: Session = Depends(get_db)):
    """Kubernetes Readiness Probe: checks database connection"""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        logger.error(f"Readiness check failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unreachable: {str(exc)}"
        )


@app.get("/api/v1/system/info", response_model=SystemInfo, tags=["System"])
def get_system_info(db: Session = Depends(get_db)):
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return SystemInfo(
        status="healthy",
        version=APP_VERSION,
        environment=ENVIRONMENT,
        pod_name=POD_NAME,
        node_name=NODE_NAME,
        database_connected=db_ok,
        uptime_seconds=round(time.time() - start_time, 2),
    )


# Business Endpoints
@app.get("/api/v1/tasks", response_model=List[TaskResponse], tags=["Tasks"])
def list_tasks(db: Session = Depends(get_db)):
    # Chaos hook: simulate error spike
    if chaos_state["error_spike_remaining"] > 0:
        chaos_state["error_spike_remaining"] -= 1
        logger.error("Chaos error injection triggered! Returning HTTP 500")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Simulated internal server failure for AIOps triage test"
        )

    tasks = db.query(TaskModel).order_by(TaskModel.id.desc()).all()
    return tasks


@app.post("/api/v1/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
def create_task(task_in: TaskCreate, db: Session = Depends(get_db)):
    task = TaskModel(title=task_in.title, description=task_in.description)
    db.add(task)
    db.commit()
    db.refresh(task)
    logger.info(f"Task created successfully: ID={task.id}, Title='{task.title}'")
    return task


@app.delete("/api/v1/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tasks"])
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return None


# Chaos / Fault Injection Endpoints for AIOps Demonstration
@app.post("/api/v1/chaos/crash", tags=["Chaos Testing"])
def chaos_crash():
    """Forces pod to exit immediately with code 1, triggering Kubernetes CrashLoopBackOff."""
    logger.critical("🚨 AIOps Chaos Experiment: Simulating unhandled fatal exception / pod crash!")
    # Exit process cleanly to trigger Kubernetes container restart
    def _crash():
        time.sleep(0.5)
        sys.exit(1)

    import threading
    threading.Thread(target=_crash).start()
    return {"message": "Crash signal dispatched. Process terminating in 500ms to test CrashLoopBackOff triage."}


@app.post("/api/v1/chaos/memory-leak", tags=["Chaos Testing"])
def chaos_memory_leak(megabytes: int = Query(256, ge=50, le=2048)):
    """Allocates large byte arrays to trigger container memory limits (OOMKilled)."""
    logger.warning(f"🚨 AIOps Chaos Experiment: Allocating {megabytes} MB to trigger OOMKilled!")
    chunk = b"X" * (megabytes * 1024 * 1024)
    chaos_state["memory_leak_chunks"].append(chunk)
    return {
        "message": f"Allocated {megabytes} MB. Total leaked chunks: {len(chaos_state['memory_leak_chunks'])}",
        "approx_allocated_mb": len(chaos_state["memory_leak_chunks"]) * megabytes
    }


@app.post("/api/v1/chaos/error-spike", tags=["Chaos Testing"])
def chaos_error_spike(count: int = Query(20, ge=1, le=100)):
    """Instructs backend to throw 500 Internal Server Errors on subsequent requests."""
    chaos_state["error_spike_remaining"] += count
    logger.warning(f"🚨 AIOps Chaos Experiment: Injected {count} consecutive HTTP 500 failures!")
    return {"message": f"Configured {chaos_state['error_spike_remaining']} upcoming requests to fail with HTTP 500."}
