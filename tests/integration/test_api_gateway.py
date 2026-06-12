import os

import boto3
import pytest
import requests


class TestApiGateway:
    @pytest.fixture()
    def api_gateway_url(self):
        stack_name = os.environ.get("AWS_SAM_STACK_NAME")

        if stack_name is None:
            pytest.skip("Set AWS_SAM_STACK_NAME to run integration tests")

        client = boto3.client("cloudformation")
        response = client.describe_stacks(StackName=stack_name)
        stack_outputs = response["Stacks"][0]["Outputs"]
        api_outputs = [output for output in stack_outputs if output["OutputKey"] == "ApiEndpoint"]

        if not api_outputs:
            raise KeyError(f"ApiEndpoint output not found in stack {stack_name}")

        return api_outputs[0]["OutputValue"]

    def test_get_missing_batch_returns_404(self, api_gateway_url):
        response = requests.get(f"{api_gateway_url}/batches/integration-missing-batch")

        assert response.status_code == 404
