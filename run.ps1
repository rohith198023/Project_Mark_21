param (
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet("setup", "start", "stop", "logs", "reset", "status", "desktop")]
    [string]$Action
)

switch ($Action) {
    "setup" {
        if (-not (Test-Path ".env")) {
            Copy-Item ".env.example" ".env"
            Write-Host ".env file created from template. Configure settings as needed." -ForegroundColor Green
        } else {
            Write-Host ".env file already exists. Skipping copy." -ForegroundColor Yellow
        }
    }
    "start" {
        Write-Host "Building and starting JARVIS Docker services in background..." -ForegroundColor Cyan
        docker compose up --build -d
        Write-Host "Services starting. Visit http://localhost:3000 to access the Dashboard." -ForegroundColor Green
    }
    "stop" {
        Write-Host "Stopping and removing JARVIS Docker services..." -ForegroundColor Cyan
        docker compose down
        Write-Host "Services stopped." -ForegroundColor Green
    }
    "logs" {
        Write-Host "Attaching to live service log streams. Press Ctrl+C to disconnect." -ForegroundColor Cyan
        docker compose logs -f
    }
    "status" {
        Write-Host "Inspecting current container status..." -ForegroundColor Cyan
        docker compose ps
    }
    "reset" {
        Write-Host "Warning: Resetting environment. This stops all services and purges local vector DB and Postgres volumes." -ForegroundColor Yellow
        docker compose down -v
        Write-Host "Environment reset complete. Volumes deleted." -ForegroundColor Green
    }
    "desktop" {
        Write-Host "Installing Desktop Agent dependencies on Windows..." -ForegroundColor Cyan
        pip install -r services/desktop/requirements.txt
        Write-Host "Starting Desktop Agent natively on Windows (Port 8005)..." -ForegroundColor Green
        $env:PYTHONPATH = "."
        
        $pipCommand = Get-Command pip -ErrorAction SilentlyContinue
        if ($pipCommand) {
            $venvPython = Join-Path (Split-Path $pipCommand.Source) "python.exe"
            if (Test-Path $venvPython) {
                Write-Host "Using Python interpreter from virtual environment: $venvPython" -ForegroundColor Gray
                & $venvPython services/desktop/main.py
                return
            }
        }
        
        python services/desktop/main.py
    }
}
