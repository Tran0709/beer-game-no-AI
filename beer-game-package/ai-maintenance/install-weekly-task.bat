@echo off
rem Schedules the weekly maintenance on THIS computer (Mondays 10:00). Desktop notifications appear here.
rem Run once. To remove:  schtasks /Delete /TN BeerGameMaintenance /F
cd /d "%~dp0\.."
schtasks /Create /SC WEEKLY /D MON /ST 10:00 /TN "BeerGameMaintenance" /TR "cmd /c cd /d \"%CD%\" && python ai-maintenance\agent\maintain.py weekly" /F
echo.
echo Test it now with:  python ai-maintenance\agent\maintain.py weekly
pause
