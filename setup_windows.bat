@echo off
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python tests\run_checks.py
echo.
echo Setup done. Start the app with:  streamlit run app.py
