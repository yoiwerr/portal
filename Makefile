.PHONY: dev

dev:
	@echo "[+] Starting FastAPI  on http://localhost:8000"
	@echo "[+] Starting Streamlit on http://localhost:8501"
	@echo "[+] Press Ctrl+C to stop both"
	@echo ""
	cd ChatHistoryAnalyst && \
	trap 'echo ""; echo "[STOP] All services stopped."; exit 0' INT TERM; \
	uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 & \
	uv run streamlit run front/frontend.py --server.port 8501 --server.headless true & \
	wait
