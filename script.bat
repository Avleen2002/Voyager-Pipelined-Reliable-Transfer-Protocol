@echo off
echo Starting Voyager fairness test...

REM === Start Server 1 ===
start "Server9000" cmd /k python voyager.py --role server --port 9000 --out outA.txt

REM === Start Server 2 ===
start "Server9001" cmd /k python voyager.py --role server --port 9001 --out outB.txt

REM Wait 1 second for servers to initialize
timeout /t 1 > nul

REM === Start Client 1 (A.txt) ===
start "ClientA" cmd /k python voyager.py --role client --server-ip 127.0.0.1 --server-port 9000 --file A.txt

REM === Start Client 2 (B.txt) ===
start "ClientB" cmd /k python voyager.py --role client --server-ip 127.0.0.1 --server-port 9001 --file B.txt

echo All 4 programs started!
