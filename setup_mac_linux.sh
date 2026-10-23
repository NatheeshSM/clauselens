#!/bin/bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python tests/run_checks.py
echo "Setup done. Start the app with:  streamlit run app.py"
