# AdidLaBs — LiteLLM gateway as a Lambda CONTAINER IMAGE (alternative to the LWA layer)
# Concept demo — no affiliation with adidas AG. All products fictional.
#
# This is the container alternative to the zip-plus-layer path (build_zip.sh).
# The AWS Lambda Web Adapter is copied in from its public image instead of being
# attached as a layer. Everything else — config, entrypoint, IAM-auth function
# URL — is identical.
#
# Build & push (region ap-southeast-2):
#   ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
#   REPO=${ACCOUNT}.dkr.ecr.ap-southeast-2.amazonaws.com/adidlabs-litellm
#   aws ecr create-repository --repository-name adidlabs-litellm --region ap-southeast-2 || true
#   aws ecr get-login-password --region ap-southeast-2 \
#     | docker login --username AWS --password-stdin ${ACCOUNT}.dkr.ecr.ap-southeast-2.amazonaws.com
#   docker build --platform linux/amd64 -f gateway/lambda/Dockerfile -t ${REPO}:latest gateway
#   docker push ${REPO}:latest
# Then create the Lambda with PackageType=Image pointing at ${REPO}:latest.

# AWS base image for Python 3.12 Lambda.
FROM public.ecr.aws/lambda/python:3.12

# Bring in the AWS Lambda Web Adapter extension from its official image.
# For a CONTAINER IMAGE the adapter runs as a Lambda external extension: placing
# it under /opt/extensions/ is all that's required — the Lambda runtime discovers
# and auto-starts it, so AWS_LAMBDA_EXEC_WRAPPER is NOT set here and is not needed
# for the image path. (AWS_LAMBDA_EXEC_WRAPPER=/opt/bootstrap is the SEPARATE
# activation mechanism used ONLY by the zip+layer path — see build_zip.sh/bootstrap.)
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

# The Web Adapter forwards events to this port; PORT is read by gateway_app.py.
# PYTHONPATH pins the entrypoint location (${LAMBDA_TASK_ROOT}) explicitly so
# `python -m gateway_app` resolves regardless of the process cwd — same posture
# as the zip bootstrap.
ENV AWS_LWA_PORT=8000 \
    PORT=8000 \
    AWS_REGION=ap-southeast-2 \
    AWS_DEFAULT_REGION=ap-southeast-2 \
    PYTHONPATH=${LAMBDA_TASK_ROOT}

WORKDIR ${LAMBDA_TASK_ROOT}

# Install dependencies. Build context is the gateway/ directory, so paths are
# relative to gateway/.
COPY lambda/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application: the two-route config plus the server entrypoint.
COPY config.yaml ./config.yaml
COPY lambda/gateway_app.py ./gateway_app.py

# Run the HTTP server directly; the Web Adapter (extension) proxies to it.
# Override the base image's Python-handler entrypoint.
ENTRYPOINT []
CMD ["python", "-m", "gateway_app"]
