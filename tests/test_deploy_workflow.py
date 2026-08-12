from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_tagged_main_commit_is_built_with_the_tag_name():
    workflow = yaml.load(
        (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    assert workflow["on"]["push"]["tags"] == ["*"]
    assert workflow["jobs"]["tests"]["uses"] == "./.github/workflows/tests.yml"
    job = workflow["jobs"]["docker"]
    assert job["needs"] == "tests"
    assert "if" not in job

    steps = {step["name"]: step for step in job["steps"]}
    checkout = steps["Check out the tagged commit"]
    assert checkout["with"]["fetch-depth"] == "0"

    main_check = steps["Verify the tagged commit belongs to main"]["run"]
    assert "git merge-base --is-ancestor" in main_check

    version_check = steps["Verify the tag matches the application version"]["run"]
    assert 'check_release_version.py "$RELEASE_TAG"' in version_check

    build = steps["Build and push"]
    assert build["with"]["context"] == "."
    assert build["with"]["push"] == "true"
    assert build["with"]["tags"].endswith(":${{ github.ref_name }}")

    tests_workflow = yaml.load(
        (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert "workflow_call" in tests_workflow["on"]
    assert "checkout_ref" in tests_workflow["on"]["workflow_call"]["inputs"]
    test_job = tests_workflow["jobs"]["build_and_test"]
    assert test_job["services"]["postgres"]["image"] == "postgres:16"
    test_steps = {step["name"]: step for step in test_job["steps"] if "name" in step}
    postgres_test = test_steps["Pytest with DB_URL set"]
    assert postgres_test["env"]["DEBRIEFLY_TEST_POSTGRES_URL"] == (
        postgres_test["env"]["DB_URL"]
    )


def test_clerk_rollback_build_requires_an_immutable_base_image():
    workflow = yaml.load(
        (ROOT / ".github/workflows/clerk-rollback.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["release_tag"]["required"] == "true"
    assert inputs["clerk_base_image"]["required"] == "true"
    assert inputs["output_tag"]["required"] == "true"

    tests_job = workflow["jobs"]["tests"]
    assert tests_job["uses"] == "./.github/workflows/tests.yml"
    assert tests_job["with"]["checkout_ref"] == "${{ inputs.release_tag }}"
    assert workflow["jobs"]["docker"]["needs"] == "tests"

    steps = {step["name"]: step for step in workflow["jobs"]["docker"]["steps"]}
    checkout = steps["Check out the reviewed release tag"]
    assert checkout["with"]["ref"] == "${{ inputs.release_tag }}"
    assert checkout["with"]["fetch-depth"] == "0"

    validation = steps["Validate pinned inputs and migration head"]["run"]
    assert "@sha256:[0-9a-fA-F]{64}$" in validation
    assert "git tag --points-at HEAD" in validation
    assert 'check_release_version.py "$RELEASE_TAG"' in validation
    assert "check_migration_head.py 2f4c8a1d9e7b" in validation

    build = steps["Build and push the Clerk rollback image"]
    assert build["with"]["file"] == "Dockerfile.clerk-rollback"
    assert (
        "CLERK_BASE_IMAGE=${{ inputs.clerk_base_image }}" in build["with"]["build-args"]
    )
    assert build["with"]["push"] == "true"
    assert build["with"]["tags"].endswith(":${{ inputs.output_tag }}")
