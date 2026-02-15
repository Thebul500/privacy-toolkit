"""Allow running as python -m src."""
import sys

if len(sys.argv) > 1 and sys.argv[1] == "cli":
    # Direct CLI mode: python -m src cli ...
    sys.argv.pop(1)
    from src.cli import main
    main()
else:
    # Default: launch web app
    import uvicorn
    from src.config import Config
    config = Config.load()
    uvicorn.run("src.app:app", host=config.web.host, port=config.web.port, log_level="info")
