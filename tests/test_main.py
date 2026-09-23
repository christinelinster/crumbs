from io import StringIO
import unittest
from unittest.mock import call, patch

from app.main import main


class MainTests(unittest.TestCase):
    @patch("app.main.process_query", side_effect=["first answer", "second answer"])
    @patch("app.main.pool")
    @patch(
        "builtins.input",
        side_effect=["first question", "second question", "quit"],
    )
    def test_main_reuses_one_history_list_for_process_lifetime(
        self, input_mock, pool_mock, process_query_mock
    ):
        pool_mock.__enter__.return_value = pool_mock

        with patch("sys.stdout", new_callable=StringIO) as output:
            main()

        self.assertEqual(process_query_mock.call_count, 2)
        first_history = process_query_mock.call_args_list[0].args[1]
        second_history = process_query_mock.call_args_list[1].args[1]
        self.assertIs(first_history, second_history)
        self.assertEqual(first_history, [])
        self.assertEqual(input_mock.call_args_list, [call("\nUser: ")] * 3)

        rendered = output.getvalue()
        self.assertEqual(rendered.count("What would you like to make today?"), 1)
        self.assertIn("\nCrumbs:\nfirst answer", rendered)
        self.assertIn("\nCrumbs:\nsecond answer", rendered)
        self.assertNotIn("\nResponse:", rendered)

        pool_mock.__enter__.assert_called_once_with()
        pool_mock.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
