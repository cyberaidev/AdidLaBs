#!/usr/bin/env python3
"""Apply the mandatory Project=adidlabs tag to AdidLaBs AWS resources.

This is intentionally idempotent and safe to run after every deployment.
CloudFormation stack tags are updated first so the tag propagates to all
supported stack-managed resources. Resources created outside CloudFormation
(the deploy bucket, SSM secret, Bedrock KB, AgentCore runtime/gateway and
starter-toolkit IAM roles) are then tagged explicitly where the service API
supports tagging.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

TAG_KEY = "Project"
TAG_VALUE = "adidlabs"
PREFIX = "adidlabs"


def log(msg: str) -> None:
    print(f"[tags] {msg}")


def safe(label: str, fn) -> None:
    try:
        fn()
        log(f"ok: {label}")
    except Exception as exc:  # best-effort for preview/new service APIs
        log(f"warn: {label}: {exc}")


def tag_cloudformation_stack(region: str, stack: str) -> None:
    cfn = boto3.client("cloudformation", region_name=region)
    info = cfn.describe_stacks(StackName=stack)["Stacks"][0]
    tags = {t["Key"]: t["Value"] for t in info.get("Tags", [])}
    tags[TAG_KEY] = TAG_VALUE
    params = [{"ParameterKey": p["ParameterKey"], "UsePreviousValue": True}
              for p in info.get("Parameters", [])]
    kwargs: dict[str, Any] = {
        "StackName": stack,
        "UsePreviousTemplate": True,
        "Capabilities": ["CAPABILITY_NAMED_IAM"],
        "Tags": [{"Key": k, "Value": v} for k, v in tags.items()],
    }
    if params:
        kwargs["Parameters"] = params
    try:
        cfn.update_stack(**kwargs)
        cfn.get_waiter("stack_update_complete").wait(StackName=stack)
    except ClientError as exc:
        if "No updates are to be performed" not in str(exc):
            raise


def tag_s3_prefix(region: str) -> None:
    s3 = boto3.client("s3", region_name=region)
    for bucket in s3.list_buckets().get("Buckets", []):
        name = bucket["Name"]
        if not name.lower().startswith(PREFIX):
            continue
        try:
            current = s3.get_bucket_tagging(Bucket=name).get("TagSet", [])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "NoSuchTagSet":
                current = []
            else:
                raise
        tags = {t["Key"]: t["Value"] for t in current}
        tags[TAG_KEY] = TAG_VALUE
        s3.put_bucket_tagging(Bucket=name,
                              Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in tags.items()]})
        log(f"tagged S3 bucket {name}")


def tag_ssm(region: str, stack: str) -> None:
    ssm = boto3.client("ssm", region_name=region)
    name = f"/adidlabs/{stack}/litellm-master-key"
    try:
        ssm.get_parameter(Name=name)
    except ssm.exceptions.ParameterNotFound:
        return
    ssm.add_tags_to_resource(ResourceType="Parameter", ResourceId=name,
                             Tags=[{"Key": TAG_KEY, "Value": TAG_VALUE}])


def tag_iam_roles() -> None:
    iam = boto3.client("iam")
    paginator = iam.get_paginator("list_roles")
    for page in paginator.paginate():
        for role in page.get("Roles", []):
            name = role["RoleName"]
            if PREFIX in name.lower():
                iam.tag_role(RoleName=name, Tags=[{"Key": TAG_KEY, "Value": TAG_VALUE}])
                log(f"tagged IAM role {name}")


def tag_bedrock_kb(region: str) -> None:
    br = boto3.client("bedrock-agent", region_name=region)
    for page in br.get_paginator("list_knowledge_bases").paginate():
        for kb in page.get("knowledgeBaseSummaries", []):
            if PREFIX in kb.get("name", "").lower():
                detail = br.get_knowledge_base(knowledgeBaseId=kb["knowledgeBaseId"])["knowledgeBase"]
                arn = detail.get("knowledgeBaseArn")
                if arn:
                    br.tag_resource(resourceArn=arn, tags={TAG_KEY: TAG_VALUE})
                    log(f"tagged Bedrock KB {kb['knowledgeBaseId']}")


def tag_agentcore(region: str) -> None:
    ac = boto3.client("bedrock-agentcore-control", region_name=region)
    if hasattr(ac, "list_agent_runtimes"):
        paginator = ac.get_paginator("list_agent_runtimes")
        for page in paginator.paginate():
            for runtime in page.get("agentRuntimes", []):
                if PREFIX in runtime.get("agentRuntimeName", "").lower():
                    arn = runtime.get("agentRuntimeArn")
                    if arn and hasattr(ac, "tag_resource"):
                        ac.tag_resource(resourceArn=arn, tags={TAG_KEY: TAG_VALUE})
                        log(f"tagged AgentCore runtime {runtime.get('agentRuntimeName')}")
    if hasattr(ac, "list_gateways"):
        token = None
        while True:
            args = {"nextToken": token} if token else {}
            page = ac.list_gateways(**args)
            for gateway in page.get("items", page.get("gateways", [])):
                name = gateway.get("name", gateway.get("gatewayName", ""))
                if PREFIX in name.lower():
                    arn = gateway.get("gatewayArn")
                    if arn and hasattr(ac, "tag_resource"):
                        ac.tag_resource(resourceArn=arn, tags={TAG_KEY: TAG_VALUE})
                        log(f"tagged AgentCore gateway {name}")
            token = page.get("nextToken")
            if not token:
                break


def tag_s3_vectors(region: str) -> None:
    sv = boto3.client("s3vectors", region_name=region)
    if not hasattr(sv, "list_vector_buckets") or not hasattr(sv, "tag_resource"):
        return
    token = None
    while True:
        args = {"nextToken": token} if token else {}
        page = sv.list_vector_buckets(**args)
        for bucket in page.get("vectorBuckets", []):
            name = bucket.get("vectorBucketName", bucket.get("name", ""))
            if PREFIX in name.lower():
                arn = bucket.get("vectorBucketArn")
                if arn:
                    # Newer S3 Vectors SDKs expose tag_resource; tolerate API shape drift.
                    try:
                        sv.tag_resource(resourceArn=arn, tags={TAG_KEY: TAG_VALUE})
                    except TypeError:
                        sv.tag_resource(resourceArn=arn, tags=[{"key": TAG_KEY, "value": TAG_VALUE}])
                    log(f"tagged S3 Vectors bucket {name}")
        token = page.get("nextToken")
        if not token:
            break


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "ap-southeast-2"))
    parser.add_argument("--stack", default=os.getenv("STACK_NAME", "adidlabs"))
    args = parser.parse_args()

    safe(f"CloudFormation stack {args.stack}", lambda: tag_cloudformation_stack(args.region, args.stack))
    safe("AdidLaBs S3 buckets", lambda: tag_s3_prefix(args.region))
    safe("LiteLLM SSM parameter", lambda: tag_ssm(args.region, args.stack))
    safe("AdidLaBs IAM roles", tag_iam_roles)
    safe("Bedrock Knowledge Base", lambda: tag_bedrock_kb(args.region))
    safe("AgentCore resources", lambda: tag_agentcore(args.region))
    safe("S3 Vectors resources", lambda: tag_s3_vectors(args.region))
    log(f"reconciliation complete: {TAG_KEY}={TAG_VALUE}")


if __name__ == "__main__":
    main()
