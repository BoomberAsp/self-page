@echo off
cd /d "%~dp0"
pip install -q paramiko
python main.py
pause
