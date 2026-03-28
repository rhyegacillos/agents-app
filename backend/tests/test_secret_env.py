import json
import os
import unittest
from unittest.mock import Mock, patch

import secret_env


class SecretEnvTests(unittest.TestCase):
    def tearDown(self) -> None:
        for key in (
            "APP_RUNTIME_SECRETS_ARN",
            "DEFAULT_AWS_REGION",
            "GROK_API_KEY",
        ):
            os.environ.pop(key, None)
        with secret_env._LOCK:
            secret_env._SECRET_CACHE.clear()

    def test_direct_env_wins_over_secret_store(self) -> None:
        os.environ["GROK_API_KEY"] = "direct-key"
        os.environ["APP_RUNTIME_SECRETS_ARN"] = "arn:aws:secretsmanager:::secret:test"

        with patch("secret_env.boto3.client") as client_mock:
            self.assertEqual(secret_env.get_secret_env("GROK_API_KEY", ""), "direct-key")
        client_mock.assert_not_called()

    def test_runtime_secret_is_loaded_and_cached(self) -> None:
        os.environ["APP_RUNTIME_SECRETS_ARN"] = "arn:aws:secretsmanager:::secret:test"
        os.environ["DEFAULT_AWS_REGION"] = "ap-southeast-1"
        client = Mock()
        client.get_secret_value.return_value = {
            "SecretString": json.dumps({"GROK_API_KEY": "secret-key"}),
        }

        with patch("secret_env.boto3.client", return_value=client) as client_factory:
            self.assertEqual(secret_env.get_secret_env("GROK_API_KEY", ""), "secret-key")
            self.assertEqual(secret_env.get_secret_env("GROK_API_KEY", ""), "secret-key")

        client_factory.assert_called_once_with("secretsmanager", region_name="ap-southeast-1")
        client.get_secret_value.assert_called_once_with(SecretId="arn:aws:secretsmanager:::secret:test")


if __name__ == "__main__":
    unittest.main()
