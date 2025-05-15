from pathlib import Path
from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field
from rich.console import Console
import json
import threading

# Папка для логов
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "observer.log"

console = Console()
log_lock = threading.Lock()

class Event(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    event_type: str
    match_id: Optional[int] = None
    source: Optional[str] = None
    status: Optional[str] = None
    details: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

def log_event(
    event_type: str,
    match_id: Optional[int] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
    details: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    event = Event(
        event_type=event_type,
        match_id=match_id,
        source=source,
        status=status,
        details=details,
        extra=extra,
    )
    # Красивый вывод в консоль
    with log_lock:
        console.log(f"[bold cyan]{event.timestamp}[/] [green]{event.event_type}[/] "
                    f"[yellow]{event.match_id or ''}[/] [magenta]{event.source or ''}[/] "
                    f"[white]{event.status or ''}[/] [dim]{event.details or ''}[/]")
        # Запись в файл (JSON)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

# Пример использования:
if __name__ == "__main__":
    log_event(
        event_type="fixture_queued",
        match_id=123456,
        source="api-football",
        status="success",
        details="Match added to Redis queue"
    )
    log_event(
        event_type="fetcher_error",
        match_id=123456,
        source="twitter_fetcher",
        status="error",
        details="Timeout while fetching tweets",
        extra={"retries": 3}
    ) 