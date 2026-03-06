$env:CALENDAR_STUB_SLOTS = '["2026-03-03T09:00:00Z","2026-03-03T09:15:00Z","2026-03-03T14:00:00Z","2026-03-03T14:30:00Z","2026-03-04T10:00:00Z","2026-03-04T15:00:00Z","2026-03-05T09:00:00Z","2026-03-05T11:00:00Z"]'
$env:BOOKING_STUB = "1"
$env:MESSAGING_STUB = "1"
Set-Location "C:\Users\loumk\humtech-platform"
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000
