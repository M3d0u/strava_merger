launch:
	uv run streamlit run main.py

lint:
	uv run pre-commit run --all-files
