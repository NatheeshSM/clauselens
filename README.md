# ClauseLens
Pipeline: parse (page/section/bbox) -> extract (regex or LLM) -> **verify quote verbatim** -> deterministic rule engine -> UI.

## Run
    pip install -r requirements.txt
    streamlit run app.py            # click "Use sample contract"
    export ANTHROPIC_API_KEY=...    # only for LLM engine

## Files
doc_parser.py, extractor.py, verifier.py, rules.py, pipeline.py, app.py, tests/, sample/

## Next steps
eval script on 15-20 labeled contracts, PDF report export, OCR fallback, counter-wording via LLM.
