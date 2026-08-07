$ErrorActionPreference = "Stop"

$carpeta = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat     = Join-Path $carpeta "actualizar_auto.bat"
$nombre  = "Tablero Elyon - Actualizar y publicar"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host " GRUPO ELYON - Programar actualizacion diaria 8:30"    -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $bat)) {
    Write-Host "[ERROR] No se encuentra actualizar_auto.bat en la carpeta." -ForegroundColor Red
    Read-Host "Enter para salir"
    exit 1
}

try {
    $accion = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $carpeta

    $trigger = New-ScheduledTaskTrigger -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At "08:30"

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask -TaskName $nombre `
        -Action $accion -Trigger $trigger -Settings $settings `
        -Description "Actualiza BCRA, UVA, CAC, MERVAL, REM y riesgo pais del Tablero Elyon, regenera docs\index.html y lo publica en GitHub Pages." `
        -Force | Out-Null

    Write-Host "[OK] Tarea creada: '$nombre'" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Cuando  : lunes a viernes 8:30" -ForegroundColor Gray
    Write-Host "  Si la PC estaba apagada, corre apenas la prendas." -ForegroundColor Gray
    Write-Host "  Registro: log_actualizacion.txt (en esta carpeta)" -ForegroundColor Gray
    Write-Host ""

    $r = Read-Host "Probar la tarea ahora? (S/N)"
    if ($r -match '^[SsYy]') {
        Write-Host ""
        Write-Host "Ejecutando... puede tardar un minuto." -ForegroundColor Yellow
        Start-ScheduledTask -TaskName $nombre
        Start-Sleep -Seconds 45
        $info = Get-ScheduledTaskInfo -TaskName $nombre
        Write-Host ""
        Write-Host ("Ultimo resultado: {0}" -f $info.LastTaskResult) -ForegroundColor Gray
        Write-Host ("Proxima corrida : {0}" -f $info.NextRunTime)   -ForegroundColor Gray
        Write-Host ""
        $log = Join-Path $carpeta "log_actualizacion.txt"
        if (Test-Path $log) {
            Write-Host "--- ultimas lineas del registro ---" -ForegroundColor Cyan
            Get-Content $log -Tail 20
        }
    }
}
catch {
    Write-Host ""
    Write-Host "[ERROR] No se pudo crear la tarea:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Proba cerrar y volver a abrir como Administrador." -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Enter para salir"
