@echo off
echo ========================================
echo  IELTS Vocab Platform - Backend Setup
echo ========================================
echo.

cd /d "%~dp0"

echo Installing Python dependencies...
pip install -r requirements.txt --quiet

echo.
echo Extracting vocabulary from PDF...
python scripts/extract_pdf.py

echo.
echo Importing vocabulary to database...
python scripts/import_vocabulary.py

echo.
echo Starting backend server...
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
