$ErrorActionPreference = "Stop"

$carpeta = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat     = Join-Path $carpeta "actualizar_auto.bat"
$nombre  = "Tablero Elyon - Actualizar y publicar"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host " GRUPO ELYON - Actualizar cada 2 horas, de 11 a 17"     -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $bat)) {
    Write-Host "[ERROR] No se encuentra actualizar_auto.bat en la carpeta." -ForegroundColor Red
    Read-Host "Enter para salir"
    exit 1
}

try {
    $accion = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $carpeta

    # Una corrida cada 2 horas, de 11 a 17. Un trigger no admite varias horas,
    # asi que se arma uno por horario y se registran todos juntos: es una sola
    # tarea con cuatro disparadores, no cuatro tareas separadas.
    #
    # Para cambiar la frecuencia alcanza con tocar este rango y el paso.
    # 11..18 con paso 1 era la version anterior (una corrida por hora).
    $horarios = 11, 13, 15, 17 | ForEach-Object { "{0:00}:00" -f $_ }
    $trigger = foreach ($h in $horarios) {
        New-ScheduledTaskTrigger -Weekly `
            -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
            -At $h
    }

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask -TaskName $nombre `
        -Action $accion -Trigger $trigger -Settings $settings `
        -Description "Actualiza las fuentes del Tablero Elyon (BCRA, UVA, CAC, MERVAL, caucion, dolar futuro, acciones, REM, riesgo pais e indices de la construccion, incluido el Indice Construya), regenera docs\index.html y lo publica en GitHub Pages. Corre lunes a viernes, cada 2 horas de 11 a 17." `
        -Force | Out-Null

    Write-Host "[OK] Tarea creada: '$nombre'" -ForegroundColor Green
    Write-Host ""
    Write-Host ("  Cuando  : lunes a viernes, cada 2 horas de {0} a {1}" -f $horarios[0], $horarios[-1]) -ForegroundColor Gray
    Write-Host "  Si la PC estaba apagada, corre apenas la prendas." -ForegroundColor Gray
    Write-Host ("  Corridas por dia: {0}" -f $horarios.Count) -ForegroundColor Gray
    Write-Host "  Si se solapan dos corridas, la segunda se descarta." -ForegroundColor Gray
    Write-Host "  Solo publica en GitHub si algun dato cambio." -ForegroundColor Gray
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
