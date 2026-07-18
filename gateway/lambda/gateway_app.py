"""AdidLaBs — LiteLLM gateway entrypoint (runs behind the AWS Lambda Web Adapter).

Concept demo — no affiliation with adidas AG. All products fictional.

The AWS Lambda Web Adapter turns the Lambda into a standard HTTP service: it
forwards the incoming API Gateway / function-URL event to an HTTP server that
this module starts on 127.0.0.1:$PORT. We reuse LiteLLM's own FastAPI proxy app
(the exact same server ``litellm --config`` runs locally) so local and Lambda
behaviour are identical.

Config resolution order:
1. LITELLM_CONFIG_PATH env var, if set.
2. ``config.yaml`` next to this file (the deploy script copies gateway/config.yaml
   into the Lambda package root — see build_zip.sh).

Exactly two routes are defined in that config: ``nova-pro`` and ``haiku-4.5``.
"""

import os
import pathlib

import uvicorn

# LiteLLM ships its proxy as an importable FastAPI app. Importing initialises
# the app; ``save_worker_config`` tells it which YAML to load on startup.
from litellm.proxy.proxy_server import app, save_worker_config

_HERE = pathlib.Path(__file__).resolve().parent


def _config_path() -> str:
    """Locate the LiteLLM YAML config, honouring an env override."""
    override = os.environ.get("LITELLM_CONFIG_PATH")
    if override:
        p = pathlib.Path(override)
        if not p.is_file():
            raise FileNotFoundError(f"LITELLM_CONFIG_PATH set but not found: {override}")
        return str(p)

    local = _HERE / "config.yaml"
    if local.is_file():
        return str(local)

    raise FileNotFoundError(
        "config.yaml not found next to gateway_app.py and LITELLM_CONFIG_PATH is unset. "
        "The deploy package must include the gateway config at the Lambda root."
    )


def _configure() -> None:
    """Bind the YAML config to the LiteLLM proxy app before serving."""
    config = _config_path()
    # Signature mirrors what the ``litellm`` CLI passes through. Only the config
    # path is meaningful for the demo; the rest take LiteLLM defaults.
    save_worker_config(
        config=config,
        model=None,
        alias=None,
        api_base=None,
        api_version=None,
        debug=False,
        temperature=None,
        max_tokens=None,
        request_timeout=600,
        max_budget=None,
        telemetry=False,
        # Kept in sync with litellm_settings.drop_params in config.yaml. This kwarg
        # is authoritative for the in-process Lambda path; the YAML value for the
        # CLI/local path (run_local.sh). Change both together if you change one.
        drop_params=True,
        add_function_to_prompt=False,
        headers=None,
        save=False,
        use_queue=False,
    )


def main() -> None:
    _configure()
    port = int(os.environ.get("PORT", os.environ.get("AWS_LWA_PORT", "8000")))
    # Bind to loopback only — the Web Adapter is the sole client. One worker:
    # Lambda gives one request per execution environment at a time.
    uvicorn.run(app, host="127.0.0.1", port=port, workers=1, log_level="info")


if __name__ == "__main__":
    main()
