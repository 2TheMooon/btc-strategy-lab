@echo off
chcp 65001 >nul
cd /d "C:\Users\2TheMoon\Documents\testing btc strategy"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
python paper_trade.py >> paper_trade.log 2>&1
