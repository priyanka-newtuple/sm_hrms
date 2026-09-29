param([ValidateSet('up','native-up','native-migrate-steps','native-test','native-performance-test','native-project-test','native-demo-users','down','logs','test')][string]$Action = 'up')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot
try {
    $envPath = Join-Path $repoRoot '.hrms.local.env'
    if (-not (Test-Path -LiteralPath $envPath)) {
        $dbSecret = [guid]::NewGuid().ToString('N')
        $jwtSecret = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
        $adminSecret = [guid]::NewGuid().ToString('N')
        $employeeSecret = [guid]::NewGuid().ToString('N')
        $managerSecret = [guid]::NewGuid().ToString('N')
        [IO.File]::WriteAllText($envPath, "HRMS_DB_PASSWORD=$dbSecret`nHRMS_JWT_SECRET=$jwtSecret`nHRMS_PLATFORM_ADMIN_PASSWORD=$adminSecret`nHRMS_DEMO_EMPLOYEE_PASSWORD=$employeeSecret`nHRMS_DEMO_MANAGER_PASSWORD=$managerSecret`n")
    } elseif (-not ([IO.File]::ReadAllText($envPath) -match '(?m)^HRMS_PLATFORM_ADMIN_PASSWORD=')) {
        $adminSecret = [guid]::NewGuid().ToString('N')
        [IO.File]::AppendAllText($envPath, "HRMS_PLATFORM_ADMIN_PASSWORD=$adminSecret`n")
    }
    foreach ($name in @('HRMS_DEMO_EMPLOYEE_PASSWORD', 'HRMS_DEMO_MANAGER_PASSWORD', 'HRMS_SERVICE_PASSWORD', 'HRMS_APP_DB_PASSWORD')) {
        if (-not ([IO.File]::ReadAllText($envPath) -match "(?m)^$name=")) {
            [IO.File]::AppendAllText($envPath, "$name=$([guid]::NewGuid().ToString('N'))`n")
        }
    }
    $composeArgs = @('compose','--env-file',$envPath,'-f','docker-compose.hrms.yml')
    switch ($Action) {
        'up' { & docker @composeArgs up --build -d }
        'native-up' {
            & docker @composeArgs --profile native up --build -d platform-web
            if ($LASTEXITCODE -ne 0) { throw 'Native platform startup failed' }
        }
        'native-migrate-steps' { & docker @composeArgs --profile native --profile migration run --rm --no-deps platform-step-migrate }
        'native-test' { & docker @composeArgs --profile native --profile test run --rm --no-deps hrms-smoke }
        'native-performance-test' { & docker @composeArgs --profile native --profile test run --rm --no-deps hrms-smoke python /tools/smoke_performance.py }
        'native-project-test' {
            $demoDirectory = Join-Path $repoRoot '.hrms-demo-local'
            if (-not (Test-Path -LiteralPath (Join-Path $demoDirectory 'users.json'))) { throw 'Run native-demo-users first' }
            & docker @composeArgs --profile native --profile test run --rm --no-deps -v "${demoDirectory}:/demo" hrms-smoke python /tools/smoke_projects.py
        }
        'native-demo-users' {
            $demoDirectory = Join-Path $repoRoot '.hrms-demo-local'
            New-Item -ItemType Directory -Force -Path $demoDirectory | Out-Null
            & docker @composeArgs --profile native --profile test run --rm --no-deps -v "${demoDirectory}:/demo" hrms-smoke python /tools/seed_demo_users.py
        }
        'down' { & docker @composeArgs --profile native down }
        'logs' { & docker @composeArgs logs --tail 100 }
        'test' {
            & docker @composeArgs exec -T db psql -U sm_hrms -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='sm_hrms_test'" | Tee-Object -Variable testExists | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Database is unavailable' }
            if ($testExists -notcontains '1') { & docker @composeArgs exec -T db createdb -U sm_hrms sm_hrms_test }
            & docker @composeArgs run --build --rm tests
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "HRMS $Action failed" }
    if ($Action -eq 'up') { Write-Host 'HRMS: http://localhost:5181 — choose a local test role on the login page.' }
    if ($Action -eq 'native-up') { Write-Host 'Native platform: http://localhost:5182 — HRMS entities, forms and workflows installed.' }
} finally { Pop-Location }
