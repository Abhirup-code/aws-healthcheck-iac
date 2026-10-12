"""Offline checks on the Terraform files. They run without Terraform or AWS."""
from pathlib import Path

import pytest

hcl2 = pytest.importorskip("hcl2")

TF_DIR = Path(__file__).resolve().parent.parent / "terraform"


def load_all():
    merged = {}
    for f in sorted(TF_DIR.glob("*.tf")):
        with open(f) as fh:
            data = hcl2.load(fh)
        for key, val in data.items():
            merged.setdefault(key, []).extend(val if isinstance(val, list) else [val])
    return merged


def resource_types(merged):
    types = set()
    for block in merged.get("resource", []):
        types.update(block.keys())
    return types


def test_all_tf_files_parse():
    assert list(TF_DIR.glob("*.tf")), "no .tf files found"
    load_all()


def test_expected_resources_exist():
    types = resource_types(load_all())
    for expected in [
        "aws_s3_bucket",
        "aws_sns_topic",
        "aws_lambda_function",
        "aws_cloudwatch_metric_alarm",
        "aws_cloudwatch_event_rule",
        "aws_iam_role",
    ]:
        assert expected in types


def test_bucket_is_locked_down():
    types = resource_types(load_all())
    assert "aws_s3_bucket_public_access_block" in types
    assert "aws_s3_bucket_server_side_encryption_configuration" in types


def test_every_variable_has_a_description():
    for block in load_all().get("variable", []):
        for name, body in block.items():
            assert body.get("description"), f"variable {name} has no description"


def test_localstack_is_off_by_default():
    for block in load_all().get("variable", []):
        if "use_localstack" in block:
            default = block["use_localstack"]["default"]
            default = default[0] if isinstance(default, list) else default
            assert default is False
